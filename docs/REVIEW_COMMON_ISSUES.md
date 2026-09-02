# Common source issues, and the pass that fixes them

Findings from a four-dimension review of `src/std/lex` (2026-09-02), written as
the checklist for the same pass over every other folder. `STYLE.md` owns the
rules; this page records what applying them to one module found, so the next
folder starts from evidence instead of suspicion.

## How the free-function habit arose

1. `83c4d66b0` (2026-08-15) added to STYLE.md: a free function whose first
   parameter is the module's principal type "is a method someone declined to
   write inside the braces; **call it as one**", and shipped a gate that
   checked only the call shape.
2. `af2f9af78` (2026-08-24) rewrote ~1,150 call sites from `f(x, ..)` to
   `x.f(..)` by swarm. Declarations stayed free.
3. `DESIGN.md:442` and `SOURCE_OWNERSHIP_AUDIT.md:346` then fixed the result
   as doctrine: no out-of-line `impl`; "a fact two modules would both write
   belongs on the type; an operation one module owns stays in that module and
   is dot-called".

The rule optimised how a call looks and never asked whether the declaration
belongs in the type's body. `STYLE.md` now says "make it a method in the
type's module"; the tree has not caught up. The 800-line cap is only an
indirect cause: it is why one type's operations sit in several files.

## Language facts that bound every fix

- **No out-of-line `impl`.** A method is declared inside the record literal,
  in the type's file, or not at all (`DESIGN.md:442`).
- **Enums have no body.** `message(fault)`, `kind_name(kind)` and every
  `colour_of(kind)` must stay free. Making them methods is a language change.
- **Primitives have no body.** `is_digit(b)`, `parse_u64(s)` are exported
  free functions on `u8`/`str`, dot-called. Correct as they are.
- **No import rename.** One file cannot hold both `lex.Span` and `ast.Span`,
  so the converter between them is hand-written in every consumer
  (`parser.zen:91`, `zen_build.zen:240`). Not collatable today.
- **A guard chain is a `loop<T>` that always breaks.** Its result is `Res<T>`,
  so every flattened ladder carries an unreachable `None` arm. Rule from
  `2b9aeae81`: flatten where the function returns a plain value; keep the
  ladder where it returns a `Res` (breaking with a `Res` nests it).
- **Overloading by arity works** (`Cursor.peek()` / `peek(ahead)`); the
  0-arity form should delegate to the n-arity one.
- **An unannotated `Res<T>` binder inside a loop lambda can lose `T` for
  intrinsic conversions.** `self[i].hex_value().match({ Ok(d) => d.to_u64() })`
  inside `Range.loop` fails with "codegen cannot resolve `to_u64`"; binding
  `digit: Res<u8> = ..` first resolves it (`text_num.zen:parse_u64_radix`).
  Sema reports nothing; only codegen does.

## The four issue classes, with what the lexer showed

### 1. Free functions where a body method belongs

Lexer: 51 free functions, 17 body methods. Only **2** violated a rule:
`text_of(source, token)` (two modules used it; the parser had already wrapped
it as a method) and `add_digit(acc, ..)` (the sole operation on a record
declared 30 lines above it). 2 more were call-style slips (`is_hex_prefix(lx)`
beside `lx.hex_number(..)`). 45 were the `DESIGN.md:442` rule working: a
single-owner `(lx :: Lexer)` operation in the module that owns it, dot-called.

The lexer is not an outlier (body:free 0.33; `std.parse` 0.27, `fmt` 0.26,
`std.text` 0.52, `zen` 0.89). The known worse case is `src/fmt/fmt_decl.zen`:
the `Aligned` record has 3 body methods and 8 free `(al :: Aligned, ..)`
functions in the same file, used by nothing else — that is STYLE.md's "a
source file full of `write(backend, ..)`".

Test for each free function:

- Does more than one module call it, or is it intrinsic to its first
  parameter's type (a record declared in the same file)? → **move into the
  body**. Callers become `x.f(..)`; drop the facade export if it was only
  there to reach the function.
- Is it a single-owner operation on a type from another file, a constructor,
  a conversion, or a predicate on a primitive/enum? → **leave it free**, but
  call it on its receiver, and drop `*` if nothing outside the file uses it.
- Is it called both `f(x, ..)` and `x.f(..)`? → one spelling: the receiver.

### 2. Comments that transcribe the author instead of documenting the code

