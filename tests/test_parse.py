"""std.parse — a recursive-descent parser written IN zen. It pulls tokens from the
lexer's pure positional scan() and builds genc's Expr AST (a heap tree of Ptr<Expr>
nodes through an explicit allocator) — the same AST genc lowers, so the front and back
ends meet. This first cut parses arithmetic (integers, + - * /, parens) with the usual
precedence; eval() interprets the tree, so each test is `eval_str(<src>) == <value>`,
computed entirely in zen.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def eval_str(tmp_path, expr):
    src = ('{ Malloc } = std.alloc\n{ eval_str } = std.parse\n'
           'main* = () i32 { m := Malloc { _: 0 }\n addr(m).eval_str("%s") }\n' % expr)
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


@pytest.mark.parametrize("expr,want", [
    ("(1 + 2) * 3", 9),       # parens override precedence
    ("1 + 2 * 3", 7),         # * binds tighter than +
    ("10 - 3 - 2", 5),        # - is left-associative
    ("20 / 4 / 5", 1),        # / is left-associative
    ("2 * (3 + 4) - 1", 13),  # a mix
    ("100", 100),             # a multi-digit atom
    ("((1+1))*((2+2))", 8),   # nested parens
])
def test_eval_arithmetic(tmp_path, expr, want):
    assert eval_str(tmp_path, expr) == want
