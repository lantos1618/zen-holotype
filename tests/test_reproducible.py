"""Codegen is reproducible: the same source must emit byte-identical C every run.

Temp/subject/loop-sequence names used to be derived from `id(node)` — a memory
address — so the emitted C differed run-to-run, defeating ccache, reproducible
builds, and any C-level diff. Names now come from deterministic counters; these
tests lock that in across the sites that generate them (closures/templates →
`_v`, match → `_subj`, element loops → `_seq`)."""
import os
import re
import subprocess
import sys
import textwrap

from holotype.main import (load, build_space, build_scopes, resolve, check, emit_c)


def emit(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    return emit_c(files, passing, space)


# every temp-name site at once: a template + closure (_v), a match (_subj),
# an element-form loop (_seq), and a generic instance.
_SRC = """
box*: { v: i32 }
fold = (xs: [i32], init: i32, f: (i32, i32) i32) i32 {
    acc := init
    xs.loop((h, i, x) { acc = f(acc, x) })
    acc
}
classify = (n: i32) i32 { match (n < 0) { true => 0, false => 1 } }
id* = (b: box) i32 { b.v }
main* = () i32 {
    s := fold([1, 2, 3], 0, (a, x) { a + x })
    s + classify(s) + id(box { v: 4 })
}
"""


def test_emit_is_byte_identical_across_runs(tmp_path):
    # the same compiler invocation, twice — must be character-for-character equal
    a = emit(tmp_path, _SRC)
    b = emit(tmp_path, _SRC)
    assert a == b


def test_no_address_like_temp_names(tmp_path):
    # an id()-derived name looks like `_subj140234567891234` — a 6+ digit run.
    # deterministic counters stay small, so no generated name carries a long number.
    c = emit(tmp_path, _SRC)
    assert not re.search(r"_(?:v|subj|seq)\d{6,}", c), "address-like temp name leaked into output"


def test_names_use_small_counters(tmp_path):
    # sanity: the deterministic names actually appear, and they're small
    c = emit(tmp_path, _SRC)
    assert "_seq1" in c                          # the element loop's sequence temp
    assert re.search(r"_subj\d\b", c)            # a single-digit match subject
    assert re.search(r"_v\d+_0", c)              # a template/closure binding temp


# trait-impl emission order came from a `set`, whose iteration order varies with
# PYTHONHASHSEED — so the only way to catch a regression is across processes with
# different seeds. This source has four impls of one trait (enough to expose a
# set's ordering); all seeds must produce byte-identical C.
_MULTI_IMPL = """
Sq*: { s: i32 }
Rect*: { w: i32 }
Circle*: { r: i32 }
Tri*: { b: i32 }
Area: { area: (Ptr<Self>) i32 }
Sq.impl(Area) { area = (x: Ptr<Sq>) i32 { x.s } }
Rect.impl(Area) { area = (x: Ptr<Rect>) i32 { x.w } }
Circle.impl(Area) { area = (x: Ptr<Circle>) i32 { x.r } }
Tri.impl(Area) { area = (x: Ptr<Tri>) i32 { x.b } }
go*<T: Area> = (x: Ptr<T>) i32 { area(x) }
sum* = (a: Ptr<Sq>, b: Ptr<Rect>, c: Ptr<Circle>, d: Ptr<Tri>) i32 {
    go(a) + go(b) + go(c) + go(d)
}
"""

_EMIT_SNIPPET = textwrap.dedent("""
    import sys, tempfile, pathlib, hashlib
    from holotype.main import (load, build_space, build_scopes, resolve, check,
                               emit_c, fold_comptime, run_emits)
    d = pathlib.Path(tempfile.mkdtemp()); (d / "m.zen").write_text(sys.argv[1])
    files = load(d); space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    _, passing = check(files, space)
    sys.stdout.write(hashlib.sha256(emit_c(files, passing, space).encode()).hexdigest())
""")


def _emit_hash(seed):
    env = {**os.environ, "PYTHONHASHSEED": str(seed), "PYTHONPATH": os.getcwd()}
    r = subprocess.run([sys.executable, "-c", _EMIT_SNIPPET, _MULTI_IMPL],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_trait_impl_order_is_hashseed_independent():
    hashes = {_emit_hash(seed) for seed in (0, 1, 2, 3, 42, 99)}
    assert len(hashes) == 1, f"emit order varies with PYTHONHASHSEED: {hashes}"
