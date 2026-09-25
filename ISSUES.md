# ISSUES

**Paste here. No ceremony, no format.** A code snippet with no words is a valid
entry — the snippet is the report. Anything under OPEN gets worked; anything
under DECIDE needs a call that is not mine to make.

Move an entry to CLOSED with the commit that closed it, or delete it. Do not
leave a fixed thing sitting under OPEN; a stale queue stops being read, which is
how a gate that cannot fail happens to a list.

**Verify before you record.** A closed entry is a claim that the defect no
longer reproduces. Re-run the reproducer against the current compiler; an
entry that no longer reproduces is closed, not open. On 2026-09-25 three
headline INBOX miscompiles were stale: rebinding is now rejected with a
precise diagnostic, call argument order is fixed, binder shadowing runs
correctly. The maintained differential manifest has 14 fixtures; its success
does not classify the separate historical 92-case hunt. Counts written here decay
faster than the code does.

---

## INBOX — paste below this line

**Reflection-based project test discovery remains unimplemented.**
`Tester.expect` and generic `Tester.expect_eq` have executable bodies in
`src/std/test/test.zen`. The remaining gap is `Module.functions`, registration
of discovered functions in build plans, and executing `Builder.test(Test)`
function targets. `zen test` runs explicitly registered executable targets via
`Builder.exe_test(Exe)`; `std.test.Suite` provides isolated assertion callbacks.
The compiler follows imports, so a test file beside an entry is not automatically checked.
Discovery must explicitly include those files and reject invalid tests before
execution. `docs/DESIGN.md` describes the intended discovery policy. The example build
also uses other features that the current planner does not implement.

**UFCS gate blind spots (2026-08-23 spot check; STYLE.md now documents them):**
- `src/fmt/` is structurally invisible to `rule_ufcs` — no fmt module has a
  principal type (receivers split across `Alloc`/`Src`/`Out`). ~60 sites a
  reader would flag: `write_module(out, ..)` fmt.zen:106, `arrow_col(src, ..)`
  fmt_decl.zen:251, the `fmt_break.zen` Alloc/Src-first machinery. Closing them
  means widening the rule or paying them down unledgered.
- `sema_own.zen` declares 9 free functions on `o :: Own` (`find_var`, `kill`,
  `revive`, `is_dead`, `take_dead`, ..) called function-style ~19 times —
  uncounted, and candidates for struct-body methods on `Own` (the dividing
  rule), which retires rather than re-spells them.
- `sema_match.zen`: ~6 `f(ps, ..)` sites on `ps :: Pats`, same shape.

**"A gap is only spaces" — one fact, four homes, two definitions.**
`past_spaces` (fmt_decl.zen:490, `== ' '`) vs `skip_space` (fmt_break.zen:736,
`.is_space()`) vs `all_space` (fmt_break.zen:732) vs `Src.all_spaces`
(fmt_src.zen:75). Belongs once, on `Src`. Also `verbatim` (fmt_decl.zen:627)
and `copy_of` (fmt_break.zen:237) are identical twins.