Lexer: 119 comment lines, 42 (35%) failed STYLE.md's list — 12 paraphrases
of the next line, 11 duplicates of a contract stated in another file, 15 in a
persuasive voice (CAPS, "never one or the other", invented numbers), 4 false
or vague. One was factually wrong (`lex_byte.zen:22` claimed guard order
mattered; the predicates are disjoint) and would have stopped a maintainer
simplifying safe code.

Three habits produced them: design justifications pasted from PR discussion
in the voice of a reply; a comment on every function whether or not it had a
fact to state; each file written without reading its neighbours, so one
contract was restated at up to three layers.

Test: a comment states a fact a test could check — an invariant, a span, a
return contract, a consumer. If it contains "because", "rather than", "never",
CAPS, or a number not in the code, it is a reply and goes. Before writing a
"why", grep the module for the same fact and keep one home. Enum-variant
annotations that give the minimal triggering input (`LeadingZero // 010`) are
the best comments in the module; keep those, delete ones that echo the name.

### 3. Structure that forces the other issues

- A type's operations split across files because of the line cap, so the
  body holds only what every sibling file needs and the rest is free. Check
  the split against STYLE.md "When to split a file". The lexer's split passes
  4/5 (fails "a consumer can need one without the other") and was kept; a
  split that fails 2+ should merge.
- Byte/table classification done twice on the same input (`class_of` then
  `punct_of` then `punct_kind` per punctuation token). Collate to one table.
- The same conversion written by each consumer (`lex.Span → ast.Span` ×2).
  Collate when the language allows; record when it does not.
- Over-subdivision: a folder of files that only ever import each other, with
  a facade whose exports have no external consumer, is one subject in several
  files. The lexer's facade exported 14 names nothing outside used.

### 4. Local redefinitions of std, and uncollated twins

Lexer: no byte predicate was redefined (all resolve to `std.core.byte`), but
the u64 accumulator duplicated `text_num.parse_usize`'s overflow loop (now
`str.parse_u64` / `parse_u64_radix` in `std.text`), `keyword_of` hand-rolled
`Range.find`, and `since` duplicated `text_of`. No twin disagreed with its
owner — check this explicitly; a disagreeing twin is a bug, not a cleanup.

Test: for every table, loop, or predicate, grep `src/std/core` and
`src/std/text` first, then the tree, for the same shape. The owner is the
lowest layer that can hold it without importing upward (`std` may not import
`std.lex`/`std.parse`/`std.ast`; enforced by `tests/run.py:876` pruning the
sublayer from every test that does not name it).

## Deferred, with the reason

| Finding | Why not now |
|---|---|
| `TokenKind.impl(Eq)` is 48 hand-written arms (`lex_token.zen`) | No enum in the tree has `Eq`; sema does not derive tag equality (`sema_bound.zen:574-588`). A `kind_name` string compare would land on the parser's hottest predicate. Needs a sema tag-compare intrinsic. |
| `lex.Pos` duplicates `ast_span.Pos` + Display | Pinned deliberately by `tests/corpus/std/pos_display_both_format_doors_agree.zen`. |
| `lex.Span → ast.Span` converter ×2 | No import rename; one file cannot name both types. |
| `lex_diag` has no `render`/`say` while sema/gen/parse diags do | `zen_fmt.zen:76` spells the format itself; adding the method without a caller is dead code. Do it when a second consumer appears. |
| `message`/`kind_name` on enums | Enums have no body. |

## The pass, per folder

1. Read the folder whole before editing any file. List every top-level free
   function with its first parameter and how it is called.
2. Apply the four tests above. Edit in place; do not add files, folders,
   `helpers`, or a second facade.
3. Flatten `.match({ true => X, false => <match> })` ladders to guard chains
   only where the function returns a plain value.
4. Do not touch `seed/`. Do not regenerate the seed in a lane.
5. Local gate before commit: `./zen fmt <files>`, then
   `python3 tests/run.py --filter '<the folder's corpus>'`, then `make build`
   (a red `make build` is evidence only after it reproduces). The gate is
   behaviour, not bytes: emitted C may change, and a better pattern found on
   the way is in scope. Only the seed fixpoint (`cmp seed/zen.c stage2.c`,
   run once at integration) is a byte check, and it proves the new seed is
   self-consistent, not that output is unchanged.
6. Commit on the lane branch with the numbers: free functions before/after,
   comment lines before/after, lines saved by collation, and every deferred
   finding with its reason.

Integration regenerates the seed once, after the last lane lands, and runs
`make test` from the new seed (`Makefile: seed`, `docs/PLAN.md:238`).
