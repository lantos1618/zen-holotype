# errors-widen lane

A narrow error (one member) widening into a wider set, and what survives the trip.

tests/corpus/errors-widen/shared_variant_name_keeps_its_member -- keying a widened union's
    tag on the variant NAME instead of the member type (both members here declare `Hit`)
    takes both errors down the same arm; expected `fault hit` then `snag hit` fails.
tests/corpus/errors-widen/payload_rides_the_widened_err -- dropping or shifting the Err
    payload to make room for a tag word truncates `1234567890123`; low bits are zero on
    purpose so /4-style corruption is visible.
tests/corpus/errors-widen/inferred_middle_set_flattens_into_wider -- typing the
    `Res<i32, _>` middle layer from its FIRST arm only loses Big: one of the two output
    lines goes missing or swaps.
tests/corpus/errors-widen/one_member_two_targets_retagged -- memoizing "Narrow already
    widened" by SOURCE type reuses Mid's tag inside Wide3's numbering; the second read
    prints the wrong member. Member orders deliberately do not coincide.
tests/corpus/errors-widen/alias_retag_chain_translates_tags -- a hop that copies the
    previous hop's tag instead of translating it for `Mid` then `All` lands in the wrong
    final arm; Ok line pins the value, Err line pins the identity.

## Compiler bugs found (programs admitted by sema, rejected by cc -- no stdout exists,
so they cannot be encoded as .expected; kept out of corpus per instructions)

ONE ROOT CAUSE, four faces. sema admits widening through a NAMED error-set alias
(`Mid = Narrow | Other`) everywhere via `set_of`/`set_assignable` (`sema_check.zen:644`,
`sema_try.zen:172`) — "a union is its members", so the alias IS the set. The C backend
only widens when the wanted type is literally `Ty.Union`: `gen_c_widen.zen:119`
`is_set` matches `Union(_)` and never consults `check.set_of`, and the same test guards
`member_reaches_set` (`gen_c_widen.zen:114-117`, used by `needs_widen`) and
`settled_member` (`gen_c_widen.zen:174`). A named alias answers `Named`, every widening
predicate says no, the expression lowers Plain at its own narrow type, and cc rejects
the raw struct assignment. The same program with the union spelled INLINE
(`Res<i32, Narrow | Other>`) widens correctly at every position — proof the miss is the
spelling, not the semantics. Fix locus: make those three predicates ask
`be.check.set_of(ty)` (as `gen_c_try.write_member_tag` already does for Named sets at
`gen_c_try.zen:620-623`), not `types.at(ty)`.

1. named alias as a typed LOCAL / parameter / name-read target
   repro: `m: Res<i32, Mid> = make(7);` / `read(make(-3))` / `w: Res<i32, Mid> = r;`
   emitted: `zu_l1m = zu_f...makeO...(7);` -- Res<Narrow> struct assigned to Res<Mid>.
   control: identical code with `Res<i32, Narrow | Other>` inline compiles and prints 7/-1/9.

2. bare tail call into a function whose declared set is a named alias
   repro: `wrap = (n: i32) Res<i32, Mid> { make(n); }`
   emitted: `return zu_f...make(n);` in a function returning Res<Mid>.

3. direct `Err(member)` built under a declared named-alias set (also under `.match` arms)
   repro: `raise_mid = () Res<i32, Mid> { Err(Narrow.Nope); }`
   emitted: `.zg_data.zu_m3Err = (zu_t_Narrow){...}` -- raw member struct written into
   the alias slot with no set build; cc reports the initializer type mismatch.
   control: inline spelling builds the tagged set and runs.

4. return-position match whose arms carry two different named-member sets, joined at a
   NAMED union (`either = ... Res<i32, Joined> { (n > 0).match({true => fa(n), false => fb(n)}) }`)
   emitted: each arm returns its own narrow Res directly; cc rejects both returns.
   note: tests/corpus/std/res_match_arm_widening_keeps_the_member passes ONLY because its
   join union is spelled inline in the signature; give it an alias name and it fails the
   same way (verified). Also: matching on the INLINE spelling of a structural union is
   refused today ("match is not exhaustive") -- known hole per that std test's header;
   my probes hit it and routed around it.

Verified correct along the way (do not re-probe without cause): `.try()` member-to-named-
alias retagging incl. two-hop chains (`write_member_tag`'s Named carrier path);
member-to-inline-union at locals/params/tail/Err-build; shared variant names across
members; payload integrity through widening (i64 across a tag boundary); inferred `_`
middle sets flattening into a declared union; canonical containment refusals
(`expected AllocError, found All`) are correct sema behaviour, not bugs.

TESTS: 5
