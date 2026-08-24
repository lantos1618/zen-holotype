# tests/corpus/vec -- LANE REPORT

8 corpus tests for Vec (push, index, iterate, grow, empty). Every `.expected`
is the real stdout of `./runzen.sh <dir>` on this tree; each header comment
names the one-line compiler change that would redden it.

| test | breaks if |
|---|---|
| grow_moves_every_element_whole_at_every_width | `Ptr.write` scales its index by 1 instead of sizeof(T), or realloc copies fewer bytes than `capacity * sizeof(T)` -- a 2-byte element lands in a 4-byte slot or the tail of the old pages never moves; boundary indices 7/8, 15/16, 31/32 catch both sides of every growth |
| take_moves_an_element_out_and_closes_the_gap | the shift loop writes `j` from `j - 1` swapped (survivors become left-neighbour copies), starts at `i` not `i + 1`, decrements `len` before shifting, or shifts by 4 not 16 for str elements -- the len/pointer pairs stop matching their contents |
| set_overwrites_one_slot_and_leaves_len_alone | set's bounds test uses `<=` (a set AT len grows the vec invisibly) or writes before checking: the "at len none" line still mutates; also catches write scaled by 1 on two-word str elements |
| empty_vec_owns_no_pages_until_the_first_add | any path assumes non-null data at len 0 (`ptr().is_null()` prints false) or bounds-checks with `<` against len 0 where `<=` differs by nothing -- get/take on the empty vec must answer None, and the first add must run realloc through the null-data fresh-allocation path |
| break_returns_the_element_and_next_skips_a_pass | the indexed loop's lowering passes the counter `i` to h.break's value slot (prints 400's index instead of 400) or lowers `h.next()` to the loop's break label (walk ends at first skip; `seen` drops to 1) |
| outer_realloc_copies_nested_vec_rows_whole | the outer growth memcpys per element word instead of whole four-word row headers -- rows answer a neighbour's cells after the move; cell values encode (row,col) so every read-back names its own row |
| map_and_filter_walk_in_order_to_the_end | filter/map visit out of order or map hands the counter twice as `(i, i)` -- `x + i * 1000` prints 0..11 instead of 0/11011; also flips the "filter keeping nothing is an empty vec, not None" contract |
| reserve_then_drain_to_empty_and_refill | reserve allocates less than asked (adds land past the buffer, reads come back shifted) or `want = len + n` mis-threaded; drain pins len bookkeeping under repeated front-takes down to exactly 0 |

## Compiler bugs found while writing these tests

1. MIXED INT/FLOAT ARITHMETIC INSIDE A LOOP CLOSURE COMPUTES IN THE WRONG
   TYPE. Program (also isolated in probes):

       main = (env: Env) Res<i32, AllocError> {
           Range(3, 4).loop((h, k) {
               z: f64 = k * 1.5;
               println("z {}", z);   // prints 3, correct is 4.5
           });
           Ok(0);
       }

   The same expression outside the closure (`n ::= 3; x: f64 = n * 1.5`)
   prints 4.5. Emitted C inside the loop is
   `zu_l1z = zg_add_usize(zu_l1k, ...)` -- the f64 binding is assigned via
   the USIZE checked-add helper with the literal truncated to an int
   operand. Sema types the loop closure's `k` as the literal family `int`
   (which agrees with everything), the fold to f64 happens at comptime, but
   gen_c emits an integer operation and silently truncates. No diagnostic;
   wrong values only when the fraction matters. Worked around in
   grow_moves_every_element_whole_at_every_width by picking f64 fill values
   through a match on the index instead of arithmetic.

2. `0 - n` ON THE LOOP'S INDEX TRAPS AT RUNTIME WITH A MISLEADING SITE.
   The loop index is usize, so `0 - n` lowers to `zg_sub_usize(0, n)` and
   traps ("integer overflow") for n > 0. Defensible under "unsigned
   underflow IS the trap", but the trap fires at the SUBTRACTION site
   rather than reporting a type error, and sema accepts the program even
   though `0 - usize` can never be valid for n > 0. A comptime proof (like
   the one that rejects literal overflow) would refuse it up front.
   Worked around: bind `m: i32 = n;` before negating.

3. `Vec<str>.take(0)` FOLLOWED BY `println("took {}", got)` EMITS INVALID C
   (cc error: passing `int` where `zg_str` expected) when the taken str is
   interpolated alone in the hole; the same value prints fine when another
   argument follows it (`println("{} {}", got, 3)` works). Repro:

       v.add("only").try();
       got = v.take(0).ok_or(E).try();
       println("took {}", got);   // cc: expected zg_str but argument is int

   Looks like the Display/format expansion picking the scalar toString
   overload for a Res-unwrapped str in a single-hole format string. Not a
   Vec bug per se -- the vec lane only supplies the smallest repro found --
   so it is recorded here rather than encoded as expected behaviour.

4. MINOR: chained generic calls lose their type arguments:
   `grid.get(r).ok_or(..).try().get(0)` (get -> ok_or -> try -> get on the
   resulting inner Vec) reaches cc with incompatible struct types
   (`Res<Vec<i32>>` vs `AllocError` argument mismatch inside ok_or's
   monomorphisation). Binding intermediate steps makes it work. Recorded
   as an inference gap in nested-generic chains; avoided in the nested-rows
   test by naming each step.

TESTS: 8
