# LANE: enum-basic — enum construction, matching, variants with and without payloads

All tests verified byte-for-byte against `./runzen.sh` on 2026-08-24. Each
pins a value only a correct tag/payload lowering produces; after each path
is the one-line compiler change that would fail it.

## Tests

- three_variants_construct_and_match_every_arm -- resolve the Case by position instead of name in `write_variant_call` (gen_c_member.zen) or stamp a constant `.zg_tag = 0` in `write_case_value`: every construction becomes First, `gap` goes quiet, and the payloads read First's union member.
- bare_nullary_names_cross_a_call_boundary -- drop sema's result-type fallback for an unqualified nullary variant and emit tag 0 ("name not locally bound, assume a variant"): all three calls answer "got zebra" with valid C.
- single_variant_leading_bar_still_an_enum -- lower the leading bar to a no-op so `Solo = | Lone(i64)` stores the payload bare (no tag word): prints fine here, breaks beside any two-variant read; or read the member at offset 0 and print the tag/garbage.
- wide_payload_survives_call_and_rewrap -- truncate the aggregate argument (or the return slot) to 32 bits across `loud`: 4294967297 arrives as 1; or leave the old tag in place when the arm builds `Wide.Vast(..)` and the inner match answers "still modest".
- reassigned_local_reads_the_current_tag -- lower reassignment of an enum-typed `::=` as field-wise store into `.zg_data` only (compound literal not rebuilt): the initialisation tag survives every reassignment and arms two/three misfile under First.
- enum_typed_parameter_dispatches_in_the_callee -- copy only part of the aggregate argument into the callee frame (or read the parameter back at the wrong width): the inner match takes some other arm and prints a plausible word for all three arguments.

## Notes on what could NOT be tested here, and why

1. **A type declaration inside a function body parses but never binds its
   name.** DESIGN.md: "an enum may be declared anywhere", declarations take
   no semicolon -- yet both spellings are refused:
       local_pick = (n: i64) i64 {
           Temp = Cold | Warm | Hot      // declaration form, per DESIGN.md
           t: Temp = Temp.Cold; ..       // "undefined name: ... is in scope `Temp`"
       }
   The trailing-semicolon spelling adds "expected expression: no token here
   can begin one" at the semicolon, which confirms the DECLARATION parsed
   and the `;` is what broke -- the name simply never reaches scope. A
   local struct (`Pt = { x: i64, y: i64 }`) fails identically, so this is
   general to type declarations in bodies, not enum-specific. Left out of
   the lane: it is a clean rejection standing in for a missing feature,
   not a silent wrong answer a corpus test could pin.

2. **Bare variant names collide across enums, and the diagnostic points
   at the wrong thing.** With `Word = Zebra | Mango | Alpha` AND
   `Mix = Mango | Chip | Rye` in one module, bare `Mango` annotated
   `: Mix` is rejected "type mismatch: expected Mix, found Word" -- i.e.
   a bare name resolves to the FIRST visible enum declaring it, then the
   written annotation is reported as the mistake. Existing corpus test
   codegen/bare_variant_picks_its_own_enum pins the resolution itself;
   recorded here because my first probe tripped over it and the message's
   voice (the annotation blamed, not the ambiguity) may be worth a look.

3. **`==` on enum values needs an `Eq` impl** ("equality dispatches to the
   impl, so write one or compare the parts") -- a designed diagnostic, so
   structural equality of variants belongs to struct-equality's lane, not
   this one.

4. Two shapes were probed and thrown away as redundant rather than wrong:
   qualified-nullary-only matching (covered by the existing corpus), and a
   negative-payload probe (`Signed.Neg(0 - 5000000005)` round-trips
   correctly through construction and match).

TESTS: 6
