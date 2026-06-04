"""Goal Arc 3 (Slice 1) — generic DATA structures RUN via backend monomorphization.

genc has no type parameters, so a `Box<T>: { v: T }` is a DGenStruct template that emits no C of its
own. The monomorphize pass (genModule's pass 0) discovers each concrete `Box<i32>` used in a typed
position and emits a specialized C struct `Box_i32` with `T` substituted, mangling the name; the
generic struct literal `Box<i32>{…}` carries that mangled name. End-to-end through the self-hosted
toolchain: source -> parse -> resolve -> genModule -> C -> compile -> run.
"""
import pytest

from _selfhost import run_value, emit_c_for, check_errors


def test_generic_struct_runs(tmp_path):
    src = ("Box<T>: { v: T }\n"
           "get* = (b: Box<i32>) i32 { b.v }\n"
           "test* = () i32 { get(Box<i32>{ v: 42 }) }")
    run_value(tmp_path, src, 42)


def test_monomorphized_name_is_emitted(tmp_path):
    # the concrete struct + its mangled name appear in the emitted C; the bare `Box`/`T` do not.
    c = emit_c_for(tmp_path, "Box<T>: { v: T }\nget* = (b: Box<i32>) i32 { b.v }")
    assert "struct Box_i32 { int32_t v; }" in c
    assert "Box_i32 b" in c
    assert " T " not in c                        # the type param never leaks into C


def test_generic_struct_extra_concrete_field(tmp_path):
    # a field whose type is NOT the type param stays as-is under substitution
    run_value(tmp_path,
        "W<T>: { a: T, b: i32 }\n"
        "f* = (w: W<i32>) i32 { w.a + w.b }\n"
        "test* = () i32 { f(W<i32>{ a: 40, b: 2 }) }", 42)


def test_two_type_params(tmp_path):
    run_value(tmp_path,
        "Pair<A, B>: { x: A, y: B }\n"
        "f* = (p: Pair<i32, i32>) i32 { p.x + p.y }\n"
        "test* = () i32 { f(Pair<i32, i32>{ x: 20, y: 22 }) }", 42)


def test_two_distinct_instantiations(tmp_path):
    # Box<i32> and Box<u8> each monomorphize to their own struct (and uses of one type dedupe).
    src = ("B<T>: { v: T }\n"
           "gi* = (b: B<i32>) i32 { b.v }\n"
           "gu* = (b: B<u8>) i32 { b.v }\n"
           "test* = () i32 { gi(B<i32>{ v: 40 }) + gu(B<u8>{ v: 2 }) }")
    c = emit_c_for(tmp_path, src)
    assert "struct B_i32 { int32_t v; }" in c
    assert "struct B_u8 { uint8_t v; }" in c
    run_value(tmp_path, src, 42)


def test_plain_struct_still_works(tmp_path):
    # a non-generic struct literal is unaffected by the monomorphize pass
    run_value(tmp_path, "P*: { x: i32, y: i32 }\ntest* = () i32 { P{ x: 19, y: 23 }.x + P{ x: 19, y: 23 }.y }", 42)


def test_comparison_not_mistaken_for_generic(tmp_path):
    # `a < b` in expression position must still parse as a comparison, not a generic literal
    run_value(tmp_path, "test* = () i32 { x := 5\n (x < 9).match({ true => 42, false => 0 }) }", 42)


# Slice 2 — generic ENUMs. `Opt<T>: Some(T) | None` monomorphizes to `Opt_i32` (tag + union with the
# substituted payload). A bare constructor `.Some(5)` is stamped with the monomorphized name via the
# expected type threaded from the callee's parameter.
def test_generic_enum_some(tmp_path):
    run_value(tmp_path,
        "Opt<T>: Some(T) | None\n"
        "f* = (o: Opt<i32>) i32 { o.match({ .Some(x) => x, .None => 0 }) }\n"
        "test* = () i32 { f(.Some(42)) }", 42)


def test_generic_enum_none(tmp_path):
    run_value(tmp_path,
        "Opt<T>: Some(T) | None\n"
        "f* = (o: Opt<i32>) i32 { o.match({ .Some(x) => x, .None => 99 }) }\n"
        "test* = () i32 { f(.None) }", 99)


def test_generic_enum_emits_monomorphized_tagged_union(tmp_path):
    c = emit_c_for(tmp_path, "Opt<T>: Some(T) | None\nf* = (o: Opt<i32>) i32 { o.match({ .Some(x) => x, .None => 0 }) }")
    assert "struct Opt_i32 { int32_t tag; union { int32_t Some; } u; }" in c
    assert "Opt_i32_Some" in c


def test_two_distinct_enum_instantiations(tmp_path):
    src = ("Opt<T>: Some(T) | None\n"
           "gi* = (o: Opt<i32>) i32 { o.match({ .Some(x) => x, .None => 0 }) }\n"
           "gu* = (o: Opt<u8>) i32 { o.match({ .Some(x) => x, .None => 0 }) }\n"
           "test* = () i32 { gi(.Some(40)) + gu(.Some(2)) }")
    c = emit_c_for(tmp_path, src)
    assert "struct Opt_i32" in c and "struct Opt_u8" in c
    run_value(tmp_path, src, 42)


