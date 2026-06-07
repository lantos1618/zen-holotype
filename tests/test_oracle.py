"""Stage-C2 PROTOTYPE: the self-hosted-compiler oracle WITHOUT the Python reference frontend.

Re-runs the differential GOLDEN corpus (the value + reject-parity expectations migrated to
_oracle_corpus.py) through `_oracle.self_side`, which drives ONLY the self-hosted BINARIES
(emit + check). This whole module imports NO `zen.*` / `zen.main` — verified by
test_oracle_has_no_python_frontend_dependency below.

This is the conversion target for Stage D: the binary-only oracle is a drop-in for the
cross-frontend `_difftest.self_side` for every test that asserts a self-hosted golden value/verdict.

test_oracle_catches_regression deliberately checks WRONG golden values/verdicts and asserts the
oracle FAILS them — proving the net isn't hollow.
"""
import sys

import pytest

import _oracle
from _oracle import self_side
from _oracle_corpus import VALUE_CASES, VERDICT_CASES


@pytest.mark.parametrize("src,want", VALUE_CASES)
def test_oracle_value(src, want):
    # the self-hosted binary must COMPUTE `want` (silent-miscompile guard) — no Python in the loop.
    assert self_side(src)["value"] == want, src


@pytest.mark.parametrize("src,verdict", VERDICT_CASES)
def test_oracle_verdict(src, verdict):
    # the check binary's exit code drives accept/reject (reject-parity guard) — no Python in the loop.
    assert self_side(src)["verdict"] == verdict, src


def test_oracle_catches_regression():
    # The NET IS NOT HOLLOW: feed WRONG golden expectations, assert the oracle REJECTS them.
    with pytest.raises(AssertionError):                                   # real value is 42
        assert self_side("test* = () i32 { 40 + 2 }")["value"] == 43
    with pytest.raises(AssertionError):                                   # really rejects
        assert self_side("test* = () i32 {  }")["verdict"] == "accept"
    with pytest.raises(AssertionError):                                   # really accepts
        assert self_side("test* = () i32 { 1 + 1 }")["verdict"] == "reject"


def test_oracle_has_no_python_frontend_dependency():
    # The point of Stage C2: this oracle path loads NONE of the Python reference frontend. We check
    # in a CLEAN subprocess (the shared conftest.py imports zen.* at session scope, which would
    # pollute this process's sys.modules — that import dies WITH zen/*.py in Stage D). The subprocess
    # imports only the oracle + corpus and runs both binaries, then reports any leaked `zen.*` module.
    import subprocess
    from pathlib import Path
    here = Path(__file__).resolve().parent
    root = here.parent
    probe = (
        "import sys, _oracle as o, _oracle_corpus\n"
        "o.self_side('test* = () i32 { 40 + 2 }')\n"      # exercise emit + check
        "o.self_side('test* = () i32 {  }')\n"
        "leaked = sorted(m for m in sys.modules if m == 'zen' or m.startswith('zen.'))\n"
        "print(','.join(leaked))\n"
    )
    env = {"PYTHONPATH": f"{root}:{here}"}
    import os
    env = {**os.environ, **env}
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    leaked = [m for m in r.stdout.strip().split(",") if m]
    assert not leaked, f"Python frontend leaked into the oracle path: {leaked}"
