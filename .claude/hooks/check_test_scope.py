"""Refuse a Bash command that runs a test suite with no scope.

Refused:
  - `cargo test` or `cargo nextest run` with no test filter, no `-E`
    expression and no `--profile quick`;
  - a whole run of a binary named by `--forbid-binary CRATE::BINARY`: an `-E`
    naming it with no `test(...)` predicate, or its built executable with no
    filter;
  - `pytest` with no path or node id, and `pytest --lf`/`--last-failed`;
  - `vitest`, `npm test` or `npm run test:unit` with no file.

Allowed: any `make` target, a named test or file, a `--no-run` build. The
command is tokenized with `shlex` after env assignments and runner wrappers
(`timeout`, `uv run`, `npx`, `python -m`, `bash -c`) are unwrapped; heredoc
bodies and quoted arguments are not read as commands, and a command that
does not parse is allowed.

Installed by eng-rig into `.claude/hooks/` and wired as a PreToolUse hook on
Bash, with the repo's own words as arguments:
    check_test_scope.py [--gate "make gate"] [--forbid-binary CRATE::BINARY ...]
Exit 2 denies with the reason on stderr.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from collections.abc import Sequence
from pathlib import PurePath

_PUNCTUATION = "();<>|&\n"
_VALUE_OPTIONS = set(
    """
    -p --package --manifest-path --profile -P --features -F --target --target-dir
    -j --jobs --test --bin --bench --example --exclude --config -Z --color
    --message-format --cargo-profile --partition --run-ignored --retries
    --test-threads --max-fail --no-tests --status-level --final-status-level
    --failure-output --success-output --archive-file --workspace-remap
    --tool-config-file
    -k -m -c -o --rootdir --basetemp --maxfail --tb -W --deselect --ignore
    --ignore-glob --junitxml --durations --confcutdir --cov -n --timeout
    --log-level --import-mode --override-ini --capture --dist
    -t --testNamePattern --reporter --root --dir --project --environment --pool
    --shard --outputFile
    """.split()
)
"""Options that consume the next token. One missing here reads its value as a
filter, which allows: the check errs toward letting a command run."""

_FILTER_EXPR = {"-E", "--filterset", "--filter-expr"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.DOTALL)


class Binary:
    """A test binary too slow to run whole, named `crate::binary`."""

    def __init__(self, spec: str) -> None:
        crate, _, name = spec.rpartition("::")
        self.spec = spec
        prefix = rf"(?:{re.escape(crate)}::)?" if crate else ""
        self.expression = re.compile(rf"binary(?:_id)?\(\s*=?\s*{prefix}{re.escape(name)}\s*\)")
        self.built = re.compile(rf"^{re.escape(name)}-[0-9a-f]{{8,}}$")
        self.reason = f"runs the whole `{spec}` binary"


def _simple_commands(command: str) -> list[list[str]]:
    """Each simple command's words, with redirections dropped."""
    lexer = shlex.shlex(_HEREDOC.sub("\n", command), posix=True, punctuation_chars=_PUNCTUATION)
    lexer.whitespace_split = True
    lexer.whitespace = " \t\r"
    commands: list[list[str]] = [[]]
    skip_next = False
    for token in lexer:
        if skip_next:
            skip_next = False
        elif token and all(c in _PUNCTUATION for c in token):
            if "<" in token or ">" in token:
                if commands[-1] and commands[-1][-1].isdigit():
                    commands[-1].pop()
                skip_next = True
            else:
                commands.append([])
        else:
            commands[-1].append(token)
    return [c for c in commands if c]


def _unwrap(argv: list[str]) -> list[str]:
    while argv:
        head = PurePath(argv[0]).name
        if _ASSIGNMENT.match(argv[0]) or head in ("time", "nice", "command", "exec", "env"):
            argv = argv[1:]
        elif head in ("timeout", "gtimeout"):
            rest = argv[1:]
            while rest and rest[0].startswith("-"):
                rest = rest[1:]
            argv = rest[1:]
        elif head == "uv" and len(argv) > 1 and argv[1] == "run":
            rest = argv[2:]
            while rest and rest[0].startswith("-"):
                takes = rest[0] in ("--project", "--directory", "--with", "--python", "--package")
                rest = rest[2:] if takes and "=" not in rest[0] else rest[1:]
            argv = rest
        elif head in ("npx", "pnpx", "bunx"):
            argv = [a for a in argv[1:] if a not in ("--yes", "-y", "--no-install")]
        elif head in ("npm", "pnpm") and len(argv) > 1 and argv[1] == "exec":
            argv = argv[2:]
        elif head.startswith("python") and len(argv) > 2 and argv[1] == "-m":
            argv = argv[2:]
        elif head in ("bash", "sh", "zsh") and len(argv) > 2 and argv[1] in ("-c", "-lc"):
            return ["__shell__", argv[2]]
        else:
            return argv
    return argv