def test_plain_enum_still_works(tmp_path):
    # a non-generic enum + bare constructor is unaffected
    run_value(tmp_path,
        "Sh*: Circle(i32) | Square(i32)\n"
        "area* = (s: Sh) i32 { s.match({ .Circle(r) => r, .Square(w) => w * w }) }\n"
        "test* = () i32 { area(.Square(6)) + area(.Circle(6)) }", 42)


# Nested generics: an instance's substituted fields/payloads may name FURTHER instances, which must
# also be discovered + substituted (transitive monomorphization, with toposort accounting for a
# by-value generic field).
def test_nested_generic_field(tmp_path):
    c = emit_c_for(tmp_path, "Inner<T>: { v: T }\nOuter<T>: { i: Inner<T> }\nf* = (o: Outer<i32>) i32 { o.i.v }")
    assert "struct Inner_i32 { int32_t v; }" in c     # the nested instance is emitted
    assert "Inner_i32 i;" in c                          # and the field type is substituted (not Inner_T)


def test_nested_generic_runs(tmp_path):
    run_value(tmp_path,
        "Inner<T>: { v: T }\nOuter<T>: { i: Inner<T> }\n"
        "get* = (o: Outer<i32>) i32 { o.i.v }\n"
        "test* = () i32 { get(Outer<i32>{ i: Inner<i32>{ v: 42 } }) }", 42)


def test_generic_enum_of_generic_struct_runs(tmp_path):
    # Opt<Box<i32>> -> the enum AND the Box<i32> it wraps both monomorphize
    run_value(tmp_path,
        "Box<T>: { v: T }\nOpt<T>: Some(T) | None\n"
        "f* = (o: Opt<Box<i32>>) i32 { o.match({ .Some(b) => b.v, .None => 0 }) }\n"
        "test* = () i32 { f(.Some(Box<i32>{ v: 42 })) }", 42)


def test_generic_payload_in_plain_enum(tmp_path):
    # a NON-generic enum whose variant payload is a generic instance — discovered via the payload scan
    c = emit_c_for(tmp_path, "Box<T>: { v: T }\nWrap*: Has(Box<i32>) | Nil\nf* = (w: Wrap) i32 { w.match({ .Has(b) => b.v, .Nil => 0 }) }")
    assert "struct Box_i32 { int32_t v; }" in c


# Literal-only discovery: a generic struct used ONLY via a literal in an expression (no typed
# param/return naming it) is still discovered + emitted — the monomorphize pass walks fn bodies for
# struct literals carrying type args, not just signatures.
def test_literal_only_let(tmp_path):
    c = emit_c_for(tmp_path, "Box<T>: { v: T }\ntest* = () i32 { b := Box<i32>{ v: 42 }\n b.v }")
    assert "struct Box_i32 { int32_t v; }" in c
    run_value(tmp_path, "Box<T>: { v: T }\ntest* = () i32 { b := Box<i32>{ v: 42 }\n b.v }", 42)


def test_literal_only_inline(tmp_path):
    run_value(tmp_path, "Box<T>: { v: T }\ntest* = () i32 { Box<i32>{ v: 20 }.v + Box<i32>{ v: 22 }.v }", 42)


def test_literal_in_match_arm(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\ntest* = () i32 { (3 < 4).match({ true => Box<i32>{ v: 42 }.v, false => 0 }) }", 42)


# Generic FUNCTIONS (Slice 3, consumer subset): a function with type params `get<T>` is inlined at
# each call (like an FnT template), so `T` erases — no standalone `get` emitted, no `Box_T` leak.
# Handles functions that CONSUME generic values (read fields, return T, T-typed locals).
def test_generic_consumer_fn_runs(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\nget<T> = (b: Box<T>) i32 { b.v }\n"
        "test* = () i32 { get(Box<i32>{ v: 42 }) }", 42)


def test_generic_fn_at_two_types(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\nget<T> = (b: Box<T>) i32 { b.v }\n"
        "test* = () i32 { get(Box<i32>{ v: 40 }) + get(Box<u8>{ v: 2 }) }", 42)


def test_generic_fn_returns_t(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\nfetch<T> = (b: Box<T>) T { b.v }\n"
        "test* = () i32 { fetch(Box<i32>{ v: 42 }) }", 42)


def test_generic_fn_t_typed_local(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\ndbl<T> = (b: Box<T>) i32 { x := b.v\n x + x }\n"
        "test* = () i32 { dbl(Box<i32>{ v: 21 }) }", 42)


def test_generic_fn_not_emitted_standalone(tmp_path):
    # the template itself is inlined, never emitted -> no `int32_t get(` and no Box_T leak
    c = emit_c_for(tmp_path, "Box<T>: { v: T }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 { get(Box<i32>{ v: 1 }) }")
    assert "Box_T" not in c
    assert "get(" not in c


# Generic CONSTRUCTORS (Slice 3b): a generic fn that builds a generic value `wrap<T> -> Box<T>` runs.
# Inlining substitutes the type param T in the body's types (Box<T> -> Box_i32) using type args
# inferred from the call's arguments. NOTE: T is pinned by a CONCRETE-typed arg (a struct, or a
# numeric literal taken as i32) — a T determined solely by a polymorphic literal defaults to i32.
def test_generic_constructor_runs(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>{ v: x } }\n"
        "g* = (b: Box<i32>) i32 { b.v }\ntest* = () i32 { g(wrap(42)) }", 42)


