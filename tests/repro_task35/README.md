# Task #35 — wave-regression repros (3 holes in check_validate.zen)

Standalone `zenc check` / `zenc build` repros for the three bugs. Phase 2 folds
these into `tests/oracle_verdict.zen` as `VerdictCase` entries (and a build/run
case for C1); this dir is the phase-1 review artifact and is removed once the
oracle cases land.

Run from repo root after `make -f bootstrap/Makefile zenc`.

## CRITICAL 2 — generic callee disables arg-type checking of its CONCRETE params
- `c2_generic.zen`    — `gen<T>=(n:i32,x:T)`, `gen("s",5)` — BUG: `check` says ok (str into i32 `n`).
- `c2_nongeneric.zen` — identical non-generic — correctly `error[arg-type]`.
- `c2_i8.zen`         — `gen<T>=(n:i8,x:T)`, `gen(200,5)` — BUG: `check` says ok (i8 overflow).
- `c2_i8_nongen.zen`  — identical non-generic — correctly rejects.

Root cause: right-arity local generic calls are INLINED during `resolve_module`,
so the post-inline call check (`call_errs`/`arg_err_at`) never sees them. The
pre-inline pass that still has the call site (`check_module_arg_kind`, the `ka_*`
family) only checks TPARAM-typed param slots and only when the call carries a
turbofish `<…>`. A concrete slot (`n:i32`, `sep:u8`) of a generic callee is
therefore never arg-type checked. Impact: every stdlib API threads `MutPtr<A>`
so it is generic — arg-type safety is off stdlib-wide.

## CRITICAL 1 — generic forwarder launders a MutPtr past the #407 send-mut check
- `c1_direct.zen` — `h.send(.Poke(p))` with `p:MutPtr<i32>` — correctly `error[sendable]`.
- `c1_fwd.zen`    — `fwd<T>=(h,payload:T){ h.send(.Poke(payload)) }` — BUG: `check` says ok.

Root cause: the `sm_msg_mut` send-mut pass runs on RAW pre-monomorphization decls,
so the payload leaf infers as `.Named("T")`; `ty_reaches_mutptr`'s `.Named` arm
only inspects struct/enum decls — a bare tparam has neither → false → send passes.
With a call site binding T=MutPtr, `zenc run` exits 99 (cross-actor race).

## MAJOR 6 — enum member-access has no arm → "compiler bug" on the #1 newcomer trap
- `m6.zen` — `r.len` on `Result<i32,i32>` — BUG: `check` says ok, then `build`
  surfaces raw C wrapped in "internal: … compiler bug — please report".

Root cause: `member_err` handles struct / generic-struct / scalar receivers but
has NO enum arm — an enum/Result/Opt receiver falls to the lenient `false => 0`.
Every Vec/Map/stdin/str op returns a Result/Opt, so this is the #1 newcomer trap.
