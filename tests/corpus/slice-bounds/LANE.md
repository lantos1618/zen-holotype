# slice-bounds

One line per test: path -- the one-line compiler change that breaks it.
All six programs trap (exit 134); each main.expected holds exactly the
stdout printed before the abort, since zg_trap flushes stdout before
exiting.

- array_at_len_traps_not_reads/main.zen -- runtime check `i >= len` loosened to `i > len` lets index 4 read past a length of 4 and print a plausible 0 instead of trapping
- loop_overruns_array_and_traps_mid_iteration/main.zen -- check hoisted out of the loop, or applied once to the first iteration's index, clears the whole walk and prints 0 for the out-of-range iterations instead of stopping after 7
- str_index_at_len_traps_by_underflow/main.zen -- text_str.index's check rewritten as `len - i` (or the subtraction made wrapping) reads one byte past the literal at i == len and prints 0 where it must trap; also pins get(4) answering None while [] traps
- empty_str_index_zero_traps/main.zen -- an is_empty fast path or defaulted byte in text_str.index returns 0 on ""[0] instead of dying through the same underflow as every other out-of-range index
- slice_to_past_len_traps_in_its_check/main.zen -- dropping or reordering slice's two subtractions (`tail = len - to` first) hands back a view with length past the buffer instead of trapping inside slice
- signed_negative_index_needs_its_own_test/main.zen -- helper_of keying on the wrong type routes -1 to zg_idx_u, whose unsigned compare wraps it into a huge index; the load then lands inside the array struct and prints a plausible value instead of trapping

## Compiler bugs found

None. Every probe matched the behavior derived from source:

- Fixed-array traps report "index out of bounds" at the caller's file and
  operator column; str traps report "integer overflow" pointing INTO
  text_str.zen. Surprising but by design: str.index spells its bounds
  check as an unsigned underflow (text_str.zen:35), the documented idiom
  hex_digit_out_of_range.zen also uses. Not encoded as a fixed-array trap;
  expected stdout never contains stderr text anyway.
- A literal index past a known count is a compile error (proven-trap rule,
  sema_trap.zen), so every runtime test here reaches its check through a
  call parameter -- the other boundary the literals-only prover stops at,
  verified against the generated C: usize indexes emit zg_idx_u, i64 emits
  zg_idx_s.

TESTS: 6
