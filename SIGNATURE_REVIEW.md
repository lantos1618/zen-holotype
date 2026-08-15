# Where LOC can still be killed

A signature digest of `src/`, reviewed for redundancy, verified against the
tree. Every number below is an ESTIMATE and is deliberately on the low side.

Produced by `scripts/signatures.py` (new, this commit) plus a review pass and
a hand check of every finding that survived.

## The digest

`python3 scripts/signatures.py --out sigs.txt` walks `src/**/*.zen`, parses
each file with `bootstrap/cst.py` — the real grammar, never a regex, for the
reason `docs/STYLE.md:23` gives — and prints one line per declaration under a
`### <path>` header: functions with parameter names, types, `::` vs `:`, and
return type; structs with every field, default and const; enums with variant
payloads; traits; impls; aliases.

    178 files      5,828 lines      363 KB
    src/ itself   54,570 lines     2.0 MB

So the declared surface is 10.7% of the lines and 17.4% of the bytes. That is
what makes a whole-tree read possible at all.

A trait is reported as `trait` when a struct stores nothing and every function
member is bodiless. Zen has no `trait` keyword, so that is a reading of the
shape, not a fact the grammar states; the script says so at the function.

## Method, and what the review is worth

The digest was chunked by folder and each chunk sent to `gemini`:

    cat PROMPT.md <chunk>.txt > req.md
    /home/ubuntu/.local/bin/gemini --max 32000 -t 0.2 -f req.md

(`--max 4000`, the default, silently truncates mid-finding: the model's
thinking is charged against the same budget. At 6000 every chunk came back
cut off after two findings. 32000 is what made the pass complete.)

The prompt asked only for near-duplicate signatures, one-parameter-apart
families, `*_one`/`*_at` variant families, structs with identical field sets,
duplicated enums, and signatures whose file placement contradicts the file
name — and forbade bug-finding, correctness claims, and behaviour inference.
Every finding had to quote its lines verbatim.

**Quote fidelity: 142 findings offered, 142 exact. Zero misquotes.** A script
re-checked every quoted line against the digest at the named file and line
number and required a character-for-character match; it was mutation-tested
(corrupt one quoted character, the check goes red) so the 0 is not vacuous.

**Claim fidelity is the different number.** I adjudicated 15 findings against
the actual source. 8 survived, 5 were rejected outright, 2 were demoted to
high-risk. That is a **33% rejection rate on the sample**, against 0% on
quotes — the model reproduces text perfectly and infers relationships poorly.

The rejections matter more than the rate, because **the model's own top two
findings by claimed saving were both wrong**:

- `src/std/core/num.zen:109-129`, 18 `to_*` conversions "that should be one
  generic". They are bodiless intrinsic declarations, one per (source, target)
  pair, and the file's own comment explains that the list *is* the conversion
  set. Nothing to collapse into.
- `src/std/core/num.zen:141-148`, the 8 `ToU16`/`ToU32`/… traits. Same file,
  same comment, same answer: "one behavior per target… the prelude needs the
  behavior NAMES".

Its ranking is anti-correlated with value. Most of the 127 findings I did not
adjudicate claim "LINES SAVED: 1" and are the same shape as the rejections —
two functions whose names rhyme, where one calls the other. Decomposition, not
duplication. Treat the model as a lead generator over the digest and nothing
more.

