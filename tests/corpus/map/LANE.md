# tests/corpus/map — LANE REPORT

Six tests, each directory holds `main.zen` + `main.expected` (exact stdout,
verified byte-for-byte against `./runzen.sh` on the tree as of this lane).
All six PASS on the current tree; nothing was left out for wrong output.

One line per test: path -- the one-line compiler change that breaks it.

- every_key_reads_back_its_own_value/ -- emit `entries[probe_index]`
  (address the dense row by the slot/probe index instead of the stored
  one-based position): keys inserted out of order then read back swapped,
  and the empty-string key pins a hash-of-nothing row.
- a_missing_key_answers_none_not_another_row/ -- stop the probe at the
  first `hash == h` without consulting eq (or return the row's value on a
  hash match): absent-but-colliding key answers Ok with another row's
  value instead of None. Constant hash makes the collision certain, not
  probabilistic; the two real rows must still read back afterwards.
- an_overwrite_rewrites_its_own_row_under_collisions/ -- overwrite the row
  found by hash alone (not hash AND eq), or append a second entry for an
  existing key: with every key hashing to one bucket, overwrites in
  reverse insertion order land on the wrong rows / duplicate rows.
- a_struct_key_is_its_fields_not_its_binding/ -- hash or compare the
  struct key by address/identity instead of field-wise: set under one
  binding, looked up through a fresh equal struct, answers None. Near-miss
  shares the FIRST field, so an eq stopping after one matching field also
  fails it. (Also catches a Hash impl that ignores any field.)
- a_str_key_is_its_bytes_not_its_pointer/ -- key/hash str by its data
  pointer instead of its bytes: stored literal and lookup literal are
  distinct static bindings with equal bytes, so lookup misses. Prefix pair
  additionally breaks an eq/hash comparing only the shorter length ("ada"
  would alias "adaline").
- two_maps_never_share_rows/ -- hoist/share the table between two Map<K,V>
  instances of the same type (static table, stale alloc handle): values are
  deliberately cross-wired so any leak prints the other map's value.

## Notes / near-bugs found (NOT compiler bugs, but worth knowing)

1. No signed -> unsigned conversion exists anywhere in std/core/num.zen:
   i32/i64 have no `to_u64`/`to_usize` (only u8/u16/u32 widen upward).
   Writing a Hash impl for a signed-field struct key requires either
   reinterpreting bits (no such method) or going through f64. My first
   draft used `self.id.to_u64()` and sema rejected it cleanly (good
   diagnostic); `.to_i64().to_u64()` is rejected too, which is consistent
   with the declared matrix, but it means signed-int keys need a hand-
   rolled mix (`*% 1000003 +%` on the i64 then... nothing). Consider a
   documented bitcast or a `to_bits` on signed ints before someone writes
   a Map<i32-ish-key, V> in the compiler itself.
2. `str.index` bounds-check shape (`self.len - i - 1` underflow-as-trap)
   means out-of-range reads trap rather than return garbage -- fine, but
   note `Hash` for str walks bytes via `data.read(i)` directly, so the
   trap path there is untested by these tests (deliberately: that is
   std's own test lane).

TESTS: 6
