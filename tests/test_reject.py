"""Phase 6 — reject-parity: the self-hosted checker (check_module) catches errors, not just
accepts valid code. Toward "same accept/reject as the Python frontend".

Each program is run through parse_module -> resolve_module -> check_module; the error count is
the process exit code. Valid programs give 0; the listed bugs give >= 1.

Scope today: call ARITY, arg-TYPE fit, and RETURN-type mismatches — both CATEGORY (str/bool/
struct where another is declared) AND computed numeric NARROWING (an i64-returning call declared
i32). A polymorphic int LITERAL returned to a numeric type is fine (`(…) u8 { 10 }`); a Cond that
mixes a literal and a typed branch takes the typed branch's type (so `esc_byte` checks clean).
"""
import pytest

from _selfhost import check_errors as _errors


@pytest.mark.parametrize("src", [
    "f* = (n: i32) i32 { n + 1 }",
    "f* = (a: i32, b: i32) bool { a < b }",
    "g* = (n: i32) u8 { 10 }",                       # int literal -> u8 is fine (polymorphic)
    "id* = (s: str) str { s }",
    "Pt*: { x: i32 }\nf* = (p: Pt) i32 { p.x }",
])
def test_checker_accepts_valid(tmp_path, src):
    assert _errors(tmp_path, src) == 0


@pytest.mark.parametrize("src", [
    'f* = (n: i32) i32 { "hi" }',                    # str returned where i32 declared
    "f* = (n: i32) i32 { n < 5 }",                   # bool returned where i32 declared
    "f* = (n: i32) str { n }",                       # i32 returned where str declared
    "f* = (a: i32) i32 { a }\ng* = () i32 { f(1, 2) }",   # arity: f takes 1, called with 2
    "g* = () i64 { 5 }\nf* = () i32 { g() }",             # computed i64 narrowed to i32
])
def test_checker_rejects_invalid(tmp_path, src):
    assert _errors(tmp_path, src) >= 1