**`FrameFault`'s facts live in three files.** The type is lsp_frame.zen:36;
`frame_byte`/`frame_why` are starred free functions in lsp_serve.zen:778,787
(with a comment explaining why they're starred); `partial` sits in
lsp_stdio.zen:148. As struct-body methods (`f.byte()`, `f.why()`) the exports
and the justifying comment disappear.

**Wrapper chain:** lsp_reply.zen:227-287 — `request_of` delegates through
eight 5-7-line functions each wrapping one `method.eq(..)` test; ~60 lines
where one nested match would be ~25.

**Possibly-orphaned workarounds.** parser.zen's `nothing` (:321) and
`took`/`missed`/`missed_after` (:447-472) say "fold back when the seed's
`Ok(())` match-arm typing is fixed" — no entry tracked that bug. Same question
for stale bootstrapper framings: gen_c_expr.zen:118-119 (`ty_of`'s fallback
justified by "the bootstrapper's backend") and gen_c_type.zen:52
(`MAX_TYPE_PASSES` = "what the bootstrapper allows").

**Duplicate free-function names need receiver-aware review.** Measured 2026-09-25: `src/` declares 119 names more than once
(6x `settled`, 6x `to_i32`, 4x `message`), including legal receiver overloads. Emitted C mangles the
module path into the symbol, so `write_label` on `CBackend` is
`zu_f..._3gen5gen_c11gen_c_state8CBackendb3strb5usize`; a scan of `seed/zen.c`
for duplicate *definitions* (signature plus body, ignoring forward
declarations) finds **0 of 6591**. The `write_label` claim below was measured
stale: only `gen_c_loop.zen` defines it now, and `gen_c_sink.zen` does not.
The residual value here is as a REVIEW aid, not a soundness gate: a
same-receiver collision would be the defect, and nothing checks that today.
`ufcs_collisions.py` only checks a free function shadowing a METHOD.

`block` is the same shape but benign: `parse_stmt.zen:31` on
`Parser` and `gen_c_stmt.zen:51` on `CBackend` are different receivers.

---

## OPEN — being worked

**Historical accepted-to-C hunt still needs classification.** The earlier
1232-program hunt reported 92 C rejections and 47 warning cases. The current
14-fixture differential manifest does not prove those separate cases fixed.
Recover the original inputs and classify each against the current compiler
before closing this report; retained failures need minimized regression tests.

**The LSP hand-writes JSON; it should have structs with a derived `to_json`.**
Measured: ~97 `add` calls spelling JSON punctuation across 12 files, and
**34 `write_*` functions each spelling one protocol object by hand**, inside
2,562 lines. The structs already exist (`WirePos`, `Item`, `Classed`,
`Envelope`, `Spot`) — they sit BESIDE the writers instead of being the source
of them. `parse_error` in `lsp_reply.zen` is the type case: it spells
`{"jsonrpc":"2.0","id":null,"error":{"code":-` a byte-run at a time.

**Two steps, and the first is NOT blocked:**

1. **Now** — define the protocol structs and a `ToJson` trait with HAND-WRITTEN
   impls, the way `Display` declares `toString` today. Collapses 34 scattered
   writers into one impl per type, next to the type. Also kills the `}}`-escape
   hazard outright: punctuation stops being string literals sprinkled through
   12 files, so no conversion lane can turn `"}}"` into one brace.
2. **After `@meta`** — each impl is DELETED, not rewritten; the derived
   field-wise walk drops into the same slot. That is why step 1 is a migration
   and not throwaway work.

Unblocked: `src/lsp/` is inside `src/`, which used to mean the Python
bootstrapper had to compile any `@meta` it adopted. Fixpoint is rooted at
`seed/zen.c` now, so step 2 waits on `@meta` itself and on nothing else.

**`DIGITS` duplication and the magic `NAME_LEN`: measured stale 2026-09-25.**
`lsp_frame.zen` declares no `DIGITS` any more (grep: 0 hits), so the lookup
table has been replaced with `DIGIT_ZERO + n`. Re-check the surviving half
before working it.

**File headers carry design prose that belongs in `docs/`.** 4,592 of `src/`'s
16,641 comment lines are file headers. Worst: `fmt_break.zen` 114,
`lsp_colour.zen` 76, `fmt_decl.zen` 74, `lsp_diag.zen` 72, `text_fmt.zen` 59,
`lsp_hover.zen`, `lsp_names.zen` 55, `gen_c_try.zen` 53, `lsp_serve.zen` 52.
The criterion is NOT "is the comment good" — a previous cull already kept only
8.5/10 and above, so there is no junk. It is **does this belong here**: a header
says what a reader of THIS FILE needs; design rationale belongs in `docs/` with
a one-line pointer. `lsp_diag.zen`'s header cites `design_lsp.md §5` repeatedly
while re-deriving it. MOVE, never delete.

**Emit runs: 705 collapsible writes across 63 files.** Consecutive statements
writing into one buffer that a single `fmt` collapses. Find them with
`awk -f scripts/emit-runs.awk`, mark them off with `make emit-runs` (a ledger:
it fails if a file EXCEEDS its number, so the backlog only ratchets down).
Distribution: `gen/gen_c` 491, `lsp` 109, `sema` 83, `gen` 14, `fmt` 5, `zen` 3.
Worst files: `sema_diag.zen` 53, `gen_c_try.zen` 41, `gen_c_ptr.zen` 37,
`gen_c_op.zen` 30, `gen_c_loop.zen` 29.

**67 needlessly split imports.** A module imported on two lines where the merged
line fits in 80 columns (`gen_c_floor.zen:56-57` merges to 79). 125 split-module
imports in non-root files total; the other 58 genuinely exceed 80.

**~~`[u8, -1]` silently floors to `[u8, 0]`~~ — CLOSED.** Negative literal,
named-constant, and folded array counts are rejected by SEMA; zero remains a
valid fixed-array size.

**`gen_c_print.zen` holds two subjects** at 543 lines — `println`'s lowering and
the shared format classifier. A split is owed, and it carries the UFCS
import hazard, so it needs its own fixpoint cycle.

**`group_end_at` rescans the rest of the file for every `(` after an unclosed
one.** `parse_lookahead.zen:144-152` walks `Range(from, p.tokens_len())`
counting depth and stops only when depth returns to 0. Its sibling
`angles_end_at` (`:158-172`) gives up properly — `angle_stop:226` includes
`Eof => true` and a statement terminator. This one has neither. It cannot run
past the array (`token_kind_at:254` answers `Eof` out of range), so it is not a
termination bug; it is quadratic time on a half-typed buffer, from six call
sites (`lambda_ahead:91`, `fixed_array_ahead:127`, `paren_shape:261`,
`variant_ahead:296`, `declares_fn:425`, `bar_after:440`). The LSP re-parses per
keystroke and an unclosed `(` is the commonest state a buffer is ever in.

Three neighbours found in the same read, same file family:

- **`enter`/`leave` are not failure-safe.** `parse_expr.zen:63-66` calls
  `p.leave()` after a `.try()`, so an `AllocError` leaks a depth level forever.
  Same shape at `parse_stmt.zen:32`, `parse_type.zen:31`, `parse_pattern.zen:28`
  and `unwind` at `parse_expr.zen:257`. `depth` is a `usize` and `leave` is
  `self.depth - 1`, so an unbalanced count underflows rather than traps.
- **`too_deep` is sticky, file-global, and aborts the module.**
  `parse_decl.zen:70`: `running = !p.at_eof() && !p.too_deep`. One over-deep
  construct on line 1 stops the rest of the file being parsed, and `hushed`
  (`parser.zen:545`) silences every later diagnostic.
- **`recover()`'s body is reached by no test.**
  `tests/corpus/parse/parser_error_recovery.zen` feeds four declarations that
  each begin with an identifier, so `p.at` always advances and the
  `p.at == before` branch at `parse_decl.zen:66` is never taken. No
  module-level input starting with `;`, `}` or `+` exists anywhere in `tests/`.

**There is no AST dump, and `PLAN.md:268` reads as if there is.** `DumpAst`
appears only in prose — `DESIGN.md:1301`, `PLAN.md:268`, `tests/parse/
constructs.md:1323` — always as an example of overload syntax. `grep -rn
'DumpAst\|dump_ast' src/` is empty and `./zen ast` answers `unknown argument`.
Everything it needs is there: the node set is closed, every node carries a span,
`Display` already declares `toString`. Wanted by `@meta`, by every parser bug
report, and by anyone feeding a tree to a model — which is what asked for it.
Mark that `PLAN.md` line NOT WRITTEN in the same change; `PLAN.md:125` is
explicit that a path naming a file that does not exist is worse than listing
nothing.

**The CLI has no machine-readable diagnostics.** `--json-diags` or similar. The
LSP already publishes JSON from the same `Diag` values (`lsp_diag.zen:355-380`),
and every phase already produces a `Diag` carrying a position. **This is step 3
of the `to_json` entry above, not a separate job** — adding a second
hand-written JSON writer for the CLI before that entry lands means writing the
thing it exists to delete. The seven flags the CLI accepts today are
`--emit-c`, `-o`, `--entry`, `--repeat`, `--permute`, `--check`, `--stdio`
(`zen_cli.zen:250-277`); there is no `--help` and no `--version` either.

**A declared union used as an ordinary value type does not survive `gen_c`.**
Sema admits it and `cc` rejects it, which is the shape the differential oracle
is blind to:

    Ea = | Boom
    Eb = | Bang
    Both = Ea | Eb
    b: Both = Eb.Bang;      // -> zu_l1b = (zu_t2_4main2Eb){ .zg_tag = .. };
                            // error: incompatible types when assigning to
                            // type 'zu_t2_4main4Both' from 'zu_t2_4main2Eb'

`gen_c_widen.zen` widens a member into a set for a `Res` error set and nothing
widens one into a plain declared union. The only union test in the corpus,
`tests/corpus/sema/match_union_member_carries_its_type.zen`, reaches unions only
through `Res<T, E>` propagation and its own header says so — "the values arrive
by propagation rather than by writing `Error.Torn(..)` at the call site". So the
direct form is untested rather than merely unlucky, and `DESIGN.md:137-164`
spends five paragraphs specifying it.

**A diagnostic naming a rule the code stopped enforcing.**
`gen_c_const.zen:158` refuses with *"a constant whose value is not a literal"*,
but the gate actually applied is `is_pure_value` (`:170`), which admits
operators, constructions, nullary variants and type constants. Rejected
constants are told the wrong reason, and it is user-facing.

**`lsp_def.disk_text` and `lsp_diag.on_disk` are the same five lines**
(`lsp_def.zen:203`, `lsp_diag.zen:344`), both private — a STYLE.md
second-caller violation. `lsp_def.zen:201`'s comment describes it accurately;
the code is the problem.

**A garbled sentence in a file header.** `gen_c_try.zen:18` — *"which made
every merge / DESIGN.md promises a report"* is not a sentence; a word was
dropped. Probable reading: "which made every merge DESIGN.md promises **into**
a report." Left alone rather than guessed at.

**`DESIGN.md:164` claims the leading bar means "a parser needs no lookahead".**
It removes *backtracking*, not lookahead: the `Name = <thing>` fork is still
classified by bounded lookahead (`parse_lookahead.zen:240-243`,
`variant_ahead:293`), and `grammar.js:218-220` still declares a GLR conflict
`[$.enum_variant, $._callee]` for the same fork. The bar closes the
alias-versus-one-variant-enum fork specifically. One word too many in the law.

**A comment that is a block's only content is attached to nothing.** Neither
attachment rule names an owner for it -- no node begins at it and none ends
before it on its line -- so it reaches the trivia arena and no node claims it.
DESIGN.md says trivia is attached to nodes and not discarded; TESTING.md says
no comment is lost. `tests/corpus/parse/trivia_attachment_corners` records the
loss as two zeros beside an arena listing that contradicts them, so THAT FILE
GOES RED the day a block claims its sole comment. The loss is silent today
because `fmt.zen` copies declaration bodies verbatim.

**The formatter does not print declarations from the AST.** It uses trivia for
the material *between* declarations and copies each declaration's own bytes
verbatim from source (`fmt.zen:150-159`, `fmt_src.zen`). Losslessness today is
guaranteed by byte-copying, with the trivia doing the boundary work — stronger
than printing, but a different claim from the one "trivia on AST nodes makes
`zen fmt` lossless" suggests.

**Review candidates carried out of `SIGNATURE_REVIEW.md`, which is deleted.**
These historical observations need current reproduction; the review's method write-up is in
`scripts/signatures.py`'s own docstring and the model-calibration numbers were
the point of the exercise, not of the file.

1. **Fall-through chains that are one `match` on a literal — ~150 lines.** No
   `else if`, so a multi-way test on ONE scrutinee becomes a run of functions
   each re-declaring the whole parameter list to express one comparison. Across
   the tree: 340 such arms in 80 files, 2,416 lines; 18 are maximal chains of
   3+ links. Only the one-scrutinee-many-literals class collapses — a run of
   DIFFERENT predicates (`gen_c_call.zen:468`) has nothing to match on and is
   not counted. Six sites, verified present today:

   | site | now | saved |
   |---|---:|---:|
   | `gen_c_ptr.zen:196` `verb`→`verb_7`, 7 links on `name` | 61 | 40 |
   | `gen_c_cap.zen:190` `console_verb`→`verb_5`, 6 links on `a.name.text` | 52 | 34 |
   | `sema_trap.zen:714` four literal tables, 15 functions on `name` | 61 | 31 |
   | `lsp_reply.zen:221` `request_of`→`request_after_colour`, 6 links | 42 | 30 |
   | `gen_c_ptr.zen:89` `ptr_member_type`→`ptr_type_5`, 5 links | 40 | 22 |
   | `gen_c_fs.zen:453` `fs_name`/`_2`/`_3`, number literals | 11 | 5 |

   Expressible today: `grammar.js:709` admits literal patterns, `lex_scan.zen:157`
   runs one in production, `gen_c_flow.zen str_cond` lowers it. **`UFCS_OWED` must
   come down in the same commit** or `make style` goes red. One wrinkle:
   `lsp_reply.zen` tests a const, and a pattern must be a literal.

2. **Four parallel node arenas — ~90 lines, REPORTED AND NOT RECOMMENDED.**
   `ast_arena.zen` add/at/ids/each ×4, `ast_id.zen`'s four `{index*: u32}` with
   eight character-identical Eq/Hash, plus `sema_ty.zen`'s `TyId` as a fifth. A
   phantom-tagged `Id<T>` answers the objection both files state in comments
   ("passing a TypeId where an ExprId belongs, made unrepresentable for free"),
   so the premise is refutable — but that is a design argument, not a cleanup,
   and it is 218 call sites. `sema_id.zen`'s DeclId/MemberId/ImplId are NOT part
   of it; their bodies genuinely differ. **Ask before doing it.**

**Sema has whole unchecked regions, and `cc` is the type checker there.** Five,
found by compiling `example/build.zen`, which reported 2 errors where there
were 8. Each is a two-line reproducer and each exits 0 from `zen build`.

**1. ~~A lambda body is not type-checked at all~~ — CLOSED.** The biggest one,
because `.loop` and `.then` ARE this language's control flow. `sema_call.zen`
now walks a lambda argument's body (`arg_lambdas`, `lambda_body`) at every
place resolution ENDS — the chosen candidate, a member the table answered
with, a local holding a function, a variant constructor, an indirect callee —
so the parameters get their types from the signature and every statement
inside is typed exactly as one outside is.

**AFTER RESOLUTION, AND INSTANTIATED, OR IT BREAKS CODEGEN.** Walking at
`lambda_actual` with the parameters bound at holes — the crude form, and the
only position that runs before a candidate is picked — reports nothing wrong
and still cost 28 codegen diagnostics across `src/`. The reason is that
`Checker.expr_memo` is keyed by `ExprId`: whatever the walk types into it is
what `gen_c_op.operand_type` READS BACK at lowering time, because the backend
asks sema for an operand's type rather than deriving it. A hole memoized there
made `i > 0` on a loop index "comparing values that are not scalars".
`k.params` unsubstituted has the same shape — a `Var` owned by `loop` means
nothing to the frame the closure was written in — so `settled_params` reads
what `instantiate` settled, and `settled_or_poison` binds POISON wherever the
call settled nothing at all (`loop<R: Range<T>, T>` never settles `T`).
Poison is the one answer the backend knows to step around. With that, `src/`
reports zero.

**2. A call through a bound's declared member is not checked against that
declaration — not its types, not even its arity.** Names in the arguments ARE
resolved; only the signature match is skipped.

    Shower = { show* = (self: @Self, a: i32, b: i32) i32 }
    Thing.impl(Shower, { show = (self: @Self, a: i32, b: i32) i32 { a + b } })
    use = <T: Shower>(t: T) i32 { t.show("a", "b") }   // silent, emits C
    use = <T: Shower>(t: T) i32 { t.show(1) }          // "codegen cannot resolve `show`"
    plain = (a: i32, b: i32) i32 { a + b } ..  plain(1)   // "no overload matches" ✅

Cause is `sema_call.zen:no_such_method`: when no candidate matched it asks
`bound_declares`, and `true` returns `unknown()` in silence. The comment above
it justifies that with `alloc.create<Node>()`, whose body `gen_c_alloc.zen`
writes — a real case, but it is about EXISTENCE, and the signature is right
there to check the call against. The wrong-arity spelling gets a codegen
message that names resolution, at the wrong place, for an arity error.

**3. ~~Struct construction checks nothing~~ — CLOSED by `e173ceea`.** Both
halves: a required field left out and a value that does not fit the field it
names are compile-time errors. The impl path's own check (`sema_bound.zen`,
"an impl supplies a value for every field the bound declares") is where the
constructor's now lives, because it is the same question asked of the other
form. Three narrowings are in the code and each is a form a construction
cannot supply — a function member, a `Res` field, and a positional argument.