def _positionals(args: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    positional: list[str] = []
    options: dict[str, list[str]] = {}
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional += [a for a in args[i + 1 :] if not a.startswith("-")]
            break
        if arg.startswith("-") and arg != "-":
            name, eq, value = arg.partition("=")
            if eq:
                options.setdefault(name, []).append(value)
            elif name in _VALUE_OPTIONS or name in _FILTER_EXPR:
                options.setdefault(name, []).append(args[i + 1] if i + 1 < len(args) else "")
                i += 1
            else:
                options.setdefault(name, [])
        else:
            positional.append(arg)
        i += 1
    return positional, options


def _cargo(args: list[str], binaries: Sequence[Binary]) -> str | None:
    if args and args[0].startswith("+"):
        args = args[1:]
    if args[:1] == ["test"]:
        rest = args[1:]
    elif args[:2] == ["nextest", "run"]:
        rest = args[2:]
    else:
        return None
    positional, options = _positionals(rest)
    if "--no-run" in options:
        return None
    expressions = [e for flag in _FILTER_EXPR for e in options.get(flag, [])]
    for expr in expressions:
        for binary in binaries:
            if binary.expression.search(expr) and "test(" not in expr:
                return binary.reason
    if positional or expressions:
        return None
    if [*options.get("--profile", []), *options.get("-P", [])] == ["quick"]:
        return None
    return "runs every test in the workspace or package: no test filter or -E expression"


def _pytest(args: list[str]) -> str | None:
    positional, options = _positionals(args)
    if "--lf" in options or "--last-failed" in options:
        return "`--lf` reruns whatever failed last across the whole suite"
    if not positional:
        return "has no path or node id, so it collects the whole suite"
    return None


def _vitest(args: list[str]) -> str | None:
    positional, options = _positionals(args)
    if "--help" in options or "--version" in options:
        return None
    files = [p for p in positional if p not in ("run", "watch", "related", "dev", "bench")]
    return None if files else "names no spec file"


def _npm(args: list[str]) -> str | None:
    if args[:1] in (["test"], ["t"]):
        tail = args[1:]
    elif args[:2] in (["run", "test"], ["run", "test:unit"], ["run-script", "test:unit"]):
        tail = args[2:]
    else:
        return None
    return _vitest(tail[1:] if tail[:1] == ["--"] else tail)


def refusal(command: str, binaries: Sequence[Binary] = ()) -> str | None:
    """Why `command` runs an unscoped suite, or None when it does not."""
    try:
        commands = _simple_commands(command)
    except ValueError:
        return None
    for argv in commands:
        argv = _unwrap(argv)
        if not argv:
            continue
        if argv[0] == "__shell__":
            reason = refusal(argv[1], binaries)
        else:
            head = PurePath(argv[0]).name
            built = next((b for b in binaries if b.built.match(head)), None)
            if head == "cargo":
                reason = _cargo(argv[1:], binaries)
            elif head in ("pytest", "py.test"):
                reason = _pytest(argv[1:])
            elif head == "vitest":
                reason = _vitest(argv[1:])
            elif head in ("npm", "pnpm"):
                reason = _npm(argv[1:])
            elif built is not None:
                reason = None if _positionals(argv[1:])[0] else built.reason
            else:
                reason = None
        if reason:
            return f"`{' '.join(argv)[:160]}` {reason}"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", default="make gate", help="the repo's diff-scoped test run")
    parser.add_argument("--forbid-binary", action="append", default=[], type=Binary)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    reason = refusal((payload.get("tool_input") or {}).get("command", ""), args.forbid_binary)
    if not reason:
        return 0
    print(
        f"Refused: {reason}.\n\n"
        f"Run `{args.gate}`: it picks the tests this branch's changes can break. To run "
        "one test, name it: `cargo nextest run -E 'test(=module::name)'`, "
        "`uv run pytest -q tests/test_x.py::test_y`, `npx vitest run src/lib/x.test.ts`.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
