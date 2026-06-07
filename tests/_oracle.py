"""Python-FREE self-hosted oracle — the Stage-C2 replacement for `_difftest.self_side`.

The self-hosted `zenc` BINARY is the sole correctness reference: NO `zen.main` (the Python
reference frontend) is imported here. Two binaries, both built from the committed bootstrap C
(`cc` is the only toolchain in the loop — zero Python compiler):

  EMIT  binary  (bootstrap/{zenc.gen.c,zenrt.c,main.c})        — Zen source -> C on stdout
  CHECK binary  (a check-mode gen.c + check_main.c)            — exit code = check error count

`emit_value(src, want)` compiles `src` with the EMIT binary, compiles + runs the emitted C, and
returns the int `test()` computes (silent-miscompile guard: assert == want).
`verdict(src)` runs the CHECK binary; exit 0 == "accept", >0 == "reject" (reject-parity guard).

How the CHECK binary stays Python-free: the committed EMIT binary compiles the compiler sources
PLUS check_validate.zen (which the emit-only binary leaves out) into check-mode C, which `cc`
links with check_main.c. So `cc` + the committed `zenc` binary build BOTH — Python never runs.
(The import-strip+concat used to assemble the check-mode source is the same transform std.resolve
reproduces byte-for-byte; here it's done in this harness's setup, OUTSIDE the per-test loop.)
"""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOT = ROOT / "bootstrap"
HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "
_CC = ["cc", "-std=gnu11", "-w"]
_RUNNER = "\n#include <stdio.h>\nint main(void){ printf(\"%%lld\", (long long)(test())); return 0; }\n"

# the compiler IS these files (generate.py SOURCES); check_validate.zen adds the VALIDATING pass
# (check_module) the emit-only binary omits. Imports (`{…} = std.x`) are stripped — runtime types
# come from zenrt.{h,c}. (This list mirrors bootstrap/generate.py.SOURCES + check_validate.zen.)
_EMIT_SOURCES = ["zen/std/genc.zen", "zen/std/genc_mono.zen", "zen/std/genc_emit.zen",
                 "zen/std/lex.zen", "zen/std/parse_expr.zen", "zen/std/parse_type.zen",
                 "zen/std/parse_stmt.zen", "zen/std/parse.zen", "zen/std/check.zen"]
_CHECK_SOURCES = _EMIT_SOURCES + ["zen/std/check_validate.zen"]

# a CLI entry that returns check_module's error count as the process exit code.
_CHECK_MAIN = r"""#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
int32_t check_module(Malloc* a, zslice decls);
int main(int argc, char** argv){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "cannot open %s\n", argv[1]); return 2; } }
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    Malloc m = { 0 };
    return check_module(&m, resolve_module(&m, parse_module(&m, buf)));
}
"""

# Runtime/compiler symbols the _selfhost driver's _PRELUDE makes visible to a checked program
# (Malloc, heap, slice, putchar, …). The check binary's flat source has no module resolver, so a
# program that uses these names would otherwise count them as undefined. We prepend bodyless
# DForeign decls so the checker treats them as known imported signatures (matching _selfhost).
# (Only used by the CHECK path; the emit path tolerates them via genc's intrinsic handling.)
_PRELUDE = (
    "heap = (n: i64) RawPtr<u8>\n"
    "putchar = (c: i32) i32\n"
)

_emit_exe = None
_check_exe = None


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


def _build_check():
    """The CHECK binary: have the EMIT binary compile (SOURCES + check_validate.zen) into check-mode
    C, then cc that with check_main.c. NO Python compiler — only the committed binary + cc."""
    global _check_exe
    if _check_exe is None:
        emit = _build_emit()
        d = Path(tempfile.mkdtemp())
        (d / "checksrc.zen").write_text("\n".join(_strip_imports(p) for p in _CHECK_SOURCES))
        c = subprocess.run([str(emit), str(d / "checksrc.zen")], capture_output=True, text=True).stdout
        assert c.startswith(HEAD), c[:80]
        (d / "checkc.gen.c").write_text('#include "zenrt.h"\n' + c[len(HEAD):])
        (d / "check_main.c").write_text(_CHECK_MAIN)
        exe = d / "zenc-check"
        r = subprocess.run(_CC + ["-I", str(BOOT), str(d / "checkc.gen.c"), str(BOOT / "zenrt.c"),
                                  str(d / "check_main.c"), "-o", str(exe)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _check_exe = exe
    return _check_exe


def emit_c_for(src):
    """The C the self-hosted EMIT binary produces for `src` (raises on a non-zero compile of the C)."""
    return subprocess.run([str(_build_emit())], input=src, capture_output=True, text=True).stdout


def check_count(src):
    """The CHECK binary's error count (process exit code) — the drop-in for _selfhost.check_errors.
    The runtime _PRELUDE makes _selfhost's imported runtime symbols (heap, …) known to the checker."""
    return subprocess.run([str(_build_check())], input=_PRELUDE + src, capture_output=True,
                          text=True, timeout=30).returncode


def verdict(src):
    """'accept' iff the CHECK binary reports zero errors, else 'reject'."""
    return "accept" if check_count(src) == 0 else "reject"


def emit_value(src):
    """Compile `src` with the EMIT binary, compile+run the emitted C, return test()'s int (or None)."""
    c = emit_c_for(src)
    if not c.strip():
        return None
    body = c[len(HEAD):] if c.startswith(HEAD) else c
    d = Path(tempfile.mkdtemp())
    prog = "#include <stdint.h>\n#include <stdbool.h>\n" + HEAD + "\n" + body + (_RUNNER % ())
    (d / "g.c").write_text(prog)
    if subprocess.run(_CC + [str(d / "g.c"), "-o", str(d / "g")],
                      capture_output=True, text=True).returncode != 0:
        return None
    out = subprocess.run([str(d / "g")], capture_output=True, text=True, timeout=10)
    s = out.stdout.strip()
    return int(s) if s.lstrip("-").isdigit() else None


def self_side(src):
    """Drop-in shape-compatible with _difftest.self_side: {verdict, value}."""
    v = verdict(src)
    val = emit_value(src) if ("test*" in src or "test *" in src) else None
    return {"verdict": v, "value": val}
