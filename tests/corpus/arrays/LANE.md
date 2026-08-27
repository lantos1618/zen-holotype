# tests/corpus/arrays — LANE REPORT

Eight tests, each directory holds `main.zen` + `main.expected` (exact stdout,
verified byte-for-byte against `./runzen.sh`, rerun twice for determinism).
All eight PASS on the tree as of this lane; nothing was left out for wrong
output. Area: fixed arrays -- literals, indexing, arrays of structs.

One line per test: path -- the one-line compiler change that breaks it.

- literals_take_the_type_the_position_writes/ -- make `literal_ty`
  fall back to the literal's own settled `[int, N]` instead of taking
  the position's array type: the u8 row stores int64s, `cc` rejects
  the compound literal (or a signed store prints 200..203 as -56..-53).
- an_index_steps_one_whole_element/ -- take the index addressing stride
  from the FIELD's width (4) instead of the element's (8): prints
  "1 2 3", the neighbouring field of the previous element.
- a_struct_field_holds_the_whole_array/ -- lay the array field out at
  offset 0 (or initialiser walks slots one-to-one past the hole): the
  cells' compound literal stomps `tag` (loses the 99) and/or the tag
  lands in cells[0].
- the_walk_hands_element_and_index/ -- pass the counter where the body's
  value goes in lower_array_walk's run_body: total is 14 (counter as
  value) or 200 (value as multiplier of itself), never with the printed
  rows agreeing with the total.
- a_function_returns_a_fresh_array/ -- return the wrapper struct by
  hidden pointer to callee stack / static slot: second() reads stale or
  first()-derived numbers; also breaks if the return type ignores the
  written `[i64, 3]` signature.
- a_copy_walks_on_its_own/ -- alias instead of copy (`ys ::= xs` shares
  xs's buffer), copy at i32 width, or copy only a prefix: the indexed walk
  and reverse read-back expose aliasing, truncation, and missing tail slots.
- an_array_argument_is_a_private_copy/ -- lower array arguments (or
  `consume`) as reference rename: the callee answers from main's buffer;
  combined with first-touch lowering the walk lines come out wrong.

COMPILER BUGS FOUND: none. Every expectation is the program's real output,
checked by hand against docs/DESIGN.md (fixed arrays: `[type, count]`,
comptime count in the TYPE, bounds-checked indexing, intrinsic Range) and
src/gen/gen_c/gen_c_array.zen (struct-around-C-array wrapper, zg_elems
member, count-from-type, plain C for over elements).

Two near-misses while writing expectations, both mine, not the compiler's:
1. Type aliases do not reach array types: `Row = [Pair, 2]` is rejected
   ("expected Row, found [Pair, 2]") even though DESIGN.md line 143 shows
   alias syntax for shapes. Arrays are type CONSTRUCTORS (`[T, N] is a
   type constructor, not a name` -- std/core/range.zen via gen_c_array),
   so there is no name to bind; whether aliases SHOULD cover them is an
   open design question, not obviously a bug. Worked around by writing
   `[Pair, 2]` inline everywhere.
2. Enum-typed fields inside array elements work fine, but bare enum
   declarations are spelled `Tag = { A, B }` only in the prelude import
   form (`A, B, C = tags.tags`); a local `Tag ::= { .. }` is rejected by
   the parser ("expected `:`, `::`, `=` after a member's name"). Used a
   union instead in the planned enums-in-arrays test and folded that
   coverage into an_array_argument_is_a_private_copy rather than pinning
   parser behaviour I could not verify as intended.

TESTS: 8