**A NOTE THE NEXT PERSON WANTS.** The type half looks like it belongs in
`sema_hoist.zen`'s `hoist_into`, whose `_` arm swallowed exactly this. It does
not: importing `sema_bound` there closes
`sema_hoist -> sema_bound -> sema_call -> sema_hoist`, and the cost is not a
diagnostic — the backend stops emitting whole instantiations and corpus
programs come out calling `Vec<Diag>(alloc)` in C that never declares it.
Asking `members_of` during `construct` does the same, for the same reason: it
walks impls and instantiates, in the middle of the resolution that is queueing
the construction.

**4. `==` does not check its two sides against each other.** A missing `Eq` IS
caught (`5 == Tester` → "`Tester` has none"), so the rule exists and stops one
step short: `5 == "five"` is silent.

**5. A misleading diagnostic falls out of (2).** A call at the wrong arity to a
name the receiver DOES have reports "no `<name>` on `<Type>`" — the sentence for
a name that is not there at all. It should say the arity. Met while fixing
`b.module(p).functions(a)`, where `functions` was declared at a different arity.

None of the open ones is caught by `make test` — the corpus has no case that
miscalls a bound. (1) was expected to find the others' instances in `src/`
itself; it found none, which is its own answer: `src/` has no wrong-typed
statement inside a closure, only the unchecked region that could have hidden
one.

