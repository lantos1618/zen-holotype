"""The Type/Expr unions on the AST are only worth anything if something enforces
them. This runs mypy over the package so the annotations can't silently rot.
"""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).parent.parent


@pytest.mark.skipif(importlib.util.find_spec("mypy") is None, reason="mypy not installed")
def test_mypy_clean():
    r = subprocess.run([sys.executable, "-m", "mypy", "holotype"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
