# COMMENT_AUDIT.md

Review surface for the comment cull of `src/`. **No gate in this repo can see a
comment**, so this document is the only check on the work. Green gates below
prove the build survived; they prove nothing about whether the deletions were
right.

## Result

| folder | files | before | after | removed | % |
|---|---|---|---|---|---|
| `src/gen`  | 51 | 5609 | 5273 | 336 | 6.0% |
| `src/sema` | 35 | 4044 | 3967 |  77 | 1.9% |
| `src/std`  | 62 | 3596 | 3464 | 132 | 3.7% |
| `src/lsp`  | 19 | 1839 | 1782 |  57 | 3.1% |
| `src/zen`  |  7 |  784 |  734 |  50 | 6.4% |
| `src/fmt`  |  5 |  745 |  701 |  44 | 5.9% |
| **total**  | **179** | **16617** | **15921** | **696** | **4.2%** |

Comment ratio of `src/`: **27.2% → 26.3%**.

**4.2% is well under the 12-15% target and it is the honest number.** Every
folder was read in full. See "Why the yield is low" below — the short version is
that the premise of the task (that 27% comments implies a large filler band) is
false for this tree, and the evidence for that is stronger than the evidence for
any particular cut.

## Verification

Code identity was checked mechanically, not by eye. For every file, the sequence
of **non-comment lines** was compared against `git HEAD`:

```
checked 179 files; 0 with code changes
```

This is the highest-value check in the task, and it earned its keep three times:
it caught the identical slip in `zen_build.zen:emit_c`, `fmt_decl.zen:joins` and
`gen_c_fat.zen:write_thunk`, where deleting the comment directly above a
definition silently ate the space in `name = (args)` → `name =(args)`. No gate
in this repo would have caught that as a comment edit going wrong.

Discipline adopted after the first slip and circulated to every contributor:
**every edit's search and replacement text consists only of comment lines** —
never extend a match down onto a code line to anchor it.

---

# FALSE comments (score 0) — the highest-value find

**24 false comments across 6 folders. Five have live code shaped around them, and
one is a claimed safety net that does not exist.**

Every claim below was verified against the current tree by reading the code or
doc it refers to. **No code was changed anywhere in this task**, including the
code these comments have deformed — that is reported, not fixed.

## The dominant finding: one stale belief, propagated, with code built on it

Nine of the 22 are the same two claims, repeated across `src/gen` and
`src/sema`, and **both are false**:

### "sema does not type a call"

- `gen_c_call.zen:26` — "sema doesn't type a call yet… The fallback stops firing
  the moment sema types a call."
- `gen_c_expr.zen:128` — same claim at `ty_of`.
- `gen_c_ptr.zen:86` — "Sema does not type a call, so a binding that holds…"

**Contradicted six lines above the first one.** `gen_c_call.zen:20` already
says "`Checker.call_memo` under the call's node id, so `loop`'s six declarations
arrive here as a decision". Verified: `call_memo` is declared at
`sema_check.zen:127` (`Map<ExprId, DeclId>`), read at `:215`, written at `:220`;
`sema_type.zen:398` dispatches `Call(k) => c.call_type(...)`; `sema_call.zen:131`
defines `call_type*`.

### "instantiation does not SUBSTITUTE"

- `sema_check.zen:497` (`uninstantiated`) — "generic instantiation does not
  SUBSTITUTE, and this is where that costs something… Every line of this deletes
  when substitution lands." **CODE IS SHAPED AROUND IT.**
- `sema_bound.zen` (`satisfies_bound`) — same claim, second site.

**Contradicted by the folder's own index file.** `sema.zen:22` states
"INSTANTIATION SUBSTITUTES (`sema_inst.zen`)". Verified: `subst*` is declared at
`sema_inst.zen:120` with a full structural walk (`subst_kind`, `subst_named`,
`subst_res`, `subst_fn`, `subst_union`, `subst_list`) and is called from
`sema_apply.zen:240`, `sema_apply.zen:535` and `sema_member.zen:700`.

The code shaped around it is the whole `uninstantiated` disjunct of
`assignable`, reached from every assignability question in the folder. Whether
its arms are now dead could not be determined by reading — **that is a question
for a human, and it is the most valuable thing in this document.**

## Code shaped around a false comment (4 sites)

**1. `sema_check.zen:497`** — the `uninstantiated` disjunct of `assignable`,
above.

**2. `sema_ty.zen:663` — `key_before`, a dead duplicate of a closed gap.**

The comment says `std.text` "doesn't declare one yet… Delete this once text_str
grows an ordering." Verified false three ways:

- `str.before` exists at `text_str.zen:65`, exported via `text.zen:11`.
- `text_str.before`'s own comment names "sema's type-key ordering" as one of
  **three** duplicates it was written to consolidate.
- `sema_cycle.zen:294` **already calls** `str.before`, and `sema_cycle.zen:588`
  explains it declines to import `ast_find.before` precisely because `before` is
  "ALSO `str`'s byte order".

`docs/SEMA_BOOTSTRAP_FIXES.md` §4 states outright: *"The moment it exists,
`key_before` deletes and an import replaces it."* It exists.

Dead weight, **not deleted**: `key_before` (`sema_ty.zen:664`), its re-export
(`sema.zen:53`), its one consumer `Types.before` (`sema_ty.zen:611`).
`SEMA_BOOTSTRAP_FIXES.md` §4 is stale for the same reason (docs/ out of scope).

**3. Eight `§10` sites asserting a gap the cited doc records as CLOSED.**

`sema_check.zen`, `sema_def.zen`, `sema_call.zen` (×2), `sema_member.zen` (×3),
`sema_supply.zen` all said, present tense, "a loop binding read inside a nested
closure does not resolve". Verified: `docs/SEMA_BOOTSTRAP_FIXES.md:358` reads
**"CLOSED as written, 2026-08-08"**, and :382 says "The seven workaround sites
named below are therefore no longer required… but each site should be re-tested
rather than assumed."

Code shaped around it: helper functions that exist only as that workaround.
**Not deleted.** Comments now cite §10 as closed and carry the doc's own
instruction to re-test before removing. (Note a discrepancy worth a human's eye:
the doc names **seven** sites; **eight** were found in the tree.)

**4. `std/env/env.zen:63` — `FsError.OutOfMemory`, and an unresolved
contradiction.**

The comment says "the compiler is written in the seed subset, which has no error
unions (PLAN.md 0.5) — that's what puts OutOfMemory here", and "When unions
arrive this becomes `Res<String, FsError | AllocError>` and the variant goes."

The PLAN.md citation is accurate (`docs/PLAN.md:220`). **But error unions
demonstrably work**: `std/core/io.zen:14` declares `WriteError = IoError |
AllocError` and it is used in real signatures throughout `text_fmt.zen`
(`add*`, `add_u64*`, `add_i64*`, `add_bool*`). Meanwhile `FsError.OutOfMemory`
(`env.zen:76`) is live, matched at `zen_build.zen:709`, and exists *only*
because of the claimed limitation.

**Deliberately NOT rewritten.** Either PLAN.md is stale or `FsError` avoids a
union for a reason not written down, and reading could not settle which. This is
flagged, not decided. `lsp_json_read.zen:14` leans on the same premise.

**5. `allocs_op: 0` — three files cite a safety net that does not exist.**

The worst kind of false comment: not a stale limitation, but a claimed
*guarantee*. `src/std/core/loop/loop_iter.zen:14` said `bench_loop.zen` "**gates**
that last one at `allocs_op: 0` — a hit of 1 means an inliner regression, boxing
the body, **and fails the build**." `src/std/core/range.zen:19` said it "**gates**
a fold at `allocs_op: 0`". `gen_c_inline.zen:15` made the same claim.

Verified — nothing gates it:
- `tests/bench/bench_loop.zen:6` **does declare** `Budget(name:
  "fold_stack_array", allocs_op: 0)`, and calls it "the load-bearing number".
- `scripts/bench.py:14`: "allocs_op/bytes_op are **NOT measured** — that needs
  compiler instrumentation that does not exist yet (deferred, deliberately)".
  `:379` prints `allocs_op/bytes_op: unmeasured`.
- `make bench` is a **separate target, not part of `make test`** (Makefile:185).

So the budget is written down, never measured, by a target the test run does not
invoke. Anyone trusting "an inliner regression fails the build" is unprotected —
and this is precisely the vacuous-gate class where a wrong answer that *looks*
guarded survives every oracle. `gen_c_inline.zen` was corrected to "declares"
during the cull; the other two now say declared-not-enforced and name the
evidence. **No code changed.** Whether the budget should be enforced, or the
claims dropped, is a call for a human.

## Other false comments (verified, no code shaped around them)

- **`std/env/env.zen:25`** — "the IoError every Console signature names and **no
  module declares yet**". `core/io.zen:6` declares it; it reaches the prelude via
  `core.zen:48` and `std.zen:21`. Corrected to name `std.core.io`.
- **`gen_c_flow.zen:17`** — "exhaustiveness is sema's to check, and **until it
  does**, a value matching no arm traps there". Sema checks it:
  `sema_match.zen`, `sema_case.zen`, and the `NotExhaustive` diagnostic at
  `sema_diag.zen:123`/`:204`. (`zg_unreachable` remains correct defensive
  codegen; only the "until it does" was false.)
- **`zen_build.zen:27`** — "WHAT STOPS THIS FILE SHORT OF A COMPILER is written
  down at `deliver`." `deliver` documents no limitation; it recorded one that had
  been CLOSED by `Fs.write`. Reader is sent somewhere that says the opposite.
- **`zen_order.zen:45`** — labelled "Evens then odds" over code that does odds
  first (`i < half` → `i*2+1`), contradicting the rest of its own sentence. This
  is the permutation `tests/determinism/check.sh` check 3 varies.
- **`lsp_serve.zen:790`** — an orphaned six-line doc comment for a function that
  is not in the file (`own` moved to `lsp_reply.zen` as `own_str`; this file now
  imports it). It also claimed `lsp_diag.zen` has an `owned_str` — it does not.
- **`lsp_def.zen:22` and `lsp_compl.zen:37`** — "TWO WAYS IN… Both rebuild per
  request; there is no cache." There are **three**: `definition_with` (:143) and
  `complete_shared` read the shared slot's checker, which *is* the cache, and
  `lsp_serve.zen` calls them.
- **`gen_c_member.zen:37`** — a refusal list contradicted by the file's own code.
- **`gen_c_cap.zen`**, **`gen_c_read.zen:637`**, **`gen_c_op.zen:241`**,
  **`gen_c_fs.zen:77`**, **`gen_c_decl.zen:59`**, **`gen_name.zen:37`** — stale
  refusal/limitation claims and one stale cross-reference; each detailed in the
  gen appendices.
- **`sema_member.zen:187`** — cited "§7 records twenty-two diagnostics". §7 is a
  different entry entirely; §8 is the one meant and says **twenty-three**
  (`SEMA_BOOTSTRAP_FIXES.md:316`). Both the section and the number were wrong.
  *Flagged because it touches a protected measurement; corrected to match the doc
  verbatim, and trivially revertible.*
- **`sema_check.zen:104`** — "the memo tables. **All three**…" above a list of
  two, in a struct with seven.
- **`sema_depth.zen:477`** — a rhetorical question whose **polarity was backwards**
  relative to the function it described.

## Defects found but NOT fixed (reported only)

- **A garbled sentence, pre-existing in HEAD.** `gen_c_try.zen:18`: *"which made
  every merge / DESIGN.md promises a report"* is not a sentence — a word was
  dropped. Left alone rather than guessing at intent. Probable reading: "which
  made every merge DESIGN.md promises **into** a report."
- **Stranded comment paragraphs** — two paragraphs jammed onto the wrong function
  with no separating `//`: "CONSTRUCTING IS A RESOLUTION TOO" on
  `sema_call.no_overload` (belongs to construction), and "Both sides, always" on
  `sema_diag.write_export` (belongs to `write_types`). Moved onto the functions
  they describe, no text lost. **This is a defect class worth grepping for.**
- **~11 drifted line-number citations**, all verified by reading both sides, none
  rewritten: `design_lsp.md:157`→`:248`, `design_lsp.md:174`→`:209`,
  `TESTING.md:48`→`:49`, `PLAN.md:200`→`:220`, `PLAN.md:194`→`:220`,
  `num.zen:124`→`:112`, `env.zen:45`/`:83` point at unrelated paragraphs,
  `DESIGN.md:302` is a `try()` example rather than the position rule.
  **`PLAN.md:137` ("names a second grammar as the failure") could not be found
  anywhere in `PLAN.md` — unresolved, flagged rather than guessed.**
  Section-level (`§N`) citations were all checked and still hold.
- **Duplicated code**: `lsp_def.zen:disk_text` and `lsp_diag.zen:on_disk` are the
  same five lines, both private — a real STYLE.md second-caller violation. The
  comment at `lsp_def.zen:208` describes it accurately; the code is the problem.
- **A diagnostic naming a rule the code stopped enforcing** —
  `gen_c_const.zen:158`. It refuses with *"a constant whose value is not a
  literal"*, but the gate actually applied is `is_pure_value`, which admits
  operators, constructions, nullary variants and type constants. **Rejected
  constants are told the wrong reason.** This is user-facing and is the most
  consequential wrong-code finding; not fixed.
- **`gen_c_member.zen:774`** says "Six lowerings" and lists seven (there are
  seven `member_symbol` call sites).
- **A backend divergence, both figures protected**: `gen_c_decl.zen` puts the
  driver corpus test at **3754** functions, `bootstrap/gen_c.py` at **4086**. The
  other number in the pair (4069) agrees exactly. Not reconciled.

---

# What was cut, by lever

Deletion was the minority operation. The four levers, in the order they were
applied:

### 1. Deduplicate (largest yield)

One point, one place: the fullest statement stays at the most discoverable site,
other sites defer and keep only their own distinct fact.

- `parser.zen` wrote out the same open bootstrapper bug **twice in full**, 140
  lines apart. Kept at `nothing`; `took`/`missed` now cross-reference it and keep
  only "one arm returning a typed `Res<T, E>` pins the whole match". 22 → 12.
- `fmt_break.zen`'s homogeneous-sequence argument for `fill` appeared at **five**
  sites (its header, `Cand.fill`, `add_array`, `emit_break`, and `fmt.zen`'s
  header). Kept once.
- `zen_path.zen` stated the determinism-oracle argument **three times** in one
  file. Kept at the header with an explicit "every 'must not reach a Span' note
  below is this rule".
- `zen_cli.zen` stated the argv-offset fact twice, ten lines apart.

### 2. De-rhetoricize

**88 comments written as questions restating the function's own name**, converted
to the assertions they imply, content preserved. `gen` 33, `sema` 23, `std` 17,
`lsp` 10, `fmt` 5. One (`sema_depth.zen:477`) turned out to have its polarity
backwards — the question form had hidden a wrong statement.

### 3. Stale history, with each claim checked

This lever produced most of the FALSE list above, which is exactly why it was
run: "this used to be", "was three lines inside X", "does not yet". Deleting the
narration is worth a line or two; **checking the claim is worth the whole task.**

### 4. Closing flourishes

Final sentences restating the sentence before them in more rhetorical words.

---

# Deliberate scope decisions

- **Section banners kept** (ratified). Navigation, not commentary; 434 lines,
  under 3% of volume.
- **No code changed anywhere**, including code shaped around false comments.
- **No new factual claims invented.** A mid-task rule after one contributor
  rewrote a stale forward-looking note into a confident assertion about the
  present ("substitution has since landed and this arm was never re-measured")
  without evidence for either clause. That is *worse* than the stale comment it
  replaced — authoritative, plausible, invisible to every gate. Reverted, and the
  rule applied retroactively across all folders, catching six such sites. The
  standing rule: **you may delete a claim shown false, and compress a claim; you
  may not invent one.** An unresolved flag in a report is a good outcome; a
  confident wrong sentence in the source is not.
- **Measurements kept exact** — `WIDTH`'s "372 of 52092 lines", `report`'s "all
  117 of `tests/must-fail`", `MAX_DEPTH`'s two measured tables, `eq.zen`'s "45
  differential tests". Two measurements were changed, both flagged above with
  their evidence (`sema_member.zen:187`, and the `allocs_op` gate below).

---

# Why the yield is low

The task's premise was that a 27% comment ratio implies a large filler band. **It
does not, and the evidence is stronger than for any individual cut:**

1. **Grepping all of `src/` for the classic low-value doc-comment openers**
   (`Returns`/`Gets`/`Sets`/`Creates`/`Adds`/`Helper`/`Convert`) returns **one
   match across 179 files** — and that one is a high-value comment about an
   integer underflow.
2. **Sentence-level duplication was measured**, not assumed: bucketing every
   7+-word comment sentence in `src/sema` by normalised word sequence found
   **six exact cross-file repeats**, all deliberate citations or
   cross-references.
3. **The mass is in file headers** — ~4,556 lines tree-wide, ~700 in `src/sema`
   alone. These are the design record: subject, split justification, rejected
   alternatives. They compress by 10-15% and then the next cut removes an
   argument.

Whole files yielded nothing after a full read, correctly: `gen_c_frame.zen` (89
lines, five struct docs each carrying a distinct fact), `sema_trap.zen` (138
lines, every one a spec citation, measurement or refusal rationale),
`std/core/range.zen` and `std/core/eq.zen` (DESIGN.md citations and the
`allocs_op: 0` and 45-tests measurements), `lsp_colour.zen` and
`lsp_json_read.zen` (numbered spec-conformance lists with exact UTF-16
arithmetic). **41 of 61 editable files in `src/std` came out unchanged.**

Applying the literal 8.5 threshold would have been destructive: the 7-8 band in
this tree is spec citations and domain facts, not filler.

**The real return on this task was not the 696 lines. It was the 24 false
comments — the five sites where live code is shaped around a limitation that no
longer exists, and the claimed `allocs_op: 0` gate that nothing measures.**

---

# Gates

Exit codes captured separately from any pipe (`cmd > log 2>&1; echo $?`), because
`cmd 2>&1 | tail` reports the status of `tail`.

```
make build                BUILD_EXIT=0
make test                 TEST_EXIT=0      497 passed, 0 failed, 4 deferred
make fmt                  FMT_EXIT=0       (see note)
make cap                  CAP_EXIT=0       51 over 500, 0 over 800
python3 scripts/style.py  STYLE_EXIT=0     10 rules, 13257 sites, 0 violations
make fixpoint             FIXPOINT_EXIT=0  stage2.c == stage3.c
```

