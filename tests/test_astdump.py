"""astdump — a canonical, deterministic serialization of the parsed AST.

It's the reference a future Zen-written parser will be diffed against. These tests pin
that it is STRUCTURAL (independent of source formatting and of pipeline stage) and STABLE
(same structure -> same dump -> same hash), which is what makes it usable as a parity gate.
"""
import pathlib

from zen.parser import parse
from zen.astdump import dump, ast_hash
from zen.main import cli

_EXAMPLES = pathlib.Path(__file__).parent.parent / "examples"


def test_golden_dump_of_a_function():
    d = dump(parse("main* = () i32 { 42 }", "m"))
    assert d == ("(File ns='m' imports=[] decls=[(Fn name='main' params=[] "
                 "ret=(PrimT prim=I32) body=[(Lit n=42)] pub=True tparams=[] "
                 "bounds={} extern=False)])")


def test_dump_renders_nested_structure():
    d = dump(parse("add* = (x: i32, y: i32) i32 { x + y }", "m"))
    # params, the declared return type, and the body expression all appear structurally
    assert "(Param name='x' type=(PrimT prim=I32))" in d
    assert "ret=(PrimT prim=I32)" in d
    assert "body=[(Bin op='+' l=(Var name='x') r=(Var name='y'))]" in d


def test_dump_is_formatting_invariant():
    # extra whitespace is not structure: same dump AND same hash
    a = parse("add* = (x: i32, y: i32) i32 { x + y }", "m")
    b = parse("add*  =  (x: i32,   y: i32) i32 {   x + y   }", "m")
    assert dump(a) == dump(b)
    assert ast_hash(a) == ast_hash(b)


def test_hash_is_stable_and_distinguishes_structure():
    one = parse("f* = () i32 { 1 }", "m")
    one_again = parse("f* = () i32 { 1 }", "m")
    two = parse("f* = () i32 { 2 }", "m")
    assert ast_hash(one) == ast_hash(one_again)   # deterministic
    assert ast_hash(one) != ast_hash(two)         # a real structural difference shows


def test_struct_and_enum_dump():
    assert "(Struct name='Pt'" in dump(parse("Pt*: { x: i32, y: i32 }", "m"))
    ed = dump(parse("Color*: Red | Green | Blue", "m"))
    assert "(EnumDecl name='Color'" in ed and "(Variant name='Red'" in ed


def test_dump_cli_is_stable(capsys):
    # `zen dump <root>` prints each module's dump + hash, and is byte-identical run-to-run
    cli(["dump", str(_EXAMPLES)])
    first = capsys.readouterr().out
    assert "── main.zen ──" in first and "(Fn name='main'" in first
    cli(["dump", str(_EXAMPLES)])
    assert capsys.readouterr().out == first        # deterministic across invocations
