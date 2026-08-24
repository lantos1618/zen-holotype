# struct-basic lane

One line per test: path -- the one-line compiler change that would break it.

- tests/corpus/struct-basic/construction_arguments_bind_by_name_not_by_position/ -- emit the initialiser list from the argument SEQUENCE instead of binding each argument to its named field (positional emission); every field is i64 so nothing but the printed permutation can catch it.
- tests/corpus/struct-basic/default_fills_the_omitted_tail_field/ -- build the initialiser from supplied arguments alone and let C's rest-value zeroing answer for omitted fields; `part 7 0` is plausible output, wrong default.
- tests/corpus/struct-basic/nested_field_read_walks_every_offset/ -- fold a two-level projection back onto the first-level member of the same name (`outer.inner.value` emitted as `outer.value`'s slot); compiles cleanly because both members are i64, prints 40 or 5 instead of 6.
- tests/corpus/struct-basic/nested_default_is_copied_per_construction/ -- lower a construction-typed default to ONE shared sub-object hoisted out of the call; two constructions then alias, and mutating the first moves the second (`9 8 9 2`).
- tests/corpus/struct-basic/struct_returned_by_value_keeps_its_fields/ -- return an inner struct through a pointer into the dead callee frame instead of by value; at -O0 this usually prints correctly, which is why it needs pinning beside struct_return_large.zen.
- tests/corpus/struct-basic/mutable_method_writes_through_the_callers_field/ -- pass a `::` receiver as a copy instead of by reference: callee's read-back still prints the new value, caller's re-read prints the old, nothing traps. Both sides are printed on purpose.
- tests/corpus/struct-basic/copy_carries_every_field_value/ -- copy from the type's DEFAULT initialiser instead of the source's storage; g prints defaults while f reads fine.
- tests/corpus/struct-basic/loop_body_constructs_a_fresh_value_each_pass/ -- hoist the loop body's construction out of the loop (one object reused across passes); per-pass totals drift because the previous pass's written field survives.

## Compiler bugs found

None. All eight programs compiled and ran on the first correct syntax; every
output was checked against hand-computed values before being written to
`main.expected`.

Two things worth noting, neither a bug:

1. An assignment statement inside a single-line function body needs its
   trailing `;` (`grow = (p :: P, k: i64) () { p.n = p.n + k; }`) even though
   the last expression in such a body does not. The diagnostic says exactly
   that ("an assignment is a statement, not a value"), so this is the parser
   working as documented -- just easy to trip over when copying Vec method
   bodies, whose last statements are `Ok(());`.
2. `Range(0, 4).fold(..)` does not exist -- fold is a free overload of `loop`
   (`loop*<R, T, A> = (range, init, body)`, src/std/core/loop/loop_iter.zen),
   not a member of Range, and the receiver-rule diagnostic names that
   correctly. The loop test uses `total ::= 0` outside the loop plus
   `.loop((h, i) {..})` instead.

TESTS: 8
