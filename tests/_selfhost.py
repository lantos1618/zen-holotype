"""Shared harness for the self-hosted-toolchain tests.

Feed Zen source through the Zen-written toolchain (std.parse -> std.check -> std.genc, all
compiled by the Python host as `main.zen`), then act on the result three ways:

  emit_c_for(tmp, src)   -> the C the toolchain emits for `src` (genModule's output)
  check_errors(tmp, src) -> check_module's error count for `src` (a reject-parity gate)
  run_value(tmp, src, n) -> compile + run the emitted C; assert its `test()` returns n

One driver, one place — instead of the same 40 lines copied into every test module.
"""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "

# imports + helpers shared by all drivers; the unused ones are dead-code-eliminated per driver.
_PRELUDE = """
{ Malloc } = std.alloc
{ parse, parse_module } = std.parse
{ resolve_module, check_module, check_linked } = std.check
{ genModule, gen_sexpr } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
"""
_EMIT_MAIN = """main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""
_CHECK_MAIN = """main* = () i32 {
    m := Malloc { _: 0 }
    addr(m).check_module(addr(m).resolve_module(addr(m).parse_module("%s")))
}
"""
# check the first source against the second as an imported module (cross-module signature linking)
_LINK_MAIN = """main* = () i32 {
    m := Malloc { _: 0 }
    addr(m).check_linked(addr(m).parse_module("%s"), addr(m).parse_module("%s"))
}
"""
_SEXPR_MAIN = """main* = () i32 {
    m := Malloc { _: 0 }
    emit(new().gen_sexpr(addr(m).parse("%s")))
    0
}
"""


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _run(tmp_path, filled_main):
    """Compile the driver (PRELUDE + an already-source-embedded main) via the Python host, then run
    it. Returns the CompletedProcess (stdout = emitted C, returncode = check count)."""
    (tmp_path / "main.zen").write_text(_PRELUDE + filled_main)
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True)


def _drive(tmp_path, main, src):
    """_run with a single `src` embedded into a one-`%s` main template."""
    return _run(tmp_path, main % _zlit(src))


def emit_c_for(tmp_path, src):
    """The C the self-hosted toolchain emits for `src`."""
    return _drive(tmp_path, _EMIT_MAIN, src).stdout


def check_errors(tmp_path, src):
    """check_module's error count for `src` (the process exit code)."""
    return _drive(tmp_path, _CHECK_MAIN, src).returncode


def check_linked_errors(tmp_path, src, lib):
    """check_module's error count for `src` linked against `lib` as an imported module — so a
    cross-module call in `src` is checked against `lib`'s signatures (the process exit code)."""
    return _run(tmp_path, _LINK_MAIN % (_zlit(src), _zlit(lib))).returncode


def sexpr_of(tmp_path, expr):
    """The self-hosted parser's prefix s-expression for a single `expr` (via std.genc.gen_sexpr)."""
    return _drive(tmp_path, _SEXPR_MAIN, expr).stdout


def run_value(tmp_path, src, want):
    """Compile `src` with the self-hosted toolchain, then compile + run the emitted C with a main
    that returns 0 iff `test()` == want."""
    emitted = emit_c_for(tmp_path, src)
    body = emitted[len(HEAD):] if emitted.startswith(HEAD) else emitted
    (tmp_path / "g.c").write_text("#include <stdint.h>\n#include <stdbool.h>\n" + HEAD + "\n" + body
                                  + "\nint main(void){ return test() == %d ? 0 : 1; }\n" % want)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0, f"{src!r} should give {want}"