def test_generic_constructor_t_from_struct_arg(tmp_path):
    run_value(tmp_path,
        "Box<T>: { v: T }\nrewrap<T> = (b: Box<T>) Box<T> { Box<T>{ v: b.v } }\n"
        "g* = (b: Box<i32>) i32 { b.v }\ntest* = () i32 { g(rewrap(Box<i32>{ v: 42 })) }", 42)


def test_generic_constructor_two_type_params(tmp_path):
    run_value(tmp_path,
        "Pair<A, B>: { x: A, y: B }\nmk<A, B> = (p: A, q: B) Pair<A, B> { Pair<A, B>{ x: p, y: q } }\n"
        "f* = (pr: Pair<i32, i32>) i32 { pr.x + pr.y }\ntest* = () i32 { f(mk(20, 22)) }", 42)


def test_generic_constructor_substitutes_in_emitted_c(tmp_path):
    c = emit_c_for(tmp_path,
        "Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>{ v: x } }\n"
        "g* = (b: Box<i32>) i32 { b.v }\ntest* = () i32 { g(wrap(7)) }")
    assert "(Box_i32){" in c        # the body's Box<T> was substituted to Box_i32, not Box_T
    assert "Box_T" not in c


# Integration: the whole generic story in one pipeline — a generic struct `Pair<A,B>`, generic
# constructors (mkpair, and swap which REORDERS the type params -> Pair<B,A>), and generic consumers
# (fst/snd), all monomorphizing together. Proves generic data structures + functions run end-to-end.
def test_generic_pipeline_end_to_end(tmp_path):
    src = ("Pair<A, B>: { fst: A, snd: B }\n"
           "mkpair<A, B> = (a: A, b: B) Pair<A, B> { Pair<A, B>{ fst: a, snd: b } }\n"
           "fst<A, B> = (p: Pair<A, B>) A { p.fst }\n"
           "snd<A, B> = (p: Pair<A, B>) B { p.snd }\n"
           "swap<A, B> = (p: Pair<A, B>) Pair<B, A> { Pair<B, A>{ fst: p.snd, snd: p.fst } }\n"
           "useSwap* = (p: Pair<i32, i32>) i32 { fst(p) * 10 + snd(p) }\n"
           "test* = () i32 { useSwap(swap(mkpair(2, 4))) }")     # swap(2,4)->(4,2) -> 4*10+2 = 42
    assert "struct Pair_i32_i32" in emit_c_for(tmp_path, src)
    run_value(tmp_path, src, 42)


# Nested generic LITERALS `Box<Box<i32>>` — both as a type and a literal. (An earlier audit flagged
# the `>>` token as a possible gap; it isn't — the parser handles the doubled angle bracket.)
def test_nested_generic_literal_runs(tmp_path):
    c = emit_c_for(tmp_path,
        "Box<T>: { v: T }\nf* = (b: Box<Box<i32>>) i32 { b.v.v }\n"
        "test* = () i32 { f(Box<Box<i32>>{ v: Box<i32>{ v: 42 } }) }")
    assert "struct Box_Box_i32" in c and "struct Box_i32" in c
    run_value(tmp_path,
        "Box<T>: { v: T }\nf* = (b: Box<Box<i32>>) i32 { b.v.v }\n"
        "test* = () i32 { f(Box<Box<i32>>{ v: Box<i32>{ v: 42 } }) }", 42)


# Checker correctness on generic args (bug-hunt #12/#13): the self-hosted checker must ACCEPT a
# generic literal / bare constructor passed where a generic type is expected (its codegen runs it),
# and still REJECT a mismatched instance. (check_errors == 0 means accepted.)
def test_checker_accepts_generic_struct_literal_arg(tmp_path):
    assert check_errors(tmp_path, "Box<T>: { v: T }\ng* = (b: Box<i32>) i32 { b.v }\ntest* = () i32 { g(Box<i32>{ v: 42 }) }") == 0

def test_checker_accepts_bare_ctor_to_generic_enum(tmp_path):
    assert check_errors(tmp_path, "E<T>: A(T)\nf* = (o: E<i32>) i32 { o.match({ .A(x)=>x }) }\ntest* = () i32 { f(.A(42)) }") == 0

def test_checker_rejects_mismatched_generic_arg(tmp_path):
    assert check_errors(tmp_path, "Box<T>: { v: T }\ng* = (b: Box<i32>) i32 { b.v }\ntest* = () i32 { g(Box<u8>{ v: 1 }) }") >= 1
