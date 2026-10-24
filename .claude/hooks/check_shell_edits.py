"""Refuse a shell command that edits a tracked file.

A `python3 - <<'PY' ... write_text(...)`, `sed -i` or `perl -pi` edit of
source is a semantic change made through a text substitution: a pattern
matching twice edits both, a slice computed from `.index()` lands mid-
function once the file has moved, and nothing reports it. Edit/MultiEdit
require the file to have been read, refuse a non-unique match and error
instead of guessing.

Writes only, never reads: measuring, benchmarking and writing to scratch
space stay shell work. A command is refused only when it both performs a
write and names a file `git ls-files` lists in the repository containing
the command's working directory or in any of that repository's worktrees.
In-place editors match on a flag cluster containing `i` (`perl -0pi`,
`sed -Ei`), a redirect is judged by its own target (so `2>/dev/null` does
not disarm the check), bare filenames resolve against the cwd and every
`cd` in the command, and a `$NAME` or `${NAME}` the command assigns
(`L=/path/to/worktree; sed -i ... $L/file`) is expanded before any of it.

Installed by eng-rig into `.claude/hooks/` and wired as a PreToolUse hook on
Bash; exit 2 denies with the message on stderr.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_WRITES = (
    re.compile(r"\b(?:sed|perl|ruby)\s+(?:-\S+\s+)*-[A-Za-z0-9]*i"),
    re.compile(r"\.write_text\s*\("),
    re.compile(r"\.write_bytes\s*\("),
    re.compile(r"\bopen\s*\([^)]*['\"][wa]\+?['\"]"),
    re.compile(r"\bshutil\.(move|copy)\b"),
    re.compile(r"\btee\s+(?:-\S+\s+)*[^\s|]"),
)
_REDIRECT = re.compile(r"(?<![-=<>])>>?\s*([\w./~-]+\.[A-Za-z0-9_]+)")
"""A redirect, not an arrow: `->` and `=>` in a commit message are prose."""

_ALWAYS_FINE = ("/tmp/", "/private/tmp/", "scratchpad", "/dev/null")
_PATH_TOKEN = re.compile(r"[\w./~-]+\.[A-Za-z0-9_]+")
_CD = re.compile(r"\bcd\s+([^\s;&|)]+)")
_ASSIGN = re.compile(r"(?:^|[\s;&|(])([A-Za-z_]\w*)=('[^']*'|\"[^\"]*\"|[^\s;&|)]+)")


def repo_root(cwd: str | None) -> Path | None:
    start = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    try:
        done = subprocess.run(
            ["git", "-C", start, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Path(done.stdout.strip()) if done.returncode == 0 else None


def expand_assigned(command: str) -> str:
    """`command` with each `$NAME`/`${NAME}` it assigns replaced by the value."""
    for match in _ASSIGN.finditer(command):
        name = match.group(1)
        value = match.group(2).strip("'\"")

        def assigned_value(_match: re.Match[str], replacement: str = value) -> str:
            return replacement

        command = re.sub(rf"\$(?:\{{{name}\}}|{name}\b)", assigned_value, command)
    return command


def _worktrees(repo: Path) -> list[Path]:
    """Every worktree of `repo`'s repository, `repo` first."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [repo]
    others = [
        Path(line.removeprefix("worktree "))
        for line in done.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return [repo, *(w for w in others if w.resolve() != repo.resolve())]


def _tracked(repo: Path) -> set[str]:
    try:
        done = subprocess.run(
            ["git", "ls-files"], cwd=repo, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(done.stdout.split("\n")) if done.returncode == 0 else set()


def _names_repo_file(command: str, path: str) -> bool:
    """`command` names repo-relative `path` not as the tail of a longer path,
    which would root it in another tree (a worktree elsewhere has the same suffix)."""
    at = command.find(path)
    while at != -1:
        if at == 0 or command[at - 1] != "/":
            return True
        at = command.find(path, at + 1)
    return False


def _bases(command: str, cwd: Path, repo: Path) -> list[Path]:
    bases = [cwd, repo]
    for match in _CD.finditer(command):
        candidate = Path(match.group(1).strip("'\"")).expanduser()
        bases.append(candidate if candidate.is_absolute() else cwd / candidate)
    return bases


def offending_paths(command: str, cwd: str | None, repo: Path) -> list[str]:
    """Tracked files `command` looks like it writes, each worktree but
    `repo` named by its absolute path."""
    command = expand_assigned(command)
    redirects = _REDIRECT.findall(command)
    if not any(p.search(command) for p in _WRITES):
        if not redirects or all(any(f in t for f in _ALWAYS_FINE) for t in redirects):
            return []
    tracked = _tracked(repo)
    hits = {path for path in tracked if path and _names_repo_file(command, path)}
    trees = _worktrees(repo)
    tracked_in: dict[Path, set[str]] = {repo: tracked}
    for token in _PATH_TOKEN.findall(command):
        for base in _bases(command, Path(cwd) if cwd else repo, repo):
            hit = _tracked_hit(base / token, trees, tracked_in)
            if hit:
                hits.add(hit)
                break
    return sorted(hits)


def _tracked_hit(path: Path, trees: list[Path], tracked_in: dict[Path, set[str]]) -> str | None:
    for tree in trees:
        try:
            relative = path.resolve().relative_to(tree.resolve()).as_posix()
        except (ValueError, OSError):
            continue
        if relative in tracked_in.setdefault(tree, _tracked(tree)):
            return relative if tree is trees[0] else str(tree / relative)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    cwd = payload.get("cwd")
    repo = repo_root(cwd)
    if repo is None:
        return 0
    hits = offending_paths(command, cwd, repo)
    if not hits:
        return 0
    shown = "\n".join(f"  {p}" for p in hits[:8])
    print(
        "Refused: this shell command writes to tracked files.\n"
        f"{shown}\n\n"
        "Use Edit/MultiEdit for source changes: they require the file to have been "
        "read, refuse a non-unique match, and error rather than guess. Use the LSP to "
        "find a symbol's definition or callers.\n\n"
        "Reading, measuring, benchmarking and writing to the scratchpad are unaffected.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
