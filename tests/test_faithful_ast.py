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
import subprocess
import tempfile
from pathlib import Path

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
