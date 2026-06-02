"""Parser parity (Phase 8 gate): the Zen-written parser (std.parse) must build the same
tree the Python parser (ast.py) does.

Unlike the backend gate (test_parity, which compares the two BACKENDS by result) and the
lexer gate (test_lex_parity), this compares the two PARSERS structurally: each parser's
expression tree is rendered to the SAME backend-neutral prefix s-expression — `(* (+ 1 2)
3)` — and the strings must match. A precedence or associativity disagreement between the
two parsers shows up as a different tree shape. (Arithmetic + identifiers — the subset
std.parse covers.)
"""
import subprocess

import pytest

from zen.ast import Lit, Var, Bin
from zen.parser import parse
from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def py_sexpr(e):
    """Render an ast.py expression as the same prefix s-expr std.genc.gen_sexpr emits."""
    if isinstance(e, Lit):
        return str(e.n)
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Bin):
        return f"({e.op} {py_sexpr(e.l)} {py_sexpr(e.r)})"
    return "?"


def python_parser_sexpr(expr):
    f = parse(f"f* = () i32 {{ {expr} }}", "m")
    return py_sexpr(f.decls[0].body[0])              # the single body expression


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


def zen_parser_sexpr(tmp_path, expr):
    (tmp_path / "main.zen").write_text(_DRIVER % expr)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


@pytest.mark.parametrize("expr", [
    "(1 + 2) * 3",
    "1 + 2 * 3",
    "a - b - c",            # left-assoc
    "x * (y + 1)",
    "10 - 2 * 3 + 1",
    "((1 + 1)) * 2",
])
def test_zen_and_python_parsers_build_the_same_tree(tmp_path, expr):
    assert zen_parser_sexpr(tmp_path, expr) == python_parser_sexpr(expr)
