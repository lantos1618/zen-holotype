# ISSUES

**Paste here. No ceremony, no format.** A code snippet with no words is a valid
entry — the snippet is the report. Anything under OPEN gets worked; anything
under DECIDE needs a call that is not mine to make.

Move an entry to CLOSED with the commit that closed it, or delete it. Do not
leave a fixed thing sitting under OPEN; a stale queue stops being read, which is
how a gate that cannot fail happens to a list.

---

## INBOX — paste below this line

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
around it is what `COMMENT_AUDIT.md` calls the highest-value find.

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
is `test: build parse design cap dupcomments faults ufcs style grammar-test
editors bench-allocs` — no `fmt` — and the repository has no `.github/`, no
`.gitlab-ci.yml`, no CI configuration at all. The per-file guard inside
`fmt.zen` still runs on every invocation, so losslessness is protected; what is
not protected is the tree staying formatted. `Makefile:53-63` has diagnosed this
exact disease three times about three other targets.

## DECIDE — needs a call

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
