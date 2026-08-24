# tests/corpus/string-utf8

One program per interesting case in multi-byte text: byte length vs
codepoint count, the four UTF-8 sequence widths, and the boundaries where a
wrong answer still looks like a plausible number. Everything here exercises
`src/std/text/text_utf8.zen` (decoder, cursor, `count_codepoints`,
`validate_utf8`, `push_utf8`) over `str`'s raw bytes.

## The tests

| path | what one-line compiler change breaks it |
|---|---|
| `count_codepoints_walks_all_four_widths/` | `count_codepoints` returning `str.len` (or the walk stepping 1/2 instead of per-sequence width) — 11/5 and the five decoded values all move |
| `a_cursor_steps_by_sequence_width_not_one/` | `Codepoints.next` advancing `at` by a fixed step instead of the decoded width — the intermediate offsets 2/5/9 are only right if each step was exact |
| `byte_len_and_codepoint_count_disagree_on_the_same_string/` | `len` counting codepoints (6→5) or `count_codepoints` delegating to `len` (5→6) — either shortcut collapses the pair |
| `a_boundary_value_changes_width_not_its_payload/` | an off-by-one band test in the encoder (`v < UTF8_MIN_3` / `UTF8_MIN_4`) — 0x800 or 0x10000 encode one byte short and the lead bytes 224/240 move |
| `an_encode_decode_roundtrip_holds_at_every_width/` | any encoder/decoder disagreement at the width minima — U+0000/U+0080/U+0800/U+10000 must survive with widths exactly 1 2 3 4 |
| `the_last_codepoint_decodes_and_one_bit_past_it_does_not/` | dropping the `value <= UTF8_MAX_CODEPOINT` check in `four_byte` — F4 90 80 80 decodes as garbage "past-max" |
| `a_well_formed_lead_with_a_forbidden_value_is_invalid/` | removing any of the three value checks (`overlong3`, `surrogate`, `overlong4`) — its verdict flips 0→1 while lead-band-only validation stays green |
| `a_surrogate_gap_edges_still_decode/` | over-rejecting the whole 0xED lead band instead of checking values — U+D7FF (real Hangul range) would be lost |
| `a_forbidden_lead_band_never_eats_its_ascii/` | accepting ANY of leads 0x80..0xC1, or consuming a fixed 2 bytes on failure — `rejected 66 ascii 66` cannot both hold |
| `a_bad_lead_leaves_its_ascii_follower_readable/` | error recovery that skips the full sequence length instead of 1 byte — the 'A' at offset 1 disappears |
| `a_sequence_cut_at_the_buffer_end_is_invalid/` | reading continuation bytes past `str.len` without going through `get`'s miss — silent out-of-bounds reads in C instead of Invalid |
| `an_astral_codepoint_inside_ascii_text_steps_cleanly/` | cursor misalignment after a 4-byte sequence — trailing 'y' at offset 5 or `at 7` |
| `a_bom_inside_a_literal_is_payload_not_skipped/` | BOM-stripping applied outside file-start (lexer or decoder) — U+FEFF vanishes from the middle of data |
| `a_replacement_character_in_data_decodes_to_its_own_value/` | a decoder that emits U+FFFD for input it has not validated — valid EF BF BD gets re-substituted |

## Notes for the next person

- The decoder is value-driven by design: `three_byte` checks
  `value >= UTF8_MIN_3` plus the surrogate gap, `four_byte` checks
  `value >= UTF8_MIN_4 && value <= UTF8_MAX_CODEPOINT`. That is why the
  surrogate-gap edges (U+D7FF / U+E000) and its middle (ED A0 80) live in
  three different tests.
- `.try()` on a free-function call (`push_utf8(v, sb).try()`) fails codegen
  with "codegen has no type for `the operand of .try()`"; route it through a
  helper that matches first. Method-call `.try()` on the same shapes works.

## Compiler bug found while writing this

**`.try()` on free-function calls does not lower.**
`push_utf8(v, sb).try();` → `codegen has no type for 'the operand of
.try()'`, while `sb.add("x").try();` (a method call) lowers fine. Sema
accepts both shapes; only gen_c chokes. Worked around with
`.match({ Ok(_) => .., Err(_) => .. })` helpers throughout this lane.

No expectation here encodes a bug: every value was verified against the
UTF-8 spec by hand (lead/continuation byte tables computed independently
before running anything).

TESTS: 14
