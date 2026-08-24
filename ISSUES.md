# ISSUES

**Paste here. No ceremony, no format.** A code snippet with no words is a valid
entry — the snippet is the report. Anything under OPEN gets worked; anything
under DECIDE needs a call that is not mine to make.

Move an entry to CLOSED with the commit that closed it, or delete it. Do not
leave a fixed thing sitting under OPEN; a stale queue stops being read, which is
how a gate that cannot fail happens to a list.

---

## INBOX — paste below this line

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

**Hand-copied insertion sort, twice.** lsp_compl.zen:572-611 and
lsp_colour.zen:348-388 — same five functions line-for-line; only the element
type and comparator differ. Zen has generics; std has no sort at all.

**Wrapper chain:** lsp_reply.zen:227-287 — `request_of` delegates through
eight 5-7-line functions each wrapping one `method.eq(..)` test; ~60 lines
where one nested match would be ~25.

**Possibly-orphaned workarounds.** parser.zen's `nothing` (:321) and
`took`/`missed`/`missed_after` (:447-472) say "fold back when the seed's
`Ok(())` match-arm typing is fixed" — no entry tracked that bug. Same question
for stale bootstrapper framings: gen_c_expr.zen:118-119 (`ty_of`'s fallback
justified by "the bootstrapper's backend") and gen_c_type.zen:52
(`MAX_TYPE_PASSES` = "what the bootstrapper allows").

**Two exported `write_label*` on `CBackend`, in the same folder.**
`gen_c_loop.zen:762` takes `(be, stem: str, n: usize)` and
`gen_c_sink.zen:921` takes `(be, done: usize)`. Zen has no function
overloading and the C namespace is flat, so this is a name that resolves by
luck. The UFCS rule DECLINES to recommend `be.write_label(..)` for either --
"exactly one free function in the tree declares that name" is the condition
that saved it -- so the gate silently routes around a collision instead of
reporting one. `block` is the same shape but benign: `parse_stmt.zen:31` on
`Parser` and `gen_c_stmt.zen:51` on `CBackend` are different receivers.
Nothing gates duplicate free-function names; `ufcs_collisions.py` only checks
a free function shadowing a METHOD.

**A second `x = ..` in one block: sema says shadowing, gen_c says assignment,
and nobody type-checks it.** Found by a bug-hunt lane, reproduced three ways.
sema permits the rebinding AT A DIFFERENT TYPE (shadowing "falls out for free"
because `lookup` walks top-down, sema_check.zen:286); gen_c reuses ONE C slot
and ONE live flag per NAME. Three symptoms, one cause:
- `x = Noisy(id: 1); x = Noisy(id: 2)` prints `drop 2` and never `drop 1` --
  the shadowed value's Drop never runs. An arena, file or lock held by the
  first binding leaks, at exit 0.
- `x = 1; x = "str"` emits `zg_str` into an `int64_t`. Only `cc` rejects it;
  Zen reports nothing. `cc` is the type checker again.
- `n = 42; n = 3.5` prints **3**. The emitted C is `int64_t zu_l1n; zu_l1n =
  42; zu_l1n = 3.5;` -- C truncates, no Zen diagnostic, no cc warning, exit 0.
  Zen has no cast keyword and conversions are methods, so an implicit
  float->int here is exactly the silent wrong answer the gates cannot see.
Repros (NOT added to tests/corpus -- a red board is the project's loudest
signal and landing one is a decision, not a side effect): the three programs
are in the session scratchpad under repros/. Decide the semantics first: if a
rebinding is a new binding, both values must drop and the types may differ; if
it is assignment, the old value must drop at the rebind and the type must
match. Today it is neither.

**Call arguments evaluate RIGHT-TO-LEFT, and the tree predicted it.**
`three(d.tick(), d.tick(), d.tick())` over a counter prints `210`, not `012`;
`pick(c.tick(), c.tick())` answers 10 instead of 01. The same three ticks
written as statements run in order, so the corruption is specific to arguments
inside one call. Cause: `write_written_args` (gen_c_call.zen) emits every
argument inline into ONE C call expression, which hands the ordering decision
to C, where it is unspecified -- gcc happens to go right-to-left.
tests/corpus/codegen/nesting_calls.zen SAYS SO IN ITS HEADER: "any lowering
that turns one Zen call into several C calls in an argument list has silently
handed the ordering decision to the C compiler ... that test does not exist
yet." It exists now and it is red. Decide whether Zen specifies an order (then
gen_c must emit temporaries) or does not (then it must be written down, and
`println`'s left-to-right walk is inconsistent with it).

**A match binder shadowing an outer local emits an undeclared C variable.**
`d: i32 = 7; got.get(0).match({ Ok(d) => println("{}", d), .. })` -- gen_c
renames the binder to `zu_l1d_2` to dodge the collision with the outer `zu_l1d`
and then never DECLARES it. cc: "'zu_l1d_2' undeclared (first use in this
function); did you mean 'zu_l1d'?". 20-line repro; found by four independent
hunt lanes. Shadowing is legal by design, so this is gen_c's bookkeeping, not
a sema question.

