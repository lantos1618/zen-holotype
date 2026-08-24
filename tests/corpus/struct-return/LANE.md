# struct-return lane

Returning structs by value: large, zero-field-adjacent sizes, nested,
carrying slices (str) and Vec handles, on both the Ok and the Err side
of a Res. The codegen suite already owns the plain ABI size classes
(struct_return_large/zero_field); these tests own what rides INSIDE a
returned struct and WHO drops what around the crossing.

One line per test -- path: what one-line compiler change breaks it.

- a_17_byte_struct_and_a_res_payload/main.zen -- truncate the memory-class
  return copy to 16 bytes and `c` (the trailing u8) prints 0 while the two
  i64s still print correctly; return `swap`'s argument unswapped and lo/hi
  trade places with no diagnostic.
- a_chain_of_methods_threads_the_value/main.zen -- reuse the receiver's
  storage as the return slot and the middle link of `.add(10).add(20).grow(100)`
  reads a half-overwritten receiver (sum/n go wrong mid-chain); alias the
  return onto the receiver and `b` prints c's values.
- a_str_field_crosses_its_return/main.zen -- drop or zero the str's data
  pointer (or its len) when copying the returned struct's str field and
  head/tail print short, empty, or garbage; swap field order in the layout
  and len 15 becomes 8 (pointer-sized) on every line.
- a_vec_handle_inside_a_returned_struct/main.zen -- copy only part of the
  Vec handle (two of three words) out of the returned struct and `get(4)`
  returns None or garbage instead of 16; re-zero the handle as "moved" and
  `b.items.len` prints 0; double-realloc through caller and callee copies
  and the program corrupts before exit.
- an_err_payload_struct_keeps_its_fields/main.zen -- build the Err payload
  in the wrong arm slot or lose the fields on re-tagging and `code` prints
  0 / note prints empty; bind `Ok(v)` instead of `Err(e)`'s payload shape
  and the match arm stops compiling (caught by cc, so the silent half is
  the payload copy).
- nested_returns_copy_not_alias/main.zen -- return a struct as a pointer
  into the callee frame and `snap.mid.in.v` prints 100 after `o` is
  written (the two aliases move together); alias struct assignment like
  return and "snap 100 orig 100" replaces "snap 3 orig 100".
- the_abandoned_local_drops_in_the_callee/main.zen -- emit the returned
  value's drop in the callee (prints "drop 1 / drop 2 / got 2"), skip the
  abandoned local's drop (no "drop 1"), or hoist both drops to main ("drop 1"
  last): three plausible orderings, one right one.

Not encoded as tests (found while probing, kept out of the corpus):

1. Free functions taking/returning `@Self`-typed values cannot be UFCS --
   `add = (self: @Self, v: i64) Acc {...}` at top level is rejected with
   `codegen cannot spell the type 'add'`. Methods in the struct body work.
   Looks like a sema/codegen boundary gap, not a struct-return bug, and
   must-fail is not this lane.
2. `.fmt` holes that are not `str` are rejected at codegen
   (`a format hole on this door that is not a str`) even where `{}` on an
   integer works through `println`/`String.add`. Documented floor
   (`string_fmt_answers_the_buffer_floor`), so not a bug -- but it shapes
   how the slice test builds its bytes.
3. Error-set widening through `.try()` is `GenFault.Unsupported`
   (gen_c_try.zen:450). Known gap; the tests here keep every function's
   declared error set exactly as wide as what it raises.

TESTS: 7
