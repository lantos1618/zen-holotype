"""Division `/` and remainder `%` — numeric arithmetic at the `*` precedence level,
with C truncate-toward-zero semantics shared by the runtime and the comptime folder."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def build(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    return results, passing, namespace, files


def run(tmp_path, files, passing, namespace):
    c = emit_c(files, passing, namespace)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(cfile), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_div_rem_precedence_and_runtime(tmp_path):
    # `/` and `%` bind tighter than `+`/`-` (the `*` level): 1 + 6/2*2 + 17%5 = 1+6+2 = 9
    _, passing, namespace, files = build(tmp_path, "main* = () i32 { 1 + 6 / 2 * 2 + 17 % 5 }")
    assert "main.main" in passing
    assert run(tmp_path, files, passing, namespace) == 9


def test_negative_truncates_toward_zero(tmp_path):
    # C semantics: -7/2 == -3 (trunc, not floor), -7%2 == -1 (sign of the dividend).
    # encode into an exit-code-safe value: (-3+10)*10 + (-1+10) = 70 + 9 = 79
    _, passing, namespace, files = build(tmp_path, """
main* = () i32 {
    d := 0 - 7
    q := d / 2
    r := d % 2
    (q + 10) * 10 + (r + 10)
}
""")
    assert run(tmp_path, files, passing, namespace) == 79


def test_comptime_div_rem_agrees_with_runtime(tmp_path):
    # the comptime folder uses the same truncating semantics, so a folded constant
    # matches what the runtime would compute.
    _, passing, namespace, files = build(tmp_path,
        "main* = () i32 { comptime((0 - 7) / 2 + 10) * 10 + comptime((0 - 7) % 2 + 10) }")
    c = emit_c(files, passing, namespace)
    assert "(7 * 10)" in c and "9)" in c                 # folded: (-3+10)=7, (-1+10)=9
    assert run(tmp_path, files, passing, namespace) == 79


def test_div_by_zero_at_comptime_is_an_error(tmp_path):
    import pytest
    from zen.comptime import ComptimeErr
    with pytest.raises(ComptimeErr, match="division by zero"):
        build(tmp_path, "main* = () i32 { comptime(1 / 0) }")
