# tests/corpus/loop-basic

One line per test: path -- the one-line compiler change that turns it red.

- empty_collections_run_zero_passes -- emit a do-while (or compare the end
  inclusively) and all four empty shapes run their body once; drop the
  fold-over-nothing special case and `fold answered 41` becomes a crash or 0.
- single_element_collections_walk_exactly_once -- an inclusive end or a
  body-tested condition doubles every pass (`fold 7` -> `fold 14`); handing
  the i64 element through a word-wide slot prints 9000000000 truncated to a
  plausible-looking 705032704.
- index_and_value_differ_when_the_walk_is_not_zero_based -- hand the pass
  counter to BOTH body parameters (the exact gen_c bug recorded in
  gen_zen/lowers_the_loop_intrinsic) and every line prints its counter
  twice; assume a zero-based range and the 10..13 block shifts by ten.
- next_skips_the_rest_of_one_pass_only -- lower h.next() as a jump to the
  loop EPILOGUE instead of the back edge and every tail after the first skip
  vanishes (`skip 4` goes); bind the handle at the wrong depth and the outer
  `outer 1` line disappears too, or the all-skip block hangs.
- break_exits_at_depth_and_carries_a_value -- bind the handle one level in
  and the first inner break kills the OUTER loop (`outer 1`/`outer 2` go);
  carry the index instead of the element and `broke 411` becomes `broke 41`;
  drop the payload and every Ok arm answers None.
- fold_threads_acc_by_value_through_the_passes -- swap the acc thread for
  the index thread and `sum 33` becomes `sum 3`; seed acc from the first
  element instead of init and `threaded 333` becomes 343 and `empty 41`
  becomes 0.
- array_literals_walk_in_place -- wrap the literal in an i32 element slot
  and both 90000000xx values truncate; consume the temporary on the first
  walk and every `second` line goes; run N+1 passes and `solo 0 7` repeats.
- vec_walk_hands_out_insertion_order_elements -- iterate the buffer in
  reverse and ada/grace/alan flips; read elements through a word-wide slot
  and 9000000000 truncates; count passes from end-1 downward and `passes 3`
  moves.

## Suspected compiler bugs (observed, deliberately NOT encoded)

1. Sema does not check h.break's payload against the enclosing loop's T.
   loop_handle.zen: "T is the enclosing loop's own T, fixed by the loop this
   handle names". But `Range(0, 100).loop((h, v) { ...; h.break("hit three") })`
   -- a str out of an i32-element walk -- compiles clean through sema and
   codegen and dies in cc: `incompatible types when initializing type 'long
   unsigned int' using type 'zg_str'`. The loop's Res<T> is typed by the
   BODY's break calls, not by the loop's element type. A must-fail case.

2. The collection walk snapshots bounds and data at entry; neither matches
   the docs. range.zen and collections_vec.zen both claim start/end are
   "supplied, not stored, so growing mid-loop reports the new end" and that
   a shrinking container "stops rather than reading past itself"
   (a None from `at` ends the walk early). Measured behaviour:
     - GROW: elements appended inside the body mutate the Vec (len rises)
       but are never walked. [1] + append during pass -> sees only 1.
     - SHRINK: worse -- it reads PAST len into stale slots. [1,2,3],
       take(2) during pass 1 -> body still sees 1, 2, 3. [1,2,3],
       take(1) during pass 1 -> sees 1, 3, 3: pass 2 read data[1] after
       the shift (fine), pass 3 read data[2] with len==2 -- a raw read of
       freed/stale memory, no per-pass bounds check at all.
   So the intrinsic lowers to a C loop over entry-time {data, start, end}
   with unchecked indexing. Both documented behaviours are false. Not
   encoded because the docs and the code disagree about which behaviour is
   the spec; whichever way the tree settles, one of these programs belongs
   in the corpus.

3. Codegen gaps hit while drafting (limitations, not wrong answers):
     - fold over a Vec: "codegen does not lower this yet: a fold over a
       range whose bounds an impl supplies" (folds work over ranges and
       stack arrays only).
     - `.try()` inside a loop-body closure widening into the function's
       error set: "codegen does not lower this yet: widening an error set
       through .try()" (worked around with .match).

TESTS: 8
