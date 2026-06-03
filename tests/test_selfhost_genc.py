"""The fixpoint milestone: the self-hosted toolchain (std.lex -> std.parse -> std.check ->
std.genc, all written IN Zen) compiles genc.zen — the C BACKEND ITSELF — into valid C.

We feed std/genc.zen through the Zen-written toolchain and assert the emitted C compiles
(cc -c) given the external decls genc.zen imports (String + std.str). A real compiler source
file compiled by the compiler-in-itself.
"""
import subprocess
from pathlib import Path

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)

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
    src := "%s"
    emit(genModule(addr(m).resolve_module(addr(m).parse_module(src))))
    0
}
"""


def _zen_lit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def test_self_hosted_toolchain_compiles_genc_zen(tmp_path):
    full = Path("zen/std/genc.zen").read_text()
    # the self-hosted parser skips imports; std.string / std.str are provided as externs below.
    src = "\n".join(l for l in full.splitlines() if not (l.strip().startswith("{ ") and "= std." in l))
    (tmp_path / "main.zen").write_text(_DRIVER % _zen_lit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    assert "main.main" in passing
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    genc_c = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    # the self-hosted toolchain produced C for genc.zen's real functions
    assert len(genc_c) > 20000
    for fn in ("genModule", "gen_expr", "gen_stmt", "gen_func", "gen_loop"):
        assert fn in genc_c

    # and that emitted C COMPILES, given the external decls genc.zen imports
    head = "typedef struct { void* ptr; int64_t len; } zslice; "
    assert genc_c.startswith(head)
    prelude = ("#include <stdint.h>\n#include <stdbool.h>\n" + head + "\n"
        "typedef struct { uint8_t* ptr; int64_t len; int64_t cap; } String;\n"
        "String new(void); String append(String s, const char* x); String push(String s, uint8_t b);\n"
        "zslice view(const char* v); bool is_empty(const char* s); bool eq(const char* a, const char* b);\n")
    (tmp_path / "genc.c").write_text(prelude + genc_c[len(head):])
    r = subprocess.run(["cc", "-c", "-std=gnu11", str(tmp_path / "genc.c"), "-o", str(tmp_path / "genc.o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr   # genc.zen, compiled by the compiler-in-itself, is valid C


def test_self_hosted_toolchain_compiles_genc_AND_check(tmp_path):
    # genc.zen + check.zen together (check imports genc's types+ctors) — the self-hosted
    # toolchain parses, checks, lowers BOTH; the emitted C compiles given the std externs.
    def strip(f):
        return "\n".join(l for l in Path(f).read_text().splitlines()
                         if not (l.strip().startswith("{ ") and "= std." in l))
    src = strip("zen/std/genc.zen") + "\n" + strip("zen/std/check.zen")
    (tmp_path / "main.zen").write_text(_DRIVER % _zen_lit(src))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    assert "main.main" in passing
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    out = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    for fn in ("genModule", "resolve_module", "infer_expr", "check_module", "fits"):
        assert fn in out
    head = "typedef struct { void* ptr; int64_t len; } zslice; "
    prelude = ("#include <stdint.h>\n#include <stdbool.h>\n" + head + "\n"
        "typedef struct { uint8_t* ptr; int64_t len; int64_t cap; } String;\n"
        "String new(void); String append(String s, const char* x); String push(String s, uint8_t b);\n"
        "zslice view(const char* v); bool is_empty(const char* s); bool eq(const char* a, const char* b);\n"
        "typedef struct { int32_t _; } Malloc;\nvoid* heap(int64_t n);\n")
    (tmp_path / "gc.c").write_text(prelude + out[len(head):])
    r = subprocess.run(["cc", "-c", "-std=gnu11", str(tmp_path / "gc.c"), "-o", str(tmp_path / "gc.o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr   # genc.zen + check.zen, compiled by the compiler-in-itself
