"""Phase 2 — surface operators (`!=`, prefix `-`/`!`), block comments, hex literals, and
multi-statement match arms — each compiled + run through the self-hosted toolchain.
"""
import pytest

from _selfhost import run_value


@pytest.mark.parametrize("prog,want", [
    # != comparison (yields bool, matched to an int here)
    ("test* = () i32 { (5 != 3).match({ true => 1, false => 0 }) }", 1),
    ("test* = () i32 { (5 != 5).match({ true => 1, false => 0 }) }", 0),
    ("test* = () i32 { (7 != 7).match({ true => 1, false => 0 }) + (1 != 2).match({ true => 10, false => 0 }) }", 10),
    # prefix negation, lowered as (0 - x)
    ("test* = () i32 { -5 + 8 }", 3),
    ("test* = () i32 { -3 * 4 }", -12),          # unary binds tighter than *
    ("test* = () i32 { x := 5\n 0 - -x }", 5),   # binary minus then unary minus
    # negation applied to a call result
    ("neg* = (n: i32) i32 { 0 - n }\ntest* = () i32 { -neg(7) }", 7),
])
def test_operator_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # a multi-statement match arm `{ … }` (a genc Block / statement-expression)
    ("test* = () i32 { (3 < 5).match({ true => { x := 10\n y := 20\n x + y }, false => 0 }) }", 30),
    # one single-expr arm, one block arm
    ("classify* = (n: i32) i32 { (n < 0).match({ true => { 0 - n }, false => { d := n * 2\n d + 1 } }) }\n"
     "test* = () i32 { classify(5) }", 11),
    # a variant arm whose block uses the payload binding `r`
    ("Shape*: Circle(i32) | Square(i32)\n"
     "area* = (s: Shape) i32 { s.match({ .Circle(r) => { rr := r * r\n rr * 3 }, .Square(w) => w * w }) }\n"
     "test* = () i32 { area(.Circle(2)) }", 12),
])
def test_multi_statement_match_arm_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # prefix `!` (logical not), lowered as (x ? false : true)
    ("test* = () i32 { (!(5 < 3)).match({ true => 1, false => 0 }) }", 1),
    ("test* = () i32 { (!(5 < 8)).match({ true => 1, false => 0 }) }", 0),
    ("test* = () i32 { ok := 3 != 4\n (!ok).match({ true => 1, false => 0 }) }", 0),
])
def test_logical_not_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # /* */ block comments (single and multi-line, inline)
    ("test* = () i32 { /* a\n block comment */ 40 + 2 }", 42),
    ("test* = () i32 { x := 10 /* inline */ + 5\n x /* trailing */ }", 15),
])
def test_block_comments(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    ("test* = () i32 { 0x2a }", 42),
    ("test* = () i32 { 0xFF }", 255),
    ("test* = () i32 { 0x10 + 0x0a }", 26),
    ("test* = () i32 { 255 }", 255),     # decimal still works
])
def test_hex_literals(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # @emit(expr) is a comptime decl generator; the self-hosted frontend has no comptime
    # evaluator, so it PARSES the form and skips it (surrounding decls are unaffected).
    ("inc* = (n: i32) i32 { n + 1 }\n@emit(gen(reflect(Point)))\ntest* = () i32 { inc(41) }", 42),
    ("@emit(foo(bar))\ntest* = () i32 { 7 }", 7),
])
def test_emit_form_parses_and_is_skipped(tmp_path, prog, want):
    run_value(tmp_path, prog, want)
