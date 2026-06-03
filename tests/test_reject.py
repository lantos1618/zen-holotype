"""Phase 6 — reject-parity: the self-hosted checker (check_module) catches errors, not just
accepts valid code. Toward "same accept/reject as the Python frontend".

Each program is run through parse_module -> resolve_module -> check_module; the error count is
the process exit code. Valid programs give 0; the listed bugs give >= 1.

Scope today: call ARITY, arg-TYPE fit (categorical), and RETURN-type category mismatches
(str/bool/struct returned where another category is declared). Numeric->numeric narrowing on
returns is intentionally skipped — int literals are polymorphic and the checker can't track
literal-ness through a Cond, so flagging it would false-reject valid code like `(…) u8 { 10 }`.
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
])
def test_checker_rejects_invalid(tmp_path, src):
    assert _errors(tmp_path, src) >= 1
