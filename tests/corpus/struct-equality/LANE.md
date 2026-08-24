# struct-equality lane

`==` on a non-scalar is a call to the type's own `eq` (or the impl-supplied
one), `!=` is that same call negated; floats are scalars for the operator but
carry no `Eq` impl by design. Each test below pins one link of that chain.

- tests/corpus/struct-equality/eq_dispatches_to_the_types_own_eq/ -- op_kind returning Refused or Infix instead of Dispatched for named types (`is_comparison(b.op) && be.scalar(operand)` widened past primitives); or lower_eq_call looking up an impl-supplied `ne` that DESIGN.md says does not exist.
- tests/corpus/struct-equality/every_field_decides_one_pair/ -- emit_eq passing only the first argument whole (write_arg's slot index hardcoded to 0), or any single field skipped in the hand-written eq body; either way score stops being 16.
- tests/corpus/struct-equality/float_field_decides_the_compare/ -- eq lowered bytewise (memcmp) instead of per-field: the -0.0-vs-0.0 line flips to false while every other line stays plausible.
- tests/corpus/struct-equality/nested_eq_recurses_per_level/ -- inner site calling Outer's eq instead of Inner's (site_of resolved from the outer receiver), which loops forever instead of printing three lines.
- tests/corpus/struct-equality/str_field_compares_bytes_not_pointers/ -- str falling back to C `==` on the aggregate (the silent emit match_on_str_literals documents): both lines print true because equal literals pool at one address.
- tests/corpus/struct-equality/operator_and_method_are_one_call/ -- operator path emitting its own inline compare rather than the member call: op_ab/op_ba disagree with call_ab/call_ba and the score moves off 10.
- tests/corpus/struct-equality/defaulted_float_field_participates/ -- initialiser built from arguments alone so defaults fall back to C `{0}` (the field_defaults bug): `same` compares 7.5 against 0.0 and prints false.

## Compiler bug found

**`==` on a union type: sema accepts the impl, codegen refuses the operator.**
Program (rejected):

```zen
Shape = Rect | Dot
Rect = { w*: i64, h*: i64 }
Dot  = { r*: i64 }
Shape.impl(Eq, { eq* = (self: @Self, other: @Self) bool {
    self.match({
        Rect(me) => other.match({ Rect(o) => (me.w == o.w) && (me.h == o.h),
                                  Dot(_)  => false }),
        Dot(me)  => other.match({ Dot(o)  => me.r == o.r,
                                  Rect(_) => false }),
    })
} })
main = (env: Env) Res<i32, AllocError> {
    r = Shape.Rect(Rect(w: 3, h: 4));
    println("{}", r == Shape.Rect(Rect(w: 3, h: 4)));
    Ok(0);
}
```

Sema proves the bound (check_eq -> prove_eq -> members_of finds the impl's
eq, sema_bound.zen:607) and compilation reaches codegen, where four
diagnostics fire: ``codegen does not lower this yet: `comparing values that
are not scalars'``. Root cause is site_of (gen_c_member.zen:392): it matches
Named / Prim / _ and a union falls into `_ => Ok(None)`, so lower_eq_call
gets "no eq fn" and gen_c_op.zen reports the value as uncomparable. Either
site_of should resolve a union's decl (the tag-plus-members compare is well
defined and the impl above shows the demand), or sema should reject
`Shape.impl(Eq, ..)` up front -- today the two halves of the compiler
disagree about whether the program exists. Test not written: encoding the
refusal would pin a bug, and there is no correct output to expect yet.

TESTS: 7
