"""The bundled standard library — `std.*`, ordinary runtime Zen, importable from
any program. Unlike the comptime-only prelude, std is checked and lowered like
user code; but its helpers are templates, so importing std costs nothing unless a
program uses them (they inline at the call site, never emitted standalone)."""
import subprocess

from zen.main import (load, build_space, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    fold_comptime(files, space); run_emits(files, space)
    _, passing = check(files, space)
    return files, space, passing


def run(tmp_path, c, entry="main"):
    cfile = tmp_path / "o.c"
    cfile.write_text(c + f"\nint main(void){{ return main_{entry}(); }}\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_std_iter_is_loaded_and_importable(tmp_path):
    files, space, passing = build(tmp_path, """
{ fold } = std.iter
main* = () i32 { fold([1, 2, 3], 0, (a, x) { a + x }) }
""")
    assert "std.iter" in files                       # bundled, always loaded
    assert space.walk("std.iter.fold").value.tparams == ("T",)
    assert "main.main" in passing


def test_fold_and_each_run(tmp_path):
    files, space, passing = build(tmp_path, """
{ fold, each } = std.iter
main* = () i32 {
    s := fold([10, 20, 30], 0, (a, x) { a + x })   // 60
    r := 0
    each([1, 2, 3], (x) { r = r + x })             // 6
    s + r
}
""")
    assert run(tmp_path, emit_c(files, passing, space)) == 66


def test_fold_is_generic_over_element_type(tmp_path):
    # the same template folds an i64 slice — T solved from the arguments
    files, space, passing = build(tmp_path, """
{ fold } = std.iter
main* = () i64 { fold([100, 200, 300], 0, (a, x) { a + x }) }
""")
    c = emit_c(files, passing, space)
    assert run(tmp_path, c, entry="main") == (600 & 0xFF)   # exit code is 8-bit


def test_unused_std_emits_nothing(tmp_path):
    # importing nothing from std → std contributes no C at all (zero-cost ambient)
    files, space, passing = build(tmp_path, "main* = () i32 { 0 }")
    c = emit_c(files, passing, space)
    assert "std_iter" not in c and "fold" not in c