**`make fmt` note.** It failed first time (`FMT_EXIT=2`, "2 of 585 files are not
formatted") — exactly the predicted consequence of comments being tokens to the
formatter. Deleting two whole comment blocks left a double blank line in
`gen_c_read.zen` and `gen_c_inline.zen`. Running `./zen fmt` on those two absorbed
them, and the gate is green. That reflow is included in this commit.

Those two removed blank lines are the **only** non-comment-line differences in the
entire tree; everything else is byte-identical. `make test` reports 497 rather
than 494 because an unrelated branch was merged into this worktree mid-task,
adding three tests.

**These gates prove the build survived. They prove nothing about whether the
deletions were right — that is what the rest of this document is for.**



---

# Appendix — per-folder detail



<a name="audit_gen_A.md"></a>

## Appendix: src/gen — section A (11 largest files)

# src/gen (coordinator's own 11 files) — 1702 comment lines before, 1415 after, 287 removed (16.9%)

Files in this section: `gen.zen`, `gen_diag.zen`, `gen_emit.zen`, `gen_name.zen`,
`gen_c/gen_c.zen`, `gen_c/gen_c_report.zen`, `gen_c/gen_c_state.zen`,
`gen_c/gen_c_try.zen`, `gen_c/gen_c_member.zen`, `gen_c/gen_c_expr.zen`,
`gen_c/gen_c_call.zen`. The other 40 files are covered by sections B–F.

Per file (before -> after):

| file | before | after |
|---|---|---|
| gen.zen | 32 | 30 |
| gen_diag.zen | 48 | 45 |
| gen_emit.zen | 64 | 64 |
| gen_name.zen | 166 | 157 |
| gen_c/gen_c.zen | 66 | 64 |
| gen_c/gen_c_report.zen | 15 | 9 |
| gen_c/gen_c_state.zen | 268 | 249 |
| gen_c/gen_c_try.zen | 227 | 211 |
| gen_c/gen_c_member.zen | 225 | 219 |
| gen_c/gen_c_expr.zen | 210 | 200 |
| gen_c/gen_c_call.zen | 181 | 167 |

Every file verified with `python3 /tmp/codecheck_keep.py` after every edit:
ALL CODE IDENTICAL on all eleven, re-verified against the REBUILT `/tmp/srcbase`
after the accidental merge.

## FALSE (score 0)

### 1. `gen_c_call.zen:26-29` — false claim AND a false pointer. HIGHEST VALUE.

Quoted:

> THE TYPE FALLBACK LIVES HERE for the same reason: sema doesn't type a
> call yet, so it doesn't type a `.try()` on one either, and only the
> place that already resolves callees can answer. The fallback stops
> firing the moment sema types a call.

False on both halves:

- **"sema doesn't type a call yet"** — sema types a call. `src/sema/sema_type.zen:398`
  reads `Call(k) => c.call_type(id, node, k, ctx)`; `src/sema/sema_call.zen:131`
  defines `call_type*`, which resolves through `chosen` (:465) and `chosen_ret`
  (:480) to `instantiate`, returning a real `TyId`. `src/sema/sema_type.zen:393`
  likewise types `Try`.
- **"THE TYPE FALLBACK LIVES HERE"** — it does not. There is no fallback function
  anywhere in `gen_c_call.zen` (grep for `fallback` in that file returns only this
  comment and an unrelated use of the word at :383). The fallback is
  `fallback_type` at `gen_c_expr.zen:365`, reached from `sema_answer`
  (`gen_c_expr.zen:232-239`).

**Code shaped around it: YES, but in a different file.** `gen_c_expr.zen`'s
`fallback_type` -> `call_type` -> `named_call_type` -> `declared_call_type` ->
`def_call_type` -> `function_ret` -> `decl_ret` -> `written_ret` is roughly 50
lines of live code. It is still *reachable* — `sema_answer` falls back when sema's
answer is `Unknown`, which happens — so the code is not dead. But the stated
*reason* and the stated *location* are both wrong, so anyone acting on
"the fallback stops firing the moment sema types a call" would look in the wrong
file for a condition that has already been met and conclude the code was dead.

Action: paragraph DELETED from `gen_c_call.zen`. Code untouched.

Note: the *narrower* true statement is already written correctly elsewhere in this
folder — `gen_c_infer.zen`'s header: "Sema records a call's instantiation and value
type only inside bodies it checked (top-level decls). Calls inside MEMBER bodies get
nothing recorded."

### 2. `gen_c_expr.zen:128-132` — same false claim, at `ty_of`.

Quoted:

> Where it does not yet (sema doesn't type a call, so not a `.try()` on
> one either), the callee's own declaration is read instead — the same
> "degrade to your own resolution when absent" the bootstrapper's
> backend documents. The fallback stops firing the moment sema types a
> call.

Same evidence as #1. **Code IS shaped around it here** — this comment sits directly
above `ty_of`, whose `sema_answer` -> `fallback_type` path is the code in question.

Action: the false parenthetical and the false final sentence were DELETED; the
remaining sentence now describes what the adjacent code plainly does
(`sema_answer` at :232-239 uses sema's answer unless it is `Unknown`). No new
claim was introduced. Code untouched.

### 3. `gen_c_member.zen:37-40` — stale refusal list, contradicted by the file's own code.

Quoted:

> WHAT THIS FILE REFUSES, it refuses BY NAME: a generic receiver needing
> monomorphisation, a `::` parameter passed by address — each a
> `GenFault` with a position, never C that compiles but means something
> else.

Both examples are false:

- **"a generic receiver needing monomorphisation"** is contradicted 680 lines later
  by this file's own `refuse_method` comment ("A GENERIC RECEIVER IS NOT A REFUSAL
  ANY MORE: `Vec<GenDiag>.add` is `Vec.add` emitted at `GenDiag`"). The code agrees
  with `refuse_method`, not with the header: `refuse_method` (:724) tests
  `(f.tparams.len > 0) || (has_body(f) == false)` — the MEMBER's own type
  parameters, not the receiver's.
- **"a `::` parameter passed by address"** is refused nowhere in the file. Grepping
  every `unsupported(` call site in `gen_c_member.zen` gives exactly four fault
  texts: "a call through a function-valued field" (:575), the three
  `method_fault`/`method_fault_2` strings (:730/:737/:738), "a method on a receiver
  whose type arguments nothing settles" (:765), and "a call to an impl-supplied
  member" (:1036, :1053). None mentions `::` or an address. `::`-by-address is
  IMPLEMENTED, not refused — `gen_c_call.write_address` (:1062).

**Code shaped around it: NO.** The refusals the code actually performs are all
described accurately at their own sites.

Action: the two stale examples were DELETED; the true general rule ("it refuses BY
NAME: a `GenFault` with a position, never C that compiles but means something
else") was kept. No replacement examples were invented.

### 4. `gen_name.zen:37-38` — stale pointer.

Quoted: "C STANDARD TARGETED IS C99, stated once in the runtime banner in
`gen_c.zen`".

The C standard is stated once as `C_STANDARD* : str = "C99 (ISO/IEC 9899:1999)"` at
`gen_c/gen_c_runtime.zen:34`, not in `gen_c.zen`. (`gen_c.zen` re-exports the name,
which is probably how the pointer drifted.) No code shaped around it.

Action: pointer corrected to `gen_c_runtime.C_STANDARD`, which I read directly.

## Reported, NOT changed (wrong, but not mine to fix)

### `gen_c_member.zen:774` — a count that is off by one.

> Six lowerings reach a member this way — a method, `eq`, `index`, an associated
> function, `raw`, `drop`, `toString` —

That list has **seven** items, and there are **seven** call sites of `member_symbol`:
`gen_c_display.zen:199` (toString), `gen_c_index.zen:242` (index),
`gen_c_assoc.zen:371` (associated function), `gen_c_alloc.zen:300` (raw),
`gen_c_own.zen:346` (drop), `gen_c_member.zen:816` (a method),
`gen_c_member.zen:967` (eq). The word "Six" is simply wrong. Left alone per the
brief's "keep numbers EXACT / do not fix" rule — flagging it for the merge.

## Deduplicated

- **"the walk is reachability-driven"** — stated in full in `gen_c_decl.zen`'s
  header, again in full at `gen_c_state.zen:115-123` (`fn_queue`), and again at
  `gen_c_call.zen:866-869` (`call_reachable`). Kept in `gen_c_decl.zen`; the other
  two now state only their own local fact and point there. -9 lines.
- **"a generic function is emitted once per distinct set of type arguments"** —
  `gen_c_mono.zen`'s header owns it. `gen_c_state.zen:129-134` (`fn_insts`) and
  `gen_c_call.zen:838-842` (`call_settled`) restated it; both now defer, keeping
  their own facts (the symbol at the call site and above the body must be the same
  bytes; a free parameter mangles to one letter). -4 lines.
- **"put the type parameters back in scope while a declared type is read"** —
  `gen_c_mono.zen`'s header owns it; `gen_c_call.zen:912-915` (`signature_of`) and
  `gen_c_member.zen:830-833` (`method_sig`) restated it. Both now defer. -2 lines.
- **"`tcode` is injective, so two types share a name exactly when they are one
  type"** — `gen_c_type.zen`'s header owns it; `gen_c_state.zen:233-235`
  (`type_index`) now states only "the name IS the type". -1 line.
- **"a tag is a function of the DECLARATION, never an instantiation; `Res<i32, E>`
  and `Res<i32, F>` share `Ok`"** — `gen_c_layout.zen`'s header owns it;
  `gen_name.zen:258-262` (`sym_variant`) repeated it verbatim and now points there.
  -3 lines.
- **"`Inst` is two parallel lists filled from `tparams`, never a `Map`"** —
  `gen_c_mono.zen`'s header owns it; `gen_name.zen:228-231` (`write_targs`) now
  defers. -1 line.
- **"`Res` is structural: `TyRes` carries no declaration because `Res<T>` and
  `Res<T, E>` are two arities of one name"** — stated in `gen_c_call.zen`'s header,
  `gen_c_type.zen`'s header, and at `gen_name.RES_PATH`. `gen_c_type.zen` owns it
  (it is that file's subject); `gen_name.zen:58-62` now keeps only its own fact
  (the library path is written down once, here). -2 lines.
- **"a diagnostic is a value, not a raise / the only Err is AllocError"** — stated
  in `gen.zen`'s header, `gen_diag.zen`'s header, and `gen_c_report.zen`'s header.
  `gen_diag.zen` owns it; the other two now point at it. -3 lines.
- **"a copy of a `Vec`-owning value diverges from the original on first growth"** —
  `gen_emit.zen` (about the buffer), `gen_c_state.zen` (about the `Checker`) and
  `gen_c.zen:57-58` (about the `Checker`, again). `gen_c_state.zen` owns the
  `Checker` version; `gen_c.zen` now points there. `gen_emit.zen`'s is about a
  different value and was kept. -1 line.
- **The spill distinction (`spills` vs `spills_anywhere` vs `spill_temp`)** —
  `gen_c_expr.zen` stated it three times: header lines 9-15, at `spills`/
  `spills_anywhere`, and again at `expr*`. The header keeps it; the two sites keep
  only their own facts (which callers ask; the `.try()`-three-parens-deep case; that
  the temporary is declared and filled BEFORE the statement being built). -7 lines.
- **`gen_c_try.zen` header vs its implementation sites** — the header's five
  arguments (declared-vs-structural construction, one set in two spellings, strict
  widening as a re-tagging, what is still not lowered) were each restated at length
  at `propagate_wider`, `widen_or_report`, `retag_or_report`, `tagged` and
  `write_copy`. Header keeps each argument; the sites now carry only what is local
  to them (`set_of` is the question; the fork is here rather than in `carrier`; a
  member added anywhere but last shifts every rank after it; `union_ty` flattened
  `WriteError` into four members). -14 lines.
- **`gen_c_state.zen`'s five-bullet header vs its own field comments** — the header
  already argues the local-scope numbering, the temporary counter, the helper
  family and the body buffer. `declare`, `reset_frame`, `need_helpers` and the
  `buf` field each re-argued one of them; each now keeps only its own fact. -8 lines.
- **`h` is not a value / recognised at the NAME** — `gen_c_handle.zen`'s header owns
  it and even names `lower_dot_call` as the site. `gen_c_member.zen:91-94` restated
  it; now points there. -1 line.
- **the symbol of a member is the TYPE's qualified name plus the member's** —
  stated in `gen_c_member.zen`'s header, at `write_method_call`, at `member_symbol`,
  and in `gen_c_state.MethodRef`. Header keeps it; `write_method_call` defers. -1 line.
- **`gen_c_report.zen`'s four one-line comments** — each restated the matching
  `GenFault` variant comment in `gen_diag.zen:38-41` word for word. Deleted; the
  header now says "one per `GenFault` the lowerings raise". -6 lines.

## De-rhetoricized

- `gen_c_state.zen:print_used` — "did anything reach `println`? The print floor is
  emitted only for..." -> "The print floor is emitted only for..."
- `gen_c_state.zen:fs_used` — "did anything reach the filesystem? The two POSIX
  headers..." -> "The two POSIX headers..."
- `gen_c_state.zen:stdin_used` — "did anything read standard input? Its own flag
  and not `fs_used`, because..." -> "Its own flag and not `fs_used`: ..."
- `gen_c_state.zen:scope_used` — "did anything reach `@scope`? The block record..."
  -> "The block record and its runtime are emitted only for a program that defers,
  on the same rule as `print_used` above."
- `gen_c_state.zen:type_index` — "Is this type already queued? The name is the
  identity..." -> "The name is the identity..."
- `gen_c_state.zen:bound_in_frame` — "Is `name` bound in THE BODY BEING LOWERED?"
  -> "Bound in THE BODY BEING LOWERED."
- `gen_c_expr.zen:spills` — "Does this form need statements of its own? A spilling
  form may not appear..." -> "A spilling form may not appear..."
- `gen_c_expr.zen:spills_anywhere` — "Does lowering this expression need statements
  of its own ANYWHERE inside it?" -> "Whether a spill hides ANYWHERE inside, which
  is the half of the header's distinction short-circuiting needs."
- `gen_c_call.zen:receives` — "Is the receiver this declaration's first parameter?"
  -> "Whether the receiver is this declaration's first parameter."
- `gen_c_member.zen:reaches` — "Does the dot reach this name through an IMPL rather
  than the declaration's own body?" -> "Whether the dot reaches this name through
  an IMPL rather than the declaration's own body."
- `gen_c_try.zen:tagged` — "Has this set a tag constant for `m`? A structural set
  composes one..." -> "A structural set composes a tag constant out of the two type
  codes and always has one."

After this pass, zero rhetorical-question comments remain in these eleven files.

## Compressed (score 7-9)

- `gen_c_state.zen:MethodRef` — 21 -> 16 lines. Both regression records kept EXACT
  (`Cursor.peek()`/`peek(ahead)` lowered under one symbol; `Display`'s two arity-two
  `toString`s). Merged the two "a name is not an identity" / "an arity is a
  projection" paragraphs, which reached the same conclusion twice, and dropped the
  closing "which is a redefinition and a link error from one missing field", which
  restated the sentence before it.
- `gen_c_try.zen:propagate_wider` — 14 -> 10. Kept the DESIGN.md quote and `set_of`;
  dropped the `WriteError`/`Error` worked example, which the header already spells out.
- `gen_c_try.zen:retag_or_report` — 19 -> 18. Kept "only the TAG is mapped" and the
  all-or-nothing argument in full; the opening paragraph now points at the header.
- `gen_c_try.zen:Carry` — 19 -> 15. All five cases kept; the paragraph breaks that
  repeated "a variant name and a member type are not the same thing" collapsed.
- `gen_c_try.zen:write_copy` — 13 -> 12. DESIGN.md's "Canonical numbering makes the
  widening a copy" kept verbatim; the flourish introducing it ("Bytes are the whole
  of the meaning, which is") cut.
- `gen_c_state.zen:need_helpers` — 5 -> 4. Kept the "a family, not a single helper"
  argument; the header already says one family per type actually used.
- `gen_name.zen:sym_union_member` — 8 -> 6. Kept the `zu_m10AllocError` layout fact;
  replaced "now that `gen_c_layout.write_enum_tags` numbers a union-reading enum
  canonically, so propagation between them is a copy, not a re-tagging map" (a
  restatement of `gen_c_try.write_copy`) with a pointer to it.
- `gen_diag.zen:GenFault`/`write_bound` — the `Overrun` argument appeared three
  times (header, the variant comment, `write_bound`). `write_bound` cut to one line.
- `gen_c_member.zen:lower_fat_or_method` — dropped "the whole reason
  monomorphisation survives", which restated the sentence before it.

## Trimmed closing flourishes (Lever 4)

- `gen.zen` — "and is cheap insurance regardless" (the sentence already said the
  seam costs nothing).
- `gen_c_try.zen` header — "Nothing converts, and there is still no From;" (the
  paragraph above already asserted both).
- `gen_c_try.zen:wrap_error` — "which is what the old report was telling the truth
  about" (stale history + restatement).
- `gen_c_try.zen:within` — "and asking it is what keeps a widening this backend
  writes from disagreeing with the containment sema admitted the `.try()` on"
  (`widen_into_set` makes the same point 40 lines above).
- `gen_diag.zen` — "A limit nobody hits is fine; a limit hit silently is not."
- `gen_c_state.zen:reset_frame` — "so a function's temporaries are a function of its
  own body" (the header bullet says exactly this).
- `gen_c_expr.zen` header — "and left when this file outgrew its cap" (refactor
  narration), plus the parenthetical restating `gen_c_op.zen`'s own three-rule list.
- `gen_c_call.zen:call_kind` — comment deleted entirely; it restated the header's
  opening sentence and nothing else.

## Refused to cut

- Every DESIGN.md / PLAN.md / STYLE.md / TESTING.md / C11 / C99 citation, and
  `docs/SEMA_BOOTSTRAP_FIXES.md` at `gen_emit.number`. On that last one I checked
  the claim rather than assuming: `std.text`'s integer writers `add_u64`/`add_i64`
  (`src/std/text/text_fmt.zen:83,88`) do return `Res<(), WriteError>`, so
  "`std.text` has no `AllocError`-only integer writer" is TRUE and stays.
- `gen_c_expr.zen:local_answer` (the `Vec<Diag>.get` / `Vec<TyId>.get` memo bug and
  the `Map<K,V>.confirms` / `str.eq` bug) and `gen_c_expr.zen:ptr_answer` (the
  `src.back(8)` thirty-two-byte stride bug). Three regression records with
  measurements; all kept whole.
- `gen_c_expr.zen:sugar_call_type` — the `println` / `needs_hoist` / `return 0;`
  regression record.
- `gen_c_expr.zen:lower_int_literal` — the C99 decimal-constant constraint violation
  and the `u64.MAX` / FNV basis warning.
- `gen_c_print.zen`-style refusal arguments generally, and `gen_c_state.zen`'s
  "ENTERING AN INSTANTIATION IS NOT A STACK".
- `gen_name.zen`'s five PLAN.md 0.4 decisions, including the two worked mangling
  examples (`2_5alpha10beta_gamma` / `2_10alpha_beta5gamma`) — that is the whole
  proof that the scheme is unambiguous.
- `gen_c.zen`'s 34-line file index. It is navigation, like a section banner.
- All section banners.

## Process note

One edit deleted four comment lines by anchoring upward onto the preceding blank
line, which ATE the blank lines separating four declarations in
`gen_c_report.zen`. `codecheck_keep.py` caught it (blank lines count as code lines
to that checker) and the blank lines were restored; final state ALL CODE IDENTICAL.
The safe pattern is to match the comment text INCLUDING its own trailing newline.



<a name="audit_gen_B.md"></a>

## Appendix: src/gen — section B

## gen/gen_c (B: alloc, array, assoc, bound, build, cap, const) — 645 comment lines before, 609 after, 36 removed (5.6%)

Per file (before -> after, removed):

| file | before | after | removed |
|---|---|---|---|
| gen_c_alloc.zen | 78 | 75 | 3 |
| gen_c_array.zen | 78 | 76 | 2 |
| gen_c_assoc.zen | 64 | 62 | 2 |
| gen_c_bound.zen | 110 | 105 | 5 |
| gen_c_build.zen | 141 | 132 | 9 |
| gen_c_cap.zen | 121 | 109 | 12 |
| gen_c_const.zen | 53 | 50 | 3 |

`python3 /tmp/codecheck_keep.py` run on all seven after every edit: ALL CODE IDENTICAL.

Under target (12-15%) and this is the honest number. Scan of every comment block of
1-3 lines in the seven files (52 blocks) found ZERO in the 1-4 band: every short
comment is a spec citation, a refusal, a precondition or a named trap. The mass is
in 6-32 line header/banner blocks whose paragraphs are each a distinct argument.
What was actually removable: one false paragraph, five true duplications, four
closing flourishes, four rhetorical questions.

### FALSE (score 0)

**1. `gen_c_cap.zen` header, "WHAT IS STILL REFUSED, AND WHY IT'S THE INTERESTING
ONE" (8 lines, deleted).**

> "`Fs.read` takes an `Alloc` and allocates the buffer through it. An `Alloc` is a
> BOUND ("an ordinary struct whose fields happen to be functions"), so a value of
> static type `Alloc` is a fat value this backend doesn't build yet. The refusal
> names that, not the member — EVERY allocation in the language goes through the
> same door, and `Fs.read` is simply the first capability that walks through it."

FALSE. There is no refusal. `Fs.read` is lowered (line numbers are post-edit;
independently confirmed by the group-C agent):
- `gen_c_cap.zen:116` — `name.is_in(["exists", "is_dir", "write", "read"])`.
- `gen_c_cap.zen:294-295` — `a.name.text.eq("read").match({ true => lower_read(...`
  i.e. `verb_5` dispatches `"read"` to `lower_read`, imported from `gen_c_fs.zen`
  at `gen_c_cap.zen:56`.
- `gen_c_fs.lower_read` (`src/gen/gen_c/gen_c_fs.zen:158`) allocates the buffer,
  and `gen_c_fs.zen:309` reaches the allocator with
  `slot_call(be, al, aty, "raw", args.view(), 2, call)` — i.e. a call THROUGH the
  fat record, the thing the comment says the backend "doesn't build yet".
- `gen_c_fs.zen`'s own header contradicts it directly: "`read` is the one that
  allocates, and does it THROUGH A BOUND".
- `gen_c_bound.slot_call` exists precisely to serve that call and names `Fs.read`
  as its caller.

CODE SHAPED AROUND IT: no dead code, but the stale narrative had propagated into
three more places in the same file, all corrected here:
- header member list omitted `Fs.read` from the bodiless-capability set and said
  "this file is the other four" -> now "the memory three, `gen_c_fs.zen` the other
  four" (verified against the imports and the `verb_1..verb_5` chain);
- `is_capability` said a wrong test "would make any bodiless member anywhere
  silently become one of these six" — the count is stale (the Mem 3 + Fs 4 the
  file recognises, before `println`, `Stdin.read` and `Scope.defer`); the number is
  dropped rather than replaced with another that will rot;
- `fs_verb`: "`read` is in the set so that it reaches THIS file's refusal, which
  names the bound" — there is no such refusal; rewritten to name
  `gen_c_fs.lower_read`, which is where the set membership actually sends it.

**2. Not my files, reported only (NOT edited):**

- `src/gen/gen_c/gen_c_fs.zen:16-17` — "the only place in the backend that calls
  through one without a call node to lower". False: `gen_c_sink.sink_write`
  (`src/gen/gen_c/gen_c_sink.zen:703-712`) is a second one, same `slot_call`.
- `src/gen/gen_c/gen_c_fs.zen:76-77` — `write` "is the half of the pair this
  backend can write today", implying `read` is not written. Same stale refusal as
  (1), contradicting that file's own header 60 lines above.

### Verified and KEPT (limitation claims that still hold)

- `gen_c_alloc.zen` "16 IS ALIGN_MAX, not a guess ... `gen_c_fs.zen` writes the
  same 16" — TRUE. `src/std/mem/mem_arena.zen:39` `ALIGN_MAX: usize = 16`;
  `gen_c_fs.zen:308` writes `", 16"`. Number and cross-file claim kept exact.
- `gen_c_build.zen` "A field that doesn't exist is a diagnostic SEMA owes and
  neither implementation raises" — TRUE; no construction-time unknown-field
  diagnostic exists anywhere in `src/sema/`.
- `gen_c_assoc.zen:7` "which is what this backend used to do, emitting an
  undeclared `D2` that no Zen diagnostic named and only `cc` caught" — regression
  record, KEPT verbatim.
- `gen_c_build.zen:660` "this shape once produced a `Map` instantiated at
  unresolved type arguments (docs/GEN_BOOTSTRAP_FIXES.md)" — regression record,
  KEPT.
- `gen_c_build.zen` `{0}` / `Cursor()` and "every default in std happened to
  already be zero" — regression record of a silent-wrong-answer bug, KEPT (only
  the duplicate half trimmed, see Deduplicated).
- `gen_c_cap.zen` `is_console_capability`'s "Without this it fell through to
  `lower_fat_call` ... `cc` rejected every argument" — regression record, KEPT.
- `gen_c_bound.zen` `fat_ret_type`'s `Buf.grow` record — KEPT whole.
- `gen_c_array.zen` C99 6.7.5.2 zero-length-array citation and the
  `std/core/range.zen` quote — KEPT verbatim.

### Deleted (score 1-4)

- `gen_c_cap.zen` — "WHAT IS STILL REFUSED, AND WHY IT'S THE INTERESTING ONE ..." —
  score 0 — false, see above (8 lines).
- `gen_c_const.zen` — "The restriction moved from "is a literal" to "cannot be
  observed twice" — what it was always trying to say." — score 3 — narration of a
  past refactor; the rule it describes is stated in the header and enforced by
  `is_pure_value` right below.

### Deduplicated

- "a conversion REBUILDS, never reinterprets; nothing assumes two pointer types
  share a representation" was stated in `gen_c_bound.zen`'s header AND restated
  almost verbatim in its own "rebuilding a value at another type" banner ->
  kept whole in the header (which owns it for the folder), banner now keeps only
  its distinct fact ("erasure is what lets one slot serve every instantiation;
  this is the way back").
- "THE ONLY DYNAMIC DISPATCH IN THE LANGUAGE" — `gen_c_bound.zen` header and its
  "call through the record" banner -> kept in the header; banner keeps the
  mechanism (the value IS the bound) and the static-call contrast.
- "`Fs.read`'s `Alloc` is a fat value / an `Alloc` is a BOUND" — premise owned by
  `gen_c_fat.zen` -> `gen_c_cap.zen`'s copy deleted (it was also false);
  `gen_c_bound.slot_call` keeps the one clause it needs, and now names both real
  callers (`Fs.read`, `Sink.write`) instead of implying `Fs.read` is the only one.
- "the `raw` this file calls is the receiver's own, under the symbol `a.raw(..)`
  would produce" — `gen_c_alloc.zen` header and `raw_call` -> full statement kept
  at `raw_call` (it has the qualified-name/signature/queue-entry detail); header
  now points at it.
- "types are read off `raw`'s own declaration, not built" — `gen_c_alloc.zen`
  header ("ELEMENT TYPE IS NOT LOOKED UP BY NAME") and `raw_result` -> header
  keeps the argument, `raw_result` keeps only the consequence.
- "`Point(x: 3, y: 4)` and `area(p)` are the same AST node" — owned by
  `gen_c_call.zen` -> `gen_c_build.zen`'s header now cites rather than re-narrates.
- "WHAT IS BEING BUILT IS SEMA'S ANSWER FOR THIS NODE / `Box<i32>(held: 7)`" —
  `gen_c_build.zen` header and `construct_type` -> full version kept at
  `construct_type` (it also explains `constructed` and the `chosen_def` parallel);
  header states the rule and points there.
- the positional-argument name rule + "a `Vec<str>` cannot be read back" was in
  `supplies`, `field_name` and `storage_name` -> definition kept at `field_name`,
  the `Vec<str>`/`Vec.get` inference trap kept at `storage_name` (it carries the
  docs/GEN_BOOTSTRAP_FIXES.md citation), `supplies` now defers to both.
- the `{0}` shortcut story was in `write_literal` and in the "defaults" banner ->
  banner keeps why it went unnoticed (every default in std was already zero),
  `write_literal` keeps the `Cursor()` case and points at the section.
- `is_pure_value`'s soundness condition was stated in `gen_c_const.zen`'s header,
  again in `lower_global_value`, and again at `is_pure_value` -> header owns it;
  `lower_global_value` keeps only its own facts (no C object, DESIGN.md,
  `I64_MIN`/`UNRESOLVED`); `gen_c_build.member_default` now cites the gate instead
  of re-deriving why it is sound.
- `Scope.defer` "is a capability by the same test" was argued at
  `is_console_capability` and again at `lower_capability` -> kept at
  `is_console_capability`; `lower_capability` keeps only why defer takes the short
  path (its lowering is about the closure) plus the `scope.zen` quote.
- "`read` names two capabilities, so the owner is the test" was at `is_stdin_read`
  and again at `verb` -> full version kept at `is_stdin_read`.

### De-rhetoricized

- `gen_c_alloc.zen:alloc_raw` — "Is this `alloc.create<T>()`? Checks the name AND a
  receiver that really allocates" -> "The name AND a receiver that really
  allocates".
- `gen_c_assoc.zen:takes_receiver` — "Is this member's first parameter the type
  itself? Resolved with `@Self` bound..." -> "The first parameter, resolved with
  `@Self` bound to the receiver...".
- `gen_c_build.zen:supplies` — "Did the call supply this field? Under the SAME name
  rule..." -> "Under `field_name`'s rule, asked again here rather than remembered
  from the walk".
- `gen_c_const.zen:is_pure_value` — "Can this expression be written twice without
  anyone being able to tell?" -> "Written twice without anyone being able to
  tell: a literal can; ...".

### Compressed (score 7-9)

- `gen_c_cap.zen:header` — 32 -> 22 lines — kept the env.zen "a capability's floor
  is the target language's" quote, the C floor list, the not-a-special-case rule
  and the whole ArenaState-licence argument; cut the false paragraph and the
  closing flourish "One place knows the shape: the place the value is born."
- `gen_c_cap.zen:lower_capability` — 6 -> 4 — kept the `scope.zen` `= sig` quote
  and the short-path reason.
- `gen_c_cap.zen:verb` — 4 -> 3.
- `gen_c_bound.zen:banner "rebuilding a value at another type"` — 6 -> 4.
- `gen_c_bound.zen:banner "the call through the record"` — 8 -> 7.
- `gen_c_bound.zen:slot_call` — 12 -> 11 — same content, and now factually names
  both call sites that reach a record with no call node.
- `gen_c_bound.zen:emit_fat_call` — 3 -> 2 — cut "and an expression read twice is
  an expression evaluated twice" down to "read twice is evaluated twice".
- `gen_c_build.zen:supplied_initialiser` — 11 -> 10 — the `Param(.., value: None)`
  regression record and the open sema-gap kept; the "reaches the same answer from
  the other side" restatement folded into the sentence that already said it.
- `gen_c_build.zen:decl_ctx_of` — 8 -> 6 — kept `Lexed`/`Vec<Token>`, the memoize
  trap and "forty-four initialisers" exactly; cut the closing flourish "One reader
  with the wrong module poisons the declaration for the whole program."
- `gen_c_build.zen:layout_open` — 14 -> 13 — cut the closing restatement "The
  declaration that introduced the name is the one that binds it."
- `gen_c_build.zen:member_default` — 7 -> 6.
- `gen_c_array.zen:ELEMS` — 3 -> 2; `write_array_index` — 7 -> 6 (the count-comes-
  from-the-type rule is the header's); walk-body inline note — 3 -> 2.
- `gen_c_assoc.zen:module_fn_decl` — 9 -> 8; `assoc_at_site` inline — 3 -> 3
  (reworded to defer to the arity rule rather than re-derive it).
- `gen_c_const.zen:header` — 15 -> 14; `lower_global_value` — 15 -> 13.
- `gen_c_alloc.zen:header` — 33 -> 32; `raw_result` — 4 -> 3.

### Refused to cut

- Every DESIGN.md / AST_CONTRACT.md / GEN_BOOTSTRAP_FIXES.md / SEMA_BOOTSTRAP_FIXES
  §10 / C99 6.7.5.2 / C99 6.7.8 / `std/core/range.zen` / env.zen / scope.zen /
  mem_arena.zen citation.
- All seven regression records listed above.
- `gen_c_alloc.zen`'s "WITHOUT THIS FILE THE CALL RESOLVES TO NOTHING" and
  "16 IS ALIGN_MAX" paragraphs (protected, verified).
- Every section banner.

### WRONG CODE noticed (not fixed)

- `src/gen/gen_c/gen_c_const.zen:158-164` — `lower_const_value` refuses with the
  user-visible message **"a constant whose value is not a literal"**, but the gate
  it just applied is `is_pure_value`, which admits unary/binary operators over pure
  operands, constructions of pure arguments, nullary variants and type constants.
  The message names a rule the code stopped enforcing, so a constant rejected today
  is told the wrong reason. (The comment that recorded that move — "the restriction
  moved from 'is a literal' to 'cannot be observed twice'" — was the only thing
  keeping the mismatch visible, and it is stale history; the diagnostic string is
  where the fix belongs.)



<a name="audit_gen_C.md"></a>

## Appendix: src/gen — section C

## gen_c (C-file slice: decl/display/fat/flow/fmt/fold/frame/fs) — 772 comment lines before, 734 after, 38 removed (4.9%)

Per file (leading-`//` lines):

| file | before | after | removed |
|---|---|---|---|
| `gen_c_decl.zen` | 195 | 186 | 9 |
| `gen_c_display.zen` | 68 | 62 | 6 |
| `gen_c_fat.zen` | 135 | 125 | 10 |
| `gen_c_flow.zen` | 93 | 89 | 4 |
| `gen_c_fmt.zen` | 77 | 75 | 2 |
| `gen_c_fold.zen` | 46 | 41 | 5 |
| `gen_c_frame.zen` | 89 | 89 | 0 |
| `gen_c_fs.zen` | 69 | 67 | 2 |

**Honest yield: 4.9%, not 12-15%.** These eight files have no filler band at all
and almost no intra-file duplication: the repetition that exists is a header
owning an argument and one call site restating a clause of it, which is worth
2-4 lines a file, not 15. Everything else is a measurement, a regression record,
a rejected-alternative argument, or a spec citation. `gen_c_frame.zen` yielded
literally nothing (as predicted in the brief) — it is five struct docs, each row
carrying a distinct fact. I did not reach for a quota.

`codecheck_keep.py` reports ALL CODE IDENTICAL on all eight files.

---

### FALSE (score 0)

**1. `gen_c_flow.zen:17` (header) — "exhaustiveness is sema's to check, and
UNTIL IT DOES, a value matching no arm traps there instead of falling out with
an uninitialised result."**

FALSE. Sema checks match exhaustiveness today, and has a full implementation of
it:

- `src/sema/sema_match.zen:302 check_exhaustive` — Maranget's usefulness
  algorithm, `_` asked against every arm.
- `src/sema/sema_match.zen:261` — wired into `run_coverage`, called on every
  match with a checkable scrutinee.
- `src/sema/sema_diag.zen:127` `NotExhaustive(NameFault)` and `:208` the
  rendered message; the header of `sema_match.zen` cites DESIGN.md for the rule.

**Code shaped around it: NO, and the trap must stay.** `zg_unreachable` is still
required: `sema_match.zen:249 checkable` deliberately SKIPS both coverage checks
when the scrutinee type is poison, a hole, or an unsubstituted type parameter
(SEMA_BOOTSTRAP_FIXES.md §8), and the emitted `if`/`else if` chain has to be
total in C regardless. Only the "and until it does" clause was false. **Deleted
that clause; the rest of the sentence stands unchanged.**

**2. `gen_c_fs.zen:77` (`lower_write`) — "...which is also why it is the half of
the pair this backend can write today."**

FALSE. It claims `read` is the half this backend cannot lower yet. `lower_read`
is defined in this very file (`gen_c_fs.zen:158`, plus `read_string`,
`read_run`, `read_body`, `run_and_read`, `write_string_ok`) and is dispatched
from `src/gen/gen_c/gen_c_cap.zen:307`. The file's own header (paragraph 3)
describes read's allocation path in detail. The comment is stale by its own
file.

**Code shaped around it: NO.** Both halves are lowered. **Deleted the false
clause; the `Alloc`/law-1 reason above it is true and kept.**

**3. `gen_c_decl.zen:59` (`MAX_FUNCTIONS`) — "IT COUNTS FUNCTIONS LOWERED —
SAME UNIT as `bootstrap/gen_c.py`'s `MAX_INSTANCES`, same number, so the two
implementations agree on which programs they accept rather than differing by an
undocumented factor."**

FALSE — it names the wrong bootstrap constant, which inverts the point it is
making. `bootstrap/gen_c.py:162`:

```python
MAX_INSTANCES = 8192  # generic TYPE instantiations; a divergence stops here
```

incremented at `gen_c.py:1283` inside the type-interning path — it counts
generic TYPE instantiations, a different unit. The same-unit counterpart exists
and is `bootstrap/gen_c.py:168 MAX_FUNCTIONS = 8192`, whose own comment says so
outright: *"Functions emitted, which is a different thing counted in a different
loop and was the same constant until the two diagnostics had to say different
words."* It is reported at `gen_c.py:1791`.

So the number is right, the parity is real, and the citation points at the one
bootstrap constant that does NOT share the unit. **NOT corrected in place** —
the fix is to change `MAX_INSTANCES` to `MAX_FUNCTIONS` in that sentence, which
is asserting a new claim rather than deleting a false one, so it is left for the
parent. **Code shaped around it: NO** — the value 8192 is independently
justified by the measured 4069/3754 figures in the same comment.

### Discrepancy worth a second look (not scored, not touched)

`gen_c_decl.zen:66-69` measures `corpus/cli/build_walks_a_root_it_is_given`,
staging the driver, at **3754** functions lowered. `bootstrap/gen_c.py:164-165`
measures the same pair as *"`zen build src` lowers 4069 and the driver corpus
test 4086"*. The `zen build src` figure agrees exactly (4069); the driver-corpus
figure does not (3754 vs 4086). Either the two backends genuinely lower
different counts for that program — which is a divergence worth recording as one
— or one of the two numbers was never re-measured. Both are PROTECTED
measurements, so both are left exactly as written.

---

### Deleted (score 1-4)

- `gen_c_fat.zen:466-467` (`write_thunk`) — "THE IMPL IS COMPILED AT THE ERASED
  ELEMENT TYPE — one byte — so the scaled count the shim hands it is already
  the byte count it wants" — score 3 — the fourth statement of the erasure/
  scaling rule in one file (header ¶3, `thunk_arg`, `cast_arg` all say it), and
  the only one not attached to the code that does the scaling.

### Deduplicated

- **"a lowered function is held as a head with no punctuation and a body that is
  only statements; `gen_c_decl.zen` writes the `;`/braces, so one that carried
  either would get a second"** — stated in full in `gen_c_display.zen`
  (`emit_console_fn`) and `gen_c_fat.zen` (`emit_thunk`). Kept whole at
  `emit_thunk` (the thunk file owns synthesized functions, and `console_name`
  already defers to it for the naming rule); `emit_console_fn` now reads "Head
  and body carry no punctuation of their own, the shape `emit_thunk` explains."
  6 -> 3 lines.
- **"a fat value is built only where the DESTINATION's static type is the
  bound"** — owned by `gen_c_fat.zen`'s header; `gen_c_display.zen`'s header ¶3
  restated it plus "the call is resolved statically, like `==` through `Eq`".
  Folded ¶3 into ¶2 as a pointer to `gen_c_fat.zen` plus display's own distinct
  facts (the console is the one fat value the print path builds; `zg_self` is
  NULL — stdout is not a value the program owns). 9 -> 6 lines.
- **"a variadic parameter has no C spelling and `{}` resolves by the argument's
  type, so the compiler is the body"** — owned by `gen_c_sink.zen` per the
  folder decision. `gen_c_fmt.zen`'s opening restated the whole argument; now
  the `text_string.zen` quote plus a pointer to `gen_c_sink.zen`'s head. Its
  three distinct facts are untouched and exact: the **seven** linker errors `cc`
  reported against stage 2 in `zen_build.zen`'s module-path resolution, the
  two-walks-drifted regression record with its `"point {}"` example, and the
  differing ERROR type (`Res<String, AllocError>` vs `Res<(), WriteError>`).
- **The two error sets** — `gen_c_fmt.zen`'s header ¶4 spells both types and
  points at `write_failure_arm`; `write_failure_arm` spelled both types again.
  Local site now says "the two error sets the header names". Kept exact: the
  `OutOfMemory`/`AllocError`-one-variant argument, the bootstrapper's `full_of`,
  the **112** corpus mains measurement, and the failing-path-only note.
- **`gen_c_fold.zen` header's three bullets** were each restated at two or three
  call sites (`Fold`, `lower_fold`, `result_element`, `write_fold_result`). The
  header is PROTECTED (it carries the `bootstrap/gen_c.py` divergence
  measurement about writing `Ok(acc)` after the break label) and is untouched;
  the four sites now defer to it and keep only their own distinct facts —
  `result_element` keeps "the argument before the body — one place, so the type
  a temporary is declared at and the type the loop assigns cannot disagree".
- **"one `void *`-receiving shim per (impl member, slot), named after the
  function it calls so two requests for one shim are one"** — `gen_c_fat.zen`
  header ¶4 states it; `thunk_for` repeated the first half near-verbatim and
  `thunk_name` the second. Both now defer, keeping `thunk_for`'s "or nothing
  when the impl supplies no answer" and `thunk_name`'s `zg_v`/`zu_` spelling.
- **"a record is a function of the DECLARATION alone"** (header ¶3) was restated
  by the `the slots` banner prose; banner prose cut to its own point
  (determinism, two programs' records compiled to the same shape). 4 -> 2.
- **"the size travels beside the pointer exactly as in Zig's
  `std.mem.Allocator`"** — header ¶1 and ¶3 both state the Zig shape and the
  `size_t`-beside-the-pointer trade; dropped the third statement in
  `add_slot_at`, keeping `Ptr<T>` in the declaration IS `Ptr<u8>` in the slot.
- **"`::` means the method writes the receiver's own bytes"** — stated twice in
  `gen_c_decl.zen` 18 lines apart (`write_param`, `ref_declarator`). Kept the
  fuller one at `ref_declarator` (it names `LocalSlot.by_ref` and the inlined
  case); `write_param` now points at it. (`gen_c_frame.zen:38` states it a third
  time, but that is the field the rule is *recorded in* — kept.)
- **"a diagnostic rather than a walk that does not terminate"** —
  `MAX_FUNCTIONS`'s own doc and `drain`'s opening. Kept at the constant;
  `drain` now names the bound. `report_overrun`'s "silent truncation is the
  worst failure mode this compiler has" is a distinct point and untouched.
- **`gen_c_decl.zen` `seed`** restated the header's "seeds ONE module's
  functions and follows the calls that resolve"; now one line pointing at it.

### De-rhetoricized

- `gen_c_frame.zen:38 LocalSlot.by_ref` — "Is the C name a POINTER to the value
  rather than the value?" -> "The C name is a POINTER to the value rather than
  the value." (the brief's named lead)
- `gen_c_fat.zen:69 is_fat` — "Is a value of this type a fat value?" (restates
  the function's own name, and the paragraph below already answers it) ->
  dropped, the answer now opens the comment.
- `gen_c_fat.zen:711 needs_fat` — "Does this expression have to become a fat
  value to land where it is going?" -> "Only where the DESTINATION's static type
  is a bound and the value's own type is not — ..."
- `gen_c_fat.zen:782 is_place` — "Is this emitted text a C place? A name, a
  field hop, ..." -> "A C place is a name, a field hop, ..."

### Compressed (score 7-9)

- `gen_c_decl.zen:MAX_FUNCTIONS` — 18 -> 17 lines. **Every number kept exact**
  (8192, 4096, 3167 free + 902 member = 4069, 3754). Cut only the closing
  flourish "This is a guard on a program's SIZE, which is what the old number
  had quietly become", folding "guards a program's SIZE" into the sentence
  above it. The 4096/LOOP-TURNS history is kept: it explains why the unit
  changed, which is a fact about the constant, not refactor narration.
- `gen_c_decl.zen:by_sig` — 12 -> 11. The regression record is untouched and
  exact ("Asking arity alone once picked the first of `Display`'s two
  `toString`s for both queue entries: the sink body was emitted twice, and every
  call to the second ran the first"). Trimmed only the fast-path justification's
  trailing clause.
- `gen_c_decl.zen:bind_param` — 11 -> 10. Kept "TWO TYPES, AND THE DIFFERENCE IS
  THE WHOLE POINT" and the sema-memo-keyed-by-node-id argument whole; cut the
  closing "where the concrete answer belongs and is correct once".
- `gen_c_decl.zen:drain` — 13 -> 11. Kept TWO QUEUES, INTERLEAVED whole (it is
  the convergence argument); the "fixed form" paragraph reduced to the fact that
  survives it — a fixed count cannot tell a finished walk from a cut-off one.
- `gen_c_decl.zen` "one member function" banner — 8 -> 7; the UFCS quote and the
  sentence introducing it said the same thing.
- `gen_c_flow.zen:close_arms` — 3 -> 2; "match is always exhaustive" is the
  header's first sentence.
- `gen_c_flow.zen:payload_cond` — 5 -> 4; "a binder, a variant, a literal read
  the same way at every level" restates "Depth is not a special form".
- `gen_c_flow.zen:bind_payload` — 6 -> 5; "the binder must be bound at the depth
  it was written at" restates the recursion described in the clause before it.
  The consequence ("a nested binder the walk never reached is a name the arm
  body cannot resolve") is kept — that is the reason, not the restatement.
- `gen_c_fat.zen:fat_value` — 4 -> 3; the record's composition is the header's
  second sentence. The receiver-must-outlive rule is kept.
- `gen_c_fs.zen` header ¶3 — 5 -> 4; "an ordinary struct whose fields happen to
  be functions" is `gen_c_fat.zen`'s to state. The distinct fact — "the only
  place in the backend that calls through one without a call node to lower" — is
  kept.

### Refused to cut

- `gen_c_decl.zen`'s header (THE WALK IS REACHABILITY-DRIVEN / BODIES LOWERED
  FIRST, EMITTED LAST / EVERY LIST SORTED BY MANGLED NAME) — kept whole per the
  folder decision; `gen_c_state.zen` points at it.
- `gen_c_fs.zen`'s ordinal-vs-name rule — kept whole, it is this file's to own.
- `gen_c_flow.zen:str_cond` — "`==` would compare a STRUCT against a `char *` —
  invalid C, once emitted silently" plus "comparing over the shorter length is
  the classic bug, and a prefix is not the whole". Regression record twice over.
- `gen_c_flow.zen:destructure_cond` — "`Ok('\n')` and `Ok('\\')` would compile to
  the same (valid) condition, the first swallowing every `Ok`".
- `gen_c_fat.zen:request_slots` — the `Eq` -> `Eq` false by-value cycle. It is
  the same bug `bootstrap/gen_c.py:1291-1298` records; both are load-bearing.
- `gen_c_frame.zen:24-28` — the `Ast`-import compiler bug ("Recorded as a
  compiler bug rather than worked around silently").
- `gen_c_decl.zen:keep_same_sig` — "a loop binding read inside a nested closure
  does not resolve". A language-limitation claim I could not verify by reading
  (it needs a compile to test), so per the standing rule it is LEFT ALONE and
  reported as unverified rather than trimmed or asserted.
- `gen_c_fold.zen`'s header — the `bootstrap/gen_c.py` divergence measurement
  ("Writing it after the label would make a break silently return the
  accumulator instead — which is what `bootstrap/gen_c.py` does today").
- `gen_c_frame.zen` entirely, apart from the one de-rhetoricization. Five struct
  docs; every row is a distinct fact (`depth` and the goto-over-braces drop
  unwinding, `floor` vs `home`, `live` and the double-free, `rec`).

### Wrong code noticed (NOT fixed)

- None. No code defect found in these eight files.
- One cosmetic typo in a comment, left alone as it is not mine to reword:
  `gen_c_fold.zen:acc_type` opens a quotation with a backtick and closes it with
  a double quote — ``"`init is the answer when there is nothing to fold"``.



<a name="audit_gen_D.md"></a>

## Appendix: src/gen — section D

## gen/gen_c (lane D, 9 files) — 682 comment lines before, 628 after, 54 removed (7.9%)

Per file (before -> after):

| file | before | after | removed |
|---|---|---|---|
| gen_c_handle.zen | 43 | 41 | 2 |
| gen_c_hoist.zen | 32 | 29 | 3 |
| gen_c_impl.zen | 130 | 118 | 12 |
| gen_c_index.zen | 30 | 29 | 1 |
| gen_c_infer.zen | 37 | 34 | 3 |
| gen_c_inline.zen | 117 | 99 | 18 |
| gen_c_layout.zen | 113 | 108 | 5 |
| gen_c_loop.zen | 140 | 131 | 9 |
| gen_c_main.zen | 40 | 39 | 1 |

`python3 /tmp/codecheck_keep.py` run on all nine after every edit: ALL CODE
IDENTICAL. Two near-misses were caught by it and reverted immediately (an edit
window that included `needs_hoist* = (` and one that included `impl_member* = (`
each ate the space before the paren; a third removed the blank line above a
banner in `gen_c_inline.zen`). All three were restored before moving on.

7.9% is the honest number for this lane. These nine files have almost no
restatement left inside themselves: the repeated arguments were mostly the
CROSS-FILE ones the parent had already adjudicated, and outside those the prose
is regression records, DESIGN.md citations, refusals and rejected alternatives —
the protected classes. I did not cut to reach 12%.

### FALSE (score 0)

1. **`src/gen/gen_c/gen_c_index.zen:22` — "sema does not type an index"**
   (in the header: "The type is answered here too: sema does not type an index,
   and `println`'s `{}` chooses its write by the argument's type, so
   `index_type` answers the same two readings the lowering makes").
   FALSE AS WRITTEN. `src/sema/sema_type.zen:401` dispatches
   `Index(x) => c.index_element_type(node, x, ctx)`, and
   `sema_type.zen:478` `index_element_type` types the base, types the index,
   and returns `a.elem` via `array_element` (which also runs `check_index`).
   **Code shaped around it: NO — the comment is over-broad, not the code.**
   `index_element_type`'s fallthrough is `_ => c.types.unknown()`, so sema types
   ONLY the fixed-array base; a `Ptr<T>` base and a type with a declared `index`
   still come back `Unknown`. Those are exactly the two readings
   `index_type`/`not_array_index_type`/`ptr_element`/`member_index_type`
   supply (`gen_c_index.zen:80-131`, live: called from
   `gen_c_expr.zen:366`). So `index_type` is NOT dead weight — but the header
   sentence claims more than is true and should read "sema types only the
   fixed-array case". **I left the comment untouched** (rewriting it means
   asserting the boundary I inferred rather than one the tree states) — flagging
   it for the parent instead.

2. **`src/gen/gen_c/gen_c_inline.zen:16` — "the allocation budget
   `tests/bench/bench_loop.zen` gates"** — the budget is DECLARED, not gated.
   `tests/bench/bench_loop.zen:6` writes `Budget(name: "fold_stack_array",
   allocs_op: 0)`, but the only harness that reads those budgets,
   `scripts/bench.py` (the `make bench` recipe, Makefile:185-186), says in its
   own module docstring (lines 14-16) "allocs_op/bytes_op are NOT measured --
   that needs compiler instrumentation that does not exist yet (deferred,
   deliberately)" and prints `allocs_op/bytes_op: unmeasured` per bench
   (`scripts/bench.py:379`). FIXED, minimally: the sentence now reads "the same
   sentence as the `allocs_op: 0` budget `tests/bench/bench_loop.zen`
   declares" — path and number kept exact, false verb dropped.
   **Code shaped around it: no.** The no-closure-record property is real
   (`bind_closure` declares no storage); only the claim that a gate enforces it
   was false. NOTE for the parent: this same "bench_loop gates the allocation
   budget" framing is cited elsewhere in `src/` — worth a tree-wide sweep.

3. **`src/gen/gen_c/gen_c_index.zen:168` — "the order `eq_fn` above uses"** —
   there is no `eq_fn` in this file; it lives in `gen_c_member.zen:925`
   (`grep -rn eq_fn src/` returns exactly that definition, its one call site at
   `gen_c_member.zen:917`, and this comment). A pointer left behind when
   indexing was split out. **Code shaped around it: no.** Deleted the clause;
   the surviving half ("the order `sema_supply.zen` states") is the real rule
   and is stated in the header too.

4. **`src/gen/gen_c/gen_c_inline.zen` (old lines 253-255 and 752-761) — two
   ORPHANED comment blocks describing functions that are no longer in the
   file.** "The receiver, if a ufcs call arrived through one, and then the
   written arguments..." documents `arguments`, which now lives at
   `gen_c_settle.zen:63` — and `gen_c_settle.zen:60` carries the SAME comment
   verbatim above it. The trailing banner ("what an inlined call evaluates to,
   asked BEFORE it is lowered ... Same computation as `inline_free`, asked as a
   query") documents `inline_ret`, now `gen_c_settle.zen:108`, whose own header
   states the identical "ONE IMPLEMENTATION AND TWO CALLERS" argument. Both
   deleted; the trailing banner replaced by a one-line pointer (keeping the
   file's end-of-file blank-line shape, which codecheck compares).

### Suspicions checked and CLEARED (not false)

- `gen_c_impl.zen:93` "asking whether its last one is variadic used to trap on
  `0 - 1` (a `usize` underflow inside `last_is_variadic`). That guard now lives
  where the arithmetic is." — TRUE. `gen_c_sink.zen:87` `last_is_variadic` opens
  with `(f.params.len == 0).match({ true => false, ...})`, and carries its own
  fuller record of the same bug (exit 134 via `associated_functions`). KEPT.
- `gen_c_impl.zen:269` "Both, not either/or. This once ran the bound only when
  the impl block supplied nothing of that name..." — a REGRESSION RECORD, not
  refactor narration: `keep_impl_fn` today runs `im.members.loop(...)` and then
  `keep_bound_default` unconditionally, and the comment is why (the
  `p.toString(alloc)` -> sink symbol with an `Alloc` passed as a `Sink`, a
  record of NULL function pointers). KEPT WHOLE.
- `gen_c_impl.zen:44` "this once answered with one: `found.get(0)` was the
  fallback for every miss" — regression record matching today's `without_arity`
  (returns `None` when any candidate is a function). KEPT.
- `gen_c_loop.zen:212` "A range whose bounds an impl supplies carries no
  accumulator yet, so it's refused BY NAME" — still true: `lower_impl_walk`'s
  `fold.has` arm calls `unsupported(..., "a fold over a range whose bounds an
  impl supplies", ...)`. KEPT.
- `gen_c_main.zen:109` "`(Env){0}` made `env.argv.len` 0 in every program this
  backend compiled, so no stage-2 binary could fixpoint" — regression record.
  KEPT.

### Deleted (score 1-4)

- `gen_c_hoist.zen:39` — "Does this value have to be lifted into the `Res` that
  is wanted?" — score 2 — pure restatement of `needs_hoist`, no content.
- `gen_c_impl.zen` — "The function an impl on this type supplies under `name`,
  when one does." — score 3 — restates `impl_member`, and the banner three lines
  above already says what an impl supplies.
- `gen_c_impl.zen` — "A required member is still absent here — `keep_named_fn`
  keeps only what has a body (see `impl_member_at` above)." — score 3 — the
  third statement of the no-body rule in one file (`impl_member_at`'s comment
  and `has_body`'s own paragraph both state it).
- `gen_c_inline.zen` — "The binding a name has when it is a closure, and nothing
  when it is an ordinary local or nothing at all." — score 3 — restates
  `closure_slot` and `keep_closure`.
- `gen_c_inline.zen` — "The parameter types and the return type a function TYPE
  carries." — score 2 — restates `fn_parts`.
- `gen_c_inline.zen` — the two ORPHAN blocks in FALSE #4 above (13 lines).
- `gen_c_layout.zen` — "The tag, then the payload union when any variant carries
  one, omitted entirely for a tag-only enum (see header)." — score 3 — sat on
  `open_struct` (which writes only `struct X {`), described `write_union`, and
  already deferred to the header that states it.
- `gen_c_hoist.zen` — "Wrong in that direction emits the C emitted before this
  file existed" — score 2 — stale history; the asymmetry claim it belonged to
  ("wrong the other way wraps a value that was already a `Res`") is kept.
- `gen_c_inline.zen` — "The bootstrapper paid for this one and recorded it." —
  score 3 — closing flourish with no recoverable fact; the hygiene argument
  above it is complete without it.

### Deduplicated

- **the `goto`-not-`break` argument** was stated almost verbatim in
  `gen_c_handle.zen`'s header and `gen_c_loop.zen`'s header -> kept in
  `gen_c_handle.zen` (whose whole subject is leaving a loop, and which keeps its
  own distinct fact: "A label cannot be captured that way, the whole reason
  `LoopFrame` carries two of them"); `gen_c_loop.zen` now reads "`h.break(v)`
  AND `h.next()` ARE `goto`s, NOT C's `break`/`continue` — `gen_c_handle.zen`
  argues why, and owns both verbs." (5 lines -> 2)
- **"no closure record"** was in `gen_c_inline.zen`'s header (owner, kept whole)
  and restated in `gen_c_loop.zen`'s "LOOPS NEVER ALLOCATE" paragraph -> loop
  now keeps only its own distinct fact (no declaration in `loop_iter.zen` takes
  an `Alloc`; `index`, `value`, `acc` are plain automatic storage). (4 -> 3)
- **"a closure infers FROM a signature rather than into one"** — `gen_c_settle.zen`
  owns it; `gen_c_inline.zen`'s "WHAT IS REFUSED, BY NAME" paragraph keeps the
  refusal and now points at `gen_c_settle.zen` instead of re-arguing it. (5 -> 4)
- **the `0`-where-the-expression-goes rule** (a call/loop with no storage must
  still write something or `(void)()` will not parse) was argued in full in both
  `gen_c_inline.zen`'s `write_result` and `gen_c_loop.zen`'s `open_result` ->
  kept in `write_result` (it is the general statement, about any call);
  `open_result` now points at it. (4 -> 2)
- **"`println`'s `{}` chooses its write by the argument's type / the same two
  readings the lowering makes"** was in `gen_c_index.zen`'s header and again on
  `index_type` -> kept in the header; `index_type` keeps its own distinct fact
  ("needed before anything is written: the element of a raw pointer, or the
  return type of the declared `index`"). (4 -> 3)
- **"re-deriving sema's rule would be a worse copy"** was in `gen_c_infer.zen`'s
  header and again on `named_ret_type` -> kept in the header; the site keeps
  "One candidate or nothing" and points back.
- **"declared type and call symbol can't disagree"** was in `gen_c_infer.zen`'s
  header and again in `call_ret_type`'s third paragraph -> kept in the header.
  (9 -> 7)
- **"a struct holding another BY VALUE needs a complete type, a forward typedef
  is not one"** was in `gen_c_layout.zen`'s header and again in the
  "definitions" banner -> banner now says "Dependency-first, for the reason the
  header gives" and keeps its own distinct fact (the marker is set before the
  children are walked, so a by-value cycle terminates).
- **canonical-order-not-declaration-order** is argued fully at `write_enum_tags`
  (DESIGN.md quote) and partly at `collect_union_tags` -> the shorter one is now
  one paragraph instead of two, keeping "a structural set has no declaration
  order" and the cross-reference.
- **"`zg_argv_vec` names the mangled `Vec<str>`, not a name until a program asks
  for one"** was in `gen_c_main.zen`'s header and verbatim in the `zg_argv_vec`
  banner -> kept at the banner (the site), header points down. (3 -> 2)
- **"the hygiene rewind keeps a caller's `h` out of `find`'s reach"** was in
  `gen_c_inline.zen`'s header and again in the "calling a closure" banner ->
  header owns it; the banner keeps the ordering fact (arguments are lowered
  before the frame moves).
- **the module-local impl search** ("An impl lives with the type") was quoted at
  `impl_member_at` and re-quoted at `alias_of` -> `alias_of` now says "the same
  search `impl_member_at` makes for members with bodies". (4 -> 3)

### De-rhetoricized

- `gen_c_handle.zen:handle_depth` — "Is this dotted call one on a loop handle?
  The base has to be a bare name bound to a handle..." -> "The base has to be a
  bare name bound to a handle: a handle is not a value, so there is nothing else
  it could be reached through."
- `gen_c_hoist.zen:needs_hoist` — "Does this value have to be lifted into the
  `Res` that is wanted?" -> deleted (nothing left once the rhetoric goes; the
  header states the rule and `lifts_into` states the two branches).
- `gen_c_inline.zen:inlines` — "Is this callee one to inline? A body to inline,
  and a lambda written at the call site to inline it for." -> "A body to inline,
  and a lambda written at the call site to inline it for."
- `gen_c_inline.zen:takes_closure` — "Does this declaration take a body? Such a
  function is NEVER emitted: ..." -> "A function that takes a body is NEVER
  emitted: ..."

### Compressed (score 7-9)

- `gen_c_impl.zen` header — 16 -> 12 lines. KEPT the 796/800 measurement exact
  and the whole real argument (an impl is found by the DECLARATION it targets,
  so no `Site` is needed, every entry point takes a `DeclId`, and the dependency
  on `gen_c_member.zen` runs one way with no cycle). CUT the refactor narration
  ("after its comments had already been trimmed twice — a file that pays for a
  line by deleting an explanation has outgrown its subject").
- `gen_c_impl.zen` "a member an IMPL supplies" banner — 6 -> 5 lines. Kept the
  static-dispatch conclusion and the fat-value rejection; cut the restatement of
  it as two questions.
- `gen_c_impl.zen:kept_or_arity` — 5 -> 4. Kept both filters by name (`by_sig`,
  `member_that_fits`); cut the second statement of "arity is the half a backend
  can answer" that `by_arity` above already makes.
- `gen_c_impl.zen:decl_name` — reworded, same 3 lines, "Exported because ..."
  turned into the fact itself.
- `gen_c_impl.zen:add_alias` — kept "A bare Name and nothing else"; replaced the
  dangling "the old fault spelled a new way" (no identifiable referent in this
  file) with "`start = 0` is a value, not a function to call". No new claim.
- `gen_c_handle.zen:write_break` — 4 -> 3. Kept the ordering rule (value, then
  cleanup, then jump, so the result survives the drops); cut the repeat of
  `leave_pass`'s "the `goto` jumps over the braces".
- `gen_c_hoist.zen` header — 12 -> 11, plus one line off the `write_res_payload`
  paragraph. All of `sema_hoist.zen`'s refusal and the `Unknown`-fits-everything
  fact kept.
- `gen_c_loop.zen:run_body` — 4 -> 3, keeping the `loop_iter.zen` quote ("index
  and acc thread BY VALUE, so no cell is heap-allocated") exact.
- `gen_c_loop.zen:bind_threaded` — 6 -> 5, deferring the overload rule to the
  header it owns, keeping "index/value are not interchangeable" and the
  index-space fact.
- `gen_c_loop.zen:wants_result` — 3 -> 2 (dropped the closing flourish).
- `gen_c_infer.zen:call_ret_type` — 9 -> 7 (see Deduplicated).
- `gen_c_main.zen` header — 4 -> 3.

### Refused to cut

- Every regression record in `gen_c_impl.zen` (`Box`'s `grow`, `Cursor.peek`,
  the `0 - 1` underflow, the `toString` NULL-function-pointer record) and in
  `gen_c_main.zen` (`(Env){0}`).
- Every DESIGN.md / C11 / `loop_iter.zen` / `text_str.index` citation.
- `gen_c_loop.zen`'s "THE OVERLOAD IS READ OFF THE DECLARATION'S OWN PARAMETER
  NAMES" with the `(h, i)` worked example (this lane owns it).
- `gen_c_layout.zen`'s "A TAG IS A FUNCTION OF THE DECLARATION" and
  `variant_ranks`' all-or-nothing refusal with its concrete miss (this lane owns
  both; `gen_c_try.zen` points here).
- `gen_c_inline.zen`'s no-closure-record claim and the whole hygiene argument
  (`Closure` carries the depth of both scope stacks; `run_closure` rewinds).
- `gen_c_loop.zen:637` "`h` has no C storage: what the name means is the loop it
  came from" — one line at `bind_handle`; `gen_c_loop.zen`'s own header does not
  say it (only `gen_c_handle.zen`'s does, in another file).
- `gen_c_main.zen` generally: 40 comment lines, of which the header, the
  `zg_argv_vec` banner (borrowed rows, zero allocator, the rejected
  alternative), the `(Env){0}` record and the `Ok(0)`-exits-0 rule are all
  load-bearing. Low yield here was expected and is real: 1 line.

### Wrong code noticed (NOT fixed)

- None in these nine files. One observation for the parent, code-shape not bug:
  `gen_c_infer.zen` builds the same six-field `Ctx(module: .., ret: TyId(index:
  0), has_ret: false, self_ty: TyId(index: 0), has_self: false)` literal twice
  (`inferred_inst`, `fn_ret_type`) while `gen_c_decl.zen` exports `plain_ctx`,
  which `gen_c_main.zen` and `gen_c_inline.zen` both use for exactly this. Not a
  defect; a dedup lane could take it.



<a name="audit_gen_E.md"></a>

## Appendix: src/gen — section E

# gen/gen_c (set E: mono, op, own, print, ptr, range, read)

## gen_c set E — 951 comment lines before, 902 after, 49 removed (5.2%)

Per file (before -> after, removed):

| file | before | after | removed | % |
|---|---|---|---|---|
| gen_c_mono.zen  | 142 | 134 |  8 | 5.6% |
| gen_c_op.zen    | 194 | 188 |  6 | 3.1% |
| gen_c_own.zen   | 124 | 118 |  6 | 4.8% |
| gen_c_print.zen | 104 | 101 |  3 | 2.9% |
| gen_c_ptr.zen   |  96 |  94 |  2 | 2.1% |
| gen_c_range.zen | 153 | 139 | 14 | 9.2% |
| gen_c_read.zen  | 138 | 128 | 10 | 7.2% |
| **total**       | **951** | **902** | **49** | **5.2%** |

`python3 /tmp/codecheck_keep.py` run on all seven after every edit: ALL CODE
IDENTICAL.

### Why this set lands at 5%, not 12%

Two structural reasons, both checkable:

1. **These files are the designated OWNERS of the folder's cross-file
   arguments.** The parent's dedup decisions make gen_c_own the owner of the
   lifted-defer-thunk argument *including its C example* (gen_c_scope cuts to a
   pointer at it), gen_c_mono the owner of "C has no generics, so a generic
   function is emitted once per distinct set of type arguments" (gen_c_state
   already cut to it), and gen_c_range the owner of the shape-recognition claim
   for ranges. The savings from those three dedups land in OTHER agents' files.
   Set E is mostly the receiving end.
2. **Five of the seven headers are protected wholesale**: gen_c_ptr's
   `docs/LEXER_BOOTSTRAP_FIXES.md §1` bug record, gen_c_print's two named corpus
   paths plus a stated refusal, gen_c_own's DESIGN.md drop-order law and
   `Vec.take` non-goal, gen_c_op's three-rule statement (each rule cited by a
   site comment I cut to a clause), gen_c_range's `range.zen` quotes.

The remaining prose is argued, specific, and mostly stated once. I did not reach
for a quota.

### FALSE (score 0)

**1. `gen_c_read.zen:637` (orig) — "OVERLOAD RESOLUTION IS SEMA'S AND IS NOT
THERE YET, so a name with more than one declaration is REPORTED rather than
picked between".**

FALSE, and additionally ORPHANED — the block sat at the very end of the file
with no function under it, documenting "a call to a top-level function the module
can see, and the two `Res` constructors", which this file does not contain.

Evidence read in this tree:
- `src/sema/sema_call.zen:131` `call_type*`, `:369` `no_overload`, `:817`
  `check_overloads*`, `:693-696` ("that is an error AT THE DECLARATION —
  `check_overloads` names both").
- `src/sema/sema_decl.zen:76` calls `check_overload_sets`.
- `src/sema/sema_diag.zen:191` the rendered diagnostic "no overload matches:
  resolution is on declared parameter types and arity".
- `src/gen/gen_c/gen_c_call.zen:18-24` states the CURRENT fact where the
  lowering actually lives: "OVERLOAD RESOLUTION IS SEMA'S, READ BACK RATHER THAN
  REDONE. `Cand` carries the `DeclId` it came from, and `chosen` writes it into
  `Checker.call_memo`".

**Code shaped around it: NO.** Nothing follows it in the file; the reading it
described lives in `gen_c_call.zen`, whose header carries the correct version.
DELETED (7 lines). No replacement claim invented.

**2. `gen_c_op.zen:241` — "Reported, not mis-lowered."**

FALSE. `lower_logical` (`gen_c_op.zen:260-272`, same comment's own function)
dispatches to `write_short_circuit` when `spills_anywhere(be, b.rhs)` and to
`write_infix` otherwise. Neither path calls `unsupported`/`report_expr`; there is
no refusal left on this operator. The comment's own third paragraph ("SO IT IS
WRITTEN OUT: a temporary the left fills, and the right fills AGAIN under an
`if`") describes what replaced it — the first paragraph was simply never updated.

**Code shaped around it: NO** — the code already implements the written-out
form; only the sentence is stale. Deleted the clause; the rest of the paragraph
(and the protected divergence measurement two paragraphs down) kept verbatim.

**3. `gen_c_ptr.zen:86` — "Sema does not type a call, so a binding that holds
one has no type unless this answers".**

The "sema does not type a call" half is FALSE.
- `src/sema/sema_type.zen:398` — `Call(k) => c.call_type(id, node, k, ctx)`.
- `src/sema/sema_call.zen:131` — `call_type*` dispatches `Access` -> `member_call`,
  `Name` -> `named_call`, otherwise `indirect_call`, and all three answer a `TyId`
  (`method_call` -> `fn_ret`, `sema_call.zen:669-679`).

**Code shaped around it: YES.** `ptr_member_type` and its `ptr_type_2` ..
`ptr_type_5` ladder (`gen_c_ptr.zen:92-176`) exist only to answer the type of a
`Ptr` member call, and `gen_c_expr.zen:125-132` (not my file) keeps a whole
fallback whose comment says "The fallback stops firing the moment sema types a
call." The same blanket claim is stated in `gen_c_expr.zen:128` and
`gen_c_call.zen:29` as well — three sites, one of them mine.

**What I did NOT establish, and so did not write:** whether sema's answer is
USABLE for these particular calls. `gen_c_read.zen:344-345` (my file) states a
narrower version that may well still hold — "sema has nothing either:
`alloc.create<T>()` is a bodyless generic member, so the whole chain hanging off
`p` is unknown to it". So the fallback may still be load-bearing even though the
blanket sentence is wrong. I deleted only the false clause and left every other
word of that paragraph — including its stride bug record — as written. **I did
not change any code and did not substitute a claim I have not read.**

### Verified TRUE — limitation claims I checked and left alone

- `gen_c_mono.zen:160-164` "a method that ALSO declares its own parameters ...
  that half is unwritten ... `refuse_method` names it". TRUE:
  `gen_c_member.zen:724` `refuse_method = ... (f.tparams.len > 0) || (has_body(f)
  == false)`, and `method_fault` renders "a generic method". Kept (compressed to
  defer to `gen_c_member.refuse_method`, which owns the fuller statement).
- `gen_c_print.zen:18-27` "THE `Env`-IN-SCOPE CLAUSE IS NOT ENFORCED HERE ... a
  rule sema has not written". TRUE: `src/sema/sema_call.zen:201-217` types the
  print sugar as `()` and says nothing about an `Env` being in scope; no
  Env-resolution rule exists in `src/sema/`. Both named corpus paths exist
  (`tests/corpus/cli/`, `tests/corpus/gen_zen/`). Kept whole.
- `gen_c_op.zen:396-400` `corpus/gen_zen/reports_what_it_cannot_lower` — the
  directory exists. Path kept exact; only the surrounding narration compressed.
- `gen_c_print.zen:66-87` "the slot's `args: ...` has no C spelling". TRUE:
  `src/std/env/env.zen:36-38` declares `Console* = { println* = (self: @Self,
  fmt: str, args: ...) Res<(), IoError> }` — bodyless, variadic. Kept.
- `gen_c_ptr.zen:4-11` "`mem_ptr.zen` writes nine signatures and no bodies".
  TRUE: `src/std/mem/mem_ptr.zen` declares 8 bodyless members (read, write,
  offset, back, bytes, copy_from, to, is_null) plus the bodyless free function
  `null_ptr` = 9. Kept.
- `gen_c_mono.zen:23-26` "an `Inst` is two parallel lists filled from `tparams`,
  never a `Map`". TRUE: `src/sema/sema_inst.zen:38-40` `Inst* = { vars ::
  Vec<TyId>, args :: Vec<TyId> }`. Kept.

### Nit (not changed, no claim is false)

`gen_c_ptr.zen`'s mid-file banner `// the nine` sits above 8 verbs — `ptr_verb`
lists 8 names, and the ninth (`null_ptr`) is under its own banner near the end.
The HEADER's "nine signatures" is correct (8 members + `null_ptr`); only the
banner reads one short of its section. Banners are ratified as navigation, so I
left it.

### Deleted (score 1-4)

- `gen_c_read.zen` — "A call to a top-level function the module can see, and the
  two `Res` constructors. / OVERLOAD RESOLUTION IS SEMA'S AND IS NOT THERE
  YET..." — score 0 — orphaned AND false; see FALSE #1. 7 lines.
- `gen_c_mono.zen:188-190` — "(It read "THE SAME QUESTION" while `has_var`'s
  one-line wrapper stood here; the wrapper went, and `sub_with` above asks
  nothing.)" — score 2 — pure refactor narration; the assertion it qualifies
  ("ASKED OF EVERY EMPTY SLOT AND NOT ONLY OF A FREE PARAMETER") is kept and
  stands alone. 2 lines.
- `gen_c_op.zen:241` — "Reported, not mis-lowered." — score 0 — false; see
  FALSE #2.
- `gen_c_op.zen:399-400` — "keep the message they have always had ... What
  changed is the case the test does not cover." — score 3 — refactor narration
  wrapped around a test path; the path and the refusal reason are kept.

### Deduplicated

- **"THE BOUND IS RECOGNISED BY ITS SHAPE, not by its name" + the `Vec.impl`
  two-readings story** was stated in `gen_c_range.zen`'s header (lines 8-15 and
  23-27) and again, near-verbatim, in the `a range whose bounds an IMPL supplies`
  banner (105-122). Kept in the header (which the parent assigned this file as
  owner of, against `gen_c_fat.zen`'s general version); the banner now reads "The
  header's second reading, at the site" plus its own distinct fact (COMPUTED
  FIELDS vs members, and the `at` quote). 18 -> 9 lines.
- **"a None ends the walk early / a container whose length moved under the loop
  stops rather than reading past itself"** appeared three times in
  `gen_c_range.zen` (header 17-21, `lower_impl_walk` 441-444, `write_pass_guard`
  711-713). Kept in the header; the two sites now name the `brk` label mechanism
  only.
- **"`@scope` IS THE BLOCK, AS A VALUE"** — per the parent's decision,
  `gen_c_own.zen`'s header paragraph now points at `gen_c_scope.zen` for why the
  block's record is the one storage certainly alive when the closure runs, and
  keeps its own distinct fact ("This is not escaping-closure support and must not
  grow into it"). 6 -> 4 lines. The lifted-defer-thunk argument and its C example
  are UNTOUCHED, as instructed.
- **"sema checks a generic body exactly once, generically"** was in
  `gen_c_mono.zen` twice (`open_named` 92-95 with its `Vec<u8>.add` calling
  `Vec<Row>.grow` bug record, and `sub` 172-175). Kept at `open_named`; `sub` now
  cites it.
- **The header's three bullets restated at their sites** in `gen_c_mono.zen`:
  `inst_at` (bullet 1) and the `putting the parameters back in scope` banner
  (bullet 2) now defer to the header instead of restating it.
- **`gen_c_op.zen`'s three rules restated at their sites**: `lower_arith`
  (ARITHMETIC TRAPS), `lower_compare` (`==` DISPATCHES), `lower_logical` (`&&`/
  `||` SHORT-CIRCUIT) now name the header rule and keep only their own distinct
  facts (the optimizer-deletes-an-after-the-fact-test argument; the `str`/`Eq`
  example and the `std.core` no-`Ord` quote; the spill mechanism).
- **`infix_shaped`** restated the spine banner's list of the two non-folding
  operator forms a third time; cut to a pointer at the banner. 4 -> 2 lines.
- **"A prelude declaration of a primitive's name IS that primitive"** was in
  `gen_c_read.zen`'s header (12-15) and verbatim again at `lower_type_or_field`
  (73-77). Kept in the header. 5 -> 4 lines.
- **"a value goes through its own `toString` instead"** was in `gen_c_print.zen`
  at both `printer` (283-285) and `write_display` (357-360). Kept at
  `write_display`, which also names `gen_c_display.zen` and where the diagnostic
  is; `printer` now points at it.
- **"dropping it is a use-after-free of what the caller is about to read"** was
  at both `leave_block` and `drop_unless_kept` in `gen_c_own.zen`. Kept at
  `drop_unless_kept`, which carries the argument ("only one is recoverable").
- **"C answers how big a `T` is, so a layout this backend never modelled cannot
  disagree with the one `cc` chose"** was in `gen_c_ptr.zen`'s header (32-33) and
  verbatim at `byte_size` (417-418). Kept in the header. 2 -> 1 line.
- **"a same-named type elsewhere is never confused for this one"** appears at
  `gen_c_own.collect_drop`, `gen_c_range.keep_range_impl` and
  `gen_c_read.impls_supplying`. All three are two-liners at the site of the
  module check, so a cross-file pointer would cost more than it saves; trimmed
  `gen_c_read`'s trailing clause only.

### De-rhetoricized

- `gen_c_mono.zen:any_open` — "Is any of these types still open? `find` and not
  a loop, because..." -> "`find` and not a loop: the answer is a `bool`, and the
  first open type is enough."
- `gen_c_mono.zen:inst_open` — "Did this instantiation leave a parameter free? A
  free argument mangles to `q`..." -> "A free argument mangles to `q`, so two
  instantiations would be one symbol — ..."
- `gen_c_own.zen` banner — "does this block write `@scope`?" -> "a block that
  writes `@scope`" (banner kept, `@scope` kept searchable).
- `gen_c_ptr.zen:is_ptr_member` — "Is the receiver a `Ptr`, and is this one of
  the nine? Both halves are asked: ..." -> "Both halves are asked: ..."
- `gen_c_range.zen:supplies_bounds` — "Does the range's own declaration STORE
  `start` and `end`, rather than supplying them through an impl?" -> "Whether the
  range's own declaration STORES `start` and `end` rather than supplying them
  through an impl."
- `gen_c_range.zen:is_res` — "Is this a `Res`? `impl_ctx` needs it for
  `has_ret`..." -> "`impl_ctx` needs this for `has_ret`..."
- `gen_c_read.zen` — checked, no rhetorical-question comments (the brief's guess
  was right).

### Compressed (score 7-9)

- `gen_c_range.zen` impl-supplies banner — 18 -> 9 — kept COMPUTED FIELDS and the
  `range.zen` `at` quote; cut the duplicated shape-recognition paragraph.
- `gen_c_range.zen:lower_impl_walk` header — 12 -> 9 — kept "why it is not
  `lower_bounded` with two reads swapped" and the `brk`-label mechanism; cut the
  restated None-ends-the-walk reasoning.
- `gen_c_print.zen:lower_console_print` ¶1 — 9 -> 7 — kept the whole broken-slot
  mechanism (`args: ...` has no C spelling, `ctype` falls back to `int`, `cc`
  rejects the `zg_str`); cut the restated DESIGN.md quote and the "that is the
  bargain this whole file exists to keep" flourish.
- `gen_c_op.zen:lower_compare` — 9 -> 7 — kept the `str`/`std.text` example, the
  `std.core` no-`Ord` quote and the "deciding a language question" refusal.
- `gen_c_mono.zen:unsettled` placement note — 3 -> 3 — kept "the reason is a
  BACKEND one (what has a C spelling)".
- `gen_c_own.zen:unwind_to` — 7 -> 6 — kept the NOT-popped frames rule verbatim.
- `gen_c_own.zen:unwind_drops` — 2 -> 1 — the header states the use-after-free
  law in full; the site now cites it.
- `gen_c_read.zen:lower_access`, `lower_type_or_field` — kept both DESIGN quotes
  exactly; only the framing sentences shortened.
- `gen_c_ptr.zen:ptr_member_type` — 8 -> 6 — the stride bug record ("It compiles,
  it warns at most, and `src.back(8)` moves back thirty-two bytes") kept word for
  word; only the false premise removed.

### Refused to cut

- `gen_c_own.zen`'s ⚠ lifted-defer-thunk argument INCLUDING the 5-line C example
  (parent's instruction: this file owns it whole).
- `gen_c_own.zen`'s "NOT DONE HERE" DESIGN.md `Vec.take` non-goal.
- `gen_c_own.zen:block_record`'s bootstrap-divergence record (it stopped
  `scripts/fixpoint.sh` from running at all).
- `gen_c_op.zen:248` "The bootstrapper and this backend once disagreed by exactly
  that — caught by a differential run" and the whole `spills_anywhere` paragraph.
- `gen_c_op.zen:102-112`'s exact trap position `std/core/num.zen:54:17`.
- `gen_c_op.zen:479-486`'s "measured, nested `.match` lost a third of its
  headroom".
- `gen_c_op.zen`'s spine banner: `tests/corpus/lex/long_single_line.zen`, ten
  thousand terms, eight megabytes of stack, "A crash is not a diagnostic"
  (docs/TESTING.md), `bootstrap/gen_c.py`'s `ex_Binary`, `scripts/fixpoint.sh`.
- `gen_c_op.zen:606-609`'s docs/GEN_BOOTSTRAP_FIXES.md `.match`-not-`.then`
  record.
- `gen_c_ptr.zen`'s docs/LEXER_BOOTSTRAP_FIXES.md §1 record — the ONE BYTE read
  and "every `Vec` whose buffer reaches 256 bytes silently loses the rows written
  before each grow" are kept exact.
- `gen_c_print.zen`'s `Env`-in-scope refusal with `tests/corpus/cli/` and
  `tests/corpus/gen_zen/` and both signatures.
- `gen_c_read.zen:92-105` (`j.WIDTH` emitted `.zg_m5WIDTH`; the bootstrapper
  already folded it, so this was also the two implementations disagreeing; grammar
  R4) and `:338-352` (`p.read(0).next` came back unknown).
- `gen_c_read.zen:327-335`'s two-impls-supplying-one-name argument.
- `gen_c_range.zen:523-529`'s shadowed-`self` bug record ("That compiled and
  resolved to nothing, which is how it was found").
- `gen_c_read.zen:411-412` "A named helper rather than a `.then` inside the loop
  body: a loop binding read inside a nested closure does not resolve" — an open
  compiler limitation.

### Wrong code noticed

None. No code was edited in any of the seven files; `codecheck_keep.py` confirms
byte-identical non-comment lines for all seven.



<a name="audit_gen_F.md"></a>

## Appendix: src/gen — section F

# gen/gen_c (F: runtime, scope, settle, shape, sink, stdin, stmt, type, widen)

## gen_c F — 1057 comment lines before, 982 after, 75 removed (7.1%)

Per file (before → after):

| file | before | after | removed | % |
|---|---|---|---|---|
| gen_c_runtime.zen | 151 | 138 | 13 | 8.6 |
| gen_c_scope.zen | 112 | 103 | 9 | 8.0 |
| gen_c_settle.zen | 125 | 107 | 18 | 14.4 |
| gen_c_shape.zen | 67 | 60 | 7 | 10.4 |
| gen_c_sink.zen | 186 | 179 | 7 | 3.8 |
| gen_c_stdin.zen | 89 | 80 | 9 | 10.1 |
| gen_c_stmt.zen | 96 | 91 | 5 | 5.2 |
| gen_c_type.zen | 152 | 147 | 5 | 3.3 |
| gen_c_widen.zen | 79 | 77 | 2 | 2.5 |

`python3 /tmp/codecheck_keep.py` prints ALL CODE IDENTICAL for all nine files
(run after every edit; it caught two edits of mine that had eaten the space in
`carry_extra = (` and `emit_stdin* = (` — both restored immediately).

7.1% is the honest yield. This folder has no filler at all: the 12-15% band
would have had to come out of DESIGN.md/TESTING.md/PLAN.md citations, exact
measurements (exit 134, ZG_DEFER_MAX 32, eight passes, sixty `TokenKind`
variants), regression records, and refusals. See "Refused to cut" below.

### FALSE (score 0)

1. **`gen_c_stdin.zen:5-6`** (header) — "the C it bottoms out in is in
   `gen_c_runtime.zen`, **which is why that file is the largest in the
   backend**".
   FALSE. `gen_c_runtime.zen` is 823 lines / 29,417 bytes. In `src/gen/gen_c/`
   the largest are `gen_c_member.zen` (1101 lines / 34,864 b) and
   `gen_c_call.zen` (1073 / 33,184); runtime is 9th by lines and 6th by bytes
   (measured with `wc -l` and `ls -l` over the folder).
   NO CODE IS SHAPED AROUND IT — it is rhetorical support for "one capability
   is ONE subject". Deleted the false clause only; the argument it supports is
   untouched.

2. **`gen_c_type.zen:143-145`** (`declarator`) — "Nothing in this subset is a
   pointer type, so nothing binds to the name — **the moment `Ptr<T>` is
   lowered** this is where the asterisk goes".
   FALSE: `Ptr<T>` IS lowered, in this same file. `ctype` → `maybe_ptr` →
   `ptr_ctype` → `elem_ctype` (lines 94-136) writes `<elem> *`, and
   `maybe_scope` writes `zg_scope *`. `maybe_ptr`'s own comment 10 lines above
   already describes the finished state ("This is where the asterisk goes, and
   it is the one place").
   NO CODE IS SHAPED AROUND IT: `declarator` writes spelling + space + name
   either way, and a pointer spelling arrives complete from `ctype`. Replaced
   the stale conditional with a pointer to `maybe_ptr`; asserted nothing new.

3. **Disagreement, not a verified falsehood — reported, not "fixed":**
   `gen_c_stdin.zen` states the ordinal contract twice and the two do not
   agree. Header: "THE ORDINALS ARE A CONTRACT BETWEEN THE TWO HALVES OF THIS
   FILE and with nothing else". Site (before `emit_stdin`): "THE ORDINALS ARE A
   CONTRACT WITH `gen_c_cap.zen` AND WITH NOTHING ELSE". The `ZG_IO_*` macros
   are consumed inside this file (`io_chain` / `open_full_test`); `gen_c_cap`
   supplies `write_assign_ok/err`, which take a variant NAME, not an ordinal.
   I kept the header (the brief designates it as this file's own) and deleted
   the site restatement. I did not write a new claim about `gen_c_cap`.

### Unresolved / suspicions (no edit made)

- `gen_c_runtime.zen:36-40` (deleted, see below) said the delimiters used to be
  written a byte at a time to dodge a lexer bug, "Fixed now that a string is one
  token". I did not verify the lexer claim; I deleted it as refactor narration
  (Lever 3), not as a falsehood, and asserted nothing in its place.
- `gen_c_type.zen:90-93` says a declarator comes out as `uint8_t *p`. What is
  actually emitted is `uint8_t * p`: `elem_ctype` appends `" *"` to the spelling
  and `declarator` then appends `" "` + name. Both are the same legal C
  declarator, so the sentence's claim ("the `*` bound to the name") holds and I
  left the text alone. Flagging the spacing only.
- `gen_c_settle.zen:262-266`: the SAME two-line comment appears twice, separated
  by a blank line, above `carry_extra`. I deleted the orphan and then RESTORED
  it: removing it leaves two consecutive blank lines, and the pristine tree has
  ZERO double blank lines in all of `src/` (checked), so that would be a
  formatting change I am not allowed to make. **This needs one blank line
  deleted along with the duplicate — a code-line edit, outside my mandate.**
- Not mine, but noticed while checking the above: `src/gen/gen_c/gen_c_read.zen:630`
  and `src/gen/gen_c/gen_c_inline.zen:248` now contain double blank lines that
  the pristine tree does not have. Two other agents have probably just made the
  edit I backed out of.

### Deleted (score 1-4)

- `gen_c_runtime.zen` `comment` — "An earlier version wrote the delimiters a
  byte at a time, to dodge a grammar bug…" — score 3 — refactor narration; the
  code is now the plain form and nothing depends on the history.
- `gen_c_settle.zen` `peek_param_named` — "— which is what it did before any of
  this." — score 2 — closing flourish about the past.
- `gen_c_widen.zen` header — "The set half moved here from `gen_c_expr.zen`,
  which had grown two subjects" — score 3 — refactor narration; kept the fact it
  was supporting (`expr` asks both questions in order, the answers live here).
- `gen_c_widen.zen` banner — "The older shape:" — score 2 — history label; the
  regression record it introduces was kept whole.
- `gen_c_sink.zen` `lower_sink_door` — "The temporary IS the answer, and the
  last write leaves its own `Ok` in it." — score 4 — `write_ok` 130 lines below
  states it where it is done.
- `gen_c_stmt.zen` `deliver_spilling` — "That is what keeps a `.match` in return
  position from allocating a variable per arm." — score 4 — the header says it.

### Deduplicated

- **⚠ "A LIFTED DEFER THUNK NEEDS NO NAME REMAPPING"** — stated in full in
  `gen_c_own.zen`'s header and restated in full in `gen_c_scope.zen`'s header
  *after* saying "See the header of `gen_c_own.zen` for the whole of it".
  `gen_c_scope.zen` is now the pointer sentence alone (7 lines → 2). The two
  local statements at `write_env_type` (fields carry the frame's mangled names)
  and `write_prologue` (the prologue is the whole of the remapping) stay.
- **"the block's own record is the storage a deferred closure's captures live
  in"** — `gen_c_scope.zen` OWNS it (kept whole, per the folder decision);
  `gen_c_runtime.zen`'s `@scope` banner now names the layout and defers for the
  argument (6 lines → 3). Runtime keeps its own distinct facts: the env union is
  as large as the largest capture record, ZG_DEFER_MAX is a constant because
  whole-program analysis cannot bound a `defer` in a loop, and the emission
  order (after the types, before the prototypes).
- **"a closure infers FROM a signature rather than into one"** — `gen_c_settle.zen`
  OWNS it (header untouched). Its own in-file restatements are gone: the "what
  the call evaluates to" banner (6 lines → 0, banner kept) and `call_bindings`'
  bullet list (9 → 3). `gen_c_shape.zen`'s header paragraph 3 now points at
  `gen_c_settle.zen` and keeps its own distinct fact — sema hands back `Res<q>`,
  the mangler's word for a type argument nothing decided (7 → 6); and
  `loop_result_type` no longer re-derives it, keeping only what is its own (the
  range settles the element: no `at` → its own index space → `usize`; an impl's
  `at` → what `at` returns) (11 → 6).
- **"`tcode` is injective, so two types share a name exactly when they are one
  type"** — `gen_c_type.zen`'s header KEEPS it (per the folder decision);
  `request_type` now defers to the header (3 → 2).
- **The `Scope`-has-no-`defer`-FIELD argument** — stated identically at
  `maybe_scope` and `request_defined` in `gen_c_type.zen`. Kept at `maybe_scope`
  (the spelling decision); `request_defined` defers (5 → 3).
- **"signed overflow is undefined behaviour in C, so no check after the fact"**
  — `gen_c_runtime.zen`'s header quotes DESIGN.md; `checked` restated it. The
  header keeps the quote; `checked` now says the check happens BEFORE the
  operation "for the reason the header gives" (6 → 4).
- **The unsigned-wrap conversion rule** — `fallback` and `wrapped_return` both
  spelled it out. `wrapped_return` (the function that writes it) keeps it whole;
  `fallback` now points at it (4 → 2).
- **"there is nothing underneath to write them in"** — `emit_print` (Console)
  and the filesystem banner (Fs) both carried the clause; kept at `emit_print`.
- **"THE DESTINATION'S TYPE WINS"** — `gen_c_stmt.zen`'s header owns it;
  `destination_type` restated it almost verbatim and now defers, keeping the
  clause that is its own (5 → 3).
- **"sema is asked first for every statement"** — header owns it; `stmt` defers
  (3 → 2).
- **"only a bare name can be a binding this block owns"** — stated at `keep_name`
  and again at `bare_name`; kept at `keep_name`, `bare_name` now just says what
  it returns (2 → 1).
- **"the writers are `text_fmt.zen`'s own functions, not C written here"** —
  `gen_c_sink.zen`'s header owns it (kept whole, including the linker-error
  record and "the corpus pins exactly one" number format); `value_call` and
  `writer_of` no longer re-argue it.
- **"every write reachable from a `{}` answers with exactly `Res<(), WriteError>`"**
  — header owns it; `write_guarded` defers and keeps its own consequence (no
  rebuild, no re-tag, no error set to widen).
- **"NOTHING IS ALLOCATED / law 1"** in `gen_c_stdin.zen` — stated in the floor
  banner and again in the lowering banner; kept in the floor banner.
- **The ordinal contract** in `gen_c_stdin.zen` — see FALSE #3.

### De-rhetoricized

- `gen_c_type.zen:spellable` — "Can this type be spelled at all? Asked wherever
  a diagnostic has a position to point at." → "Whether the type can be spelled
  at all, asked wherever a diagnostic has a position to point at."
- `gen_c_type.zen:is_c_integer` — "Is this an integer type a trapping operation
  can be emitted for?" → "The integer types a trapping operation can be emitted
  for."
- `gen_c_widen.zen:needs_widen` — "Does this value have to be REBUILT to reach
  the `Res` that is wanted?" → "Whether the value has to be REBUILT to reach the
  `Res` that is wanted."

### Compressed (score 7-9)

- `gen_c_scope.zen` header, the `Scope`-type banner — 7 → 6 lines; every claim
  kept (frame is the authority, `LoopHandle` parallel, `std/core/scope.zen`).
- `gen_c_scope.zen:write_thunk` — 6 → 5; dropped only the restatement that this
  is not the escaping closure the design forbids (header says it twice already).
- `gen_c_runtime.zen:emit_print` — 6 → 5; DESIGN.md routing, the bodyless
  `Console` members and "one newline per `println`" all kept.
- `gen_c_sink.zen`, "reached through a receiver" banner — 10 → 9; the whole
  `text_string.zen`-declares-no-writer argument kept.
- `gen_c_sink.zen`, the `Piece` banner — 4 → 3.
- `gen_c_settle.zen:range_element` — 5 → 3; the `gen_c_loop.zen` rule is named
  rather than re-quoted (the header quotes it in full).
- `gen_c_settle.zen`, the inlined-call banner — 7 → 4; keeps the reason the
  query exists (a match scrutinee is typed before it is written).
- `gen_c_stdin.zen:io_chain` — 6 → 4; both failures and "END OF INPUT IS NEITHER
  — it is `Ok(0)`" kept exactly.
- `gen_c_type.zen:is_scope_named` — 3 → 2.
- `gen_c_type.zen:ctype` — reflowed, no claim lost.

### Refused to cut (and why)

- `gen_c_runtime.zen`'s header in full: DESIGN.md quote on signed overflow, the
  trap model (`file:line:col: trap: <what>`, exit 134, the three whats, the
  OPERATOR position and why `Binary`/`Unary` carry `op_span`), `i32.MIN / -1`
  trapping as OVERFLOW with TESTING.md's record of it, and PLAN.md's "what a
  newcomer runs needs only a C compiler" behind the builtins-are-a-fast-path
  rule. Every number and citation is byte-identical to before.
- `gen_c_type.zen:union_member_type` (21 lines): two DESIGN.md citations, the
  `TokenKind` measurement (sixty variants, one collision, three dead words per
  token), and the verified workaround claim — I checked it: `ast_node.zen:48`
  declares `Equal`, and `sema_def.zen:57` reads
  `DefKind* = StructDef | EnumDef | AliasDef | FunctionDef | ConstDef`, i.e.
  every variant suffixed `Def`. The comment is TRUE as written.
- `gen_c_sink.zen`'s header (the variadic/`{}`-by-argument-type bargain and the
  linker-error record) and `last_is_variadic`'s underflow record (exit 134).
  Also verified: "this tree's only other top-level `add` takes two Durations by
  value" — `src/std/core/time.zen:96` is the only other one.
- `gen_c_stmt.zen:bind_name` (the `i ::= 0; loop(…)` loop-that-never-ends
  regression record) and `is_store` (the inlined-callee store into the CALLER's
  binding). Both are score-10 measurements.
- `gen_c_scope.zen:lower_defer`, which names `defer_captures_at_registration` —
  the test exists at `tests/corpus/own/defer_captures_at_registration.zen`.
- `gen_c_widen.zen`'s "NARROW ON PURPOSE" paragraph (why the wider-set case is
  deliberately NOT claimed here, and that claiming it would be a silent wrong
  value) — a refusal plus a rejected alternative.
- `gen_c_settle.zen:496-498` — a section banner ("the body, in the caller's
  frame") that labels nothing: the next line is another banner, and the body
  lowering lives in `gen_c_inline.zen`. Banners are ratified KEEP, so I left it.
  Flagging it as dead navigation for a human to decide.

### Wrong code noticed

None. No behavioural defect found in the nine files.



<a name="audit_sema.md"></a>

## Appendix: src/sema

## src/sema — 4044 comment lines before, 3967 after, 77 removed (1.9%)

**This is well under the 12-15% target and it is the honest number.** See
"Why the yield is low" at the bottom. All 35 files verified with
`/tmp/codecheck_keep.py` against the rebuilt `/tmp/srcbase`: ALL CODE
IDENTICAL, exit 0.

---

### FALSE (score 0)

Six false comments, in three families. Two have code shaped around them.

**F1. `sema_check.zen:497` (`uninstantiated`) — CODE IS SHAPED AROUND IT.**
> "`sema.zen` says at the top of this folder that generic instantiation
> does not SUBSTITUTE, and this is where that costs something"
> …"Every line of this deletes when substitution lands, and nothing else
> has to change when it does."

`sema.zen:22` says the opposite — "INSTANTIATION SUBSTITUTES
(`sema_inst.zen`)". Substitution exists: `sema_inst.zen:121` declares
`subst*` with a full structural walk (`subst_kind`, `subst_named`,
`rebuild_named`, `subst_res`, `subst_fn`, `subst_union`, `subst_list`),
called from `sema_apply.zen:240` (`instantiated_ret`), `sema_apply.zen:535`
(`applied_at_recv`) and `sema_member.zen:702` (`add_own`).

The code shaped around it is the whole `uninstantiated` disjunct of
`assignable` (`sema_check.zen`), reached from every assignability question
in the folder. Whether any of its arms are now dead is NOT something I
could determine by reading; I did not touch the code. Comment now names
the three call sites and says the question is open.

**F2. `sema_bound.zen:~185` (`satisfies_bound`) — same claim, second site.**
> "`same_type` and not `eq`, and that is forced by what this folder does
> not do yet: instantiation does not SUBSTITUTE."

Same contradiction. The false clause is deleted; the rest of the argument
(two `TyVar`s by construction, id-compare is a blanket rejection) stands on
its own and is kept verbatim.

**F3. `sema_ty.zen:663` (`key_before`) — CODE IS SHAPED AROUND IT.**
(the one the brief pre-identified; confirmed independently)
> "`std.text` doesn't declare one yet … Delete this once text_str grows an
> ordering."

`str.before` EXISTS at `src/std/text/text_str.zen:65`, and its own comment
reads: "THREE components had each written their own — sema's type-key
ordering, the backend's section sort, deterministic emit". Corroborated a
third way inside this folder: `sema_cycle.zen:294` already CALLS
`str.before` (`module_name_of(..).before(..)`), and `sema_cycle.zen:588`
explains that it declines to import `ast_find.before` precisely because
`before` is "ALSO `str`'s byte order and `first_named` calls that one".

Dead weight: `key_before` (`sema_ty.zen:664`), its re-export at
`sema.zen:53`, and its only consumer `Types.before` (`sema_ty.zen:611`).
**Code NOT deleted** — reported for the parent. Comment now says plainly
that it is a duplicate of a closed gap and what to delete.
`docs/SEMA_BOOTSTRAP_FIXES.md` §4 is stale for the same reason (not edited;
docs/ is out of scope).

**F4-F6. Four §10 citation sites asserting a gap the cited doc records as
CLOSED.** `sema_check.zen` (`bounds_of`), `sema_def.zen` (`variant_each`),
`sema_call.zen` (`keep_one`), `sema_member.zen` (`keep_bounded`), plus two
sibling sites in `sema_member.zen` and one in `sema_supply.zen` and one in
`sema_call.zen`. All said, present tense, "a loop binding read inside a
nested closure does not resolve". `docs/SEMA_BOOTSTRAP_FIXES.md:358` reads
"**CLOSED as written, 2026-08-08**", and :384 says the seven workaround
sites "are therefore no longer required" but "each site should be re-tested
rather than assumed". Code shaped around it: eight named helper functions
that exist only as the workaround. **Code NOT deleted.** Comments now cite
§10 as closed and say re-test before removal — the doc's own instruction.

**Adjacent, not in the six — a wrong measurement + wrong section.**
`sema_member.zen:187` read "SEMA_BOOTSTRAP_FIXES.md **§7** records
**twenty-two** diagnostics naming unrelated modules for one missing
import". §7 is a different entry entirely (match-first-arm typing reaching
`cc`). The entry meant is §8, and §8 says **twenty-three**, from four
missing names on one import line. Corroborated inside the folder:
`sema_match.zen:30` cites "§8 is twenty-three". Changed to §8/twenty-three,
both verbatim from the doc. **Flagging explicitly because this touches a
protected measurement** — revert if the parent would rather it were only
reported.

**Adjacent — a stale count.** `sema_check.zen:104` said "the memo tables.
**All three** key on a node id" above a list of two, in a struct with seven
memo tables (one of which, `set_memo`, keys on a `TyId`, not a node id).
Changed "All three" to "They".

---

### Stranded comments (a defect class, not a score)

Two paragraphs sat on the wrong function, jammed into an unrelated comment
with no blank `//` separating them. Each was moved onto the function it
describes; no text was lost.

- `sema_call.zen` — "CONSTRUCTING IS A RESOLUTION TOO, and it is recorded
  for the same reason a call is…" sat on `no_overload`, which records
  nothing and is about the absence of a candidate. It describes
  construction; moved onto `construct_def`, with "recorded by `construct`"
  added — verified at `sema_apply.zen:61`, `c.resolve_call(id, d.id).try()`.
- `sema_diag.zen` — "Both sides, always. `expected` first, because that is
  the order the reader is thinking in…" sat on `write_export`, which prints
  a name and a module. It describes `write_types`, the function that prints
  `expected X, found Y`; moved there.

Also in `sema_diag.zen` (`write_pair`): two leading lines, "Both
declarations, named. The rule is 'named for both declarations', so a
renderer that prints one position is not implementing it", were a weaker
restatement of the paragraph immediately below them in the SAME comment
("BOTH DECLARATIONS, EACH WITH ITS FILE…"). Deleted the weaker one.

---

### Deleted (score 1-4)

Almost nothing scored this low. The only outright deletions were clauses
shown false (F1-F3 above) and closing flourishes (below). No comment was
deleted for being uninformative.

---

### Deduplicated

- **"a program full of mistakes still analyses: it yields the types it
  could compute and the diagnostics it owes"** — stated in full in
  `sema.zen`, `sema_check.zen` and `sema_diag.zen`. Kept in `sema_diag.zen`
  (the file that owns diagnostics); `sema_check.zen` now defers to it and
  keeps only its own distinct fact (the LSP showing four errors).
- **"the refusal belongs at the consumer, which is what `has_var` is
  for"** — four sites in `sema_apply.zen` alone (header, the
  ctor-inference banner, `note_edge`, `call_inst`). Kept at the header;
  the other three keep only their distinct fact (`Range(0,5)` names no `T`
  / the walk stops rather than guessing / precedence order).
- **`call_inst`'s whole 9-line comment** was the header's two paragraphs
  restated ("TWO SOURCES, AND THE WRITTEN ONE WINS" + "A PARAMETER NEITHER
  SOURCE REACHES STAYS FREE") almost verbatim. 9 → 3, deferring to the
  header.
- **"A CONSTRUCTION IS APPLIED TOO"** — `sema_apply.zen` header and
  `construct` gave the same argument, the function's version fuller. Header
  trimmed 6 → 2, pointing at `construct`.
- **"a small set, so the shape with nothing to get wrong is the right
  one"** — `sema_ty.zen` `sort_unique_into` and `insert_ordered`, 15 lines
  apart. Kept at the first; second defers.
- **"no narrowing conversion goes back from a `usize`"** — `sema_ty.zen`
  `TyId`, `Types` and `kind_at`. Kept fullest at `TyId`; `Types` defers.
- **"a match takes its type from its FIRST arm"** — `sema_ty.zen` `intern`
  and `sort_unique_into`. Second defers to the first, keeps the citation.
- **"a folder root has two spellings"** — `sema_def.zen` `PRELUDE_FILE` and
  `index_of`. `PRELUDE_FILE` defers to `index_of` (the fuller, with the
  `bootstrap/modules.py` citation), 6 → 4.
- **"a variant carries no star of its own"** — `sema_def.zen`
  `exports_name` and `collect_variant`. `collect_variant` defers.
- **"the first parameter is what makes a free function a method, and
  sharing the name never was"** — `sema_cand.zen` header, `sema_cand.zen`
  `travelled_cands`, `sema_def.zen` `exported_named`. `travelled_cands`
  defers to its own header.
- **"a signature is resolved in the module that DECLARES it, or `<T>(a: T)`
  reports its own `T` as an undefined name"** — `sema_cand.zen` header and
  `add_cand`, verbatim. `add_cand` 3 → 1.
- **"no early exit — `find` takes a closure that answers `bool`, and asking
  whether an argument keeps a bound allocates"** — `sema_cand.zen`
  `all_fit` and `args_fit`. `args_fit` 3 → 1.
- **"the three §10 named helpers"** in `sema_member.zen` — three identical
  2-line comments. First carries the full note; other two are one line each.
- **"a written type is a name, and a name means what it means where it was
  written"** — `sema_type.zen` `alias_written_type` and `const_type`,
  verbatim. `const_type` defers.
- **"`[u8, 64]` and `[u8, 65]` are different types (DESIGN.md:301)"** —
  `sema_ty.zen` `TyArray` and `sema_type.zen` `array_type`. The second
  defers, keeping the citation.
- **"a prelude declaration of a primitive's name IS that primitive"** —
  `sema_ty.zen` `named` (with the bug record) and `sema_member.zen`
  `prim_members`. The latter defers to the former, 9 → 7.
- **"`unbounded`: poison, a hole and a type parameter carry no answer"** —
  `sema_bound.zen` `unbounded` and `dispatches_eq`. Second defers.
- **"the untyped `:`-self walk that was removed"** — `sema_recv.zen` header
  (with the measurement) and `sema_decl.zen` `check_all`. `sema_decl.zen`
  defers.
- **"fail-open: a false rejection breaks a correct program, a missing check
  merely misses"** — `sema_own.zen` header and `sema_drop.zen` header
  (siblings; `sema_own` drives all four). `sema_drop.zen` defers.
- **"a print's value is unit"** (`gen_c_print.zen` quote) —
  `sema_call.zen` `print_or_call` and `sema_hoist.zen` `wrong_return`.
  `sema_hoist.zen` defers.
- **`has_var` is how a consumer finds out** — `sema_inst.zen` header,
  `subst`, `has_var`, `zip`. Kept at header + `has_var`; `subst` and `zip`
  drop the pointer.

---

### De-rhetoricized

All 23 rhetorical-question comments in the folder are converted.

- `sema_drop.zen:61` — "Does an impl OF Drop exist for this type?" → "Whether an impl OF Drop exists for this type."
- `sema_effect.zen:2` — "Does this statement DO anything?" → "What a statement DOES, and when computing is not doing."
- `sema_join.zen:5` — "given what the match is worth so far and what this arm is worth, what is it worth now?" → "what the match is worth so far, joined with what this arm is worth."
- `sema_call.zen:113` — "did the argument NAME a field?" → "whether the argument NAMED a field."
- `sema_call.zen:889` — "Does either candidate's generic accept everything the other's concrete parameter does, position by position?" → "Either candidate's generic accepts everything the other's concrete parameter does, position by position."
- `sema_bound.zen:176` — "Does `ty` keep the promise `bound` makes? An impl of it, or the same type" → "Whether `ty` keeps the promise `bound` makes: an impl of it, or the same type"
- `sema_depth.zen:477` — "Does this list still mention a type parameter nobody has substituted?" → "Whether the list is free of type parameters nobody has substituted." (**also a polarity fix**: the function is `settled`, and the question as written described its negation)
- `sema_spine.zen:37` — "Is there a spine below this operand at all?" → "Whether there is a spine below this operand at all."
- `sema_ty.zen:387` — "Is `member` one of `set`'s members? A set of one is its member…" → "A set of one is its member…" (2 → 1)
- `sema_ty.zen:403` — "Is every member of `narrow` also a member of `wide`? This is the whole of…" → "Every member of `narrow` must also be a member of `wide`, which is the whole of…"
- `sema_def.zen:122` — "Which module is spelled `std.core.result`?" → "The module spelled `std.core.result`."
- `sema_def.zen:189` — "Did `mi` write an import binding this name?" → "Whether `mi` wrote an import binding this name"
- `sema_def.zen:450` — "Does module `mi` let `name` out at all?" → "Whether module `mi` lets `name` out at all."
- `sema_cand.zen:282` — "Does the last parameter say the list does not end?" → "Whether the last parameter says the list does not end."
- `sema_cycle.zen:284` — "Is `mi` the earliest-NAMED module on this cycle?" → "Whether `mi` is the earliest-NAMED module on this cycle."
- `sema_cycle.zen:572` — "Is `at` inside `outer`, IN THE SAME FILE?" → "Whether `at` is inside `outer`, IN THE SAME FILE."
- `sema_cycle.zen:700` — "Does this dotted path denote module `mi`?" → "Whether this dotted path denotes module `mi`."
- `sema_check.zen:398` — "Is this bound one a generic in scope declared? The question impl selection asks, and the only question it asks." → "A bound some generic in scope declared — the only question impl selection asks." (2 → 2, one clause of rhetoric dropped)
- `sema_check.zen:406` — "Does anything in scope say what this type parameter promises? The question `bounds_of` answers with a list, asked as a predicate…" → "`bounds_of` asked as a predicate…" (3 → 2)
- `sema_check.zen:448` — "Is a value of type `got` acceptable where `want` is expected?" → "Whether `got` is acceptable where `want` is expected." (merged into the paragraph below, 6 → 5)
- `sema_recv.zen:17` — "The test: would a bitwise copy of the receiver see the change?" → "The test: whether a bitwise copy of the receiver would see the change."
- `sema_match.zen:382` — "`U(matrix, q)`: is there a value matched by `q` and no row of `matrix`?" → "`U(matrix, q)`, the header's question." (also a dedup — the header states it)
- `sema_inst.zen:210` — "Does this type still mention an unsubstituted parameter?" → "Still mentions an unsubstituted parameter."
- `sema_member.zen:413` — "Is `base.name` supplied by an impl — …? One question, asked by both rules" → "Whether `base.name` is supplied by an impl — … Asked by both rules"

---

### Compressed (score 7-9)

- `sema_cycle.zen` header — 53 → 46. Cut a flourish ("a program with neither mistake in it has nothing for these to look at"), "and says so", "Reported:", and the closing sentence of the STYLE.md block. Every argument, citation and the worked `even.zen`/`odd.zen` example kept.
- `sema_diag.zen` header — 46 → 42. Cut the "a tree full of mistakes still ANALYSES" sentence (deduped to `sema_diag`'s own paragraph above it and to `sema.zen`), "A payload that is one field short does not stay one field short" (restates the clause after it), and the closing half of the STYLE.md block.
- `sema_check.zen` header — 43 → 40. "A DIAGNOSTIC IS A VALUE" now defers to `sema_diag.zen`; "WHERE THE `Alloc` IS" tightened without losing the DESIGN.md quote or the rejected alternative.
- `sema_call.zen` header — 44 → 42 (STYLE.md block 8 → 6, three predicates named in one clause instead of two sentences).
- `sema_def.zen` header — 34 → 31. Cut "A `defs_of` that returned one answer would have decided the thing overload resolution exists to decide" (flourish restating the sentence before) and tightened two clauses.
- `sema_bound.zen` header — 30 → 27. "The impl half arrived first" (history, load-bearing on nothing) cut; the `bound_members` paragraph folded into the split argument.
- `sema_member.zen` header — 27 → 25. The `Rect` argument said twice ("different questions" then the example) → once, with the example.
- `sema_type.zen` header — 23 → 21. The five-file list after "the forms that grew their own subject have left" duplicated the parenthesis before it; kept the parenthesis.
- `sema_depth.zen` header — 42 → 39. Cut "a depth bound that reports at the wrong end of the cycle sends them to the wrong function" (restates "the call the author has to change") and "a program has only as many call sites as it has lines".
- `sema_scope.zen` header — 21 → 20. Cut "the three ways out below are barred to buy the one guarantee that makes `defer` free" — the sentence before already asserts it.
- `sema_recv.zen` header — the removed-walk paragraph 13 → 9, keeping "Measured, not assumed", the impl-body-write finding, and "cost the suite one sentence, no position".
- `sema_apply.zen` — header 26 → 22; `call_inst` 9 → 3; `note_edge` 4 → 2; the ctor banner 4 → 2.
- `sema_hoist.zen` `res_return` — 5 → 4; the second sentence repeated "nothing lifts, and `assignable` already answered" verbatim from the first.
- `sema_inst.zen` — `subst` 4 → 3, `zip` 3 → 2.
- `sema_cand.zen` `takes_receiver` — 22 → 21 (one clause; the rest is a regression record kept whole).

---

### Refused to cut

- **`sema_trap.zen` — nothing.** 138 comment lines and every one is a
  spec citation, a measurement (`FOLD_LIMIT`, `FOLD_DEPTH` = 256,
  `I64_MAX`), a refusal rationale ("the folder may not trap itself"), or a
  named corpus path. Read in full; no change.
- **`sema_own.zen`, `sema_layout.zen`, `sema_union.zen`, `sema_place.zen`,
  `sema_static.zen`, `sema_module.zen`, `sema_try.zen`, `sema_raise.zen`,
  `sema_id.zen`** — read in full, no compressible prose found.
- **Every "OVER 500 LINES, AND THE JUSTIFICATION STYLE.md ASKS FOR" block**
  (4 files) — compressed, never deleted. All four files are real
  exceptions listed in `scripts/line_cap.py`.
- **`sema_depth.zen`'s "60GB and 113 seconds"** and `DEPTH_BUDGET: 24` with
  its `bootstrap/sema.py` agreement — untouched, numbers exact.
- **Every "BUG FOUND THE HARD WAY" / regression record** — `sema_hoist`'s
  `str`-as-two-types, `sema_inst`'s `ok_or` binding, `sema_case`'s
  `res_try_error_set_keeps_the_variant`, `sema_type`'s `RES_PATH` and
  fixed-array element, `sema_join`'s order-dependent join, `sema_cand`'s
  variadic `String`, `sema_call`'s `recv_off`, `sema_decl`'s three. These
  are score-10 measurements per the brief and were only ever tightened
  where a sentence literally repeated the one before it.
- **`sema_case.zen`'s "KNOWN GAP (gen_c)"** and `sema_module.zen`'s "KNOWN
  GAP" — open defects, untouched.
- **`sema_diag.zen`'s `write_literal`** note that "the bootstrapper loses a
  captured struct's type across a lambda boundary" — checked against §10
  and it is the shape that SURVIVES (§10's form (b), a parameter reaching a
  `.then` body). Correct and current; kept.

---

### Coverage — honest about depth

All 35 files had **every comment line** read. Depth of the surrounding code
differed, and that matters for how confidently a claim was checked:

- **Read in full (code + comments), 22 files:** `sema.zen`, `sema_apply`,
  `sema_bound`, `sema_call`, `sema_cand`, `sema_case`, `sema_check`,
  `sema_cycle`, `sema_def`, `sema_depth`, `sema_diag`, `sema_drop`,
  `sema_effect`, `sema_hoist`, `sema_id`, `sema_inst`, `sema_join`,
  `sema_member`, `sema_recv`, `sema_supply`, `sema_ty`, `sema_type`,
  `sema_trap`.
- **Comment lines read in full, code sampled only, 12 files:**
  `sema_layout`, `sema_match` (header + the sections I edited),
  `sema_module`, `sema_own` (header + two sections), `sema_place`,
  `sema_raise`, `sema_scope`, `sema_static`, `sema_try`, `sema_union`,
  `sema_decl` (header + edited section), `sema_spine`.

The consequence: in that second group I could judge a comment's prose and
its internal consistency, but a comment there asserting something about
code I did not read would not have been caught. The FALSE findings above
all come from the first group.

### Why the yield is low (1.9%, not 12-15%)

I did not find a filler band, and I did not find much duplication either.
Two measurements:

1. **Exact repeated sentences across the folder: six.** I extracted every
   comment sentence of 7+ words from all 35 files and bucketed by normalised
   word sequence. The only repeats are the four "OVER 500 LINES" openers,
   the DESIGN.md ufcs quote (3 files), the `satisfies_bound` phrase (2), the
   §10 helper opener (2), `ret`/`has_ret` (2), and the `check_literal` quote
   (2). Every one of those is a citation or a deliberate cross-reference.

2. **The comment mass is in file headers.** 35 headers hold roughly 700 of
   the 4044 lines, and they are the design record — each states the file's
   subject, its split justification (which STYLE.md requires), and the
   rejected alternatives. Compressing them yielded 10-15% each at the very
   limit of what I could cut without losing an argument, which is where I
   stopped.

The paraphrase-level duplication I did find is listed under Deduplicated
above and I took all of it. Beyond that, reaching 12% would have meant
deleting arguments, not restating them — which the brief forbids and which
would not be recoverable from the code.

The high-value output of this pass is not the line count. It is six false
comments (two with code shaped around them), two stranded paragraphs, a
mis-cited measurement, and a stale count.



<a name="audit_std.md"></a>

## Appendix: src/std

## src/std — 3208 comment lines before, 3139 after, 69 removed (2.2%)

Counts are pure-comment lines (what `codecheck_keep.py` ignores), measured
against the rebuilt `/tmp/srcbase/`, and EXCLUDE `parse/parser.zen` (parent's
cull, 388 -> 325, untouched by me).

Per-file:

     25 ->  24  (-1)   ast/ast.zen
     89 ->  87  (-2)   ast/ast_named.zen
    238 -> 229  (-9)   ast/ast_node.zen
     95 ->  94  (-1)   build/build.zen
     87 ->  84  (-3)   collections/collections_map.zen
     38 ->  37  (-1)   collections/collections_vec.zen
     44 ->  42  (-2)   core/display.zen
    104 -> 103  (-1)   env/env.zen
     20 ->  19  (-1)   lex/lex_byte.zen
     27 ->  24  (-3)   lex/lex_diag.zen
    123 -> 107  (-16)  parse/parse_decl.zen
     97 ->  92  (-5)   parse/parse_diag.zen
    152 -> 146  (-6)   parse/parse_expr.zen
    170 -> 166  (-4)   parse/parse_lookahead.zen
     32 ->  30  (-2)   parse/parse_match.zen
     80 ->  75  (-5)   parse/parse_member.zen
     38 ->  37  (-1)   parse/parse_pattern.zen
     70 ->  69  (-1)   parse/parse_stmt.zen
     80 ->  77  (-3)   parse/parse_token.zen
     79 ->  77  (-2)   parse/parse_type.zen
    (ast_find, lex_cursor edited with no net line change — de-rhetoricized)

All 62 files were read in full. Every edited file verified with
`codecheck_keep.py`: ALL CODE IDENTICAL, individually and in one batch run.

### FALSE (score 0)

- `env/env.zen:25-26` (before edit) — "IoError is the io failure every
  Console signature names and **no module declares yet**; see the report."
  **FALSE.** `src/std/core/io.zen:6` declares `IoError*` (Closed | Full |
  Invalid | Interrupted), and it reaches env.zen through the prelude:
  `core/core.zen:48` re-exports `IoError*, WriteError*, Sink* = std.core.io`
  and `std/std.zen:21` re-exports it again. `core/core.zen:46-47` even
  explains why it lives in core ("every Display signature names it").
  **Code shaped around it: NO.** env.zen names `IoError` bare in
  `Console.println` and `Stdin.read` and that already resolves through the
  prelude; nothing is stubbed or duplicated because of the claim.
  FIXED (comment only): now reads "…and the IoError every Console and Stdin
  signature names (declared by std.core.io)".

### SUSPECTED STALE — reported, NOT edited (no confident rewrite)

- `env/env.zen:63-68` — "ONE NOMINAL ENUM, not a union: the compiler is
  written in the seed subset, which has no error unions (PLAN.md 0.5) —
  that's what puts OutOfMemory here beside AllocError's own… **When unions
  arrive** this becomes `Res<String, FsError | AllocError>` and the variant
  goes."
  What I checked: `docs/PLAN.md:220` does list "error *unions*" as NOT in
  the seed subset, so the citation is accurate as a citation. But the tree
  around it has moved: `src/std/core/io.zen:14` declares
  `WriteError* = IoError | AllocError` and USES it —
  `Sink.write`/`write_byte` (io.zen:25,30), `Display.dump`/`toString`
  (core/display.zen:44,50,56), `String.add` and `String.impl(Sink,..)`
  (text/text_string.zen:30,57,62), `text_fmt.add*` (text_fmt.zen:80-102) —
  and the compiler has union machinery (`src/sema/sema_union.zen`,
  `src/gen/gen_c/gen_c_layout.zen:128`). So "when unions arrive" appears to
  describe a gap that is at least partly closed.
  **Code IS shaped around it:** `FsError.OutOfMemory` (env.zen:76) exists
  only because the union spelling was unavailable, and the comment names it
  as the thing that goes away.
  I did not rewrite it: I cannot tell from src/ alone whether unions are
  usable in every position the seed subset compiles, and PLAN.md still says
  they are excluded. Someone should reconcile PLAN.md 0.5 with io.zen.
  (Related: `lsp/lsp_json_read.zen:14` cites "the same choice `FsError`
  made", i.e. a second site leaning on the same premise — outside my folder.)

Every other hit of the stale-claim grep in src/std was checked and holds:
`core/eq.zen:12` ("until it lands" — @meta is still stage 5, no `@meta` in
the tree), `core/hash.zen:32`, `core/display.zen:29`, `env/env.zen:155`
(all @meta/stage-5, still open), `core/time.zen:26` (a regression record
about a comment that once lied — KEPT), `parse_diag.zen:88` ("the driver
used to print `d.message` and stop" — regression record, KEPT),
`parse_expr.zen:211,240` (both regression records for depth-guard bugs,
KEPT), `mem_arena.zen:136` ("this is the design, not a stub" — true).

### Deleted (score 1-4)

- `parse/parse_pattern.zen:68` — `// "cover every case or write `_`"` —
  score 2 — a bare verbatim repeat of the same quote ten lines above at
  `name_or_wild`, adding nothing at `wild_pattern`.
- `ast/ast_named.zen:32-33` — "The move was verbatim; only the imports below
  name sibling files directly instead of the folder root." — score 3 —
  refactor narration; the STYLE.md/design_lsp.md citation above it is kept.
- `core/display.zen:48-49` — "Writes into the CALLER's sink, so nesting
  three deep still costs one buffer, and console printing costs none." —
  score 4 — verbatim restatement of the file header, three lines up in the
  same screen.

### Deduplicated

- **"a `(` after the `)`: expression reading vs declaration reading"** was
  argued at `parse_lookahead.lambda_ahead`, `ret_start` and
  `fn_value_after` -> full argument kept at `lambda_ahead`; the other two
  now state only their own distinct fact (`ret_start`: the P2 `<` case;
  `fn_value_after`: the `() {..}` return type).
- **left-associativity via `a - b - c`** was in `parse_expr.binary_from`
  and `binary_step` -> kept at `binary_from` (which introduces `min`);
  `binary_step` defers.
- **"`<` needs a scan: `a < b` vs `alloc.Vec<i32>()`"** was in
  `parse_expr.postfix_continues` and `targs_call` -> full at
  `postfix_continues`, one line at `targs_call`.
- **`.match` is its own node, not a call** was in the parse_expr header
  (with AST_CONTRACT), at `dot_target`, at `match_expr`, and at
  `ast_node.Match` -> header + `ast_node` keep the argument; `match_expr`
  keeps only "the argument is an arm list, and exhaustiveness is checked
  on it".
- **`Module`'s fields / end-of-file trivia** was written out at
  `ast_node.Module` and again at `parse_decl.module` -> kept at
  `ast_node`; `parse_decl` keeps its own distinct fact (the module's span
  is the whole file, trivia included).
- **DESIGN.md's four-row method table (`= sig` / `= sig {..}` / `::= sig
  {..}` / `::= sig`)** was written verbatim at `ast_node.Form` and again at
  `parse_decl.fn_value` -> kept at the `Form` declaration; `fn_value` keeps
  the `form`-vs-`body` non-redundancy and points at it.
- **impl target is an `Ident`, never qualified, no orphan impls** was at
  `ast_node.Impl` and `parse_decl.impl_decl` -> kept at `ast_node`.
- **a variant payload is a TYPE, never `name: value`** was at
  `ast_node.Variant` and `parse_decl.one_variant` -> compressed at the
  parse site.
- **`leading_bar` stored, not derived from `variants.len == 1`** was at
  `ast_node.Enum` and `parse_decl.enum_decl` -> both kept (the parse site
  is where it is written) but the second reduced to three lines.
- **bounds are a LIST because `+` joins them** was at `ast_node.TParam` and
  `parse_member.type_params` -> kept at `ast_node`, referenced from the
  parser.
- **"no implicit receiver" / "a declaration names its parameter types"** was
  at `ast_node.Param`, `parse_member.one_param` and
  `parse_decl.typed_params` -> the full argument (with its regression
  record) stays at `typed_params`; `one_param` points at it.
- **a block's value / the `;`-terminated tail is sema's** was at
  `ast_node.Block` and the `parse_stmt` header -> kept at `ast_node`.
- **a union is FLAT** was at `ast_node.Union` and the `parse_type` header
  -> kept at `ast_node`; the header keeps its own fact (the bar is only
  read here in TYPE position).
- **"a file full of mistakes still lexes successfully; Err is AllocError
  only"** was in `lex/lex.zen` (THE CONTRACT), `lex_scan.scan` and the
  `lex_diag` header -> kept at `lex.zen` and at `scan`'s signature;
  `lex_diag` now defers.
- **"no `Punct` class, because two tables disagree eventually"** was
  written out in `lex_punct.zen` and `lex_byte.zen` -> full argument kept
  in `lex_punct.zen` (where the table is).
- **`Package` is fetched into a content-addressed cache and hash-verified**
  was at `build.Package` and `build.Builder.add` -> kept at `Package`.
- **the four sub-headers of `ast/` (node shape, ids, trivia, by-value
  children)** were restated in the `ast.zen` root -> the root now names the
  file each argument lives in.
- **trailing trivia belongs to the arm that precedes it** was said twice
  inside `parse_match.one_arm` (doc comment + inline) -> the mechanism
  stays inline at the code; the doc comment keeps the test names.

### De-rhetoricized

- `ast_find.zen:in_span` — "Is `p` inside `span`, in `file`?" ->
  "Whether `p` sits inside `span`, in `file`. Half-open: `end` is past it."
- `ast_find.zen:before` — "Is `a` earlier in the file than `b`? Line first,
  then byte column." -> "Whether `a` is earlier in the file than `b`: line,
  then byte column."
- `ast_find.zen:take` — "Does this candidate beat the best so far? It has
  to cover…" -> "A candidate beats the best so far by covering the position
  and then either being the first thing that does or sitting strictly
  inside what already does."
- `collections_map.zen:settles` — "does the walk stop here? an EMPTY slot
  stops it…" -> "an EMPTY slot stops the walk (path ends, key absent), and
  so does the slot already holding this key"
- `lex_cursor.zen:at_bom` — "does a byte-order mark sit exactly here?" ->
  "whether a byte-order mark sits exactly here."

Left as questions deliberately: `parse_lookahead.zen:14-17` (the FOUR
QUESTIONS table — the questions ARE the file's subject and its navigation),
`mem_alloc.zen:4` ("does this allocate?" is a quoted question inside an
assertion about signatures), `core/drop.zen:7` ("Want a second one?
Construct one — there is no Clone." — vivid, and the brief says not to
flatten those).

### Compressed (score 7-9)

- `parse_token.zen` header — 28 -> 25 lines. The "four assumptions held,
  three did not / MOVED —" framing became present-tense assertions about
  the real alphabet. Every fact kept, and each re-verified against
  `lex/lex_token.zen`: `Token* = {kind, span}` (line 96), no `Blank`
  token, no `Underscore` token, comments are tokens (line 49), one `Eof`
  last (line 92), kinds flat (line 46).
- `parse_diag.zen` header — "WHERE THIS BELONGS" + "THE SECOND CALLER HAS
  ARRIVED" 15 -> 11 lines. Kept: the stranger test, the second-caller
  firing, both rejected homes and why, and the "a FOURTH struct is the
  duplication this note prevents" rule. Cut: "Still reported, now with a
  caller."
- `parse_decl.fn_value` — 13 -> 7 (table moved to its declaration site).
- `parse_decl.module` — 8 -> 4.
- `parse_member.one_param` — 8 -> 6; `type_params` — 5 -> 2.
- `parse_expr` header ("OVER 500 LINES, JUSTIFIED") — 8 -> 7; cut only
  "the second subject that WAS here".
- `ast_node.zen` — nine lines across `Literal`, `Match`, `Try`, `Index`,
  `Function`, `Enum`, `Impl`, `Module` and the header: paragraph merges
  where a blank `//` separated two halves of one thought. No fact dropped.
- `collections_map.zen` Map constructor — 8 -> 5 (three one-sentence
  paragraphs into one).
- `collections_vec.zen` Vec constructor — same shape, 5 -> 4.
- `parse_type.paren_type` — 11 -> 10; header union paragraph 6 -> 5.
- `env.zen` `Fs.write` — 4 -> 3 ("Arrived when the fixpoint needed it"
  became "what `zen build src -o stage2.c` needs to honour its own `-o`" —
  same fact, no history framing).
- `core/display.zen` sealed `toString` — 4 -> 3.

### Refused to cut

- `core/eq.zen:40-45` (`is_in`'s accumulator, "fails at `cc` in every one
  of the 45 differential tests that stages this file") — protected by
  instruction and by the rules; number and reason untouched.
- `text/text_str.zen:57-64` (`before*`, "THREE components had each written
  their own") — untouched.
- `core/range.zen`, `core/result.zen`, `core/loop/loop_iter.zen`,
  `core/loop/loop_handle.zen`, `core/scope.zen`, `core/drop.zen`,
  `mem/mem_alloc.zen`, `mem/mem_ptr.zen`, `core/num.zen`, `core/byte.zen`,
  `core/bool.zen`, `core/hash.zen`, `core/io.zen`, `core/time.zen`,
  `core/path.zen`, `std.zen`, `text/text.zen`, `collections/collections.zen`,
  `mem/mem.zen`, `core/loop/loop.zen`, `core/loop/loop_find.zen` — read in
  full, nothing cut. These are DESIGN.md/PLAN.md citations, law statements,
  the `allocs_op: 0` bench gate, and rejected-alternative arguments, at
  roughly 72 columns with no restatement.
- `ast/ast_span.zen:69-77` (`nowhere`, "written out five times under three
  names") — a consolidation measurement, same class as `text_str.before`.
- `ast/ast_arena.zen` — the "reading" banner's underflow story and the
  `stale` note are regression records; the usize/u32 argument already
  defers to the count fields. Nothing cut.
- `lex/lex_literal.zen`, `lex/lex_scan.zen`, `lex/lex_punct.zen`,
  `lex/lex_state.zen`, `text/text_fmt.zen`, `text/text_utf8.zen`,
  `text/text_string.zen`, `parse/parse.zen`, `lex/lex.zen`, `ast/ast_id.zen`,
  `test/test.zen` — read in full, no slack found.

### Why the number is 2.2% and not 12%

Outside `parser.zen` this folder has no filler band at all and very little
restatement: 41 of 61 editable files came out unchanged after a full read.
The prose is already wrapped at ~72 columns, and almost every sentence
carries a distinct fact, a spec citation, a measurement, a named test path,
or a rejected alternative. The dedup lever paid (parse_decl -16,
parse_expr -6, parse_member -5) because the parser restates its own AST
contract; everywhere else the second statement was already a one-line
deferral. Reaching 12% here would mean deleting arguments, not tightening
prose.

### Wrong code noticed (NOT fixed)

- `src/std/text/text_fmt.zen:113-125` declares `digit` twice — `(d: u64)`
  and `(d: i64)` — with identical bodies. The comment at 109-112 states
  this is deliberate ("the digit table, twice — once per integer domain,
  since a u64 past i64.MAX can't widen into one"), so it is documented, not
  a defect; noting it only because a reader may flag it.
- `src/std/core/num.zen` `to_u64* = (self: u8)` etc. are declared with no
  bodies (intrinsics lowered by gen_c) — expected, not a defect.
- Nothing else. I changed no code line anywhere.



<a name="audit_lsp.md"></a>

## Appendix: src/lsp

## src/lsp — 1839 comment lines before, 1782 after, 57 removed (3.1%)

Below target (12-15%). That is the honest number for this folder and the
reasoning is in "What I refused to cut" at the bottom. The high-value output
of this pass is the FALSE list, not the line count.

All 19 files verified with `/tmp/codecheck_keep.py` against the REBUILT
`/tmp/srcbase/` baseline: **19/19 ALL CODE IDENTICAL**. I never restored or
reverted any code line (see the note on `lsp_json_read.zen` at the bottom).

---

### FALSE (score 0)

**1. `lsp_serve.zen:790-795` (end of file) — an ORPHANED doc comment for a
function that is no longer in the file.**

> `// A `str` copied into an arena — what the document store, the workspace`
> `// and the owed marker keep. […] `lsp_diag.zen`'s `owned_str` is the same`
> `// five lines for the same reason, private to its file.`

False twice over:
- It documents `own`, which moved to `lsp_reply.zen` as `own_str`.
  `lsp_serve.zen:82` now IMPORTS it (`RpcFault, own_str = lsp.lsp_reply`).
  The comment sat at the very end of the file with no declaration under it.
- `lsp_diag.zen` has NO `owned_str`. It imports the same `own_str` from
  `lsp_reply.zen` (`lsp_diag.zen:88`). The duplication the comment describes
  was consolidated; `lsp_reply.zen:293` records the consolidation.

CODE SHAPED AROUND IT: **no.** It is a dangling comment attached to nothing.
Replaced with a 2-line true pointer to `lsp_reply.zen`'s `own_str`.
(Note: I had to keep the trailing blank line the comment sat behind —
deleting it changed the non-comment line sequence. No file in the tree ends
with a blank line, so the replacement pointer preserves the file's shape.)

**2. `lsp_def.zen:22-27` — "TWO WAYS IN" and "there is no cache".**

> `// TWO WAYS IN, AND THE WORKSPACE DECIDES — `definition_in` … ,`
> `// `definition_at` … . Both rebuild per request; `lsp_hover.zen`'s`
> `// header says why there is no cache.`

There are **THREE** ways in. `definition_with` (`lsp_def.zen:143`) takes a
`Checker` and is called by `lsp_serve.zen`'s `write_definition` with `sh.c`
— the shared slot's checker from `lsp_diag.zen`'s `shared`. That IS the
cache, and `lsp_hover.zen`'s header describes it rather than arguing against
one. The claim was already false in the baseline tree, before my edits.

CODE SHAPED AROUND IT: **no.** `definition_with` exists and is wired up; only
the header never caught up. Rewritten to name all three ways in.

**3. `lsp_compl.zen:37-40` — "TWO WAYS IN".**

Same defect. `complete_shared` (`lsp_compl.zen:153`) is the third way in,
called by `lsp_serve.zen`'s `write_completion` off the slot's checker.
CODE SHAPED AROUND IT: **no.** Rewritten to name all three.

**4. `lsp_frame.zen:12` — `design_lsp.md:157` no longer points at the cited
text.** VERIFIED both sides: `docs/design_lsp.md:157` is now the "semantic row
in the table above has now LANDED" paragraph about colour. The byte-counted
`read` with explicitly no `read_line` is at **`design_lsp.md:248`** (also
summarised at :42), inside §4 "Reading — the capability, as built".
The SUBSTANCE of the citation is correct; only the line number drifted.
**NOT FIXED** — see "Citations I checked but did not rewrite" below.

**5. `lsp_json_read.zen:309` — `design_lsp.md:174` no longer points at the
cited text.** VERIFIED: line 174 is the "Rename is the request this language
makes dangerous" paragraph. The surrogate-pair fact (UTF-16 width is 1 below
65536 and 2 at or above, because that is one surrogate pair) is at
**`design_lsp.md:209`**, inside §3 "The algorithm, and the one arithmetic
fact". Substance correct, line number drifted. **NOT FIXED.**

#### Citations I checked but did not rewrite (report-only)

I read `docs/` and the cited source files. In every case below the cited
CLAIM is still true and the doc/code still says it — only the LINE NUMBER
has drifted. I did not rewrite them: correcting a number that has drifted
once with a number that will drift again is not obviously an improvement,
and the parent may prefer section references. All verified by reading both
sides:

| citation in src/lsp | cited text actually lives at |
|---|---|
| `design_lsp.md:157` (lsp_frame) | `design_lsp.md:248` (§4) |
| `design_lsp.md:174` (lsp_json_read) | `design_lsp.md:209` (§3) |
| `TESTING.md:48` (lsp_pos) | `TESTING.md:49` — off by one |
| `PLAN.md:200` (lsp_json_read ×1, lsp_reply-adjacent) "error unions outside the seed subset" | `PLAN.md:220` |
| `PLAN.md:194` (lsp_serve) "the seed subset has no threads" | `PLAN.md:220` (:194 is `### 0.4 gen_c`) |
| `PLAN.md:137` (lsp_colour) "names a second grammar as the failure" | **not found in PLAN.md at all** — :137 is a `---` rule. I could not locate the sentence; flagging as unresolved rather than guessing. |
| `src/std/core/num.zen:124` (lsp_frame, lsp_json_read) — the quoted "a narrowing conversion can fail…" | `num.zen:112-113` |
| `src/std/env/env.zen:45` (lsp_frame) "`Console.println` … appends one `\n`" | :45 is inside the **Stdin** `read_line` paragraph, not Console |
| `src/std/env/env.zen:83` (lsp_json) "every `std` member … forever" | :83 is about a module path being COMPUTED |
| `DESIGN.md:302` (lsp_pos) — Zen's 1-based line / byte column | :302 is a `try()` example; the position rule is `DESIGN.md:49` (which the same comment already cites correctly) |
| `ast_span.zen:22` / `:25` (lsp_pos) | :22 is `Pos* = {`, :25 is `}` — the byte-column comment is :19-21. Minor; arguably points at the struct on purpose. |

**Accurate and confirmed:** `DESIGN.md:45`, `DESIGN.md:49`, `DESIGN.md:99`,
`DESIGN.md:438`, `TESTING.md:17`.

**§-level citations (§1, §2, §4, §5, §6 of `design_lsp.md`) all still
describe what the code does.** I read §1's three lists, §2's staged request
surface + the colour and hover subsections, §4's transport, §5's sync/
overlay/diagnostics (including the two `BUILT 2026-08-08` amendments) and
§6's client notes. In particular §5's "the debounce cannot be written" and
§2's L3 pricing of local/binder spans match `lsp_diag.zen` and `lsp_def.zen`
as written.

---

### Deleted (score 1-4)

- `lsp_serve.zen` — "A `str` copied into an arena — what the document store…"
  — score 0 — orphaned + false; see FALSE #1.
- `lsp_pos.zen` — "Moved here from a private copy in `lsp_serve.zen` once
  `publishDiagnostics` became a second caller (`STYLE.md`'s rule)." — score 3
  — refactor narration; the placement ARGUMENT in the preceding sentence is
  what carries the weight and it is kept.
- `lsp_built.zen` — "Moved from `lsp_diag.zen` unchanged in shape:" — score 3
  — same; the "the gather belongs with the arena that owns what it gathers"
  clause is kept.
- `lsp_built.zen` — "…(`lsp_names.zen`'s doctrine, moved with the code)."
  — score 3 — trailing move-narration on an otherwise load-bearing comment.
- `lsp_hover.zen` — "…lived here as `lsp_decl.zen` and is now `ast_named.zen`
  (moved on its second caller)" — score 4 — kept the pointer, dropped the
  move story.
- `lsp_fmt.zen` — "…which is what \"not now\" looks like." — score 3 —
  closing flourish restating the sentence before it.
- `lsp_fmt.zen` — "a formatter that hands back a whole-document replacement
  it does not trust is an editor." — score 3 — closing flourish; the
  preceding sentence already asserts the rule.
- `lsp_diag.zen` — "as it has always been" (in `shared`) — score 2 — history
  aside inside a live argument.

### Deduplicated

- **The `own_str` copy rule** was stated in `lsp_serve.zen` (orphan, 6 lines),
  `lsp_reply.zen` (6) and implied in `lsp_built.zen`/`lsp_diag.zen` import
  notes → kept in full at `lsp_reply.zen`'s `own_str`; `lsp_serve.zen`'s
  `Server` doc and its trailing note now defer. `lsp_reply.zen`'s own
  three-old-names history compressed to "THE ONLY COPY IN THIS FOLDER"
  (verified by grep: all three files import and call it).
- **"`Types` IS IMPORTED FOR ITS METHODS" bootstrapper note** was written out
  in `lsp_hover.zen`, `lsp_def.zen`, `lsp_compl.zen`, `lsp_built.zen` →
  kept in full at `lsp_hover.zen`; the other three now read "as
  `lsp_hover.zen` explains".
- **"TWO/THREE WAYS IN, AND THE WORKSPACE DECIDES"** was spelled out in
  `lsp_hover.zen`, `lsp_def.zen`, `lsp_compl.zen`, and again in
  `lsp_serve.zen`'s `hovered` and `defined` → the full shape now lives in
  `lsp_hover.zen`'s header (rewritten as one paragraph instead of two, and
  the "THREE WAYS IN NOW" history dropped); the other four defer to it.
- **"the slot is ensured … building once if the state is new … the `None` arm
  is unreachable"** was in `lsp_diag.zen`'s `shared`, `lsp_serve.zen`'s
  `shared_hover`, `write_definition` and `write_completion` → kept in
  `lsp_diag.zen`'s `shared` (the function that ensures); the three
  `lsp_serve.zen` sites now defer.
- **"`c` is a `Res` because the type system cannot see that a successful
  `ensure` left a build in the slot"** was stated at `lsp_diag.zen`'s
  `Shared` type AND its `shared` method, ~90 lines apart → kept at the type.
- **The `held`/two-arenas aliasing invariant** was written out fully in
  `lsp_stdio.zen`'s header and again in `answered` → kept at the header
  (per your instruction to prefer keeping these); `answered` now names the
  rule and keeps its own distinct fact (what the server KEEPS it copies in
  `changed_to`, once per real change).
- **`partial`'s reading of `Short`/`NoBlank`** was in `lsp_stdio.zen`'s
  header and repeated at the function → header keeps it, function defers
  and keeps its own fact (over a buffer `serve` treats every fault as the
  end of the session).
- **"an empty `classed`/`classes_for` IS the lexical answer", with the list
  of states that produce it**, was in four places: `lsp_colour.zen`'s header,
  `lsp_colour.zen`'s `write_tokens`, `lsp_diag.zen`'s `classes_for`, and
  `lsp_serve.zen`'s `coloured` → the enumeration of states is kept once (at
  `classes_for`, the producer) and at the colour header's doctrine; the
  other two now refer to it.
- **"AND NOTHING IS SAID TWICE" notification dedup** — header + `say_one` →
  `say_one` defers.
- **"THE THREE SETS"** — header + `say_all` → `say_all` defers.
- **The `showing` eviction rule** — the field's declaration + `remember_showing`
  → the "session-arena copies because the slot's pages go back" argument is
  kept at both (it is an aliasing invariant), but the second copy of the
  pointer to `lsp_built.zen` is dropped.
- **"the URI is resolved at gather time, not write time — a build knows its
  compilation root and a writer does not"** — `lsp_built.zen`'s `Spot`,
  `lsp_colour.zen`'s `Classed`, `lsp_names.zen`'s `class_as` →
  `lsp_names.zen` now defers to `Spot`.
- **The semantic-token legend "cannot be spelled in two files" note** was on
  both the `lsp_serve.zen` and `lsp_reply.zen` imports → kept at
  `lsp_reply.zen` (where `write_capabilities` lives); `lsp_serve.zen` defers.
- **`check_build`'s three choices (computed root / open document as entry /
  buffer in the overlay)** were restated in full by `hover_in` and again by
  `complete_in` → kept at `check_build`; both callers defer, `hover_in`
  keeping its own distinct `folder_root`/UFCS-pool fact.
- **`lsp_diag.zen`'s "the settle coalesces nothing at the transport"** vs
  `lsp_stdio.zen`'s `after_drain` → mechanism kept in `lsp_diag.zen`'s
  header; `after_drain` defers and keeps the slot consequence.

### De-rhetoricized

All 10 rhetorical questions in the folder:

- `lsp_frame.zen:is_length` — "Does the line at `from` name Content-Length?" → "Whether the line at `from` names Content-Length."
- `lsp_stdio.zen:partial` — "Is this fault \"the rest has not arrived yet\"?" → "The header's reading of `Short`/`NoBlank`: bytes still in flight, not faults."
- `lsp_built.zen:matches` — "Is the held build one for exactly this state?" → dropped; the following sentence ("The key is CONTENT, not versions") is the assertion.
- `lsp_built.zen:same_overlay` — "Does the held overlay read exactly what the documents hold now?" → "The held overlay reads exactly what the documents hold now:"
- `lsp_diag.zen:fresh` — "May `classed` be served?" → "Whether `classed` may be served."
- `lsp_diag.zen:gone` — "Was this URI showing errors and is it not among the ones that have them now?" → "This URI was showing errors and is not among the ones that have them now."
- `lsp_serve.zen:stopped` — "Has `shutdown` been answered?" → "Whether `shutdown` has been answered."
- `lsp_hover.zen:poison_free` — "Does this type, anywhere inside it, contain poison?" → "Poison anywhere inside this type —"
- `lsp_json_read.zen:here` — "Is `b` under the cursor?" → dropped; "Nothing moves — separate from `byte_if` …" is the assertion.
- (`lsp_json_read.zen:102` and `lsp_diag.zen:350`'s `?` matches were the JSON
  number grammar `( … )?` and a wrapped sentence, not rhetoric — untouched.)

### Compressed (score 7-9)

- `lsp_hover.zen` header — 12 → 10 lines — the two "TWO WAYS IN" / "THREE WAYS
  IN NOW" paragraphs folded into one; every entry point and its arena rule
  kept, the "NOW" history dropped.
- `lsp_hover.zen:hover_in` — 17 → 13 — the root/entry/overlay argument now
  defers to `check_build`; `folder_root`/UFCS-pool fact kept.
- `lsp_hover.zen:write_written_ty` — 14 → 13 — reflowed; DESIGN.md:438 quote,
  the `i32 — members: MIN, MAX, BITS` example and the `null` rule all kept.
- `lsp_serve.zen` header "OVER 500 LINES" — 7 → 6 — STYLE.md justification and
  the four subjects kept; the trailing restatement of the diag policy cut.
- `lsp_serve.zen:Server` doc — 6 → 4 — defers to `own_str` for why copies;
  "`changed_to`, once per real change" kept.
- `lsp_serve.zen:settled` — 6 → 4 — defers to `lsp_diag.zen`'s `settled`;
  the two callers and `t` kept, plus the whole "NOTHING IS SENT AFTER
  `shutdown`" paragraph untouched.
- `lsp_diag.zen` header "AND THE BUILD ITSELF IS SHARED" — 6 → 4.
- `lsp_diag.zen:shared` — 7 → 5.
- `lsp_built.zen` header — 5 → 4 on "WHAT A QUERY TAKES FROM THE SLOT"; the
  ~10 MB / ~30 MB measurements and both numbered rules kept EXACT.
- `lsp_def.zen` header — 6 → 5, and corrected (FALSE #2).
- `lsp_def.zen:definition_with` — 7 → 4.
- `lsp_names.zen` header — 9 → 7 — defers to `lsp_colour.zen` item 5; the
  §1 prohibition and "a name sema did not settle keeps the lexer's
  `variable`" kept.
- `lsp_decl.zen` — 6 → 5 — the move narration became a statement of what the
  file IS (a re-export) plus why the finder lives in `ast_named.zen`.
- `lsp_symbol.zen` header — 8 → 7.
- `lsp_stdio.zen:after_drain` — 6 → 5; `lsp_stdio.zen:answered` — 7 → 6.

---

### What I refused to cut, and why

- **`lsp_colour.zen` (163 lines, −1).** Its header is a numbered list of the
  five things a semantic-tokens server gets wrong, each with the mechanism
  and the observable failure, plus `PLAN.md`/`design_lsp.md` citations and
  exact UTF-16 arithmetic (2 units/4 bytes, 1 unit/2 bytes). There is no
  filler in it. The one cut I made was a four-way duplicate enumeration.
- **`lsp_json_read.zen` (117, 0).** Every block is a bug record, a security
  property (`MAX_NESTING`), a spec citation, or a named backend defect
  (`faulted_ok`'s "codegen cannot resolve `value`"). The `byte_of` comment's
  "THE RIGHT FIX IS A PRIMITIVE: `to_u8*` in `std.core.num` would delete
  this, once it has a second caller" — I checked: `to_u8` does **not** exist
  in `src/std/core/num.zen`, so the claim still holds.
- **`lsp_json.zen` (89, 0).** Rejected alternatives (why JSON is not in
  `std`, why a number is kept as its lexeme), an RFC 8259 note, and the
  `stepped` bootstrapper-capture bug record.
- **`lsp_uri.zen` / `lsp_frame.zen` (0).** Both are short files that are
  almost entirely refusals and preconditions (`%20` not decoded,
  `vscode-remote://` not understood, `short_by` and the deadlock it avoids).
- **`lsp.zen` (0).** The whole header is the folder index plus the
  BUILT/NOT BUILT status — navigation and status, the most discoverable
  place for both.
- **`lsp_compl.zen` (0 net).** Its "TWO WAYS IN" correction ADDED two lines;
  everything else is the incomplete-input argument, the L3 gaps it prices,
  and its STYLE.md over-500 justification.
- The `write_ty_id` measurement in `lsp_hover.zen` ("4/12 answers on a file
  that imports something vs 10/12 on one that does not") and the
  "three of twelve positions answered" regression record in its header —
  both kept verbatim.

### Wrong code noticed (NOT fixed)

- `src/lsp/lsp_def.zen:208-210` records honestly that `disk_text` and
  `lsp_diag.zen`'s `on_disk` are "this same five lines". Both still exist,
  both are private, and `lsp_reply.zen`'s `own_str` shows the folder's own
  answer to that pattern. A real (small) STYLE.md second-caller violation;
  the comment is accurate, the code is the problem.
- Nothing else. I found no incorrect logic.

### Note on `lsp_json_read.zen`

Before the baseline was rebuilt, `codecheck_keep.py` reported a code change
in `lsp_json_read.zen:395` (`b.is_in([' ', '\t', '\n', '\r'])` where the old
baseline had four `==` comparisons). **I did not touch it** — I had read the
file with `is_in` already present, before my only edit to it (a two-line
comment change), so I logged it as pre-existing rather than "fixing" it.
It passes against the rebuilt baseline.



<a name="audit_zen.md"></a>

## Appendix: src/zen

## src/zen — 784 comment lines before, 734 after, 50 removed (6.4%)

Per file: zen.zen 62->58, zen_build.zen 321->295, zen_cli.zen 104->95,
zen_fmt.zen 48->47, zen_order.zen 31->31, zen_path.zen 159->149,
zen_run.zen 59->52.

### FALSE (score 0)

**1. `zen_build.zen:27` — header pointer to an explanation that no longer
exists.**

```
// WHAT STOPS THIS FILE SHORT OF A COMPILER is written down at `deliver`.
```

`deliver` documents no such limitation. What it said was "This used to be a
FAULT: `std.env.Fs` had no `write`... `Fs.write` closed it." The limitation was
CLOSED; the header kept pointing at it, so a reader is told the file is short of
being a compiler and sent somewhere that says the opposite.

**Code shaped around it: NO.** Checked `deliver`, `write_out`, `write_failed`:
`Fs.write` exists and is used, the stdout path is a deliberate `-o -`
equivalent, the fault path is a real fault. Cost a reader's time only. Both the
pointer and the stale history deleted.

**2. `zen_order.zen:45` — a label contradicting its own function.**

```
// Evens then odds: odd indices first, then even ones — ...
```

The label says evens first; the rest of the same sentence and the code both do
odds first (`i < half` -> `i*2+1`). Self-contradictory in one line. Corrected to
"Odd indices first, then even ones".

**Code shaped around it: NO.** `interleaved` is correct; only the label was
wrong. But this is the permutation `tests/determinism/check.sh` check 3 varies,
so a reader trusting the label would have mis-described what the gate covers.

**3. Header arithmetic (minor).** `zen_build.zen`'s header said "the four
phases" above a five-stage diagram, with "the five phases of one" twenty lines
below in the same header. Made consistent at five.

### Deleted (score 1-4)

- `zen_build.zen` header — "Everything below this file already existed and none
  of it had ever been called by anything. What's new is the wiring..." — score 2
  — project history, nothing actionable.
- `zen_build.zen:checked` — "Was three lines inside `check_tree`, a local that
  died with the method." — score 2 — refactoring history.
- `zen_build.zen:deliver` — "This used to be a FAULT: `std.env.Fs` had no
  `write`... `Fs.write` closed it." — score 3 — closed limitation; the source of
  FALSE #1.
- `zen_build.zen:emit_c` — "Module 0 is the root: the walk queues the entry
  first..." — score 4 — verbatim duplicate of `parse_it` 90 lines above.
- `zen_build.zen` `Build*` ctor — "ufcs constructor, like `Vec`/`Ast`/`Parser`."
  — score 3 — ceremony.
- `zen_build.zen:walk_order` — "and a command line's worth of build is
  `zen_run.zen`" — score 4 — bare pointer adding nothing to the rule.
- `zen_run.zen:run_once` — "MOVED HERE FROM `zen_build.zen`: same subject this
  file already had, and that file was at its 800-line cap with the editor's
  overlay still to add. Nothing about it changed." — score 2 — pure refactoring
  history. (Also cited an 800-line cap where the file header cites STYLE.md's;
  `make cap` has both a 500 note and an 800 hard limit, so neither was wrong,
  but the pair reads as a contradiction.)
- `zen_path.zen:entry_of` — "Moving them also made room in `zen_build.zen`,
  which was at its cap." — score 2 — refactoring history, and now misleading:
  `zen_build.zen` is 711 lines and `make cap` notes it as over 500.
- `zen_cli.zen:cli` — "`argv.get(0)` is the program path, so the command is
  argv[1] and its arguments start at 2." — score 4 — near-verbatim duplicate of
  the `ARGS` constant's comment ten lines above.
- `zen_path.zen:module_name` — "(same split `bootstrap/modules.py` draws between
  a file's `dotted` and its aliases)" — score 4 — pointer into `bootstrap/`,
  which memory records as already off the build path.

### Deduplicated

- **The determinism-oracle argument** ("an absolute path in a diagnostic puts the
  checkout's location into the emitted C, and two checkouts of one tree then
  emit different bytes — voiding the oracle, TESTING.md") appeared THREE times in
  `zen_path.zen` alone: the header, the `Unit.rel` note, and `entry_named`. Kept
  in full at the header with an explicit "Every 'must not reach a Span' note
  below is this rule"; the other two now defer in one clause each.
- **"deliberately not written in terms of each other: this reports as it goes
  and emits at the end, and folding both orders into one method to save four
  lines is how a build's stdout moves by a byte"** appeared verbatim in
  `zen_build.zen:whole` and `zen_run.zen:run_once`. Kept at `whole` (the unusual
  path, and the one a reader arrives at asking why); `run_once` now points there.
- **The no-listing / file-set-is-the-caller's argument** was in `zen_cli.zen`'s
  `FmtJob` and `zen_fmt.zen`'s header. Kept at `zen_fmt.zen` (where a directory
  is actually refused); `zen_cli.zen` now defers.

### De-rhetoricized

None — `src/zen` contained no question-form comments.

### Compressed (score 7-9)

- `zen_build.zen` header 35 -> 27. Kept the PLAN.md 0.5 citation, the
  diagnostic-is-a-value rule, THE MODULE TREE IS COMPUTED, THE PROGRAM IS ONE
  `Ast`, and the STYLE.md over-500 justification.
- `zen_build.zen` the `Diag` collision 13 -> 12 — PROTECTED (names a reported
  bug with a pinning test). Restructured so "BUG, reported" leads; kept
  `tests/corpus/modules/module_alias_qualified` and the wrong-receiver symptom.
- `zen_build.zen:folder_root` 19 -> 18 — PROTECTED. Kept the DESIGN.md UFCS
  candidate set, "a program's MEANING is not a loader's to decide", and the four
  `tests/corpus/sema_zen/` programs that surfaced it.
- `zen_build.zen:report` — UNTOUCHED measurement: "all 117 of
  `tests/must-fail`".
- `zen_build.zen:check_tree` "THE WHOLE TALLY" 7 -> 6 — kept the regression
  ("This once read `n + absent`... two sentences, one mistake"); cut only the
  back-reference to a comment 40 lines below.
- `zen_build.zen:missing_main` — kept LAW 2 and all three named must-fail tests.
- `zen.zen:lsp` — the `--stdio` comment KEPT nearly whole. It is the folder's
  best comment: a real-world bug plus the reason no gate caught it ("every gate
  here drives the server directly, so none ever passed the argv a real client
  sends"). Trimmed two clauses only.
- `zen_cli.zen:built` — UNTOUCHED. "That silent bug once held long enough that
  `make build` produced no binary — taking `test-zen`, `fmt` and `determinism`
  down with it, since a target that can't run can't go red either" is a score-10
  cascade measurement.
- `zen_path.zen:root_for` — kept the whole two-rule climb argument and the
  `editors/nvim/zen.lua` `root_markers` citation.
- `zen_fmt.zen` header — kept the bootstrapper name-collision record ("the
  bootstrapper reported this outright at two files this lane never touched").
- ~15 further one-to-three-line trims.

### Refused to cut

- `zen_run.zen`'s "STYLE.md's cap is how the split got noticed: a cap is how you
  find out a file has two subjects." Trimmed the specific line count (stale) but
  kept the insight, which is the actual reason the file exists.
- Section banners — ratified.



<a name="audit_fmt.md"></a>

## Appendix: src/fmt

## src/fmt — 745 comment lines before, 701 after, 44 removed (5.9%)

Per file: fmt.zen 114->106, fmt_break.zen 311->285, fmt_decl.zen 233->226,
fmt_out.zen 45->44, fmt_src.zen 42->40.

### FALSE (score 0)

None found in this folder.

One near-miss worth recording: `fmt_decl.zen`'s `align_binds` header announced
"Three clauses, three reasons:" and then listed **two** bullets. The three
clauses are real (consecutive, adjacent, same width) but bullet one covers two
of them. Reworded to "Why those clauses:" rather than inventing a third bullet
or miscounting. No code depends on it.

### Deleted (score 1-4)

- `fmt.zen` header — "which is a homogeneous sequence and not a list of distinct
  concepts (`fmt_break.zen` argues it)" — score 4 — re-argues a rule it already
  defers to in the same clause.
- `fmt_break.zen` header — "the corpus comes first" — score 3 — slogan
  restating "the demand is unwritten" immediately before it.
- `fmt_break.zen` — "and it is worth more than the line it costs", "which is the
  direction to be wrong in", "and ten lines go on saying what one line says
  better" — score 3-4 — closing flourishes restating the preceding sentence.
- `fmt_out.zen` / `fmt_src.zen` — "`alloc.Out()` — ufcs constructor, like
  `Emit`" / "`alloc.Src(text)` — ufcs constructor, like `Vec`/`Ast`/`Emit`" —
  score 3 — ceremony; the convention is stated in four other files and is
  visible in the signature. Kept the substantive half ("allocates its buffer up
  front" / "the line index is the only thing it allocates").
- `fmt_decl.zen` — "`alloc.Aligned(src, tree, m)` — ufcs constructor, like
  `Src`/`Out`." — score 3 — same.

### Deduplicated

- **The `fill` / homogeneous-sequence argument** was stated in `fmt_break.zen`'s
  header, at `Cand.fill`, at `add_array`, at `emit_break`, AND in `fmt.zen`'s
  header — five sites. Kept in full at `fmt_break.zen`'s header; the other four
  now defer to it in a clause.
- **The pipeline ordering** (break runs between two pad rounds, because its
  edits move the line keys the pad table uses) was in `fmt.zen`'s header twice —
  once in the list bullet and once at `write_decl`. Kept at the header, made
  `write_decl` a pointer.
- **"a comment there is a token, and replacing it with spaces is the accident
  this folder exists to prevent"** appears in `fmt_break.zen`, `fmt_decl.zen`
  and `fmt_src.zen`. KEPT all three: each justifies a *different* refusal in a
  different function, and each is one clause. Flagged, not cut.

### De-rhetoricized

Nine questions across the folder, all restating the function's own name.

- `fmt_break.zen:relaid` — "Is this list re-laid out this round?" -> "Both halves
  need the gaps rewritable at all."
- `fmt_break.zen:ends_the_item` — "Is some list INSIDE `c` closing exactly where
  its only item does?" -> "True when some list INSIDE `c` closes exactly where
  its only item does."
- `fmt_break.zen:may_join` — "May this list be PACKED?" -> "A comment in the span
  forbids packing outright"
- `fmt_break.zen:uncommented` — "Is `[from, to)` free of comment openers?" ->
  "Bytes and not tokens, so a `//` inside a string literal counts"
- `fmt_break.zen:may_relay` — "May this rule rewrite this list's gaps?" -> "This
  rule may rewrite a list's gaps, either way, only when..."
- `fmt_break.zen:rewrites` — "Does any edit added since `was` say something the
  bytes don't already say?" -> "True when some edit added since `was` says..."
- `fmt_decl.zen:movable` — "May this rule set the width before this arm's `=>`?"
  -> "The width before an arm's `=>` may be set only when..."
- `fmt_decl.zen:bind_op` — "May this rule set the width before this binding's
  operator?" -> "The same three conditions `movable` asks of an arm, asked of a
  binding"
- `fmt_decl.zen:joins` — "Does statement `i` continue the run that ends at
  `i - 1`?" -> "True when statement `i` continues the run that ends at `i - 1`."
- `fmt_src.zen:all_spaces` — "Is `[from, to)` nothing but spaces?" -> "What a
  rule asks before rewriting a gap"

### Compressed (score 7-9)

- `fmt_break.zen` header 125 -> 106. KEPT IN FULL: the
  one-rule-for-arguments-and-parameters argument, the `)`-on-its-own-line
  argument with its AST_CONTRACT.md citation, the heterogeneous/homogeneous
  distinction, the corpus measurement (`is_c_integer` ten, `ptr_verb` eight,
  `is_integer` nine, `is_integer` landing at 79), JOIN-then-BREAK, and all five
  REFUSES entries (preconditions, PROTECTED regardless of length).
- `fmt_break.zen` `WIDTH` — UNTOUCHED. "372 of 52092 lines exceed it (93 exceed
  100)" is a measurement.
- `fmt_decl.zen` header 76 -> 71. KEPT: "AT MOST ONE THING MOVES PER LINE, so
  the pad table is one entry per line and two pads can never collide" (the
  file's load-bearing invariant), the DESIGN.md four-match-rules citation, the
  seam with `fmt_break.zen`, the CANNOT-SEE-A-STRING-LITERAL refusal, and the
  IDEMPOTENT argument.
- `fmt.zen` `unchanged_tokens` — the guard. Kept whole, trimmed one restating
  clause. This is the folder's highest-value comment.
- `fmt.zen` `write_decl` — kept the "difference between a formatter and one that
  eats comments" trap with its `Cli* = Build(Job) | Missing(str)` example.
- `fmt_out.zen` `say_at` — kept "A COMMENT KEEPS THE COLUMN IT WAS WRITTEN IN"
  and the paragraph-breaking consequence.
- ~10 further one-to-three-line trims across the folder.

### Refused to cut

- Section banners — ratified as navigation.
- `fmt_out.zen`'s `blank` and `fmt_break.zen`'s `no_list` both explain why a
  non-allocating function still returns `Res` (sibling match arms must agree on
  a type). Same pattern, three sites tree-wide, each already cross-references
  another. Left as is — the reader hitting one of them needs it there.
