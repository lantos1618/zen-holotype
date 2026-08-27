string-compare -- equality and ordering, empty strings, embedded NUL bytes

eq_checks_length_before_bytes/main.zen
  -- delete the `self.len == other.len` gate in str.impl(Eq, ..)
     (src/std/text/text_str.zen): prefix rows flip to true.

eq_compares_bytes_not_addresses/main.zen
  -- make str.eq compare the `data` pointers (field-wise default) instead
     of walking bytes: view-vs-literal rows flip, false rows stay green,
     so only this file catches it from one side.

nul_byte_is_data_not_terminator/main.zen
  -- lower str == to strcmp(a.data, b.data) == 0: "a\0b" vs "a\0c" and
     "a" vs "a\0" both turn true; memcmp over min(len) flips "a" vs "a\0"
     back to false but breaks the length-gate test instead.

neq_is_eq_negated/main.zen
  -- drop the `!` in write_equality (gen_c_op.zen) or emit the NotEqual
     arm without negation in lower_eq_op: every row flips; a pointer-based
     != diverges from == on the paired rows instead.

before_orders_by_first_differing_byte/main.zen
  -- swap the operands of before's final comparison
     (`other.index(i) < self.index(i)` in std.text.before) or compare
     lengths with <= : exactly half the mirror rows flip; an off-by-one
     walk start makes "b".before("ab") answer true via the length
     tiebreak.

COMPILER BUGS FOUND: none. All six programs compiled clean (no CC warnings),
ran with exit 0, and every output line matched the value derived from
src/std/text/text_str.zen before running. One operator-behaviour note, not a
bug: `\u0000` is not in Zen's escape set by design (lex_literal.zen:98 --
`\n \t \r \v \f \0 \\ \' \"` and nothing else); the rejection is correct, the
NUL tests use `\0`.

TESTS: 5
