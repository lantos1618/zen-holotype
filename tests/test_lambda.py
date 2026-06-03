"""Phase 1 — first-class lambdas in the self-hosted toolchain.

Increment A (this file's current scope): the parser accepts lambda values `(a, x) { body }`
and tells them apart from parenthesized expressions (the trailing `{` decides). Proven via
std.genc.gen_sexpr, which renders a parsed lambda as `(lambda <names>)`. Later increments add
checking (against the FnT it's passed to) and inline lowering so a lambda actually RUNS.
"""
import pytest

from _selfhost import sexpr_of as _sexpr, run_value


@pytest.mark.parametrize("expr,want", [
    # slice literals `[a, b, c]` now parse in expression position (Phase 2)
    ("[1, 2, 3]",              "?"),     # gen_sexpr renders a SliceLit as `?` (no dedicated form)
    ("f([1, 2], x)",           "(f ? x)"),
])
def test_slice_literal_parses(tmp_path, expr, want):
    assert _sexpr(tmp_path, expr) == want


@pytest.mark.parametrize("expr,want", [
    ("(n) { n + 1 }",          "(lambda n)"),
    ("(acc, x) { acc + x }",   "(lambda acc x)"),
    ("(a, b, c) { a }",        "(lambda a b c)"),
    ("() { 42 }",              "(lambda)"),
    # a lambda as a call argument — the real usage (higher-order calls like map/fold)
    ("map(xs, (n) { n * 2 })", "(map xs (lambda n))"),
    ("fold(xs, 0, (a, x) { a + x })", "(fold xs 0 (lambda a x))"),
])
def test_lambda_parses(tmp_path, expr, want):
    assert _sexpr(tmp_path, expr) == want


@pytest.mark.parametrize("expr,want", [
    # a parenthesized expression must NOT be mistaken for a lambda (no trailing brace)
    ("(a + b) * c", "(* (+ a b) c)"),
    ("(x)",         "x"),
    ("(a, b)",      None),     # a bare paren-pair with no body isn't a lambda; just parses the first
])
def test_parens_not_mistaken_for_lambda(tmp_path, expr, want):
    out = _sexpr(tmp_path, expr)
    if want is not None:
        assert out == want
    assert "lambda" not in out


# ── lambdas RUN: a function with a function-type parameter is an inline template; the lambda
#    passed for it is spliced at the call site. run_value compiles each whole module through the
#    self-hosted toolchain, then compiles + runs the emitted C and checks test().
@pytest.mark.parametrize("prog,want", [
    # a lambda passed to a template, called once
    ("apply* = (f: (i32) i32, x: i32) i32 { f(x) }\n"
     "test* = () i32 { apply((n) { n + 1 }, 5) }", 6),
    # a CAPTURING lambda — `base` is a local at the call site, resolved at the splice point
    ("apply* = (f: (i32) i32, x: i32) i32 { f(x) }\n"
     "test* = () i32 { base := 100\n apply((n) { n + base }, 5) }", 105),
    # the FnT parameter called more than once
    ("twice* = (f: (i32) i32, x: i32) i32 { f(f(x)) }\n"
     "test* = () i32 { twice((n) { n * 2 }, 3) }", 12),
    # two different lambdas to the same template
    ("apply* = (f: (i32) i32, x: i32) i32 { f(x) }\n"
     "test* = () i32 { apply((n) { n + 1 }, 10) + apply((n) { n * n }, 4) }", 27),
    # a multi-statement template body, with the lambda spliced inside it
    ("withtmp* = (f: (i32) i32, x: i32) i32 { y := x + 1\n f(y) }\n"
     "test* = () i32 { withtmp((n) { n * 10 }, 4) }", 50),
    # the iconic one: fold over a slice literal with a closure (template body has a .loop
    # that calls the FnT param; the lambda splices inside it)
    ("fold* = (xs: [i32], init: i32, f: (i32, i32) i32) i32 {\n"
     "    acc := init\n    xs.loop((h, i, x) { acc = f(acc, x) })\n    acc\n}\n"
     "test* = () i32 { fold([1, 2, 3, 4], 0, (acc, x) { acc + x }) }", 10),
    # fold with a different combiner (product)
    ("fold* = (xs: [i32], init: i32, f: (i32, i32) i32) i32 {\n"
     "    acc := init\n    xs.loop((h, i, x) { acc = f(acc, x) })\n    acc\n}\n"
     "test* = () i32 { fold([1, 2, 3, 4], 1, (acc, x) { acc * x }) }", 24),
])
def test_lambda_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


# Generic templates: a function with a type parameter `<T>` AND an FnT parameter. Because a
# template is inlined per call site and types re-infer against the concrete args (std.check's
# post-inline re-resolve), `<T>` erases — the generic higher-order fn RUNS, monomorphized by use.
@pytest.mark.parametrize("prog,want", [
    ("fold*<T> = (xs: [T], init: T, f: (T, T) T) T {\n"
     "    acc := init\n    xs.loop((h, i, x) { acc = f(acc, x) })\n    acc\n}\n"
     "test* = () i32 { fold([3, 4, 5], 0, (a, x) { a + x }) }", 12),
    ("fold*<T> = (xs: [T], init: T, f: (T, T) T) T {\n"
     "    acc := init\n    xs.loop((h, i, x) { acc = f(acc, x) })\n    acc\n}\n"
     "test* = () i32 { fold([1, 2, 3, 4], 1, (a, x) { a * x }) }", 24),
    ("apply*<T> = (f: (T) T, x: T) T { f(x) }\n"
     "test* = () i32 { apply((n) { n + 100 }, 5) }", 105),
])
def test_generic_template_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)
