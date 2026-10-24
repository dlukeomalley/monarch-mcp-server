"""Prove strict checking, the real async bridge and Pydantic integration stay active."""

import subprocess
import sys
from pathlib import Path


def test_static_contracts(tmp_path):
    source = tmp_path / "contract.py"
    source.write_text(
        """import json
from typing import assert_type
from pydantic import BaseModel
from monarch_mcp_server.server import run_async
class Count(BaseModel):
    count: int
item = Count(count=1)
assert_type(item.count, int)
assert_type(Count.model_construct(count=2).count, int)
async def one() -> int:
    return 1
assert_type(run_async(one()), int)
bad_constructor = Count(count="wrong")
bad_construct = Count.model_construct(count="wrong")
bad_extra = Count(count=1, extra=True)
missing = Count()
missing_construct = Count.model_construct()
bad_bridge: str = run_async(one())
def wrong_body(value: int) -> int:
    return value + "wrong"
def unknown_return() -> int:
    return json.loads("1")
def untyped(value):
    return value
"""
    )
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--config-file",
            str(root / "pyproject.toml"),
            "--show-error-codes",
            "--no-pretty",
            str(source),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    codes = [
        line.rsplit("[", 1)[-1].removesuffix("]")
        for line in result.stdout.splitlines()
        if ": error:" in line
    ]
    assert result.returncode == 1, result.stdout + result.stderr
    assert not result.stderr
    assert sorted(codes) == sorted(
        [
            "arg-type",
            "arg-type",
            "call-arg",
            "call-arg",
            "call-arg",
            "assignment",
            "operator",
            "no-any-return",
            "no-untyped-def",
        ]
    ), result.stdout
