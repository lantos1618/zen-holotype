# tests/corpus/match-value

One line per test: the path, then the one-line compiler change that would
break it. Every `.expected` is `./runzen.sh`'s actual stdout, checked by
hand against what Zen specifies before it was pinned.

| test | one-line change that breaks it |
|---|---|
| a_local_binds_the_matched_arms_value | result temporary assigned from the scrutinee slot instead of the taken arm's value (both bindings then print `9`); or arms picked first/last-written instead of by tag |
| an_enum_match_in_value_position | arm payload read as the union tag/whole -- prints small ints (0/2-shaped) in place of 3136/49; or "last variant wins" instead of the matching tag (`Square` sits mid-declaration) |
| a_payload_binder_is_the_variant_value_in_operand_position | binder slot read as the union whole in the multiply/divide: `b*b` becomes tag*payload, `100/m` divides by garbage -- 25/16/9/12 move |
| match_feeds_a_call_argument | call argument reads the scrutinee or wrong arm: stored pair prints `0 5` instead of `40 50`; second half pins left-to-right argument evaluation (r-to-l silently prints 210 via the `_` arm) |
| match_as_an_operand_of_an_operator | unary minus wraps only part of the lowered if/else chain (prints 9/-2/4), or an operator operand reads the scrutinee / wrong arm (-9/-2/4 moves) |
| a_match_inside_a_loop_body | loop-carried accumulator added before the arm selection (11 = raw rows summed) or the result temporary not reassigned per iteration (stale first answer, 200) |

## Notes

- All six programs ran through `./runzen.sh`; expectations are its stdout.
- Deliberate overlap with existing suites is avoided: block-arm matches live
  in `codegen/match_all_block_arms.zen`, statement-position matches and
  binder scoping have their own tests; everything here is a plain-value
  match used as a local / argument / operand, which DESIGN.md § Control flow
  makes the primary form.

## Compiler bugs found

None. Two rejections were hit while drafting and both are CORRECT behaviour,
not bugs:

1. `7.match({ .. })` is rejected ("a float literal needs a digit after the
   `.`") -- a number literal may not be a method receiver, since `7.` lexes
   as a float. Program shows it:
   `println("{}", 7.match({ 7 => 3, _ => 30 }));`
2. `v.get(0).try()` inside `main` returning `Res<i32, AllocError>` is
   rejected ("a None never becomes an Err") -- `Vec.get` yields `Res<T>`
   whose failure could be `None`, and `.try()` refuses to invent an `Err`.
   The read-back must be matched instead, which this lane's tests now do.

TESTS: 6
