"""The bootstrap fixpoint 🏁 — the self-hosted compiler reproduces itself with no Python.

`cc bootstrap/*.c -o zenc` builds a standalone binary from the COMMITTED C (bootstrap/
zenc.gen.c + a tiny runtime). That binary reads Zen source and emits C. Fed its OWN
source manifest (via the binary's `--build-self` mode, which strips imports + concatenates the
listed Zen sources and emits C), it produces byte-for-byte the C it was built from — the fixpoint.

ZERO Python participates: `cc` builds the binary, the binary regenerates its own source. If these
fail after editing `zen/compiler/` or manifest-listed `zen/std/` sources, regenerate the committed C
with the binary:
    make -f bootstrap/Makefile regen
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "bootstrap"


def _build(tmp_path):
    """cc the committed bootstrap sources into a binary — NO Python toolchain involved."""
    exe = tmp_path / "zenc"
    r = subprocess.run(["cc", "-std=gnu11", "-w",
                        str(BOOT / "zenc.gen.c"), str(BOOT / "zenrt.c"), str(BOOT / "main.c"),
                        "-o", str(exe)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return exe


def test_bootstrap_binary_compiles_zen(tmp_path):
    # the standalone binary turns Zen source into C
    exe = _build(tmp_path)
    out = subprocess.run([str(exe)], input="sq* = (n: i32) i32 { n * n }\n",
                         capture_output=True, text=True).stdout
    assert "int32_t sq(int32_t n)" in out
    assert "return (n * n);" in out
    # and that emitted C is itself valid (compile + run it)
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + out
                                  + "\nint main(void){ return sq(7) == 49 ? 0 : 1; }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0


def test_bootstrap_fixpoint(tmp_path):
    # 🏁 the binary, fed the compiler's own source files (via --build-self), reproduces the C it was
    # built from BYTE-FOR-BYTE. No Python: the binary itself reads/strips/concats the manifest and emits.
    exe = _build(tmp_path)
    out_c = tmp_path / "repro.gen.c"
    r = subprocess.run([str(exe), "--build-self", str(out_c), str(ROOT)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out_c.read_bytes() == (BOOT / "zenc.gen.c").read_bytes(), \
        "bootstrap/zenc.gen.c is stale — run `make -f bootstrap/Makefile regen`"


# A battery proving the binary is CORRECT on real programs, not just self-consistent: each Zen
# source is compiled by the binary, then the emitted C is compiled with a `main` that checks the
# answer and run. (`check` returns 0 iff the program computed the right result.) Both boolean-match
# arm orders are here on purpose — a false-first match is what the parse_bool_match bug inverted.
PROGRAMS = [
    ("bool_true_first",  "f* = (n: i32) i32 { (n < 5).match({ true => 1, false => 0 }) }",
                         "return f(3)==1 && f(9)==0 ? 0 : 1;"),
    ("bool_false_first", "g* = (n: i32) i32 { (n < 5).match({ false => 0, true => 1 }) }",
                         "return g(3)==1 && g(9)==0 ? 0 : 1;"),
    ("recursion_fib",    "fib* = (n: i32) i32 { (n < 2).match({ true => n, false => fib(n-1)+fib(n-2) }) }",
                         "return fib(10)==55 ? 0 : 1;"),
    ("while_sum",        "sum* = (n: i32) i32 {\n s := 0\n i := 1\n @while(i <= n) {\n  s = s + i\n  i = i + 1\n }\n s\n}",
                         "return sum(5)==15 ? 0 : 1;"),
    ("nested_while",     "grid* = (n: i32) i32 {\n c := 0\n i := 0\n @while(i < n) {\n  j := 0\n  @while(j < n) {\n   c = c + 1\n   j = j + 1\n  }\n  i = i + 1\n }\n c\n}",
                         "return grid(4)==16 ? 0 : 1;"),
    ("enum_match",       "Shape*: Circle(i32) | Square(i32)\nmk* = (n: i32) Shape {\n .Circle(n)\n}\narea* = (s: Shape) i32 {\n s.match({ .Circle(r) => r*r*3, .Square(w) => w*w })\n}",
                         "return area(mk(2))==12 ? 0 : 1;"),
    ("struct_field",     "Pt*: { x: i32, y: i32 }\nmk* = (a: i32, b: i32) Pt {\n Pt(x: a, y: b)\n}\nnsq* = (p: Pt) i32 {\n p.x*p.x + p.y*p.y\n}",
                         "return nsq(mk(3,4))==25 ? 0 : 1;"),
    ("precedence",       "e* = () i32 { 1 + 2 * 3 - 4 }",
                         "return e()==3 ? 0 : 1;"),
    ("compare_and",      "c* = (a: i32, b: i32) bool { (a < b) && (b < 10) }",
                         "return c(3,7) && !c(3,12) ? 0 : 1;"),
]


@pytest.fixture(scope="module")
def bootstrap_exe(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("boot"))


@pytest.mark.parametrize("name,src,check", PROGRAMS, ids=[p[0] for p in PROGRAMS])
def test_bootstrap_binary_runs_program(bootstrap_exe, tmp_path, name, src, check):
    emitted = subprocess.run([str(bootstrap_exe)], input=src, capture_output=True, text=True).stdout
    assert emitted.strip(), f"{name}: binary emitted nothing"
    prog = ("#include <stdint.h>\n#include <stdbool.h>\n" + emitted
            + "\nint main(void){ " + check + " }\n")
    (tmp_path / "p.c").write_text(prog)
    r = subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "p.c"), "-o", str(tmp_path / "p")],
                       capture_output=True, text=True)
    assert r.returncode == 0, f"{name}: emitted C did not compile\n{r.stderr}"
    assert subprocess.run([str(tmp_path / "p")]).returncode == 0, f"{name}: wrong runtime answer"


# Robustness: malformed / truncated / edge input must never CRASH the compiler — it should emit
# something or stop cleanly, never segfault. Each of these stack-overflowed (SIGSEGV) before the
# parser grew EOF base cases: skip_to_lparen / skip_to_brace recursed past EOF (scan returns
# next==pos there), and the Pratt atom ring re-entered without consuming a token. (C-audit #2–#4.)
MALFORMED = [
    ("no_colon_param",      "f* = (p i32) i32 { 1 }"),   # space-separated param: skip_to_lparen ran off EOF
    ("colon_payload_enum",  "E: A | Some: T"),            # ':'-payload variant: dispatched to skip_to_lparen
    ("truncated_binop",     "g* = () i32 { 6 *"),         # operator with no RHS at EOF: Pratt ring looped
    ("unterminated_block",  "h* = () i32 { 1"),
    ("unterminated_import",  "{ a, b"),                   # fill_import_names ran off EOF
    ("unterminated_tparams", "f<T"),                      # fill_tparams ran off EOF
    ("empty",               ""),
    ("lone_brace",          "{"),
    ("lone_ident",          "x"),
]


@pytest.mark.parametrize("name,src", MALFORMED, ids=[m[0] for m in MALFORMED])
def test_bootstrap_binary_survives_malformed_input(bootstrap_exe, name, src):
    # must terminate via a normal exit code, never be killed by a signal (negative rc = SIGSEGV/abort).
    # timeout guards against a regressed fix turning the crash into an infinite loop instead.
    r = subprocess.run([str(bootstrap_exe)], input=src, capture_output=True, text=True, timeout=15)
    assert r.returncode >= 0, f"{name}: compiler killed by signal {-r.returncode} on malformed input"


def test_bootstrap_binary_reports_missing_file(bootstrap_exe):
    # a mistyped filename must give a clean diagnostic, not a NULL FILE* -> fgetc(NULL) segfault. (C-audit #1.)
    r = subprocess.run([str(bootstrap_exe), "/nonexistent/zzz.zen"], capture_output=True, text=True, timeout=15)
    assert r.returncode == 1, "missing file should exit 1, not crash or succeed"
    assert "cannot open" in r.stderr
