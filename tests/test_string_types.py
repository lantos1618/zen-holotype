"""Explicit string types — text / Cstr lifetime enforcement (STRING_TYPES.md).

`text` = immortal literal; `Cstr` = mortal cstr/finish result; `str` = borrowed view.
Lattice: text <: {str, Cstr}; Cstr <: str; but Cstr/str do NOT fit text. So a heap/arena
string (Cstr) cannot silently escape into an immortal (`text`) position.
"""
import _oracle as o

TEXT_FN = "foo = (s: text) i32 { 0 }\n"
STR_FN = "g = (s: str) i32 { 0 }\n"


def test_literal_into_text_accepts():
    # a string literal IS text — usable where an immortal string is required
    assert o.verdict(TEXT_FN + 'main = () i32 { foo("ok") }') == "accept"


def test_cstr_into_text_rejects():
    # cstr(...) is a Cstr (mortal) — must NOT be accepted where text is required
    assert o.verdict_kind(TEXT_FN + "main = () i32 { foo(cstr(null_ptr())) }") == "arg-type"


def test_borrowed_str_into_text_rejects():
    # a borrowed str param flowing into a text param is rejected too
    src = "bar = (x: str) i32 { foo(x) }\n" + TEXT_FN + 'main = () i32 { bar("hi") }'
    assert o.verdict_kind(src) == "arg-type"


def test_text_into_str_accepts():
    # text <: str — a literal works where a borrowed str is expected
    assert o.verdict(STR_FN + 'main = () i32 { g("ok") }') == "accept"


def test_cstr_into_str_accepts():
    # Cstr <: str — a finished pointer is a valid const char* to read
    assert o.verdict(STR_FN + "main = () i32 { g(cstr(null_ptr())) }") == "accept"