## DECIDE — needs a call

**A list literal in a `Vec<T>` field: which side moves?** `docs/DESIGN.md:1147`
writes `libs: ["sodium"]`, `deps: [json, ..]`, `budgets: [Budget(..)]` into the
build file, and `src/std/build/build.zen` declares every one of those fields
`Vec<T>`. They are not the same thing — the emitted C initialises a `zg_str *`
with a `zg_a1_b3str` and `cc` rejects it — and nothing caught the drift because
struct construction does not check field types (above). Affects `Lib.libs`,
`Lib.paths`, `Exe.deps`, `Test.deps`, `Bench.budgets`. (a) the fields become
slices, and a build file stays readable; (b) the example becomes
`b.alloc.Vec<str>()` plus `.add()`, which is a grim thing to write for a
one-element list; (c) a list literal is allowed to construct a `Vec`, which is
hidden allocation and the standing rule forbids it. Recommendation: (a).

**The format door's final name.** `String.add` and `String.fmt` are one door
twice, differing only in error set; the floor mechanism now derives the error
from the receiver, so one name can serve both. 15 call sites. Picking `add`
frees `fmt`, which currently means three things in this tree (`src/fmt/` the
source formatter, `text_fmt.zen` the grammar, `.fmt()` the method).

**The `IoError` mislabel.** `gen_c_fmt.zen:294` relabels every formatting
failure as `AllocError.OutOfMemory` — a closed pipe reads as out of memory,
verified. (a) widen the door to `WriteError`, 112 corpus mains must then match;
(b) trap on the `IoError` arm, one branch, defensible because `toString` is
handed a `String` sink that cannot produce one; (c) document and leave.
Recommendation: (b). (c) is a band-aid.

