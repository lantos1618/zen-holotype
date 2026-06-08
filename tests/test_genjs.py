"""genJs — the JavaScript backend (std.genjs), the final item of `zen generates its own C AND JS`.

std.genjs walks the SAME shared AST (std.genc) the C backend walks, and emits JavaScript. This test
drives the SELF-HOSTED toolchain — NO Python compiler — exactly like _oracle.py's check binary:

  1. The committed EMIT binary (cc bootstrap/{zenc.gen.c,zenrt.c,main.c}) compiles the frontend
     SOURCES + std/genjs.zen into one flat .gen.c (the binary is Zen-written, compiled to the
     committed bootstrap C). `cc` links that with a tiny C main that reads a .zen file, runs
     parse_module -> resolve_module, then calls genModuleJs -> a JS String written to stdout.
  2. For each program, we genjs-emit its JS, wrap it with a `console.log(test())` epilogue, run it
     with `node -e`, and assert the number node prints == the value the C backend computes.

So the proof is end-to-end: Zen source -> (Zen-written genjs, via the committed binary) -> JS ->
node -> the expected integer. If node is unavailable, we fall back to asserting the emitted JS TEXT.
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
# (resolve_module lives in parse/resolve path), PLUS std/genjs.zen — the new backend under test.
_GENJS_SOURCES = ["zen/std/genc.zen", "zen/std/genc_mono.zen", "zen/std/genc_emit.zen",
                  "zen/std/lex.zen", "zen/std/parse_expr.zen", "zen/std/parse_type.zen",
                  "zen/std/parse_stmt.zen", "zen/std/parse.zen", "zen/std/check.zen",
                  "zen/std/genjs.zen"]

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
                     if not (l.strip().startswith("{ ") and "= std." in l))


def _build_emit():
    """The committed EMIT binary: cc bootstrap/{zenc.gen.c,zenrt.c,main.c}. NO Python."""
    global _emit_exe
    if _emit_exe is None:
        d = Path(tempfile.mkdtemp())
        exe = d / "zenc"
        r = subprocess.run(_CC + [str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(BOOT / "main.c"), "-o", str(exe)],
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
    prog = js + "\nconsole.log(test());\n"
    out = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=15)
    assert out.returncode == 0, "node failed:\n" + out.stderr + "\n--- JS ---\n" + js
    s = out.stdout.strip()
    return int(s) if s.lstrip("-").isdigit() else None


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

CASES = [
    ("fac",    FAC,    120),
    ("fib",    FIB,    55),
    ("prec",   PREC,   9),
    ("div",    DIV,    3),
    ("modp",   MODP,   2),
    ("struct", STRUCT, 25),
    ("enum",   ENUM,   40),
    ("let",    LET,    42),
]


@pytest.mark.skipif(NODE is None, reason="node unavailable — see test_genjs_text_when_no_node")
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
    # integer division must emit Math.trunc — JS `/` alone would yield a float.
    assert "Math.trunc(" in emit_js(DIV)


def test_genjs_enum_match_is_tagged_object():
    js = emit_js(ENUM)
    assert '{tag: "Square"' in js          # MakeEnum -> tagged object
    assert '.tag === "Square"' in js       # Match -> tag test
    assert "_0" in js                       # payload slot


@pytest.mark.skipif(NODE is not None, reason="node present — run_js path covers it")
def test_genjs_text_when_no_node():
    # node-proof pending: at least assert the JS text is well-formed for the key cases.
    assert "function fac(n)" in emit_js(FAC)
    assert "Math.trunc(" in emit_js(DIV)
