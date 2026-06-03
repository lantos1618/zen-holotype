"""The milestone: the self-hosted compiler (std.lex -> std.parse -> std.check -> std.genc,
all written IN Zen) compiles the SCANNER CORE of its own lexer (std/lex.zen) into C — which
then compiles and actually tokenizes.

We proved earlier that "the lexer lexes itself" (std.lex tokenizes lex.zen identically to
tree-sitter). This is the stronger claim: the lexer source is *compiled* by the self-hosted
toolchain, and the resulting binary lexes.
"""
import subprocess
from pathlib import Path

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def _zen_lit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _scanner_core():
    """The scanner section of std/lex.zen — up to the materialized-list section, which uses
    slices + generics the self-hosted backend doesn't lower yet."""
    out = []
    for line in Path("zen/std/lex.zen").read_text().splitlines():
        if line.startswith("{ Allocator }") or line.strip().startswith("TokList"):
            break
        out.append(line)
    return "\n".join(out)


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


def test_self_hosted_compiler_compiles_and_runs_its_own_scanner(tmp_path):
    core = _scanner_core()
    (tmp_path / "main.zen").write_text(_DRIVER % _zen_lit(core))
    files = load(tmp_path)
    ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    assert "main.main" in passing
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    # the program PRINTS the C that the self-hosted toolchain generated for the scanner core
    scanner_c = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    assert "uint8_t byte_at" in scanner_c and "Scan scan(" in scanner_c

    # that generated C must itself compile — AND lex: count("ab + 12") sees 4 tokens (ab, +, 12 … )
    (tmp_path / "lex.c").write_text(
        "#include <stdint.h>\n#include <stdbool.h>\n" + scanner_c +
        '\nint main(void){ return count("ab + 12"); }\n')
    r = subprocess.run(["cc", "-std=gnu11", str(tmp_path / "lex.c"), "-o", str(tmp_path / "lex")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                              # the self-hosted scanner compiles
    assert subprocess.run([str(tmp_path / "lex")]).returncode == 3  # tokens: `ab`, `+`, `12`


def test_self_hosted_compiler_compiles_the_WHOLE_lexer(tmp_path):
    # the full milestone: ALL of std/lex.zen — the scanner core AND the materialized cons-list
    # section (nodebuf/node/build/tokenize, which use slices + heap) — is parsed, checked,
    # lowered, compiled, and RUN by the self-hosted toolchain. It tokenizes a real string.
    full = Path("zen/std/lex.zen").read_text()
    src = "\n".join(l for l in full.splitlines() if not l.strip().startswith("{ Malloc, heap }"))
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
    lexer_c = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout
    assert "Scan scan(" in lexer_c and "nodebuf" in lexer_c and "zslice" in lexer_c

    # the generated C compiles (with the external Malloc type + heap = malloc) and tokenizes:
    # tokenize -> list_len("a + 12 foo") == 4  (a, +, 12, foo)
    (tmp_path / "lex.c").write_text(
        "#include <stdint.h>\n#include <stdbool.h>\n#include <stdlib.h>\n"
        "typedef struct { int32_t _; } Malloc;\nstatic void* heap(int64_t n){ return malloc(n); }\n"
        + lexer_c + '\nint main(void){ return list_len(tokenize(0, "a + 12 foo")); }\n')
    r = subprocess.run(["cc", "-std=gnu11", str(tmp_path / "lex.c"), "-o", str(tmp_path / "lex")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr            # the WHOLE self-hosted lexer compiles
    assert subprocess.run([str(tmp_path / "lex")]).returncode == 4
