# LANE: match-payloads — matching enum payloads by binding, nested patterns, bare variant names

All tests verified byte-for-byte against `./runzen.sh` on 2026-08-24.
Each pins a value only a correct payload lowering produces; the "breaks
with" column is the one-line compiler change that would fail the test.

## Tests

- two_enums_share_variant_names_and_payloads — swap `payload_type`'s enum lookup to resolve by bare variant name instead of scrutinee type (or emit the union member from the wrong enum's table): prints 200 for the dart or garbage for the pixel; valid C either way.
- one_binder_name_across_arms_and_types — drop `lower_match`'s per-arm mark/release (or bind into the sibling arm's scope): arm 2's binder resolves at arm 1's type ("late" prints as a number) and/or the trailing `outer 7` reads a closed branch's slot.
- nested_pattern_binder_only_at_the_bottom — stop the recursive `arm_cond`/`arm_bind` walk one level early (treat the middle pattern as a binder over its enum type): first arm swallows both Closed values, v prints as an enum instead of 9000000000.
- literal_payload_narrows_and_binder_binds — skip `destructure_cond`'s payload test when any sibling arm binds (or compare the literal against the wrong member's bytes): Ok(4) takes the Ok(3) arm / char 'a' arm misfires at u8 width.
- bare_variant_name_tests_only_the_tag — lower a bare variant name as a binder over the whole scrutinee instead of a tag test (`bind_name`'s variant check inverted): `Bare` swallows `Carry(5000000000)` and "carried" never prints.
- match_value_is_the_payload_binding — deliver each arm's value from the previous arm's slot or the scrutinee temp instead of that arm's own expression: numbers cross between the four matches (40 where 41 belongs); the None case catches it with no binding in scope at all.
- struct_payload_fields_read_through_the_binder — spell the union member or field offset from the second enum's table (both enums declare `At`; only one is matched per value): `p.line`/`p.col` read Mark.At's u64 slot — swapped or garbage, still valid C.
- arm_binding_scrutinee_of_a_nested_match — leave the inner match's binder (or the outer arm's binding feeding it) on the checker scope stack after the arm closes: inner values misresolve or trailing `outer 99` prints a branch-local value. Two variants on Wrap are load-bearing: with one variant the declaration stops parsing as a nominal enum.

## Suspected compiler bug (NOT encoded in any test)

**Bare payload-variant call does not lower: `Wrapped(5)` fails in codegen while
`Wrap.Wrapped(5)` compiles and runs.**

- Repro:
  ```
  main = (env: Env) Res<i32, AllocError> {
      w: Wrap = Wrapped(5);   // sema accepts; codegen refuses
      println("{}", 1);
      Ok(0);
  }
  Wrap = | Wrapped(i64)
  ```
- MUST be: runs, prints `1`. ACTUALLY: `codegen cannot resolve \`Wrapped\``
  (`GenFault.Unresolved`, gen_diag.zen), same with the two-variant spelling,
  same in dead code, same unannotated.
- Controls (all pass): bare nullary value `Nothing` where `Wrap = Wrapped(i64)
  | Nothing`; qualified payload call `Wrap.Wrapped(5)`; qualified nullary
  `Torn.Badly` (existing corpus). So name lookup itself works for nullary
  values and for dotted calls — only the BARE CALL form of a payload variant
  misses.
- Source reading: sema types the bare call through `construct_or_fail`
  (`sema_call.zen`) → `construct_def` → `sema_apply.construct`, which types ANY
  type-def call as `types.named(..)` — i.e. it types `Wrapped(5)` as the whole
  ENUM rather than as the variant constructor DESIGN.md describes ("a payload
  variant IS the function that builds one", quoted verbatim in
  gen_c_member.zen's static-call header). Codegen then has no bare-form
  lowering: `gen_c_call.lower_plain_call` finds no Def of the name (variants
  file no Def by design — sema_def.zen:444-449), `sole_def` hits 0 candidates
  and reports Unresolved. The qualified form lowers via
  `gen_c_member.lower_static_call` → `write_variant_call`, which has no bare
  twin. Fix locus: teach `sema_apply.construct` (or `decl_call`) the
  variant-constructor case, and give `gen_c_call` the `write_case_value`
  fallback `sole_def` currently lacks.
- Not pinned anywhere: no must-fail test claims this refusal, and every corpus
  program writes the dotted form — so the gap is invisible to the existing
  gates. Left out of my lane per instructions (a rejection must not be encoded
  as expected behaviour).

TESTS: 8
