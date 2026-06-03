"""Phase 1 — first-class lambdas in the self-hosted toolchain.

Increment A (this file's current scope): the parser accepts lambda values `(a, x) { body }`
and tells them apart from parenthesized expressions (the trailing `{` decides). Proven via
std.genc.gen_sexpr, which renders a parsed lambda as `(lambda <names>)`. Later increments add
checking (against the FnT it's passed to) and inline lowering so a lambda actually RUNS.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

_DRIVER = """
{ Malloc } = std.alloc
{ parse } = std.parse
{ gen_sexpr } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(new().gen_sexpr(addr(m).parse("%s")))
    0
}
"""


def _sexpr(tmp_path, expr):
    (tmp_path / "main.zen").write_text(_DRIVER % expr)
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


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
#    passed for it is spliced at the call site. We compile a whole module THROUGH the self-hosted
#    toolchain (parse_module -> resolve_module -> genModule), then compile + run the emitted C.
_MOD_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module } = std.check
{ genModule } = std.genc
{ String, new, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""

_HEAD = "typedef struct { void* ptr; int64_t len; } zslice; "


def _zlit(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _compile_module(tmp_path, prog):
    """Run `prog` through the self-hosted toolchain; return the emitted C."""
    (tmp_path / "main.zen").write_text(_MOD_DRIVER % _zlit(prog))
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


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
    emitted = _compile_module(tmp_path, prog)
    body = emitted[len(_HEAD):] if emitted.startswith(_HEAD) else emitted
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + _HEAD + "\n" + body
                                  + "\nint main(void){ return test() == %d ? 0 : 1; }\n" % want)
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0, f"{prog!r} should give {want}"
