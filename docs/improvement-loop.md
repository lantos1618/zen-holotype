# The Improvement Loop — Zen's self-sustaining fix engine

A repeatable cycle: **scout → triage → fix → land → repeat**, across four dimensions, under hard
guardrails. Drives `docs/goal-clean-correct-zen.md` and beyond. Designed to run for hours, mostly
hands-off, with the main thread as conductor and background agents as the fleet.

## One cycle

### 1. SCOUT (fan out — read-only, parallel, no worktrees)
One agent per dimension, each returns a **verified, ranked** findings list (evidence/repro required —
no speculation):
- 🐛 **Correctness** — differential + fuzz on current `main`; miscompiles, crashes, rejects-valid.
- ♻️ **Slop** — redundancy, dead code, dup logic, synonym sprawl, things that should be methods.
- 🏗️ **Build** — real-language gaps (missing stdlib/features), ranked by user-value.
- ✋ **Ergonomics** — clunky surface, boilerplate, inconsistent idioms, anything that makes the
  language feel worse to *write*.

### 2. TRIAGE (conductor)
Merge → dedup → rank by (severity × value). Assign each to a **lane**. Output: an ordered fix-queue.
Apply the **ergonomics veto** (below) — drop or rework anything that worsens the surface.

### 3. FIX (fan out — worktrees, gated)
Dispatch fixers: **parallel** for independent lanes, **serial** for compiler-core. Each fixer must:
oracle (isolated) ALL PASS · seed fixpoint byte-exact · adversarial verify · **demos/fixtures compile
unchanged** · open a PR. Land a correct partial rather than ship red.

### 4. LAND (conductor)
Gate each PR (deterministic gates are authoritative — see below) · merge · regen seed · verify `main`
fixpoint · clean worktrees · **resume/salvage any silently-dead agent** (the env kills them; worktrees
persist, so the work is never lost).

### 5. REPEAT
Re-scout the improved `main`. Track convergence: if a dimension yields no new verified findings for K
cycles, it's "dry" — deepen the search or retire it.

## Guardrails (non-negotiable, hard-won)
- **Ergonomics is a VETO.** A change that improves internals but makes the user-facing surface clunkier
  is rejected. The chat/calc/actor demos + `tests/fixtures` must compile & run unchanged. Same-or-cleaner.
- **Verify before delete.** "Slop" may be load-bearing (the 46 `_ok/_err` shims were *necessary* until
  expected-type inference landed). Prove a thing is dead/replaceable before removing it.
- **Adversarially verify.** A finding isn't real until it reproduces; a fix isn't done until the repro flips.
- **Deterministic gates are necessary but NOT sufficient.** Fixpoint byte-exact and emitted-C byte-diff
  are authoritative for the *compiler's own* code — but they MISS regressions in user-facing stdlib that
  the compiler tree-shakes (e.g. a broken unused `try_*` in `std.internal.resolve`: fixpoint stayed green,
  every user import broke). So an **isolated `make harness` must be ALL PASS to merge** — especially the
  `modules`/user-import suites, which are the only thing that exercises std-as-a-user-would.
- **Do NOT dismiss oracle failures as "flake."** Only ONE suite is load-flaky: `build result-paths`
  (subprocess-heavy, times out under concurrent load). A non-zero count is REAL until you've confirmed the
  F-marks are confined to THAT suite. Failures in value/verdict/emit/**modules**/boundaries/fuzz are bugs.
  (Hard-learned: 10 `modules value` failures were waved off as flake; they were a real regression.)
- **Serialize compiler-core, parallelize the rest.** `check.zen` is a single-writer lane (two editors =
  merge-hell). `std/`, `tests/`, `docs/`, and distinct compiler files are free parallel lanes.
- **One change = one reviewed, merged PR.** Small, independently-verified commits.
- **Cap the fleet + clean up.** Don't spawn zombies; remove worktrees after merge; resume the dead.

## The drive
Self-paced `/loop`. Each tick the conductor: lands ready PRs → resumes/salvages dead agents → if a SCOUT
round is in → triages it → dispatches the next fix-queue item → when the queue empties, starts a new
SCOUT round. Cadence ~4–5 min (catches the ~15–30 min agent-death pattern without burning cache).
