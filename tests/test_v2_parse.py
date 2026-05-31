"""v2 front end: source → the one-structure AST. Guards the grammar + CST→AST."""
from holotype.v2.parser import parse
from holotype.v2.ast import Decl, Record, Sum, Fn, NamedT, Lit, Bin, Field, Var, Match, Ctor


def by_name(src):
    return {".".join(d.name): d for d in parse(src)}


def test_record_is_a_bag_of_decls():
    d = by_name("Vec = { len: i32, cap: i32 }")["Vec"]
    assert d.bind == "=" and isinstance(d.value, Record)
    fields = {".".join(x.name): x for x in d.value.decls}
    assert fields["len"].type == NamedT(("i32",), ())     # `:` = a requirement, no value
    assert fields["len"].bind is None


def test_impl_is_a_record_at_a_path():
    d = by_name("Circle.Area = { area = () i32 { @self.r } }")["Circle.Area"]
    assert d.name == ("Circle", "Area")                   # dotted decl name
    method = d.value.decls[0]
    assert method.name == ("area",) and isinstance(method.value, Fn)


def test_pub_star_and_bound():
    d = by_name("biggest*<T: Area> = (a: T) i32 { a }")["biggest"]
    assert d.pub is True
    assert d.tparams == (("T", "Area"),)
    assert isinstance(d.value, Fn)


def test_sum_with_pipe_and_payload():
    d = by_name("Tax = Free | Rate : i32")["Tax"]
    assert isinstance(d.value, Sum)
    assert d.value.variants == (("Free", None), ("Rate", NamedT(("i32",), ())))


def test_const_vs_mutable():
    ds = by_name("a : i32 = 0\nb : i32 := 0\nc := 0\nd = 0")
    assert ds["a"].bind == "=" and ds["b"].bind == ":="
    assert ds["c"].bind == ":=" and ds["c"].type is None     # mutable, inferred
    assert ds["d"].bind == "=" and ds["d"].type is None      # const, inferred


def test_postfix_match():
    d = by_name("f = (x: i32) i32 { x.match { 0 => 1, _ => x } }")["f"]
    body = d.value.body[-1]
    assert isinstance(body, Match)
    assert body.arms[0][0] == Lit(0)
    assert body.arms[1][0] == Ctor("_")


def test_nested_method_body():
    d = by_name("g = () i32 { @self.r * @self.r * 3 }")["g"]
    expr = d.value.body[-1]
    assert isinstance(expr, Bin) and expr.op == "*"
    assert isinstance(expr.l, Bin)                          # (@self.r * @self.r) * 3
    assert isinstance(expr.l.l, Field) and expr.l.l.name == "r"


def test_a_local_let_is_a_decl():
    d = by_name("h = () i32 { x := 5\n x }")["h"]
    let_ = d.value.body[0]
    assert isinstance(let_, Decl) and let_.name == ("x",) and let_.bind == ":="
