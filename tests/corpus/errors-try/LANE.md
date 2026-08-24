# LANE: errors-try -- .try() propagation through several layers

7 corpus tests under tests/corpus/errors-try/. Each line: path -- the one-line
compiler change that would break it.

- try_carries_the_payload_through_three_layers -- declare a try temp as C `int`
  instead of the payload's own i64 type (or unwrap into the Res struct's tag
  slot): 2^31 truncates and the test prints -2147483648 instead of 2147483647.
- each_member_surfaces_under_its_own_name -- number union members by source
  declaration order instead of matching identity at the widening site: top(-9)
  prints "said inner" (and 42 becomes wrong) because Outer lands in Inner's arm.
- try_inside_a_match_arm_returns_through_the_frame -- aim the .try() guard's
  early exit at the enclosing BLOCK instead of depth 0 of the frame: the first
  run prints "in arm 42 err" (arm falls through after unwinding one level), or
  drops the block's println on the second.
- try_in_a_loop_takes_the_err_edge_once -- reuse one guard/unwrap temp across
  loop passes, or lower the escape as `break` out of the C loop instead of
  `return` from the function: pass 2 prints its payload or "total" appears.
- stepwise_widening_keeps_member_and_payload -- apply only ONE re-tagging map
  across the two-hop ladder (reuse rung 1's rank table for rung 2): Grove's
  Leaf arrives tagged as Stem and main prints "stem"; clobbering the member's
  struct bytes during the copy prints "leaf age 0".
- try_through_every_frame_of_a_recursion -- skip the guard in non-base frames
  ("already checked once"), or add n before unwrapping in even frames: sum_to
  prints 45 or garbage; letting sink_to's base-case Err fall through unguarded
  prints "inner".
- try_tail_and_err_arm_join_in_one_caller -- join Ok/Err paths by copying one
  shared propagated-value temp instead of per-edge values: boom()'s failed run
  prints "ok 42"; assuming the Ok edge ran prints "total 42" there.

All expectations were produced by ./runzen.sh against the current tree and
verified byte-exact twice (determinism).

## Compiler bugs found while writing these

None of the programs below are encoded as tests. All are cases sema ACCEPTS
(the program checks; the diagnostics are codegen-stage or cc-stage) but which
produce C that does not compile.

1. `Err(member)` cannot be CONSTRUCTED anywhere except a whole-tail of a
   function whose declared error set is exactly that member's own set.
   Any wider declared set fails to lower:

       Inner = | InnerBoom
       Outer = | OuterBoom
       Any = Inner | Outer

       boom = () Res<i32, Any> {
           Err(Outer.OuterBoom);   // cc: incompatible types ... int vs zu_t_Outer
       }

   The emitted C assigns the bare `Outer` struct into the union's Err member
   slot instead of wrapping it: `.zg_data.zu_m3Err = (zu_t_Outer){...}` where
   the member field wants `{ .tag = ..., .data.Outer = ... }`. Same failure in
   let-bound position (`r = Err(...); r`), in match arms (`false => Err(..)`),
   and when returning a narrower-set call from a wider-set function. This is
   why every test here raises errors from single-member callees and widens
   them with `.try()` -- the only working spelling. Existing corpus tests
   dodge it the same way, so it is green today.

2. Matching a STRUCTURAL (inline `A | B`) union by member TYPE passes sema and
   emits nonexistent enum constants:

       v.match({
           Inner(_) => ...,    // emits zu_e_Inner5Inner -- undeclared in C
           ...
       })

   (cc: 'zu_e_..Inner' undeclared). Member-type arms work fine on NAMED unions
   (`Any = Inner | Outer`, then `e.match({ Inner(_) => .. })`); they fail only
   on the inline spelling.

3. `.try()` on a bare `Ok(literal)` / `Ok(expr)` operand is admitted by sema
   (see tests/corpus/sema/try_unconstrained_ok_carries_nothing.zen, which
   PASSES today) but gen_c reports
   `codegen does not lower this yet: widening an error set through .try()`
   whenever the enclosing function's declared set is a real failure set --
   even when the sets are identical. The absence-to-failure case skips the
   error-carry logic entirely, so this looks like a missing Carry case for
   form-mismatched operands, not an actual widening problem.

4. Printing a variant WITH its payload is unsupported
   (`codegen does not lower this yet: printing a value of this type` for
   `println("{}", Leaf.Wilted(41))`-style payloads bound as bare tags), and
   `codegen cannot resolve Wilted` for flat-tag patterns under a named-union
   member arm. Worked around in stepwise_widening by making the member a
   struct and reading its field. Related: a wildcard `_` arm inside a nested
   union match sometimes reports "unreachable" (sema) or leaves the match
   non-exhaustive depending on arm order -- see probe history in
   et_loop_* scratch files if this needs reproducing.

Bug 1 is the big one: it silently shapes how ALL existing error tests are
written (errors always raised from exact-set callees), which means the corpus
currently has no coverage of the most natural authoring style -- raising a
specific variant directly into a function whose set is wider.

TESTS: 7
