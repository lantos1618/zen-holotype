"""Faithful AST (PR feat-faithful-ast).

PHASE 1 — the parser now keeps `recv.method(args)` as a faithful `MethodCall` node (preserving the UFCS
surface syntax) instead of FLATTENING it into `Call(fn: method, args: [recv] ++ args)` at parse time.
A lowering pass (compiler.check.desugar_method_calls), run at the very start of resolve_module, rewrites
each MethodCall back into the EXACT flat Call the old parser produced — so the resolve/genc pipeline (and
the byte-exact self-host fixpoint) is unchanged. These tests pin that the desugar is transparent: UFCS
programs still emit + run identically.

PHASE 2 — `zenc fmt --ast <file>` pretty-prints the FAITHFUL AST, so UFCS survives the round-trip
(`s.len()` formats back as `s.len()`, NOT `len(s)`).
"""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

import _oracle

ROOT = _oracle.ROOT


def _zenc():
    subprocess.run(["make", "-f", "bootstrap/Makefile", "zenc"], cwd=str(ROOT),
                   check=True, capture_output=True)
    return str(ROOT / "zenc")


def _write(text):
    d = Path(tempfile.mkdtemp())
    p = d / "p.zen"
    p.write_text(text)
    return p


# ── PHASE 1: desugar is transparent ───────────────────────────────────────────
def test_emit_flattens_ufcs_method_call():
    """`zenc emit` of `s.len()` still lowers to the flat `len(s)` (desugar reproduces the old flatten)."""
    zenc = _zenc()
    src = _write("len = (s: str) i32 { 5 }\nmain = () i32 { x := \"hi\"\n x.len() }\n")
    r = subprocess.run([zenc, "emit", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "len(__zen_local_" in r.stdout or "len(x)" in r.stdout, r.stdout


def test_run_ufcs_method_chain():
    """A UFCS method chain runs and computes the same value as the equivalent prefix-call form."""
    zenc = _zenc()
    src = _write(
        "inc = (n: i32) i32 { n + 1 }\n"
        "dbl = (n: i32) i32 { n * 2 }\n"
        "main = () i32 { 5.inc().dbl() }\n"   # (5+1)*2 = 12
    )
    r = subprocess.run([zenc, "run", str(src)], capture_output=True, text=True)
    assert r.returncode == 12, r.stderr


def test_run_ufcs_method_with_extra_args():
    """A method with extra args lowers to recv-first arg order (`add(recv, a, b)`)."""
    zenc = _zenc()
    src = _write(
        "add3 = (a: i32, b: i32, c: i32) i32 { a + b * 10 + c * 100 }\n"
        "main = () i32 { 1.add3(2, 0) }\n"   # add3(1, 2, 0) = 1 + 20 + 0 = 21
    )
    r = subprocess.run([zenc, "run", str(src)], capture_output=True, text=True)
    assert r.returncode == 21, r.stderr


# ── PHASE 2: fmt --ast preserves UFCS ──────────────────────────────────────────
def test_fmt_ast_preserves_ufcs():
    """THE POINT: `fmt --ast` of a UFCS program keeps `x.len()` as `x.len()`, not `len(x)`."""
    zenc = _zenc()
    src = _write("len = (s: str) i32 { 5 }\nmain = () i32 { x := \"hi\"\n x.len() }\n")
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "x.len()" in r.stdout, r.stdout
    assert "len(x)" not in r.stdout, r.stdout


def test_fmt_ast_preserves_ufcs_chain_with_args():
    """A multi-arg method chain round-trips as UFCS with the method args inside the parens."""
    zenc = _zenc()
    src = _write(
        "add = (a: i32, b: i32) i32 { a + b }\n"
        "main = () i32 { 1.add(2).add(3) }\n"
    )
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "1.add(2).add(3)" in r.stdout, r.stdout


def test_fmt_ast_match_arms_align_and_trailing_comma():
    """A multi-arm `.match` splits one arm per line, `=>` aligned, trailing comma on the last arm —
    and the arm bodies keep their UFCS (`n.add(1)`)."""
    zenc = _zenc()
    src = _write(
        "add = (a: i32, b: i32) i32 { a + b }\n"
        "Opt: Some(i32) | None\n"
        "classify = (o: Opt) i32 { o.match ({ .Some(n) => n.add(1), .None => 0 }) }\n"
    )
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert ".Some(n) => n.add(1)," in r.stdout, r.stdout
    assert ".None    => 0," in r.stdout, r.stdout   # padded so `=>` aligns with the longer pattern


def test_fmt_ast_is_idempotent():
    """Formatting the formatted output is a fixpoint."""
    zenc = _zenc()
    src = _write(
        "Point: { x: i32, y: i32 }\n"
        "Opt: Some(i32) | None\n"
        "add = (a: i32, b: i32) i32 { a + b }\n"
        "classify = (o: Opt) i32 { o.match ({ .Some(n) => n.add(1), .None => 0 }) }\n"
        "main = () i32 { p := Point(x: 3, y: 4)  1.add(2).add(3) }\n"
    )
    once = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert once.returncode == 0, once.stderr
    fmt1 = _write(once.stdout)
    twice = subprocess.run([zenc, "fmt", "--ast", str(fmt1)], capture_output=True, text=True)
    assert twice.returncode == 0, twice.stderr
    assert once.stdout == twice.stdout, "fmt --ast is not idempotent"


def test_fmt_ast_output_recompiles_and_runs():
    """The formatted source is valid Zen: it builds and runs to the same value as the original."""
    zenc = _zenc()
    src = _write(
        "inc = (n: i32) i32 { n + 1 }\n"
        "dbl = (n: i32) i32 { n * 2 }\n"
        "main = () i32 { 5.inc().dbl() }\n"   # (5+1)*2 = 12
    )
    fmt = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert fmt.returncode == 0, fmt.stderr
    formatted = _write(fmt.stdout)
    r = subprocess.run([zenc, "run", str(formatted)], capture_output=True, text=True)
    assert r.returncode == 12, r.stderr


# ── Printer-correctness regressions (the three bug classes the formatter must NOT introduce) ────────
def test_fmt_ast_reparenthesizes_bin_receiver():
    """CORRECTNESS: a `Bin` subject of `.match` must stay parenthesized — `(n > 0).match(…)`, never
    `n > 0.match(…)` (which would bind `.match` to `0` and reparse to a DIFFERENT AST)."""
    zenc = _zenc()
    src = _write("check = (n: i32) i32 { (n > 0).match ({ true => 1, false => 0 }) }\n")
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "(n > 0).match" in r.stdout, r.stdout
    assert "n > 0.match" not in r.stdout, r.stdout


def test_fmt_ast_no_spurious_return_on_tail_expr():
    """A block's IMPLICIT tail expression prints bare — `{ s.len() }`, not `{ return s.len() }`."""
    zenc = _zenc()
    src = _write("len = (s: str) i32 { 5 }\nf = (s: str) i32 { s.len() }\n")
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "s.len()" in r.stdout and "return s.len()" not in r.stdout, r.stdout


def test_fmt_ast_keeps_explicit_early_return():
    """An EXPLICIT early `return` inside a guard arm KEEPS the keyword (it is not the block's tail)."""
    zenc = _zenc()
    src = _write(
        "g = (n: i32) i32 {\n"
        "    (n < 0).match ({ true => { return 9 }, false => {} })\n"
        "    n\n"
        "}\n"
    )
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "return 9" in r.stdout, r.stdout


def test_fmt_ast_prints_whole_import_and_exports():
    """An import prints its `= <module>` tail, and an exported decl keeps its `*` marker."""
    zenc = _zenc()
    src = _write("{ println } = std.text.fmt\nhelper* = (n: i32) i32 { n }\nmain = () i32 { 0 }\n")
    r = subprocess.run([zenc, "fmt", "--ast", str(src)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "{ println } = std.text.fmt" in r.stdout, r.stdout
    assert "helper* = (n: i32) i32" in r.stdout, r.stdout


# ── THE acceptance criterion: round-trip over a REAL corpus ────────────────────────────────────────
# For every corpus file F: emit(fmt(F)) must equal emit(F) — i.e. the formatted output reparses to the
# SAME resolved AST (a far stronger check than text equality; it catches dropped parens / returns /
# imports / struct methods / type-args). Both sides are emitted from a temp dir so a cyclically-imported
# module pulls its real twin identically on both sides (the cycle is held constant, not compared away).
_CORPUS = [
    "zen/std/text/str.zen",
    "zen/std/core/result.zen",
    "zen/std/mem/rc.zen",
    "zen/std/mem/trace.zen",          # generic struct Rc<T> with inherent methods + Rc<Node>(…) literals
    "zen/std/collections/vec.zen",
    "zen/compiler/lex.zen",
    "zen/compiler/genjs.zen",
    "zen/compiler/parse_type.zen",    # part of the parser import cycle
    "zen/compiler/parse_expr.zen",
]


def _emit(zenc, path):
    return subprocess.run([zenc, "emit", str(path)], cwd=str(ROOT),
                          env={**os.environ, "ZEN_ROOT": str(ROOT)},
                          capture_output=True, text=True)


@pytest.mark.parametrize("rel", _CORPUS)
def test_fmt_ast_roundtrips_corpus_file(rel):
    """emit(fmt(F)) == emit(F): the formatted AST resolves to byte-identical C as the original."""
    zenc = _zenc()
    f = ROOT / rel
    assert f.exists(), f

    fmt = subprocess.run([zenc, "fmt", "--ast", str(f)], cwd=str(ROOT),
                         env={**os.environ, "ZEN_ROOT": str(ROOT)},
                         capture_output=True, text=True)
    assert fmt.returncode == 0, fmt.stderr

    d = Path(tempfile.mkdtemp())
    formatted = d / "fmt.zen"
    original = d / "orig.zen"      # plain copy in the SAME temp dir → identical cyclic-import behavior
    formatted.write_text(fmt.stdout)
    original.write_text(f.read_text())

    a = _emit(zenc, original)
    b = _emit(zenc, formatted)
    assert a.returncode == 0, a.stderr
    assert b.returncode == 0, b.stderr
    assert a.stdout == b.stdout, f"{rel}: emit(fmt) != emit(orig) — formatter changed the AST"


@pytest.mark.parametrize("rel", _CORPUS)
def test_fmt_ast_idempotent_corpus_file(rel):
    """fmt(fmt(F)) == fmt(F): formatting is a fixpoint on real code."""
    zenc = _zenc()
    f = ROOT / rel
    env = {**os.environ, "ZEN_ROOT": str(ROOT)}
    one = subprocess.run([zenc, "fmt", "--ast", str(f)], cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert one.returncode == 0, one.stderr
    d = Path(tempfile.mkdtemp())
    f1 = d / "f1.zen"
    f1.write_text(one.stdout)
    two = subprocess.run([zenc, "fmt", "--ast", str(f1)], cwd=str(ROOT), env=env, capture_output=True, text=True)
    assert two.returncode == 0, two.stderr
    assert one.stdout == two.stdout, f"{rel}: fmt is not idempotent"
