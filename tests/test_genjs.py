"""genJs — the JavaScript backend (compiler.genjs), the final item of `zen generates its own C AND JS`.

compiler.genjs walks the SAME shared AST (compiler.genc) the C backend walks, and emits JavaScript. This test
drives the SELF-HOSTED toolchain — NO Python compiler — exactly like _oracle.py's check binary:

  1. The committed EMIT binary (cc bootstrap/{zenc.gen.c,zenrt.c,main.c}) compiles the frontend
     SOURCES + compiler/genjs.zen into one flat .gen.c (the binary is Zen-written, compiled to the
     committed bootstrap C). `cc` links that with a tiny C main that reads a .zen file, runs
     parse_module -> resolve_module, then calls genModuleJs -> a JS String written to stdout.
  2. For each program, we genjs-emit its JS, wrap it with a `console.log(test())` epilogue, run it
     with `node -e`, and assert the number node prints == the value the C backend computes.

So the proof is end-to-end: Zen source -> (Zen-written genjs, via the committed binary) -> JS -> node
-> the expected integer. The emitted JS text is asserted separately every run.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "bootstrap"
HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "
_CC = ["cc", "-std=gnu11", "-w"]

NODE = shutil.which("node")

# the frontend the genjs driver needs: the shared AST + mono + the C emitter (genModule is unused
# but genc_emit defines helpers genjs leans on via the shared module), the lexer/parser, the checker
# (resolve_module lives in parse/resolve path), PLUS compiler/genjs.zen — the backend under test.
_GENJS_SOURCES = ["zen/compiler/genc.zen", "zen/std/core/result.zen", "zen/compiler/mono.zen", "zen/compiler/genc_emit.zen",
                  "zen/std/text/bytes.zen",
                  "zen/compiler/lex.zen", "zen/compiler/parse_expr.zen", "zen/compiler/parse_type.zen",
                  "zen/compiler/parse_stmt.zen", "zen/compiler/parse.zen", "zen/compiler/check.zen",
                  "zen/compiler/genjs.zen"]

# a CLI entry: read a .zen file (argv[1] or stdin), parse+resolve, emit JS via genModuleJs to stdout.
_GENJS_MAIN = r"""#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
String genModuleJs(zslice decls);
static char* read_all(FILE* in){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0; return buf;
}
int main(int argc, char** argv){
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "cannot open %s\n", argv[1]); return 2; } }
    char* buf = read_all(in);
    Malloc m = { 0 };
    String out = genModuleJs(resolve_module(&m, parse_module(&m, buf)));
    fwrite(out.ptr, 1, out.len, stdout);
    return 0;
}
"""

_emit_exe = None
_genjs_exe = None


def _strip_imports(path):
    return "\n".join(l for l in (ROOT / path).read_text().splitlines()
                     if not (l.strip().startswith("{ ") and ("= std." in l or "= compiler." in l)))


def _build_emit():
    """The committed EMIT binary: cc bootstrap/{zenc.gen.c,zenrt.c,main.c}. NO Python."""
    global _emit_exe
    if _emit_exe is None:
        d = Path(tempfile.mkdtemp())
        exe = d / "zenc"
        r = subprocess.run(_CC + [str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"),
 "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _emit_exe = exe
    return _emit_exe


def _build_genjs():
    """The GENJS driver: have the committed EMIT binary compile (frontend SOURCES + genjs.zen) into
    C, then cc that with _GENJS_MAIN. Only the committed binary + cc are used; NO Python compiler."""
    global _genjs_exe
    if _genjs_exe is None:
        emit = _build_emit()
        d = Path(tempfile.mkdtemp())
        (d / "genjssrc.zen").write_text("\n".join(_strip_imports(p) for p in _GENJS_SOURCES))
        c = subprocess.run([str(emit), str(d / "genjssrc.zen")], capture_output=True, text=True).stdout
        assert c.startswith(HEAD), c[:200]
        (d / "genjsc.gen.c").write_text('#include "zenrt.h"\n' + c[len(HEAD):])
        (d / "genjs_main.c").write_text(_GENJS_MAIN)
        exe = d / "zenc-genjs"
        r = subprocess.run(_CC + ["-I", str(BOOT), str(d / "genjsc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(d / "genjs_main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _genjs_exe = exe
    return _genjs_exe


def emit_js(src):
    """The JS the self-hosted genjs backend produces for `src`."""
    return subprocess.run([str(_build_genjs())], input=src, capture_output=True, text=True, timeout=30).stdout


def run_js(src):
    """genjs-emit `src`, then run `<js>; console.log(test())` in node — returns the int it prints."""
    js = emit_js(src)
    assert NODE, "node unavailable"
    prog = js + "\nconsole.log(String(test()));\n"
    out = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=15)
    assert out.returncode == 0, "node failed:\n" + out.stderr + "\n--- JS ---\n" + js
    s = out.stdout.strip()
    assert s.lstrip("-").isdigit(), "non-integer node output: " + repr(out.stdout)
    return int(s)


# ── the corpus: (name, source, expected test() value) ───────────────────────────────────────────
FAC = "fac* = (n: i64) i64 { (n < 2).match ({ true => 1, false => n * fac(n - 1) }) }\ntest* = () i64 { fac(5) }\n"
FIB = "fib* = (n: i64) i64 { (n < 2).match ({ true => n, false => fib(n - 1) + fib(n - 2) }) }\ntest* = () i64 { fib(10) }\n"
PREC = "test* = () i32 { (1 + 2) * 3 }\n"
DIV = "test* = () i32 { 17 / 5 }\n"                       # integer division must truncate: 3, not 3.4
MODP = "test* = () i32 { 17 - (17 / 5) * 5 }\n"           # remainder via div: 2
STRUCT = ("Pt*: { x: i32, y: i32 }\n"
          "mk* = (a: i32, b: i32) Pt { Pt(x: a, y: b) }\n"
          "norm_sq* = (p: Pt) i32 { p.x * p.x + p.y * p.y }\n"
          "test* = () i32 { norm_sq(mk(3, 4)) }\n")       # 25
ENUM = ("Shape*: Circle(i32) | Square(i32) | Other\n"
        "area* = (s: Shape) i32 {\n"
        "  s.match ({\n"
        "    .Circle(r) => r * r,\n"
        "    .Square(w) => w * w,\n"
        "    .Other => 0\n"
        "  })\n"
        "}\n"
        "test* = () i32 { area(.Square(6)) + area(.Circle(2)) + area(.Other) }\n")   # 36 + 4 + 1? -> 36+4+0=40; with Other=0 -> 40; we assert below
LET = "test* = () i32 { x := 6\n  y := 7\n  x * y }\n"    # 42 — let-bindings + trailing expr
# f64: JS numbers ARE doubles, so this is the one backend where the FloatLit text is native; the
# to_i32 cast emits Math.trunc, so the C and JS backends compute the same integer.
FLOAT = "test* = () i32 { x := 1.5\n  to_i32((x + 0.25) * 4.0) }\n"   # 7
SLICE = "test* = () i32 { xs := [10, 20, 12]\n  xs[1] + xs.len + xs[2] }\n"  # 35
LOOP = "test* = () i32 { xs := [3, 4, 5]\n  total := 0\n  xs.loop((h, i, x) { total = total + x + to_i32(i) })\n  total }\n"  # 15
BLOCK = "test* = () i32 { v := { a := 2\n  a + 5 }\n  v * 3 }\n"  # 21
HOF = ("apply = (f: (i32) i32, x: i32) i32 { f(x) }\n"
       "twice = (n: i32) i32 { n * 2 }\n"
       "test* = () i32 { apply(twice, 11) + apply((n){ n + 9 }, 11) }\n")  # 42

CASES = [
    ("fac",    FAC,    120),
    ("fib",    FIB,    55),
    ("prec",   PREC,   9),
    ("div",    DIV,    3),
    ("modp",   MODP,   2),
    ("struct", STRUCT, 25),
    ("enum",   ENUM,   40),
    ("let",    LET,    42),
    ("float",  FLOAT,  7),
    ("slice",  SLICE,  35),
    ("loop",   LOOP,   15),
    ("block",  BLOCK,  21),
    ("hof",    HOF,    42),
]


@pytest.mark.parametrize("name,src,want", CASES, ids=[c[0] for c in CASES])
def test_genjs_runs_in_node(name, src, want):
    # the SELF-HOSTED genjs backend emits JS; node runs it and computes exactly `want`.
    assert run_js(src) == want


def test_genjs_emits_function_and_no_typedef():
    # a JS module is just function defs — no C `typedef`/`struct`, and structs become a comment.
    js = emit_js(STRUCT)
    assert "function mk(a, b)" in js
    assert "function norm_sq(p)" in js
    assert "({x: a, y: b})" in js          # struct literal -> structural object
    assert "typedef" not in js
    assert "struct" in js.lower()          # only the elision comment mentions "struct"


def test_genjs_division_truncates():
    # integer division must emit Math.trunc — JS `/` alone would produce a float.
    assert "Math.trunc(" in emit_js(DIV)


def test_genjs_float_literal_is_native():
    # a FloatLit's source text is emitted verbatim (a JS number IS a double); to_i32 -> Math.trunc.
    js = emit_js(FLOAT)
    assert "1.5" in js and "0.25" in js
    assert "Math.trunc(" in js


def test_genjs_enum_match_is_tagged_object():
    js = emit_js(ENUM)
    assert '{tag: "Square"' in js          # MakeEnum -> tagged object
    assert '.tag === "Square"' in js       # Match -> tag test
    assert "_0" in js                       # payload slot


def test_genjs_emits_text_for_core_cases():
    # This is useful even when node is present: it pins backend text for key lowering decisions.
    assert "function fac(n)" in emit_js(FAC)


def test_genjs_emits_slice_and_loop_as_js_values():
    js = emit_js(SLICE + LOOP.replace("test*", "loop_test*"))
    assert "ptr: [10, 20, 12]" in js
    assert ".ptr[1]" in js
    assert "for (let __zen_local" in js and " < _seq.len;" in js


def test_genjs_marks_raw_primitive_calls():
    js = emit_js("test* = () i32 { x := 1\n  @addr(x)\n  0 }\n")
    assert "unsupported-in-js: raw @addr" in js
    assert "unsupported-in-js: intrinsic addr" not in js


def test_genjs_marks_pointer_memory_intrinsics():
    js = emit_js(
        "test* = () i32 {\n"
        "  p := null_ptr()\n"
        "  load(p)\n"
        "  store(p, 1)\n"
        "  offset(p, 1)\n"
        "  cstr(p)\n"
        "  load_i64(p)\n"
        "  store_i64(p, 1)\n"
        "  atomic_add_i64(p, 1)\n"
        "  0\n"
        "}\n"
    )
    for name in ["null_ptr", "load", "store", "offset", "cstr", "load_i64", "store_i64", "atomic_add_i64"]:
        assert f"unsupported-in-js: intrinsic {name}" in js


def test_genjs_plain_malloc_is_not_magic():
    js = emit_js("malloc = (n: i32) i32 { n + 1 }\ntest* = () i32 { malloc(4) }\n")
    assert "function malloc(n)" in js
    assert "malloc(4)" in js
    assert "unsupported-in-js: intrinsic malloc" not in js