**92 programs where sema said yes and gen_c emitted C that cc rejects.**
From 1232 hunt programs, mechanically triaged. Clustered by cc's message the
population is dominated by TYPE errors -- 17 "incompatible types when
returning", 16 "incompatible types when assigning", 14 more across
initialising and argument passing -- which is the "cc is the type checker"
shape again: sema is not checking what gen_c faithfully emits. 47 more
programs compile with cc WARNINGS. Each is either gen_c emitting invalid C for
a valid program or sema accepting a program it should reject; both are
defects. The full triage is reproducible: run every program, bucket by
ZEN_REJECTED / CC_REJECTED / CC_WARNING / RAN_OK / NONZERO_EXIT.

<!-- paste snippets here. -->

---

## OPEN — being worked

**Goto-definition answers `null` on an enum variant's payload type.**
`ExprKind = Name(Name) | Literal(Literal) | ..` — asking for the definition of
the inner `Name` gets nothing. **The cause is in sema, not the LSP**, and not
where it looks: `told_at` DOES find the payload, via the arena's type-node
fallback. What is missing is the memo. Measured with a server-free probe
(reproducer at `/home/ubuntu/.claude/jobs/22ff9ad8/tmp/enum-payload-repro`):

    1:17 -> a written type -> NOT IN THE MEMO      <- Point, inside Circle(Point)
    1:15 -> a written type -> i32                  <- control, a struct field

So `check_all` never routes a variant payload through `type_from_ast`, nothing
lands in `type_memo`, and `lsp_def.zen` correctly reads the memo, finds
nothing, and answers `null`. Hover has the same hole for the same reason.

⚠️ **The obvious fix is wrong.** Adding an `Enum(en) =>` arm to `ast_named.zen`'s
`decl_told` (it is `Tell.Nothing` today) does NOT fix this and makes clicking a
variant's NAME report its payload's type, which is misleading. Verified: with
that arm reverted, the payload position still answers. The fix belongs where
enum declarations are checked.

**The LSP hand-writes JSON; it should have structs with a derived `to_json`.**
Measured: ~97 `add_bytes` calls spelling JSON punctuation across 12 files, and
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

**The UTF-8 encoding table exists TWICE, in two folders, under two names.**
`src/std/text/text_utf8.zen` owns the DECODER; `src/lsp/lsp_json_read.zen:467`
owns the ENCODER (`push_utf8` + `two_wide`/`three_wide`/`four_wide`/`byte_of`,
~60 lines) and its own comment calls itself "the inverse of
`std.text.text_utf8`'s decoder". Eight constants are declared in both:

    std UTF8_ASCII_MAX 128   = lsp ONE_BYTE_MAX 128
    std UTF8_CONT_MIN  128   = lsp CONT         128
    std UTF8_LEAD_MIN  192   = lsp LEAD_2       192
    std UTF8_LEAD_3_MIN 224  = lsp LEAD_3       224
    std UTF8_LEAD_4_MIN 240  = lsp LEAD_4       240
    std UTF8_CONT_SCALE 64   = lsp CONT_SCALE    64
    std UTF8_MIN_3    2048   = lsp TWO_BYTE_MAX 2048
    std UTF8_MIN_4   65536   = lsp FOUR_BYTE_MIN 65536

A fix to one will not reach the other. `lsp.zen:55` already re-exports
`push_utf8*` and `byte_of*`, so the LSP root is publishing them as library
surface from inside the wrong folder. **Move the encoder into
`std/text/text_utf8.zen` beside its inverse and delete the duplicate
constants.** Nothing about it is JSON.

Note this is NOT the same as "move JSON to std" — that stays: one caller, and
`build.zen:4` has no manifest ("source is the manifest"), so the obvious second
caller is architecturally excluded.

**`DIGITS` duplicates std, and `NAME_LEN` is a magic number.**
`src/lsp/lsp_frame.zen:182` declares `DIGITS*: str = "0123456789"` and renders a
digit as `DIGITS.index(n)`. `src/std/core/byte.zen:16` already has
`DIGIT_ZERO*: u8 = '0'`, and `:107` renders one as `DIGIT_ZERO + nibble` — the
lookup table does what arithmetic does. `text_fmt.zen:239` even argues the case.
Delete `DIGITS`, use `DIGIT_ZERO + n`.
In the same file, `NAME*: str = "content-length:"` beside `NAME_LEN*: usize = 15`
restates `NAME.len` as a literal. The other framing constants (`BLANK_LEN`,
`CRLF_LEN`) are protocol facts and belong where they are — this is not a
std-promotion, it is a duplication.

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

**`[u8, -1]` silently floors to `[u8, 0]`.** Same family as the array count that
was just fixed, wrong sentence for it.

**`gen_c_print.zen` holds two subjects** at 543 lines — `println`'s lowering and
the shared format classifier. A split is owed, and it carries the UFCS
import hazard, so it needs its own fixpoint cycle.

