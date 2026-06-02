"""Char literals — `'a'` is sugar for its byte value, so it reuses the integer-literal
path entirely (same typing, same comptime folding). They exist so byte-level code (the
lexer especially) reads `b == ':'` instead of `b == 58`."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def run(tmp_path, src):
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


def test_char_is_its_byte_value(tmp_path):
    assert run(tmp_path, "main* = () i32 { 'A' }") == 65
    assert run(tmp_path, "main* = () i32 { '0' }") == 48


def test_char_escapes(tmp_path):
    # \n=10 \t=9 \\=92 \0=0 — and a sum to check several at once: 10+9+92 = 111
    assert run(tmp_path, "main* = () i32 { '\\n' }") == 10
    assert run(tmp_path, "main* = () i32 { '\\\\' }") == 92
    assert run(tmp_path, "main* = () i32 { '\\n' + '\\t' + '\\\\' }") == 111


def test_char_adapts_to_u8_like_an_int_literal(tmp_path):
    # a char compares against a u8 with no cast, exactly as a bare int literal would.
    assert run(tmp_path, """
is_digit = (b: u8) bool { (b >= '0') && (b <= '9') }
main* = () i32 { is_digit('7').match { true => 1, false => 0 } }
""") == 1


def test_char_folds_at_comptime(tmp_path):
    # used where a comptime value is required (a fixed-size context via @): folds like an int.
    assert run(tmp_path, "main* = () i32 { ('Z' - 'A') }") == 25
