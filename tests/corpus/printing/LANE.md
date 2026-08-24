# printing lane

One line per test: path -- the one-line compiler change that would break it.

- tests/corpus/printing/every_width_prints_in_full/main.zen -- keying `signed_printer` on a constant instead of `is_signed(prim)` (one arm of gen_c_print's printer table) routes every unsigned type through `zg_print_i64`; 2^63, past-i64.MAX and u32 4000000000 then print as negative extremes. Also catches dropping the argument-width cast (`integer_cast`): i8 -100 zero-extends to 156, i16 -30000 read unsigned wraps to 35536, and i64.MIN from a runtime variable breaks any negate-then-print-u64 digits routine.
- tests/corpus/printing/bool_and_char_print_by_type_not_by_value/main.zen -- falling from `zg_print_bool` into an integer writer (delete bool from `printer`) prints true/false as 1/0; special-casing char-literal SYNTAX to write the byte as a character instead of decimal breaks only the `'A'` half of its row while the u8 65 beside it stays right — the two spellings must agree because the writer reads the TYPE.
- tests/corpus/printing/floats_print_only_through_f64/main.zen -- routing f32 through a second rounding or refusing it outright (remove f32 from `number_printer`'s float branch) changes 3.5; a hand-rolled formatter that always writes a decimal point breaks the `100` row (%g's integer form) beside fractional neighbours that must keep theirs.
- tests/corpus/printing/str_prints_its_bytes_verbatim/main.zen -- quoting or escaping str arguments at the write (wrapping `zg_print_str`'s bytes in delimiters), or re-reading argument bytes for format syntax, changes a str holding braces; treating any first argument as a format literal (dropping `write_from`'s None branch) rejects `println(braces)` outright.
- tests/corpus/printing/print_without_newline_and_value_only/main.zen -- making `wants_newline` answer true for both spellings (or dropping `print` from `is_print`) re-flows every line: `nonewlinehere` becomes three. Inserting separators in the value-only form changes `123`; enforcing hole/arg agreement there rejects `println(s)` altogether.
- tests/corpus/printing/the_print_grammar_escapes_and_refuses/main.zen -- asking doubled-brace before hole at a shared position (`fmt_at`'s test order swapped) pairs `{}}` backwards and prints bare `1` instead of `1}`; rescanning after an escape turns `{{n}}` into a named-hole read printing 9; handing `\t` to the C string unstepped prints backslash-t inside the sentence; resolving `{n}` in one global frame prints 9 on the callee line instead of its own parameter.
- tests/corpus/printing/each_display_hole_picks_the_right_impl/main.zen -- resolving the toString symbol by NAME alone across impls (`member_symbol` keyed without the receiver type) lets one impl serve every hole: `S<12x-34>`-style crossings built out of the wrong record, same shape right punctuation. The nesting rows additionally catch the console record rebuilt per call instead of handed down (inner fragments lost/transposed), and Line's u64 tag typed as i64 flips #2^63 negative mid-sentence.
- tests/corpus/printing/what_printing_refuses/main.zen -- losing any single entry of the writer chain (`str`/bool/integers/floats/Display/generic instantiation) turns one line below into `codegen does not lower this yet: printing a value of this type` at COMPILE time; the test pins that every printable family stays reachable, including Box<T> monomorphised per T ("text" vs 41 — one shared instantiation prints both boxes with the same field).

## Compiler bugs found

None encoded. Two refusals met while probing are DESIGN, not bugs, and are
recorded here because this lane is where they surface:

1. Printing a `Res<..>`, a plain struct with no Display impl, an enum tag
   value, a String, or a Vec is refused at compile time
   (`printing a value of this type`, gen_c_print.zen:529). The Display
   fallback `dump` has no body yet (STAGE 5, display.zen), so the refusal is
   the honest state; what_printing_refuses pins the reachable side of it.
2. An unannotated float literal settles to f32 and printing one is refused,
   while an ANNOTATED f64 prints fine — `println("{}", 2.5)` is rejected but
   `z: f64 = 2.5; println("{}", z)` works. floats_print_only_through_f64
   annotates every hole for exactly this reason, and keeps passing whichever
   way the literal settles later.

TESTS: 8
