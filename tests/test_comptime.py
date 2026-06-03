"""P3: comptime — the compile-time evaluator. `comptime(expr)` folds to a constant."""
import subprocess
import sys
import pytest

from zen.main import load, build_namespace, build_scopes, resolve, check, emit_c
from zen.comptime import ComptimeErr, fold_comptime


def frontend(tmp_path, src, fold=True):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files)
    resolve(files, namespace)
    if fold:                                 # the dedicated comptime pass: runs before check
        fold_comptime(files, namespace)
    _, passing = check(files, namespace)
    return files, namespace, passing


def test_comptime_folds_to_a_constant(tmp_path):
    files, namespace, passing = frontend(tmp_path, """
fact* = (n: i32) i32 { n.match ({ 0 => 1, _ => n * fact(n - 1) }) }
runtime*  = () i32 { fact(5) }
folded*   = () i32 { comptime(fact(5)) }
""")
    c = emit_c(files, passing, namespace)
    assert "m_runtime(void) { return m_fact(5); }" in c       # a real runtime call
    assert "m_folded(void) { return 120; }" in c              # evaluated away to a constant


def test_comptime_arithmetic_and_bool(tmp_path):
    files, namespace, passing = frontend(tmp_path, """
a* = () i32  { comptime(2 + 3 * 4) }
b* = () bool { comptime(10 > 3 && 1 == 1) }
""")
    c = emit_c(files, passing, namespace)
    assert "m_a(void) { return 14; }" in c
    assert "m_b(void) { return true; }" in c


def test_comptime_runs(tmp_path):
    files, namespace, passing = frontend(tmp_path, """
fib* = (n: i32) i32 { n.match ({ 0 => 0, 1 => 1, _ => fib(n-1) + fib(n-2) }) }
main* = () i32 { comptime(fib(10)) }
""")
    c = emit_c(files, passing, namespace)
    assert "return 55;" in c                                  # fib(10) folded
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")   # file is m.zen → m_main
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 55


def test_fold_pass_rewrites_nested_comptime(tmp_path):
    # comptime appears deep inside arithmetic, a let, and a loop body — the
    # dedicated pass must reach all of them and leave no comptime node behind.
    files, namespace, passing = frontend(tmp_path, """
k* = () i32 { 7 }
mix* = (n: i32) i32 {
    acc := n + comptime(2 * 3)
    loop(comptime(k()), (h, i) { acc = acc + comptime(10 - 8) })
    acc
}
""")
    # no comptime call survives anywhere in the AST handed to check/lower
    fn = next(d for d in files["m"].decls if d.name == "mix")
    src = repr(fn.body)
    assert "comptime" not in src
    assert "Lit(n=6" in src and "Lit(n=7" in src and "Lit(n=2" in src   # the folded constants
    c = emit_c(files, passing, namespace)
    assert "(n + 6)" in c and "(i < 7)" in c and "(acc + 2)" in c


def test_comptime_rejects_runtime_op(tmp_path):
    with pytest.raises(ComptimeErr):           # load is a runtime op — the fold pass rejects it
        frontend(tmp_path, """
malloc = (n: i64) RawPtr<u8>
bad* = () u8 { comptime(load(malloc(1))) }
""")


def test_comptime_infinite_loop_is_fueled(tmp_path):
    with pytest.raises(ComptimeErr):           # runs out of fuel instead of hanging
        frontend(tmp_path, """
spin* = (n: i32) i32 { spin(n) }
bad*  = () i32 { comptime(spin(1)) }
""")


# ── multi-method trait reflection (goal #13): count + name_at over all methods ─
def test_trait_method_count_reflects_all_methods(tmp_path):
    files, namespace, passing = frontend(tmp_path, """
TwoWay: { fwd: (Self) i32, back: (Self) i32 }
n* = () i32 { comptime(trait_method_count(reflect_trait(TwoWay))) }
""")
    c = emit_c(files, passing, namespace)
    assert "m_n(void) { return 2; }" in c                 # both methods seen (not just the first)


def test_trait_method_name_at_indexes_methods():
    # name_at(i) reaches ANY method, not just methods[0] — the core of the fix.
    # (driven directly: comptime has no string compare to assert in-source)
    from zen.parser import parse
    from zen.comptime import evaluate
    files = {"m": parse("TwoWay: { fwd: (Self) i32, back: (Self) i32 }", "m")}
    namespace = build_namespace(files); build_scopes(files); resolve(files, namespace)
    g = lambda src: evaluate(parse(f"x = () i32 {{ {src} }}", "q").decls[0].body[0],
                             namespace, files["m"].scope)
    assert g("trait_method_count(reflect_trait(TwoWay))") == 2
    assert g("trait_method_name_at(reflect_trait(TwoWay), 0)") == "fwd"
    assert g("trait_method_name_at(reflect_trait(TwoWay), 1)") == "back"   # the SECOND method