The largest finding below (#1) is mine, not the model's: it came from noticing
that two of its weak findings (`fs_name_2`/`fs_name_3`, `verb_1`…`verb_4`) were
instances of one shape, then measuring that shape across the tree.

---

## 1. Fall-through chains that are one `match` on a literal — ~150 lines

**What.** Zen has no `else if`; a multi-way test is written as a run of
functions each testing one thing and tail-calling the next. Measured over the
whole tree with `bootstrap/cst.py`: **340 such arms in 80 files, 2,416 lines
of source**, of which **18 are maximal chains of 3+ links: 72 functions,
506 lines**. Each link re-declares the full parameter list — up to ten
parameters, threaded unchanged — to express one comparison.

Not all of them can collapse, and the split is the whole finding:

- **Class A — one scrutinee, many literals.** Collapses to a single `match`
  with literal patterns. `_pattern` in `grammar/grammar.js:709` admits
  `string_literal`, `number_literal` and `char_literal`; `src/std/lex/
  lex_scan.zen:157` runs one in production (`word.match({"true" => …})`); and
  `gen_c_flow.zen:276 str_cond` is the backend that lowers it, emitting the
  same comparison sequence. So the change is expressible today and costs
  nothing at runtime.
- **Class B — a different predicate per link.** e.g.
  `src/gen/gen_c/gen_c_call.zen:468-531`, which tests `is_loop_shape`, then
  `inlines`, then `is_null_ptr`, then `is_format_door`. There is no scrutinee
  to match on. **This does not collapse** and I am not counting it.

Class A, with conservative estimates:

| site | now | after | saved |
|---|---|---|---|
| `src/gen/gen_c/gen_c_ptr.zen:156-216` `verb`→`verb_7`, 7 links on `name.eq("read"/"write"/"offset"/"back"/"bytes"/"copy_from"/"is_null")` | 61 | ~16 | **40** |
| `src/gen/gen_c/gen_c_cap.zen:182-233` `console_verb`→`verb_5`, 6 links on `a.name.text` | 52 | ~18 | **34** |
| `src/sema/sema_trap.zen:566-626` four literal tables (`signed_max`, `signed_min`, `unsigned_max`, `bits_of`), 15 functions on `name` | 61 | ~30 | **31** |
| `src/lsp/lsp_reply.zen:204-245` `request_of`→`request_after_colour`, 6 links on `method` | 42 | ~12 | **30** |
| `src/gen/gen_c/gen_c_ptr.zen:92-131` `ptr_member_type`→`ptr_type_5`, 5 links on `a.name.text` | 40 | ~14 | **22** |
| `src/gen/gen_c/gen_c_fs.zen:406-416` `fs_name`/`_2`/`_3`, number literals on `n` | 11 | ~6 | **5** |

**~160 lines, called ~150.** Verified: I read all six sites.

The `lsp_reply` one is the cleanest illustration —

    request_of* = (method: str) Request {
        method.eq("textDocument/hover").match({
            true  => Request.Hover,
            false => request_after_hover(method),
        })
    }

six times over, becomes one seven-arm `method.match({..})`.

**Risk: low.** Mechanical, arm order preserved, same comparisons emitted. One
wrinkle: `lsp_reply.zen:232` tests `method.eq(SEMANTIC_TOKENS)`, a const, and
a pattern must be a literal — that arm either inlines the string or stays a
separate test.

**Interactions.**

- `scripts/style.py`'s `UFCS_OWED` is a per-file COUNT and the gate fails when
  the count drops without the ledger being edited (`style.py:678-683`).
  Deleting these call sites lowers `gen_c_cap.zen` (83), `gen_c_ptr.zen` (48),
  `sema_trap.zen` (47) and `gen_c_fs.zen`. **The ledger numbers must come down
  in the same commit** or `make style` goes red. This is the debt shrinking,
  which is the point, but it is not automatic.
- `src/gen/gen_c/gen_c_member.zen` is 817 lines and holds an entry in
  `scripts/line_cap.py`'s `EXCEPTIONS`, whose stated reason is "the vertical
  formatter stretched it past the cap". It carries 12 chain arms over 102
  lines. Most are class B, but clearing what is clearable there is the
  cheapest route to deleting an exemption rather than renewing it. (`make
  cap` currently reports 44 files over 500 and 0 over 800 — the 800 cap is
  green only because of that dict.)

## 2. A whole insertion sort duplicated across two LSP files — ~55 lines

    src/lsp/lsp_colour.zen:370-412   sort_classes, bubble, out_of_order, swap_at, swap_pair
    src/lsp/lsp_compl.zen:505-547    sort_items,   bubble, out_of_order, swap_at, swap_pair

Line for line identical — same loop, same `.get(j-1)` / `.get(j)` nesting,
same `written()` misses, same `.set` pair — differing in exactly two places:
the element type (`Classed` vs `Item`) and one comparison expression
(`before_start(rgt, lft.line, lft.col)` vs `rgt.label.before(lft.label)`).
`lsp_compl.zen:506` even says so: "Insertion sort, `lsp_colour.zen`'s own
shape".

**Consolidation.** One `sort*<T> = (v :: Vec<T>, before: (l: T, r: T) bool)
Res<(), AllocError>` in `std.core.loop`, beside `find`/`filter`/`map`.
`loop_find.zen:35` already has exactly this shape —
`find*<R: Range<T>, T> = (range: R, pred: (value: T) bool) Res<T>` — so a
generic taking a closure is a form the compiler builds today.

86 lines become ~25 in std plus two call sites. **~55 saved**, and std gains
the sort whose absence both files apologise for ("std has no sort").

**Risk: low-medium.** New std surface, and it must land under `std.core.loop`
rather than as a free function, or `make ufcs` will find a second answer for
`v.sort(..)`. `lsp_compl.zen` owes 3 UFCS rewrites; check the count after.

**Verified:** both regions read in full. These are the only two hand-rolled
sorts in `src/`.

## 3. Four parallel node arenas — ~90 lines, but the author argues against it

    src/std/ast/ast_arena.zen:56-81    add_expr / add_type / add_pattern / add_block
    src/std/ast/ast_arena.zen:104-137  expr_at / type_at / pattern_at / block_at
    src/std/ast/ast_arena.zen:147-150  expr_ids / type_ids / pattern_ids / block_ids
    src/std/ast/ast_arena.zen:164-195  exprs_each / types_each / patterns_each / blocks_each
    src/std/ast/ast_id.zen:25-67       four `{ index*: u32 }` structs, eight identical Eq/Hash impls
    src/sema/sema_ty.zen:34-42         a fifth of the same, `TyId`

Sixteen methods that differ only in (vec field, count field, id type, node
type, one string). The Eq and Hash bodies are character-identical five times
over: `self.index == other.index` and `self.index.to_u64()`.

**Consolidation.** `Arena<T> = { items :: Vec<T>, count :: u32, add*, at*,
ids*, each* }` held four times by `Ast`, with a phantom-tagged `Id<T>`
preserving the four distinct id types.

**I am reporting this as a finding but not recommending it.** Both files
explicitly reject it, in comments written by someone who had the option:

- `ast_id.zen:12` — "Four distinct types, not one `NodeId`: passing a TypeId
  where an ExprId belongs is the mistake parallel agents will make, made
  unrepresentable for free."
- `ast_arena.zen:157` — "ONE HELPER PER FAMILY, not one generic: the four id
  types are distinct on purpose, so nothing generic can span them."

A phantom `Id<T>` answers the stated objection (distinctness survives), so the
premise is refutable — but that is a design argument, not a cleanup, and it is
**218 call sites** of `expr_at`/`add_expr`/… across the compiler. Estimated
saving ~90 lines at high risk and a large diff. **Ask before doing it.**

`src/sema/sema_id.zen`'s `DeclId`/`MemberId`/`ImplId` are NOT part of this:
their Eq and Hash bodies genuinely differ.

---

## What I did not do

- **I did not adjudicate 127 of the 142 findings.** They are almost all
  "LINES SAVED: 1" on pairs where one function calls the other. Sampling five
  of them (`parser.zen` `expect`/`expect_after`, `sema_apply.zen`
  `infer_targs`/`infer_at`, `text_string.zen`'s two `String` constructors,
  and the two `num.zen` families) rejected five out of five, which is why I
  stopped rather than kept going.
- **`src/fmt/` is excluded from every recommendation.** Another lane owns it.
  Its chunk was reviewed and produced nothing above the noise floor anyway.
- **No file-placement findings survived.** The model was asked for signatures
  sitting in wrongly-named files and offered none it could quote. I did not
  independently audit placement; `docs/STYLE.md`'s naming rule is still
  checked only by review.
- **I changed no `src/` file.** Every estimate above is from reading, not from
  doing the edit and counting the diff. Estimates made by reading run
  optimistic; halve them if you need a number you can commit to.
