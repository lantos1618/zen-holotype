# GOAL: Clean, Correct, Self-Hosted Zen

**Set 2026-06-26.** North-star for a multi-hour autonomous fleet run.

## North-star (the arc)
A self-hosted Zen that is **TRUSTWORTHY** (safety is a guarantee, not discipline), **CORRECT** (no
latent miscompiles), and **CLEAN** (one way to do each thing — no redundancy, no slop, no dead code).
Today Zen is "a self-hosting compiler that exposes a language" (~4/10 as a usable language). This goal
fixes the *foundation* so everything above it gets simpler: fix the one keystone compiler bug, collapse
the redundancy it was masking, unify the duplicated subsystems, and emerge measurably smaller + cleaner.

## The keystone insight
A single bug — **`inline_template` never substitutes type params** (check.zen ~1677: it threads only
value params through `xform_*`, leaving `ix.elem`/`l.elemTy`/`sd.elem`/`[M]` lets RAW → genc emits
`sizeof(void)`) — is the root cause of THREE separate "redundancies" the fleet just confirmed:
1. the concurrency **ring-buffer can't be unified** (generic `MutPtr<Struct<M>>` → `sizeof(void)`),
2. the **~20 `gstr_push` UAF-hoist workarounds** (side-effecting receiver duplicated on inline),
3. the **46 `_ok`/`_err` Result shims** can't collapse to a generic `ok<T,E>`/`err<T,E>` (only one
   type param inferred → `Result_cstr_void`).
Fix the inliner once and all three become removable. It is the highest-leverage change in the codebase.

## Milestones (ordered; compiler-core SERIALIZED; each gated)
**Gate for every milestone:** `make harness` ALL PASS · seed regen byte-exact (FIXPOINT) · adversarial
verify · PR + review + merge. De-slop before & after each increment.

- **M0 — Formatter unification** *(in flight, worktree `feat-unified-formatter`).* One comment-preserving
  AST formatter: multi-arm match split + `=>` align + inline-short + comments. Retire the line-reindenter.
- **M1 — THE INLINER FIX** *(keystone; serialize after M0 — both touch AST/check).* `inline_template`
  computes the tparam→arg binding and threads it through `xform_*`, applying `subst_ty_in` to `ix.elem`,
  `l.elemTy`, `sd.elem`, and `[M]` let-annotations. Adversarial tests: (a) `Box<M>.at` (the `sizeof(void)`
  repro), (b) generic `ok<T,E>` infers BOTH params (`Result_cstr_IoError`, not `_void`), (c) a `gstr_push`
  chain that no longer needs a hoist. Fully diagnosed in `pluggable-runtime-plan.md`.
- **M2 — Collapse what M1 unlocks.** Generic `ok`/`err` in std.core.result → delete the 46 shims;
  de-hoist the ~20 `gstr_push` workarounds; unify the 9 ring-buffer copies into one `Mailbox`/`Ring`.
- **M3 — Compiler-core dedup.** Remove dead O(n) `the_func`; merge 3× `dseg_eq*`; extract `sentinel_func`;
  merge data-field counters; one shared `param_list_has`; rename `collect_inits2`→`collect_inits`.
- **M4 — Concurrency cleanup.** `pool_*` free fns → `Pool` methods; settle verb sprawl (`pool_post` vs
  `pool_send`); delete alias bloat. (Ring-buffer already done in M2.)
- **M5 — De-slop + docs.** Consolidate overlapping docs (closures M0+M2, scope×2, parallel-scheduler);
  final repo-wide redundancy sweep; update MEMORY.

## Acceptance
- The inliner miscompile class is GONE (all three M1 adversarial tests pass; no `sizeof(void)`).
- Every redundancy the hunt found is either REMOVED or proven-NECESSARY-and-documented.
- ONE formatter; ONE ring buffer; ONE Result-ok/err; no `gstr_push` hoist workarounds.
- All gates green throughout; codebase measurably smaller (track LOC + shim/dup counts).
- Each milestone shipped as its own reviewed, merged PR.

## Orchestration rules (hard-won, from memory)
- SERIALIZE compiler-core agents (M0→M1→M3 touch parse/check → one at a time, or merge-hell).
- Parallelize only INDEPENDENT work (std files, docs) in separate worktrees.
- Integrate from immutable merged commits; regen the seed AFTER final regen, before push.
- Adversarially verify each guarantee; oracle + fixpoint gate EVERY change.
