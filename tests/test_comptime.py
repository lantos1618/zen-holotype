"""P3: comptime — the compile-time evaluator. `comptime(expr)` folds to a constant."""
import subprocess
import sys
import pytest

from holotype.main import load, build_space, build_scopes, resolve, check, emit_c
from holotype.comptime import ComptimeErr


def frontend(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    _, passing = check(files, space)
    return files, space, passing


def test_comptime_folds_to_a_constant(tmp_path):
    files, space, passing = frontend(tmp_path, """
pub fact = (n: i32) i32 { match n { 0 => 1, _ => n * fact(n - 1) } }
pub runtime  = () i32 { fact(5) }
pub folded   = () i32 { comptime(fact(5)) }
""")
    c = emit_c(files, passing, space)
    assert "m_runtime(void) { return m_fact(5); }" in c       # a real runtime call
    assert "m_folded(void) { return 120; }" in c              # evaluated away to a constant


def test_comptime_arithmetic_and_bool(tmp_path):
    files, space, passing = frontend(tmp_path, """
pub a = () i32  { comptime(2 + 3 * 4) }
pub b = () bool { comptime(10 > 3 && 1 == 1) }
""")
    c = emit_c(files, passing, space)
    assert "m_a(void) { return 14; }" in c
    assert "m_b(void) { return true; }" in c


def test_comptime_runs(tmp_path):
    files, space, passing = frontend(tmp_path, """
pub fib = (n: i32) i32 { match n { 0 => 0, 1 => 1, _ => fib(n-1) + fib(n-2) } }
pub main = () i32 { comptime(fib(10)) }
""")
    c = emit_c(files, passing, space)
    assert "return 55;" in c                                  # fib(10) folded
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")   # file is m.zen → m_main
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 55


def test_comptime_rejects_runtime_op(tmp_path):
    files, space, passing = frontend(tmp_path, """
extern malloc = (n: i64) RawPtr<u8>
pub bad = () u8 { comptime(load(malloc(1))) }
""")
    with pytest.raises(ComptimeErr):           # load is a runtime op — can't comptime it
        emit_c(files, passing, space)


def test_comptime_infinite_loop_is_fueled(tmp_path):
    files, space, passing = frontend(tmp_path, """
pub spin = (n: i32) i32 { spin(n) }
pub bad  = () i32 { comptime(spin(1)) }
""")
    with pytest.raises(ComptimeErr):           # runs out of fuel instead of hanging
        emit_c(files, passing, space)