**`@meta` in `src/std`.** ~~All six waiting consumers live in `src/std`, which
`bootstrap/` compiles as fixpoint stage 1.~~ **Answered by (b):** fixpoint is
re-rooted at `seed/zen.c` and the bootstrapper is deleted, so adopting `@meta`
in `src/std` no longer takes `make fixpoint` off the board. The six consumers
(`Display.dump`, the `Eq` and `Hash` defaults, `Env`'s typed args, `build.zen`'s
nodes) now wait on `@meta` being implemented and on nothing else.
See `docs/design_meta.md`.

## CLOSED

- literal `{}` — `{{` writes `{`, `}}` writes `}` — `13f9c7ee`
- `{name}` holes resolved where written — `26c50119`
- `vararg<T>`, forwardable — `3c1d9c91`
- `[u8, SIZE]` folds through a constant — `871d8798`
- unused imports: gate + 1195 culled — `03d1b597`
- a pattern naming a constant is reported, not silently irrefutable — `76dd2fe7`
- array literal element type comes from its position — `d3bd7e9f`
- a second `x = ..` in one block is rejected, not silently retyped — the
  reproducer now reports "a name is bound once per block" and the emitted C
  truncation (`n = 42; n = 3.5` printing `3`) cannot be produced
- call arguments evaluate left to right — `tests/corpus/codegen/argument_order.zen`
- a match binder may shadow an outer local — `inner 1 / outer 7` runs correctly
- the UTF-8 boundary table has one owner in `src/std/text/text_utf8.zen` — `421264a93`
- a workspace's own `std/std.zen` outranks ambient `ZEN_STD`, so LSP workspace
  diagnostics are neither duplicated nor unclassified — `corpus/lsp/workspace_diagnostics`

**`make build` fails intermittently, and the failure is a resolution error in
a file you did not touch.** Seen three times in one session:

    gen/gen_c/gen_c_main.zen:19:1: a name crosses a module boundary only with
      `*`: DeclId is not exported by module sema.sema_def
    gen/gen_c/gen_c_runtime.zen:161:8: no `uses_print` on `CBackend`

Both names exist and are exported. **The identical build succeeded on the very
next invocation, three times in a row.** The recipe overwrites `./zen` twice
in place (`cc seed/zen.c -o zen`, then `mv zen-new zen`), so a `./zen` still
held by a previous step is the obvious suspect — a `Permission denied:
'/home/ubuntu/zenc/zen'` from `tests/run.py` in the same session is the same
shape.

**THIS IS EXPENSIVE OUT OF PROPORTION TO ITS SIZE.** A flaky build reads as a
broken change: one run of the corpus reported 107 failures against a change
that, rebuilt, reported 3. Every bisect done through `make build` is
untrustworthy until this is fixed. Build to a temporary name and rename once,
or refuse to overwrite a binary that is in use.
