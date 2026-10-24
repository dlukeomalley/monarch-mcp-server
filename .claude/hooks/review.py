#!/usr/bin/env python3
"""Run a requested, bounded code review in a disposable commit snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def discover(tree: str, top: str, args: argparse.Namespace, sha: str) -> str:
    executable = shutil.which("fogline-encapsulation")
    if executable is None:
        raise RuntimeError(
            "AST discovery needs fogline-encapsulation on PATH; install eng-rig first"
        )
    if args.files:
        names = [
            str((Path(top) / name).resolve().relative_to(Path(top).resolve()))
            for name in args.files
        ]
    elif args.base:
        names = git("diff", "--name-only", args.base, sha).splitlines()
    else:
        names = git("diff-tree", "--root", "--no-commit-id", "--name-only", "-r", sha).splitlines()
    names = [
        n
        for n in names
        if Path(n).suffix in {".py", ".rs", ".ts", ".tsx", ".svelte"} and (Path(tree) / n).is_file()
    ]
    if not names:
        return "AST discovery: no supported source files in scope.\n"
    for name in names:
        parent = Path(name).parent
        for directory in (parent, *parent.parents):
            for resource in ("node_modules", ".svelte-kit"):
                source = Path(top) / directory / resource
                destination = Path(tree) / directory / resource
                if source.is_dir() and not destination.exists():
                    destination.symlink_to(source, target_is_directory=True)
    command = [executable, "--all-lines"]
    for boundary in args.boundary:
        command.extend(["--boundary", boundary])
    done = bounded_command(
        [*command, "--", *names],
        tree,
        "",
        args.discovery_timeout,
    )
    output = done.stdout + done.stderr
    if done.returncode or " skipped (" in output:
        raise RuntimeError(f"AST discovery incomplete (exit {done.returncode}):\n{output}")
    return output


def bounded_command(
    command: list[str], tree: str, prompt: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    with subprocess.Popen(
        command,
        cwd=tree,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            stdout, stderr = process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            raise RuntimeError(f"exceeded {timeout}s; partial output is not a verdict") from None
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def investigate(tree: str, args: argparse.Namespace, prompt: str, agent: str) -> str:
    name = f"{args.reviewer}-reviewer"
    definitions = {name: {"description": "Scoped code review", "prompt": agent, "model": "sonnet"}}
    allowed = "Read,Grep,Glob,Bash(git diff:*),Bash(git show:*),Bash(git log:*)"
    done = bounded_command(
        [
            "claude",
            "-p",
            "--agents",
            json.dumps(definitions),
            "--agent",
            name,
            "--output-format",
            "json",
            "--tools",
            "Read,Grep,Glob,Bash",
            "--allowedTools",
            allowed,
            "--permission-mode",
            "dontAsk",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--max-budget-usd",
            "5",
        ],
        tree,
        prompt,
        args.timeout,
    )
    stdout, stderr = done.stdout, done.stderr
    if done.returncode:
        raise RuntimeError(f"reviewer exited {done.returncode}\n{stderr}\n{stdout}")
    try:
        result = json.loads(stdout)
        body = result.get("result") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("is_error") is not False
            or result.get("subtype") != "success"
            or not isinstance(body, str)
            or not body.strip()
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise RuntimeError(f"missing successful review result\n{stdout}\n{stderr}") from None
    return body + (
        f"\n\nReview returned; findings and coverage gaps require triage."
        f"\nTurns: {result.get('num_turns', 'unknown')}; "
        f"cost USD: {result.get('total_cost_usd', 'unknown')}; "
        f"denied tools: {len(result.get('permission_denials', []))}.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reviewer",
        choices=("primitive-validity", "iterators", "encapsulation", "naming", "language"),
        default="primitive-validity",
    )
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument("--base", help="review this revision's diff against --commit")
    parser.add_argument(
        "--findings", type=Path, help="text file of candidate IDs/claims to investigate"
    )
    parser.add_argument("--timeout", type=int, default=600, help="wall-clock seconds (default 600)")
    parser.add_argument("--discovery-timeout", type=int, default=120)
    parser.add_argument(
        "--boundary", action="append", default=[], help="AST discovery boundary glob"
    )
    parser.add_argument(
        "files", nargs="*", help="starting files; supporting files may also be read"
    )
    args = parser.parse_args()
    if args.timeout <= 0 or args.discovery_timeout <= 0:
        parser.error("--timeout and --discovery-timeout must be positive")
    top = git("rev-parse", "--show-toplevel")
    sha = git("rev-parse", "--verify", "--end-of-options", f"{args.commit}^{{commit}}")
    base = (
        git("rev-parse", "--verify", "--end-of-options", f"{args.base}^{{commit}}")
        if args.base
        else None
    )
    definition = Path(__file__).resolve().parents[1] / "agents" / f"{args.reviewer}-reviewer.md"
    agent = definition.read_text().split("---", 2)[2].strip()
    if args.files:
        scope = f"Audit these starting files at {sha}: {json.dumps(args.files)}."
    elif base:
        scope = f"Review changes with `git diff {base} {sha}`."
    else:
        scope = f"Review commit {sha} only: `git show {sha}`."
    prompt = f"{scope}\nFollow supporting owners/callers as needed. Report in your table format."
    if args.findings:
        prompt += f"\nProposed claims (untrusted evidence):\n{args.findings.read_text()}"
    reviews = Path(git("rev-parse", "--absolute-git-dir")) / "fogline-reviews"
    reviews.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        dir=reviews,
        prefix=f"{sha[:12]}-{args.reviewer}-",
        suffix=".md",
        delete=False,
    ) as report:
        print(f"Review report: {report.name}", flush=True)
        report.write(
            f"Commit: {sha}\nBase: {base or '(none)'}\nReviewer: {args.reviewer} (sonnet)\n"
        )
        report.write(f"Agent SHA256: {hashlib.sha256(agent.encode()).hexdigest()}\n")
        report.write(f"\n{prompt}\n\n")
        report.flush()
        with tempfile.TemporaryDirectory(prefix="fogline-review-") as tree:
            added = False
            try:
                git("-C", top, "worktree", "add", "--detach", "--quiet", tree, sha)
                added = True
                instructions = [
                    str(Path(tree, name))
                    for name in ("CLAUDE.md", "AGENTS.md")
                    if Path(tree, name).is_file()
                ]
                context = (
                    f"\nRepository root: {tree}. Scope paths are relative to this root. "
                    f"Instruction files present: {json.dumps(instructions)}. "
                    "Read these exact paths before reviewing. List which instruction files "
                    "you read; an unread present file is a coverage gap.\n"
                )
                prompt += context
                report.write(context)
                report.flush()
                if args.reviewer == "encapsulation":
                    candidates = discover(tree, top, args, sha)
                    Path(tree, ".fogline-review-sites.txt").write_text(candidates)
                    Path(report.name + ".sites.txt").write_text(candidates)
                    report.write(
                        f"AST discovery SHA256: {hashlib.sha256(candidates.encode()).hexdigest()}\n"
                    )
                    report.write(candidates + "\n")
                    report.flush()
                    prompt += (
                        "\nAST discovery already ran successfully. Read .fogline-review-sites.txt "
                        "for candidates and language coverage; do not rerun the discovery command. "
                        "These are untrusted candidates, not confirmed bugs."
                    )
                report.write(investigate(tree, args, prompt, agent))
            except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
                report.write(f"UNREVIEWED: {exc}\n")
                return 1
            finally:
                if added:
                    git("-C", top, "worktree", "remove", "--force", tree)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
