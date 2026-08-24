tests/corpus/integer-widening/ — one line per test: what one-line compiler change breaks it.

sign_extension_survives_widening/main.zen — keying `write_convert`'s cast on the TARGET type instead of the declared parameter's (one swapped lookup in gen_c_call.zen) turns `(int64_t)x` into zero-extension; -5 prints 251.
unsigned_high_bits_zero_extend/main.zen — the same swap in the other direction (signed intermediate, e.g. `(int64_t)(int32_t)x` on a uint32_t) sign-extends 4000000000 to -294967296; also caught by dropping the cast entirely only at the u16->i64 row via C promotion.
literal_widens_by_position_variable_does_not/main.zen — deleting `is_literal_ty`'s guard in `assignable` (sema_check.zen) lets any variable of the same family fill any integer slot; `b: i8 = -5; w: i64 = b;` then compiles and C accepts it silently.
overload_picked_by_receiver_width/main.zen — resolving `.to_i32()` by name alone instead of by receiver width (drop the receiver from sema_call's overload key) makes `a.to_i64() * 3` on an i8 holding -100 compute from 156 and print 468.
widened_value_computes_at_target_width/main.zen — writing the operand of a conversion at the target's width instead of the declared parameter's (`write_convert`, gen_c_call.zen "the operand takes the DECLARED parameter's type") re-types -100 before the cast; the multiply rows also break if conversion is hoisted past arithmetic (u32 wrap prints 410065408 / 3410065408 instead of 12000000000).
wide_literal_settles_in_every_position/main.zen — folding wide literals to i32 before consulting their position (settled_arg_ty / check_literal path) wraps every value mod 2^32; the false arm row additionally catches typing match arms against the FIRST arm's width instead of the position's (-5000000000 reads as 705032704 or negative-garbage depending on fold order).
widened_value_crosses_closure_and_accumulates/main.zen — materialising loop variables at element width inside the closure body, or widening the accumulator only after .loop returns, sums [200,250,5] as 199 (mod 256); the usize equality row catches a signed intermediate on u32->usize (eq prints 0).

COMPILER BUGS FOUND (probes under /tmp/zw/, not encoded as tests):

1. The free-function spelling of a conversion faults in codegen. `std.core.num`
   declares `to_i64* = (self: u8) i64` as a prelude free function AND
   gen_c_call.zen:734 says "`b.to_u64()` and `to_u64(b)` are one call written
   two ways, which is what UFCS means" — but:

       raw: u8 = 200;
       println("{}", to_i64(raw));
     -> codegen cannot resolve `to_i64`

   sema accepts it (resolution succeeds); gen_c fails. Repro: pg.zen probe,
   first version. Either UFCS resolution should reject it in sema or gen_c
   must lower it; today it is accepted-then-unlowerable.

2. `usize` has no outbound conversions. std/core/num.zen declares to_* for
   every integer EXCEPT usize: no `to_u64(self: usize)`, no `to_i64`,
   nothing. So `sz.to_u64()` on a usize answers:

       a member is resolved on the receiver's type ...: no `to_u64` on `usize`

   even though usize is 64-bit here and the conversion is trivially lossless.
   Every other type can reach i64/u64; usize is a leaf. If that is deliberate,
   num.zen:111's comment ("Only lossless widening lives here") does not say so.

3. Transient empty output observed once (probe p9/pd class): a program that
   deterministically prints three lines produced NO stdout once through
   runzen.sh with exit 0, then printed correctly on immediate re-run. Could
   not reproduce after ~6 reruns; noting it because an oracle that sometimes
   says nothing poisons expected-file generation. Watch for it if a corpus
   test ever fails with an empty diff.

TESTS: 7
