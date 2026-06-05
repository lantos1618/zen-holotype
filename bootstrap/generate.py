#!/usr/bin/env python3
"""Regenerate bootstrap/zenc.gen.c — the C source of the self-hosted Zen compiler.

The Zen compiler is written in Zen (std/lex.zen, std/parse.zen, std/check.zen,
std/genc.zen). This script runs the toolchain ON those four files and writes the
emitted C to zenc.gen.c, which — with zenrt.c (a tiny runtime) and main.c (a CLI
entry) — builds a standalone `zenc` binary that needs no Python:

    python3 bootstrap/generate.py      # regenerate zenc.gen.c (after editing std/*.zen)
    cc -std=gnu11 -w bootstrap/*.c -o zenc
    ./zenc some.zen                    # Zen source on stdin/argv -> C on stdout

The binary REPRODUCES this file: `./zenc <the four sources concatenated>` emits
exactly zenc.gen.c's body. That fixpoint is checked by tests/test_bootstrap.py.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

# the compiler IS these four files, in dependency order (genc defines the AST + backend,
# lex the tokens, parse the parser, check the resolver/validator).
SOURCES = ["zen/std/genc.zen", "zen/std/lex.zen",
           "zen/std/parse_expr.zen", "zen/std/parse_type.zen", "zen/std/parse_stmt.zen",
           "zen/std/parse.zen", "zen/std/check.zen"]

# genc emits this zslice typedef at the head; zenrt.h provides it instead, so we strip it.
HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "

# the toolchain reads a flat module (imports stripped); the runtime types/functions it imports
# (String, new, append, push, eq, is_empty, heap, Malloc) are provided by zenrt.{h,c}.
_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module } = std.check
{ genModule } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""


def strip_imports(path):
    return "\n".join(l for l in (ROOT / path).read_text().splitlines()
                     if not (l.strip().startswith("{ ") and "= std." in l))


def compiler_source():
    """The four compiler files concatenated, imports stripped — the toolchain's own input."""
    return "\n".join(strip_imports(p) for p in SOURCES)


def _zen_lit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def generate_c(tmp_path):
    """Run the toolchain on the four sources; return the emitted compiler-library C (head kept)."""
    import subprocess
    src = compiler_source()
    (tmp_path / "main.zen").write_text(_DRIVER % _zen_lit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    assert "main.main" in passing, "the toolchain failed to type-check its own driver"
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], check=True)
    out = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    assert out.startswith(HEAD), out[:80]
    return out


def gen_c_file(out):
    """Wrap the emitted C as zenc.gen.c: include the runtime header in place of the head typedef."""
    return '#include "zenrt.h"\n' + out[len(HEAD):]


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = generate_c(Path(td))
    (Path(__file__).parent / "zenc.gen.c").write_text(gen_c_file(out))
    print(f"wrote bootstrap/zenc.gen.c ({len(out)} bytes of emitted C)")
