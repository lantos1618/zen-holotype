# casts-conversions lane

Boundary values through the lossless widening conversions (`.to_i64()` etc.).
The conversion surface has three layers, and each test aims at one:
`std/core/num.zen`'s bodiless declarations (backend is the body,
`gen_c_call.lower_convert`), the bound records (`ToI64`/`ToU64` via
erasure round-trips, `gen_c_bound.convert`), and overload resolution among
the declarations themselves.

| test | what one-line compiler change breaks it |
|---|---|
| signed_minima_sign_extend_to_i64 | spell the C cast with an unsigned intermediate (`(int64_t)(uint32_t)v`) — i8.MIN/i32.MIN flip to huge positives; also caught by casting at the wrong width (low bits kept, sign bit dropped) |
| unsigned_maxima_stay_unsigned_into_i64 | sign-fill on u32→i64 (`(int64_t)(int32_t)x`, or `movslq` in a move-based lowering) — last number becomes -1 while every control row stays right |
| every_widening_overload_at_its_extreme | key the conversion table by target width instead of the (source, target) pair — rows shift by one and the -128/255 columns stop agreeing |
| ufcs_and_method_conversion_agree | route the no-receiver spelling (`f(x)`) down a path that types argument zero at the result width instead of the declared parameter — method and function columns diverge on boundary operands |
| generic_bound_conversion_at_boundary | lower the erased bound-call argument at the slot's byte type without its element count, or re-widen at the slot instead of the caller's type after the dynamic call |
| conversion_composes_in_expression_position | hoist either cast through a shared statement-shaped temporary reused across both hops of the chain — 65535 arrives as -1 from the first hop's width |
| user_to_prim_with_body_is_a_call | drop `bodyless(f)` from `convert_shape` (name+arity alone decide) — the user's body is skipped, `(uint64_t)n` prints 5 instead of 5000000005 |
| float_widening_is_exact | emit `(float)` for the i32→f64 cast (first two verdicts flip), or store f32 bindings as C doubles (last verdict flips: the double-rounding trap would wrongly answer "yes") |

## Compiler findings

1. **A bare free-function call to a num.zen intrinsic does not resolve —
   `to_i64(n)` is rejected where `n.to_i64()` lowers fine.** Program:

   ```
   main = (env: Env) Res<i32, AllocError> {
       n: u8 = 200;
       println("{}", to_u64(n));
       Ok(0);
   }
   ```

   `zen build`: `codegen cannot resolve 'to_u64'`. Sema reports nothing.
   The seam is documented, so I did not encode it: `sema_def.zen`
   (`exported_named`, ~line 271) — "this is a query only a DOT may ask;
   `f(x)` still goes through `defs_of`" — and the prelude root
   (`core.zen`) deliberately re-exports the bound names but not the
   conversion functions ("the conversions themselves travel with their
   types"). So sema answers the bare name with poison, and codegen's
   `lower_plain_call` finds an empty pool. It fails CLOSED — loud
   rejection, no silent wrong value — which is why it is recorded here
   rather than pinned as an expectation. But `gen_c_call.recv_arg`'s
   comment ("`b.to_u64()` and `to_u64(b)` are one call written two ways,
   which is what UFCS means") is unreachable for prelude intrinsics
   today; only user-declared functions can be called both ways.

2. **No narrowing conversions exist anywhere** — not as methods returning
   `Res` either (num.zen: "a narrowing conversion ... belongs in a
   Res-returning function written on purpose"; text_utf8 builds one by
   hand with a divide loop). The area name says "casts-conversions", but
   there are no casts to test beyond the widening matrix; everything here
   pins lossless widenings plus resolution around them.

3. Overlap note: sibling lane `tests/corpus/integer-widening/` covers
   extension direction and literal-width picking. The two lanes meet at
   sign-extension, approached differently (they: literals and closure
   accumulation; me: the iN/uN extremes grid, the UFCS doors, the
   bodiless-shape collision, and floats). No duplicated programs.

TESTS: 8
