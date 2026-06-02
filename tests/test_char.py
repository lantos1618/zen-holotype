"""Char literals — `'a'` is sugar for its byte value, so it reuses the integer-literal
path entirely (same typing, same comptime folding). They exist so byte-level code (the
lexer especially) reads `b == ':'` instead of `b == 58`."""


def test_char_is_its_byte_value(compile_main):
    assert compile_main("main* = () i32 { 'A' }") == 65
    assert compile_main("main* = () i32 { '0' }") == 48


def test_char_escapes(compile_main):
    # \n=10 \t=9 \\=92 \0=0 — and a sum to check several at once: 10+9+92 = 111
    assert compile_main("main* = () i32 { '\\n' }") == 10
    assert compile_main("main* = () i32 { '\\\\' }") == 92
    assert compile_main("main* = () i32 { '\\n' + '\\t' + '\\\\' }") == 111


def test_char_adapts_to_u8_like_an_int_literal(compile_main):
    # a char compares against a u8 with no cast, exactly as a bare int literal would.
    assert compile_main("""
is_digit = (b: u8) bool { (b >= '0') && (b <= '9') }
main* = () i32 { is_digit('7').match { true => 1, false => 0 } }
""") == 1


def test_char_folds_at_comptime(compile_main):
    # used where a comptime value is required (a fixed-size context via @): folds like an int.
    assert compile_main("main* = () i32 { ('Z' - 'A') }") == 25
