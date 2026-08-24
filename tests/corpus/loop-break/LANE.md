# loop-break lane

8 corpus tests under tests/corpus/loop-break/. Each pins one rule of
`h.break` / `h.break(v)` with the wrong-answer-is-plausible property.

- first_break_executed_supplies_the_loop_value/main.zen -- taking the LAST
  written break site (or the always-executed fall-through) as the loop's value
  instead of the first EXECUTED one prints 11/33/44 instead of 22.
- natural_end_is_none_even_when_break_zero_is_ok/main.zen -- initialising the
  loop result to Ok(zeroed) instead of None prints `ok` on the natural-end
  half; conflating payload-0 with None prints `none` on the zero-payload half.
- a_handle_names_its_own_loop_depth/main.zen -- resolving a handle to the wrong
  loop frame (depth always 0, nearest label, one shared brk per function)
  corrupts both counts: anything but `a 3 6` / `b 2 8`.
- wide_break_payload_survives_whole/main.zen -- spilling the break argument
  through an int/narrower slot truncates 7000001234 (prints 705033938-ish).
- bool_break_payload_is_a_bool/main.zen -- collapsing the bool payload into a
  numeric slot prints a number; folding tag+payload into one word makes the
  None fallback's answer print.
- outer_break_carries_the_inner_loops_work/main.zen -- tearing down (or
  reusing) the result slot before the break's goto lands loses the inner
  loop's folded total (prints 0/garbage instead of 600).
- break_from_inside_then_and_match_frames/main.zen -- lowering h.break as
  "return from the enclosing closure" lets later passes print; only a labelled
  goto through both frames yields exactly `survived 0` then `got 200`.
- break_copies_the_whole_struct_payload/main.zen -- copying only the first
  machine word zeroes the second field; swapping field order transposes them;
  aliasing instead of copying shows post-break slot state.

## Compiler bug (found, NOT encoded as expected behaviour)

For the three no-range loop shapes -- while-true, while-true-with-index,
while-cond -- the loop's result temporary is emitted as `Res<usize>` NO MATTER
what the break carries or what the binding annotates:

    w: Res<i64> = loop((h, ix) { ... h.break(ix * 1000000000); ... });

is accepted by sema, then rejected by cc:

    error: incompatible types when assigning to type 'ResI1_b3i64'
           from type 'ResI1_b5usize'      (zu_l1w = zg_v3)

The emitted C declares the loop temp `Res<usize>`, assigns the i64 payload
into it, and only then copies temp -> `w`. Root cause locus: gen_c_shape.zen
`loop_element()` returns `usize` whenever `range_arg(id)` is None ("usize is
the answer whenever there is no range to ask"), and gen_c_fold.zen
`result_element()` falls back to it -- so `settle_res` never considers either
the written expectation (the annotation outranks reconstruction per
gen_c_loop.zen's own comment) or the break argument's type. With no annotation
the same shape dies earlier as "codegen does not lower this yet: a loop whose
value type nothing settles, broken with a value" (write_break's guard) or
"printing a value of this type". Repro programs (ephemeral /tmp/lb-probes/,
quoted fully here): while-true-with-index i64 (above), plain while-true i64,
while-true bool annotated (`f: Res<bool> = loop((h) { h.break(true); });`),
and a struct payload variant -- all one root cause.

History worth knowing: an earlier ./zen binary (before the 17:41 rebuild by
another lane) compiled the annotated-i64/bool while-true forms CORRECTLY
(printed 5000001234 / true). The current binary C-rejects them. Either the
rebuild regressed this, or the old binary was built from different sources --
either way the differential is live.

Working carriers today (used by the tests): ranged loops over Range (element
usize -- a designed pin, gen_c_loop.zen `lower_settled`), folds (acc = seed
type), and fixed-array walks (element = array element type; the ONLY route to
a non-usize break payload).

## Not bugs (by design, verified in source/docs)

- `total: Res<i64> = Range(0, 6).loop(...)` refused by sema ("expected
  Res<i64>, found Res<usize>"): a ranged loop's Res IS its element type
  (gen_c_loop.zen lower_settled says so explicitly).
- Inline match on the loop call itself (`loop(..).match({..})`) refused:
  STYLE.md documents T stays unresolved there; bind first.
- `[0, 3]` is a two-element array walk, not a range -- parser semantics, not
  a loop bug (this lane's own early drafts got bitten).

TESTS: 8
