"""T8 + F2: front-end — tree-sitter CST -> AST, and located parse errors."""
import pytest

from zen.ast import (Dir, Prim, PrimT, NameT, PtrT, Struct, Fn,
                          Import, Var, Bin, Field, Call, StructLit, MethodCall, Match)
from zen.parser import parse


def only(decls, kind):
    return next(d for d in decls if isinstance(d, kind))


def test_parse_struct():
    f = parse("Vec*: { len: i32, cap: i32 }", "core.vec")
    s = only(f.decls, Struct)
    assert s.name == "Vec" and s.pub
    assert [(fl.name, fl.type) for fl in s.fields] == \
           [("len", PrimT(Prim.I32)), ("cap", PrimT(Prim.I32))]


def test_parse_pointer_directions():
    f = parse("g* = (a: Ptr<Vec>, b: MutPtr<Vec>, c: RawPtr<Vec>) i32 { 0 }", "m")
    fn = only(f.decls, Fn)
    dirs = [p.type.dir for p in fn.params]
    assert dirs == [Dir.READ, Dir.MUT, Dir.RAW]
    assert all(isinstance(p.type, PtrT) for p in fn.params)


def test_parse_option_named_type():
    f = parse("g* = (a: Option<Ptr<Vec>>) i32 { 0 }", "m")
    t = only(f.decls, Fn).params[0].type
    assert isinstance(t, NameT) and t.path == "Option"
    assert isinstance(t.args[0], PtrT)


def test_parse_import():
    f = parse("{ Vec } = core.vec\n", "m")
    imp = f.imports[0]
    assert isinstance(imp, Import)
    assert imp.names == ["Vec"] and imp.module == "core.vec"


def test_parse_call_and_field_and_binary():
    f = parse("area* = (v: Ptr<Vec>) i32 { len(v) * v.cap }", "m")
    body = only(f.decls, Fn).body[-1]
    assert isinstance(body, Bin) and body.op == "*"
    assert isinstance(body.l, Call) and body.l.callee == "len"
    assert isinstance(body.r, Field) and body.r.name == "cap"


def test_parse_struct_literal_and_addr():
    f = parse("m* = () i32 { area(addr(Vec { len: 3, cap: 4 })) }", "m")
    call = only(f.decls, Fn).body[-1]
    assert isinstance(call, Call) and call.callee == "area"
    addr = call.args[0]
    assert isinstance(addr, Call) and addr.callee == "addr"
    assert isinstance(addr.args[0], StructLit)


def test_method_call_is_just_a_call_on_a_field_access():
    # a method call has no special grammar rule — it's call-of-field-access.
    f = parse('build* = (b: Ptr<Vec>) i32 { b.add(Vec { len: 1, cap: 2 }) }', "m")
    body = only(f.decls, Fn).body[-1]
    assert isinstance(body, MethodCall)
    assert body.method == "add" and isinstance(body.recv, Var)


# ── F2: parse errors carry ns:line:col ──────────────────────────────────────
def test_parse_error_is_located():
    with pytest.raises(SyntaxError) as ei:
        parse("Vec*: { len: i32, cap: }", "core.vec")   # missing field type
    msg = str(ei.value)
    assert msg.startswith("core.vec:")
    assert "parse error" in msg


def test_parse_error_reports_line_number():
    src = "a* = () i32 { 0 }\nVec*: { x: }"              # error on line 2 (field with no type)
    with pytest.raises(SyntaxError) as ei:
        parse(src, "m")
    assert str(ei.value).startswith("m:2:")


# ── A bodyless function is a foreign (C) binding — no `extern` keyword ───────
def test_bodyless_function_is_a_foreign_binding():
    fn = only(parse("malloc = (n: i64) RawPtr<u8>", "m").decls, Fn)
    assert fn.extern is True and fn.body is None
    assert fn.name == "malloc" and isinstance(fn.ret, PtrT)


def test_bodyless_function_without_ret_is_void():
    fn = only(parse("flush = (p: RawPtr<u8>)", "m").decls, Fn)
    assert fn.extern is True and fn.ret == PrimT(Prim.VOID)


def test_function_with_body_is_not_extern():
    fn = only(parse("area* = (v: i32) i32 { v }", "m").decls, Fn)
    assert fn.extern is False and fn.body is not None


def test_extern_keyword_is_gone():
    # the old `extern name = (...)` syntax no longer parses
    with pytest.raises(SyntaxError):
        parse("extern malloc = (n: i64) RawPtr<u8>", "m")


# ── match is postfix `subj.match { … }` — no `match` prefix keyword ──────────
def test_postfix_match_on_identifier():
    fn = only(parse("f = (s: i32) i32 { s.match { 0 => 1, _ => 2 } }", "m").decls, Fn)
    m = fn.body[-1]
    assert isinstance(m, Match) and isinstance(m.subject, Var) and m.subject.name == "s"


def test_postfix_match_on_parenthesized():
    fn = only(parse("f = (n: i32) i32 { (n < 0).match { true => 0, false => 1 } }", "m").decls, Fn)
    m = fn.body[-1]
    assert isinstance(m, Match) and isinstance(m.subject, Bin)


def test_postfix_match_chains_on_a_call():
    # subject-first reads well in chains: the match applies to the whole `head(xs)`
    fn = only(parse("f = (xs: [i32]) i32 { head(xs).match { 0 => 1, _ => 2 } }", "m").decls, Fn)
    assert isinstance(fn.body[-1].subject, Call)


def test_match_prefix_keyword_is_gone():
    with pytest.raises(SyntaxError):
        parse("f = (s: i32) i32 { match s { 0 => 1, _ => 2 } }", "m")


def test_statement_starting_with_paren_is_not_glued():
    # a `(`-led statement after an expression statement is its own statement,
    # not absorbed as a call's arguments (the call `(` must be glued).
    fn = only(parse("f = (n: i32) i32 { g(n)\n(n < 0).match { true => 0, false => 1 } }",
                    "m").decls, Fn)
    assert isinstance(fn.body[0], Call)            # g(n)
    assert isinstance(fn.body[1], Match)           # a separate statement
