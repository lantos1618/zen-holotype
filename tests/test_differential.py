"""Differential regression tests — guard against bugs found by the bug-hunt (the self-hosted
toolchain miscompiling or mis-checking). Each entry is a minimal program that previously diverged;
we assert the self-hosted side now computes the right value / verdict.

`self_side(src)` runs the program through the self-hosted BINARY oracle (`_oracle.self_side`) and
returns {verdict: accept|reject, value: int|None}. NO Python frontend is in the loop — the EMIT +
CHECK binaries (built from the committed bootstrap C by `cc` alone) are the sole correctness
reference.

The literal (src, want)/(src, verdict) corpus lives in `_oracle_corpus.py` and is exercised by
`test_oracle.py`; this file keeps only the GENERATED programs (too large to inline in the corpus).
"""
from _oracle import self_side


# Large constructs (bug-hunt #15/#16): parser buffers were fixed at cap 64 (params/fields/arms/
# variants) and cap 16 (type args) and overflowed the heap with no bounds check. Caps are now
# generous (1024 / 256) so any plausible program fits safely.
def test_many_params():
    ps = ", ".join(f"p{i}: i32" for i in range(80))
    args = ", ".join(str(i) for i in range(80))
    assert self_side(f"f* = ({ps}) i32 {{ p79 }}\ntest* = () i32 {{ f({args}) }}")["value"] == 79

def test_many_fields():
    fs = ", ".join(f"x{i}: i32" for i in range(80))
    inits = ", ".join(f"x{i}: {i}" for i in range(80))
    assert self_side(f"S*: {{ {fs} }}\ntest* = () i32 {{ S({inits}).x79 }}")["value"] == 79

def test_many_match_arms():
    arms = ", ".join(f"{i} => {i*2}" for i in range(80)) + ", _ => 999"
    assert self_side(f"test* = () i32 {{ (50).match({{ {arms} }}) }}")["value"] == 100
