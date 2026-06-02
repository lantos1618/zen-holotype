"""Backend parity — the first replacement gate (Phase 8 of the bootstrap plan).

The whole point of self-hosting is that the Zen-written backend (std.parse -> std.genc)
can stand in for the Python one (emit_c). Before any replacement, we need a gate that the
two AGREE. They overlap on the arithmetic subset the Zen front+back end already handle, so
this compiles the SAME source two ways and asserts the same answer:

  Python:  `main* = () i32 { <expr> }`  --emit_c-->  C  --cc-->  run
  Zen:     parse(<expr>) -> genC          --emit-->   C  --cc-->  run

A divergence (the Zen pipeline mis-parsing precedence, mis-lowering an op) fails the gate.
As the Zen compiler grows to the full ast.py, this suite is where parity is enforced.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)

ARITH = [
    "(1 + 2) * 3",
    "1 + 2 * 3",
    "10 - 3 - 2",
    "20 / 4 / 5",
    "2 * (3 + 4) - 1",
    "((1 + 1)) * ((2 + 2))",
    "100 - 7 * 8",
]


def _compile_run(tmp_path, c_src, name, call_main):
    (tmp_path / name).write_text(c_src + call_main)
    exe = tmp_path / (name + ".out")
    r = subprocess.run(["cc", "-std=gnu11", str(tmp_path / name), "-o", str(exe)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(exe)]).returncode


def python_pipeline(tmp_path, expr):
    """Compile `main* = () i32 { <expr> }` through the PYTHON backend; return main()."""
    (tmp_path / "main.zen").write_text(f"main* = () i32 {{ {expr} }}\n")
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace, roots={"main.main"})
    return _compile_run(tmp_path, c, "py.c", "\nint main(void){ return main_main(); }\n")


_ZEN_DRIVER = """
{ Malloc } = std.alloc
{ parse_fn } = std.parse
{ genC } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genC(addr(m).parse_fn("%s", "f")))
    0
}
"""


def zen_pipeline(tmp_path, expr):
    """Parse `<expr>` with std.parse, emit C via std.genc at runtime, compile + run f()."""
    (tmp_path / "main.zen").write_text(_ZEN_DRIVER % expr)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace, roots={"main.main"})
    gen = _compile_run_capture(tmp_path, c)
    return _compile_run(tmp_path, "#include <stdint.h>\n" + gen, "zen.c", "\nint main(void){ return f(); }\n")


def _compile_run_capture(tmp_path, c):
    (tmp_path / "drv.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    exe = tmp_path / "drv"
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "drv.c"), "-o", str(exe)],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(exe)], capture_output=True, text=True).stdout


@pytest.mark.parametrize("expr", ARITH)
def test_python_and_zen_backends_agree(tmp_path, expr):
    py = python_pipeline(tmp_path, expr)
    zen = zen_pipeline(tmp_path, expr)
    assert py == zen, f"backends disagree on {expr!r}: python={py} zen={zen}"
