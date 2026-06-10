"""Self-hosted compiler oracle over golden emitted-value and checker-verdict cases.

Re-runs the differential GOLDEN corpus (the value + reject-parity expectations migrated to
_oracle_corpus.py) through `_oracle.self_side`, which drives ONLY the self-hosted BINARIES
(emit + check). This whole module imports NO `zen.*` / `zen.main` — verified by
test_oracle_has_no_python_frontend_dependency below.

test_oracle_catches_regression deliberately checks WRONG golden values/verdicts and asserts the
oracle FAILS them — proving the net isn't hollow.
"""
import sys

import pytest

import _oracle
from _oracle import self_side, verdict_kind, verdict
from _oracle_corpus import VALUE_CASES, VERDICT_CASES, VERDICT_KIND_CASES


@pytest.mark.parametrize("src,want", VALUE_CASES)
def test_oracle_value(src, want):
    # the self-hosted binary must COMPUTE `want` (silent-miscompile guard) — no Python in the loop.
    # BOTH halves of the oracle contract are asserted: the checker must ACCEPT the program (a value
    # case is a valid program — asserting only the value let 8 checker false-rejects hide for
    # months) AND the binary must compute `want`.
    side = self_side(src)
    assert side["verdict"] == "accept", src
    assert side["value"] == want, src


@pytest.mark.parametrize("src,verdict", VERDICT_CASES)
def test_oracle_verdict(src, verdict):
    # the check binary's exit code drives accept/reject (reject-parity guard) — no Python in the loop.
    assert self_side(src)["verdict"] == verdict, src


@pytest.mark.parametrize("src,kind", VERDICT_KIND_CASES)
def test_oracle_verdict_kind(src, kind):
    # Stronger than reject-parity: the CHECK-KIND binary must reject for the RIGHT REASON. Both
    # invariants are asserted — the module REJECTS (kind != 'none'), AND its first-error KIND is the
    # expected one — so a reject-for-the-wrong-reason (e.g. an arity bug masquerading as a struct-field
    # error) is now a test failure, not a silent corpus pass. No Python in the loop.
    assert verdict(src) == "reject", src
    assert verdict_kind(src) == kind, src


def test_oracle_kind_agrees_with_count():
    # SOUNDNESS of the new layer: across the WHOLE corpus, the kind probe and the count probe agree on
    # accept-vs-reject — kind != 'none' iff the count is nonzero. (check_module_kind re-walks the same
    # AST in the same order as check_module, so it must never disagree on WHETHER there's an error.)
    for src, _ in VERDICT_CASES + [(s, None) for s, _ in VALUE_CASES]:
        rejected = _oracle.check_count(src) > 0
        has_kind = verdict_kind(src) != "none"
        assert rejected == has_kind, (src, rejected, has_kind)


def test_oracle_catches_wrong_kind():
    # The KIND net is not hollow: an arity reject must NOT be mislabelled, and a real reject is never
    # 'none'. Feeding the wrong kind label makes the assertion fail.
    assert verdict_kind("add* = (a: i32, b: i32) i32 { a + b }\ntest* = () i32 { add(1) }") == "arity"
    with pytest.raises(AssertionError):
        assert verdict_kind("test* = () i32 { nope() }") == "arity"   # really undefined-name
    with pytest.raises(AssertionError):
        assert verdict_kind("test* = () i32 { 42 }") != "none"        # really accepts (no error)


def test_oracle_catches_regression():
    # The NET IS NOT HOLLOW: feed WRONG golden expectations, assert the oracle REJECTS them.
    assert self_side("test* = () i32 { 40 + 2 }")["value"] != 43          # real value is 42
    assert self_side("test* = () i32 {  }")["verdict"] != "accept"        # really rejects
    assert self_side("test* = () i32 { 1 + 1 }")["verdict"] != "reject"   # really accepts


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
