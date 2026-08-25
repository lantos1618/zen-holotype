# tests/corpus/string-basic — LANE.md

One line per test: path -- the one-line compiler change that would redden it.

    a_string_grows_through_three_reallocs/ -- gen_c: emit Vec.grow's doubling as `8` constant (or grow-on-`len > capacity` instead of `==`) and byte 9 truncates or shifts the view
    three_append_doors_one_buffer/ -- gen_c sink expansion: lower String.fmt's pieces to add (WriteError) instead of add_bytes (AllocError), or append at buffer start, and door order/bytes diverge
    a_view_borrows_and_grow_moves_it/ -- sema/gen_c: make String.view return a fresh copy (or a live re-read of data.ptr) and stale-len prints 9/29 instead of the frozen 8
    a_hole_picks_its_writer_by_type/ -- gen_c_sink.zen signed_writer: flip is_signed's u64 arm to add_i64 and UINT64_MAX prints -1; drop add_bool for write("true") via i64 and booleans print 1/0
    a_slice_is_a_view_not_a_copy/ -- text_str.slice: compute len as `to - from` with either bound off by one (drop the tail subtraction) and head/mid widths shift one byte
    str_eq_is_bytes_and_length/ -- text_str Eq impl: compare only over min(len) and "hello" == "hello!" flips to true
    a_named_hole_reads_the_writing_frame/ -- backend fmt walk: resolve named holes in module scope instead of the writing frame, or charge an argument per named hole, and callee/closure/shadow values permute
    a_display_hole_writes_through_the_buffer/ -- gen_c Display hole lowering: give the impl's toString a fresh Sink/String instead of the caller's, and "<12> / <-3>" prints empty
    a_string_is_a_field_and_a_return/ -- gen_c constructor initialiser list: zero the embedded Vec fields instead of calling alloc.Vec<u8>() (the field-defaults bug class), and every view prints empty
    empty_means_zero_bytes_not_null/ -- collections_vec.zen grow: skip the null-data first-grow branch and the post-empty `alive !` line traps or prints nothing
    two_buffers_grow_without_touching/ -- gen_c realloc call: pass one String's data pointer where the other's is read (stale-handle reuse) and b's seed bytes vanish into a's digits
    a_view_feeds_the_next_append/ -- gen_c arg evaluation order vs realloc emission: read the alias after the store instead of before and self-append prints ab-- or ab-ab-ab instead of ab-ab
    byte_values_round_trip_through_the_buffer/ -- gen_c add_byte lowering: widen u8 to i32 at the call (signed char) and index reads print -55-style negatives; utf8 len prints 1 not 2
    recursion_appends_deepest_frame_first/ -- gen_c match-arm ordering: emit the append before the recursive call (straight-line lowering of arms) and "12345" becomes "54321"
    the_allocating_constructor_formats/ -- gen_c ufcs overload pick for String(fmt, ..): resolve to the 1-arg empty form and "{}-{}" prints verbatim with braces intact
    a_float_fits_the_buffer/ -- gen_c_sink writer_of: drop the float arm back to sink_display and every float hole refuses `formatting a value of this type`; bypass %g in the intrinsic render and 100 prints 100.0

## Compiler bugs / suspicions found while probing

1. **cc warns on generated error propagation — memcpy overreads the payload.**
   Any `.try()` whose Err set widens into a union-carrying Res emits
   `memcpy(&dst.zg_data.zu_m3Err, &src.zg_data.zu_m3Err,
   sizeof(dst.zg_data.zu_m3Err))` where dst's Err member is the WIDER type.
   In `a_hole_picks_its_writer_by_type` the destination member is
   `struct { int32_t tag; union {IoError; AllocError;} }` = 12 bytes while the
   source `Res<(), WriteError>`'s carrier is 12 total, so gcc -O0 flags
   "reading 12 bytes from a region of size 8" (`-Wstringop-overread`). The
   bytes copied are harmless here (union members overlap from offset 0 and the
   tag is separate), but the read runs past the source object, which is UB and
   exactly the kind of thing -O2 is free to break. Reproducer:
   tests/corpus/string-basic/a_hole_picks_its_writer_by_type/main.zen (any
   test whose main declares a widened error set shows it). The size should be
   the SOURCE member's, per gen_c_try.zen's own comment on write_payload_copy.

2. **`usize` holes go through add_u64 but `usize.MAX` formatting is untestable
   portably** — noted only because literal_boundaries_unsigned.zen already
   says it; my tests use explicit `u64` typed bindings instead.

3. Not a bug, pinned as behaviour: a stale view taken before growth still
   reports its FROZEN length (a_string_grows_through_three_reallocs' sibling
   a_view_borrows_and_grow_moves_it pins this). If view ever becomes
   invalidating or copying, that test is the canary.

TESTS: 15