**~30% of a build is `gen_emit.order`'s insertion sort, which has no early
exit.** `insert_ordered` (`gen_emit.zen:171-185`) runs `Range(1, n).loop` — ALL
n−1 iterations — on every insertion, settled or not, so it is Θ(n²)
unconditionally rather than adaptively. Measured with `make profile` and a
`-O1 -pg` build, self-compiling `src/` (2.5s baseline):

    10,032 calls to insert_ordered
       ->  20,727,600 full `str.before` compares of 100+ char mangled symbols
       ->  787,380,320 of the build's 860,436,866 `str.index` calls
    -O2 self time: str.before 23.70% + view_at 4.33% + order 1.60% = 29.63%

**The comment above it is why nobody saw this** (`gen_emit.zen:161-162`):
"Hundreds of top-level names per unit, never millions — the simplest-to-verify
version is the right one." It is ten thousand, and an insertion sort WITH an
early exit is no harder to verify than one without. ~10 lines.

Same family, both O(n²) over long mangled names and both top `str.eq` callers:
`CBackend.seen_function` (`gen_c_state.zen:456-463`, 20.6M calls) and
`CBackend.type_index` (`gen_c_state.zen:220-227`, 9.8M).

**No bench would have caught it.** `tests/bench/` measures `vec_add`, two field
reads and a stack-array fold — nothing on a compiler hot path. `Bencher.iter`,
`BenchStats` and `Builder.budget` are bodiless declarations wired to nothing
(`DESIGN.md:3` says so). Compile time is reported only as the un-baselined
informational `fmt_tree` line.

**A name is resolved by a linear scan over strings, defended by a comment that
is false.** `sema_def.zen:19-23` says "A MODULE TABLE IS A `Vec`, NOT A `Map`,
and that is measured rather than lazy: `Map.get` in this stdlib is `index_of`, a
`find` over every entry — a linear scan already." **That is no longer true of
this `Map`.** `collections_map.zen` is two Vecs, open-addressed with linear
probing — `get:78` → `index_of:104` → `settle:117` → `walk:128`, which starts at
`h.to_usize() % n` and steps — grown at a 3/4 load factor whose own comment
(`:41-43`) calls the spare quarter a guard against "the linear scan this file
exists to delete". So the premise the `Vec` was chosen on is backwards.

Measured cost: **`str.eq` is called 63,701,481 times per self-compile**, and
every caller is a linear scan, not one a hash lookup —

    20,577,719  gen_c_state.CBackend.seen_function
    11,226,859  sema_def.World.exact_index:136      one str.eq per module, x91
     9,782,641  gen_c_state.CBackend.type_index
     6,527,313  sema_def.collect_exported
     3,334,813  sema_def.collect_named:762          one str.eq per decl, per name
     2,246,379  sema_member.member_named
       217,419  sema_check.Checker.lookup:427       the local-scope stack walk

At -O2 the by-name scans sum to **16.9% of self time**. `str.eq` is a
hand-written byte loop over `data.read(i)` (`text_str.zen:80-91`) and never
reaches `memcmp`; the emitted C uses `memcmp` only for a `str` literal pattern
in a match arm (`gen_c_flow.zen:333`).

Two fixes, and they compose. Keying the tables on the `Map` that already ships
turns each scan into a probe; interning identifiers to a `u32` atom (types are
ALREADY interned — `sema_ty.zen:5-18`, every type comparison is an integer
compare) makes each surviving comparison an integer one. The population is
5,685 distinct identifiers over 137,828 code-only occurrences, 24:1 — a
favourable atom table. The `Map` is the smaller change and should go first.
Delete or correct the comment regardless; a false comment with live code shaped
around it is the highest-value find a comment audit can make.

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

**`make fmt` is in no gate, and there is no CI.** `PLAN.md:321` requires
"`zen fmt --check` over the whole tree, in CI, failing the build". `Makefile:64`
is `test: build parse design cap dupcomments faults lextile ufcs style
grammar-test editors bench-allocs` — no `fmt` — and the repository has no `.github/`, no
`.gitlab-ci.yml`, no CI configuration at all. The per-file guard inside
`fmt.zen` still runs on every invocation, so losslessness is protected; what is
not protected is the tree staying formatted. `Makefile:53-63` has diagnosed this
exact disease three times about three other targets.

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

**Three cleanups carried out of `SIGNATURE_REVIEW.md`, which is deleted.** All
re-verified against this tree; the review's method write-up is in
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

2. **A whole insertion sort duplicated across two LSP files — ~55 lines.**
   `lsp_colour.zen:348` `sort_classes` and `lsp_compl.zen:573` `sort_items`,
   with `bubble`/`out_of_order`/`swap_at`/`swap_pair` line-for-line identical,
   differing in the element type and one comparison. `lsp_compl.zen` says so in
   a comment. One `sort*<T>(v :: Vec<T>, before: (l: T, r: T) bool)` in
   `std.core.loop` beside `find`/`filter`/`map` — `loop_find.zen:35` proves the
   closure-taking generic builds. Must land under `std.core.loop`, not as a
   free function, or `make ufcs` finds a second answer for `v.sort(..)`. These
   are the only two hand-rolled sorts in `src/`.

3. **Four parallel node arenas — ~90 lines, REPORTED AND NOT RECOMMENDED.**
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
