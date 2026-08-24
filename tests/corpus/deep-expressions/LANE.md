# LANE: deep-expressions

tests/corpus/deep-expressions/twenty_two_levels_of_mixed_operator_precedence -- swap any single precedence level, associativity rule, or the `&&` short-circuit join in gen_c_op/sema_op; also catches a bool-sized join for the match result (arms 7/9 vs truncated 1).
tests/corpus/deep-expressions/twenty_nested_matches_join_through_each_other -- emit one match's scrutinee per arm instead of once per match, mis-number any wildcard sentinel (6NN names the level), or size a join slot by the wrong link.
tests/corpus/deep-expressions/twenty_nested_closures_each_capture_one_deeper -- hoist one closure level's local into a shared frame (chain collapses to 2) or resolve any capture against the defining frame instead of the use site (prints a prefix, not garbage).
tests/corpus/deep-expressions/nested_loop_break_carries_the_inner_value -- route an inner h2.break(..) payload to the outer loop's join slot, let the outer loop keep iterating after an inner break, or drop the None-vs-Ok distinction on the never-broken loop (any of these prints 0/24/40/77/104/120 instead of 124/999).
tests/corpus/deep-expressions/nested_member_chain_threads_types -- resolve any chain link against a neighbouring declaration or reuse one C member offset for two same-named fields at different depths (h0/h1/total all shift).
tests/corpus/deep-expressions/try_chain_surfaces_the_deepest_error -- forward a re-wrapped or zero Err through any of the twelve .try() hops instead of the deepest frame's ChainError(tag=12); the Ok path (66 through twelve frames) catches join-slot mix-ups from the other direction.
tests/corpus/deep-expressions/nested_arrays_settle_element_types -- settle an inner array literal to the wrong element type at depth, flatten nesting into one flat array, or apply an index to the wrong level's slot (5/44/27/10/59/1 all shift).
tests/corpus/deep-expressions/nested_enum_tags_survive_twenty_wraps -- read the wrong enum's tag when two enums share a payload shape (Node/Vine), skip one tag translation across twenty Ptr hops, or dereference the payload as a pointer (prints 0/traps instead of node 40 / vine -13).

## Compiler bugs found while writing this lane

1. **A `.match` used directly as an operand of `==` (and the other comparison
   operators) collapses its arm values to 1/0.** This is the known
   "spill_temp sizes the destination bool" class from earlier hunts, still
   reproducing on this tree. Discriminating pair:

       main = (env: Env) Res<i32, AllocError> {
           v ::= (4 > 3).match({ true => 42, false => 8 }) == 42;
           println("{}", v);          // prints false (must be true)
           m ::= (4 > 3).match({ true => 42, false => 8 });
           w ::= m == 42;
           println("{}", w);          // prints true   (control)
           Ok(0);
       }

   The bound-first control is correct, so it is specifically the inline
   binop-operand position. Arithmetic operands are NOT affected:
   `(4>3).match({true=>2,false=>3}) + 40` prints 42. Also hits `< > <= >= !=`
   with the same signature. No corpus test encodes this as expected output.

2. **A `.then()`/`ok_or(..)` chain whose later arms READ earlier unwrapped
   values fails codegen** ("codegen does not lower this yet: `printing a
   value of this type`" / "comparing values that are not scalars"), while
   ten links carrying independent constants build and run correctly
   (`ten_then_links_rewrap_each_value`). Repro shape that fails:

       v ::= (4 > 3).then(() { 40 }).ok_or(ChainError.Nope).try();
       w ::= (4 > 3).then(() { v + 1 }).ok_or(ChainError.Nope).try();
       println("{}", w);              // rejected at codegen

   The same two links printing only their constants pass, and interleaving
   plain statements between links passes too, so the defect is specific to
   reading an unwrapped Res binding inside a later spilling form. Valid
   program, sema accepts, backend refuses -- the sema-yes/gen_c-no shape.

TESTS: 8
