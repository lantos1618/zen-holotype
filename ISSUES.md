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

Blocked on the `@meta` fork below, for step 2 only: `src/lsp/` is inside `src/`,
which `bootstrap/` compiles as fixpoint stage 1. This is the THIRD payoff
riding on that one decision, alongside the six `std` consumers and `fmt`'s
writer-picking.

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

**`corpus/lex/long_single_line` has 2x timeout headroom** — ~60s against 120s on
the Python toolchain, so it flakes whenever the box is busy. Not a regression;
a fragile test.

**`gen_c_print.zen` holds two subjects** at 543 lines — `println`'s lowering and
the shared format classifier. A split is owed, and it carries the bootstrap
import hazard, so it needs its own fixpoint cycle.

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

**`@meta` in `src/std`.** All six waiting consumers (`Display.dump`, the `Eq`
and `Hash` defaults, `Env`'s typed args, `build.zen`'s nodes) live in `src/std`,
which `bootstrap/` compiles as fixpoint stage 1 — so adopting `@meta` there
takes `make fixpoint` off the board for every unrelated change. (a) teach
bootstrap `@meta`; (b) re-root fixpoint at the committed seed, losing the
independent second implementation; (c) leave the six waiting.
See `docs/design_meta.md`.

## CLOSED

- literal `{}` — `{{` writes `{`, `}}` writes `}` — `13f9c7ee`
- `{name}` holes resolved where written — `26c50119`
- `vararg<T>`, forwardable — `3c1d9c91`
- `[u8, SIZE]` folds through a constant — `871d8798`
- unused imports: gate + 1195 culled — `03d1b597`
- a pattern naming a constant is reported, not silently irrefutable — `76dd2fe7`
- array literal element type comes from its position — `d3bd7e9f`
