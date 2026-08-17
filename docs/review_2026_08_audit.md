# Audit of the external review, 2026-08

An outside reviewer scored Zen **9/10** and left a fourteen-item checklist plus
five claimed strengths. This file is the audit of that checklist, item by item,
against the tree at `84b233f2`. **No source was changed to produce it.** Three
things turned up while probing that are not the reviewer's — two live
"sema admits it, `cc` rejects it" bugs and one 30%-of-the-build performance
defect. All three are reported and none is fixed.

The reason to audit a compliment is that an unaudited checklist handed to
contributors is a list of things to break. Five of these fourteen items are
already shipped, and two of the five are shipped *by the name the reviewer used
for them*.

---

## The counts

| verdict | n | items |
|---|---|---|
| **DONE** | 5 | binary_from, recover bounds, Maranget exhaustiveness, nominal/structural, AST arena |
| **DONE DIFFERENTLY** | 3 | typed AST layer, `parse(print(AST)) == AST`, layered IRs |
| **REAL GAP** | 4 | lookahead bounds, compact AST dump, `--json-diags`, name-lookup cost |
| **CONTRADICTS DESIGN** | 2 | `.zeni` interface files, minimising `Stmt`/`Expr` |
| **UNVERIFIABLE** | 0 | |

**Five of fourteen recommendations are already in the tree**, and the
checklist's single highest-effort item — "exhaustiveness checker via Maranget's
decision-tree algorithm" — names an algorithm whose citation is already in a
file header (`src/sema/sema_match.zen:9`, `THE ALGORITHM IS MARANGET'S
USEFULNESS`). Four items are real, three of them small. Two would break a
stated law.

Of the five claimed strengths, **four are true and one is overstated** — see the
last section.

**The most valuable thing in this audit is not on the checklist.** Profiling the
compiler against itself, which the perf item forced, found that **~30% of a
build is one insertion sort with no early exit** (`gen_emit.zen:171-185`) — more
than every performance item the reviewer listed, combined, and a ~10-line fix.
It was invisible because a comment in the same file asserts the input is
"hundreds of top-level names per unit, never millions" and it is ten thousand.

---

## The verdict table

### Grammar and parsing

| item | verdict | evidence |
|---|---|---|
| all binary operators iterative (`binary_from`), not recursive | **DONE** | `parse_expr.zen:144` folds left-associatively in a `loop`; the only recursion is the right operand at `prec + 1`, capped by a 6-entry precedence table (`:97-117`). All 16 binary operators go through it. |
| every scan in `parse_lookahead.zen` halts at `Eof` or a delimiter | **REAL GAP** (narrow) | 4 of 5 scans are safe; `group_end_at` (`parse_lookahead.zen:144`) has no `Eof` and no statement-terminator give-up, so an unclosed `(` scans to end of stream, from 6 call sites. |
| `recover()` cannot loop on malformed tokens | **DONE** | `parse_decl.zen:82-101`: every iteration either sets `running = false` or calls `p.skip()`, which unconditionally advances `p.at` (`parser.zen:356`). The caller adds a `p.at == before` progress guard (`parse_decl.zen:66`). |

### Type system and sema

| item | verdict | evidence |
|---|---|---|
| add a Typed AST layer so sema stops mutating AST nodes in place | **DONE DIFFERENTLY** | Sema never mutates the AST — `Checker.tree` is a by-value snapshot (`sema_check.zen:96, 713-719`), zero `add_*` calls from `src/sema/` or `src/gen/`, and no inference slot exists to write into (`AST_CONTRACT.md:429`). Answers live in memo tables keyed on node ids (`sema_check.zen:95-143`). |
| exhaustiveness via Maranget's decision-tree algorithm; detect unreachable arms | **DONE** | `sema_match.zen:9-24` names Maranget's usefulness; `specialise` `:605`, `specialise_lit` `:682`, `default_matrix` `:715`, complete-signature split `:503-525`. Both diagnostics verified live (below). |
| formalise structural vs nominal: aliases erased, struct/enum keep identity | **DONE** | Aliases resolve through at `sema_type.zen:245-260` (two named exceptions). Nominals intern on `DeclId` + module-qualified name (`sema_ty.zen:260-290`); equality is a `u32` compare. Stated as law at `DESIGN.md:478`. |

### Tooling

| item | verdict | evidence |
|---|---|---|
| lossless round-trip: assert `parse(print(AST)) == AST` | **DONE DIFFERENTLY** — and the tree's version is the correct one | `fmt.zen:216-257` re-lexes the output and compares the token stream (count, kind, raw bytes); comments are tokens so they are covered. Runs on **every** `zen fmt`, and `zen_fmt.zen:140-159` refuses to write the file when it fails. |
| compact AST dump (`zen ast --compact`) for LLM context | **REAL GAP** | `DumpAst` exists only in prose. `grep -rn 'DumpAst\|dump_ast' src/` → no hits. `./zen ast` → `unknown argument`. There is no dump at all, compact or otherwise. |
| `--json-diags` for machine-readable errors | **REAL GAP** (CLI only) | The LSP publishes JSON diagnostics (`lsp_diag.zen:355-380`). The CLI accepts exactly seven flags — `--emit-c`, `-o`, `--entry`, `--repeat`, `--permute`, `--check`, `--stdio` (`zen_cli.zen:250-277`) — and prints `file:line:col: message` text. No `--json` anywhere in the tree. |

### Memory and performance

| item | verdict | evidence |
|---|---|---|
| arena-allocate all AST nodes in contiguous chunks | **DONE** | `ast_arena.zen` is the arena; four child families are `u32` indices into it (`AST_CONTRACT.md:72-96`); ids are assigned in creation order and nothing is an address, which is what keeps `gen_c` deterministic (`:402`). The whole program is one `Ast` (`zen_build.zen:18-20`). |
| intern identifiers into a `u32` atom table instead of raw `str` | **REAL GAP**, reframed — the direction is right and the prescription is one of two | Types are *already* interned to `u32` and every type comparison is an integer compare (`sema_ty.zen:5-18`). Identifiers are not, and every bare-name resolution is a linear scan doing `str.eq` per entry (`sema_def.zen:286` → `collect_named`, `:136` `exact_index`). The comment justifying that design is **false** — see below. |

### The OCaml lessons

| item | verdict | evidence |
|---|---|---|
| layered IRs (`AST → Typedtree → Lambda → Clambda`) instead of AST → C | **DONE DIFFERENTLY**, with a real residue the reviewer is right about | No IR exists; `gen_c` walks the parse AST and pulls from the live `Checker`. The residue is documented *by the tree itself* — see below. |
| ML-style module system with explicit interface files (`.zeni`) | **CONTRADICTS DESIGN** | No such file exists and none can. Compilation is whole-program (`DESIGN.md:69`); the public surface is the `*` marker (law 6, `DESIGN.md:82`) and a folder root of starred re-exports (`STYLE.md:134`). An interface file would be a second place a signature is written, which law 6 exists to prevent. |
| minimise the `Stmt`/`Expr` distinction | **CONTRADICTS DESIGN** | `DESIGN.md:245`: "A statement ends with `;`. A declaration does not. That is the whole rule." `:259`: a binding is a statement and therefore can never be a block's trailing value. `:261` prices and rejects both alternatives (optional semicolons; newline sensitivity). The distinction *is* the disambiguator. |

---

## The four REAL GAPs

The fourth — name lookup is a linear string scan — is written up under "the two
items that deserved care" below, because the interesting part of it is why the
tree believes otherwise.

### 1. `group_end_at` scans to end of stream on an unclosed `(`

**Size: a few lines.** `parse_lookahead.zen:144-152` walks
`Range(from, p.tokens_len())` counting delimiter depth and stops only when depth
returns to 0. Its sibling `angles_end_at` (`:158-172`) does the right thing —
`angle_stop` includes `Eof => true` (`:226`) and gives up on a statement
terminator. `group_end_at` has neither. It cannot run past the array (every read
goes through `token_kind_at`, which returns `Eof` out of range, `parser.zen:254`),
so this is not a termination bug; it is a **quadratic-time hazard**: six call
sites (`lambda_ahead:91`, `fixed_array_ahead:127`, `paren_shape:261`,
`variant_ahead:296`, `declares_fn:425`, `bar_after:440`) each rescan the whole
remaining file for every `(` after an unclosed one.

**Unblocks:** an editor-grade parser. The LSP re-parses on every keystroke, and
a half-typed `(` is the single most common state a buffer is ever in.

**ISSUES.md: yes.** This is the one checklist item that landed on something the
tree had not written down.

Two neighbours found in the same pass, both worth the same entry:

- `enter`/`leave` are not failure-safe. `parse_expr.zen:63-66` (and the same
  shape at `parse_stmt.zen:32`, `parse_type.zen:31`, `parse_pattern.zen:28`,
  and `unwind` at `parse_expr.zen:257`) calls `p.leave()` *after* a `.try()`, so
  an `AllocError` leaks a depth level permanently. `depth` is a `usize` and
  `leave` is `self.depth - 1`, so an unbalanced count underflows rather than
  traps.
- `too_deep` is sticky, file-global, and **aborts the module**:
  `parse_decl.zen:70` reads `running = !p.at_eof() && !p.too_deep`. One
  over-deep construct on line 1 stops the rest of the file being parsed, and
  `hushed` (`parser.zen:545`) silences every later diagnostic.

And a test gap rather than a code gap: `recover()`'s body appears to be
**unreached by any test**. `tests/corpus/parse/parser_error_recovery.zen` feeds
it four declarations that each begin with an identifier, so `p.at` always
advances and the `p.at == before` branch is never taken. No module-level input
starting with `;`, `}` or `+` exists anywhere in `tests/`.

### 2. There is no AST dump

**Size: a day, and it is mostly a printer.** The reviewer asked for a *compact*
mode; the tree has no dump at all. `DumpAst` is named in `DESIGN.md:1301`,
`PLAN.md:268` and `tests/parse/constructs.md:1323` purely as an example of
overload syntax, and `PLAN.md:268` reads as if it exists ("`@meta`, DumpAst and
`gen_c` all consume these nodes"). Everything it needs is already there — the
node set is closed, every node has a span, and `Display` already declares
`toString`.

**Unblocks:** the `@meta` work, which needs a way to look at nodes; every future
parser bug report, which today is "paste the source and hope"; and the reviewer's
actual use, feeding a tree to a model.

**ISSUES.md: yes**, and the `PLAN.md:268` line should be marked NOT WRITTEN in
the same change — `PLAN.md:125` is explicit that a path naming a file that does
not exist is worse than listing nothing.

### 3. The CLI has no machine-readable diagnostics

**Size: small, once the shape is decided.** The LSP already builds JSON
diagnostics from `Diag` values (`lsp_diag.zen:355-380`), and every phase already
produces `Diag` carrying a position (`PLAN.md:360`, "diagnostics are values
carrying positions — holds, every phase, no exceptions"). What is missing is a
CLI flag and a second writer.

**It should wait for the entry already in `ISSUES.md`.** That entry — "the LSP
hand-writes JSON; it should have structs with a derived `to_json`" — is the same
work seen from the other end. Adding a second hand-written JSON writer for the
CLI before that lands means writing the thing that entry exists to delete.

**ISSUES.md: yes, folded into the existing JSON entry rather than as a new one.**

---

## The two items that deserved care

### "Intern identifiers into a u32 atom table"

**Measured, not reasoned about.** `make profile` (`Makefile:266`) and a
separate `-O1 -pg` build were run against the compiler's largest realistic
workload — itself. Baseline: `./zen build src --emit-c` is 2.5 s wall.

**`str.eq` is called 63,701,481 times in one self-compile.** Its callers, from
`gprof -b -q`:

    20,577,719  gen_c_state.CBackend.seen_function
    11,226,859  sema_def.World.exact_index
     9,782,641  gen_c_state.CBackend.type_index
     6,527,313  sema_def.collect_exported
     3,596,571  sema_def.World.follow_imports
     3,334,813  sema_def.collect_named
     2,246,379  sema_member.member_named
       217,419  sema_check.Checker.lookup

Every one of those is a linear scan. Not one is a hash lookup. At `-O2` the
by-name scans sum to **16.9% of self time** (`exact_index` 3.64,
`exported_named` 3.57, `member_named` 2.47, `impls_named` 2.08,
`named_field_of` 1.44, `seen_function` 1.05, `own_members` 1.05, and six
smaller). The identifier population is 5,685 distinct names over 137,828
code-only occurrences — a 24:1 repetition ratio, which is a textbook-favourable
interning target.

**So the reviewer's item is real and worth about 17%.** It is not the biggest
win in the profile; see "what the reviewer missed", below.

**Half of it is already done, and the half that is not is defended by a
comment that is false.**

*The done half.* `sema_ty.zen:5-18`: "TYPES ARE INTERNED: two types are equal
exactly when their ids are equal, so every comparison (overload resolution,
error-set merging, assignability) is a `u32` compare, never a structural walk".
`assignable` (`sema_check.zen:444`) and `same_type` (`:543`) both bottom out in
`TyId.eq`, which is `self.index == other.index`. The inner loop of the type
checker — the thing an atom table is usually bought for — is already integer
comparison.

*The undone half.* Every bare-name resolution is a linear scan comparing
strings. `defs_of` (`sema_def.zen:174`) calls `own_defs` (`:286`), which calls
`collect_named`:

```groovy
collect_named = (defs: Vec<Def>, name: str, out :: Vec<Def>)
                Res<(), AllocError> {
    defs.loop((h, d) {
        d.name.eq(name).then(() { out.add(d).try() });
    });
```

— one `str.eq` per declaration in the module, per name resolved. Finding a
*module* is the same shape: `World.exact_index` (`sema_def.zen:136`) is a `find`
over every module table doing `t.name.eq(name)`, and this compilation has 91 of
them.

**The design note defending that is stale.** `sema_def.zen:19-23` says:

> A MODULE TABLE IS A `Vec`, NOT A `Map`, and that is measured rather than lazy:
> `Map.get` in this stdlib is `index_of`, a `find` over every entry — a linear
> scan already.

That was true of some earlier `Map` and is not true of this one.
`collections_map.zen` is **two Vecs, open-addressed with linear probing**: `get`
(`:78`) hashes, `index_of` (`:104`) calls `settle` (`:117`) which calls `walk`
(`:128`), and `walk` starts at `h.to_usize() % n` and steps forward. The file's
own header says so — "a lookup hashes, reduces to one slot, reads one or two
entries instead of walking all of them" — and it grows at a 3/4 load factor,
where `:41-43` describes the quarter left empty as guarding against "the linear
scan this file exists to delete". So the premise the `Vec` was chosen on ("a
`Map` would buy the same
complexity") is exactly backwards today. This is the same class of defect
`COMMENT_AUDIT.md` calls the highest-value find: a false comment with live code
shaped around it.

One more thing about `str.eq`: it is a hand-written byte loop over
`data.read(i)` (`text_str.zen:80-91`), and it never reaches `memcmp`. The
emitted C *does* contain `memcmp` — 45 lines of `seed/zen.c` — but only from
`gen_c_flow.zen:333`, which is the `str` literal pattern in a match arm. Every
one of those 63.7M `.eq` calls is the byte loop, and the byte-read primitive it
sits on (`str.index`) is 22.1% of self time on its own.

**What to do, and the order matters.** There are two fixes and the reviewer
named the harder one. Interning identifiers to `u32` turns each comparison into
an integer compare but leaves the scan linear; keying the tables on the `Map`
the stdlib already ships turns the scan into a probe. They compose, and the
second is the smaller change.

**ISSUES.md: yes** — filed as the false comment plus the `Vec`, with the atom
table named as the second step.

### What the reviewer missed, and it is bigger than anything on the checklist

**~29.6% of the build is one insertion sort with no early exit.**

`gen_emit.order` (`gen_emit.zen:163-192`) is the backend's single ordering
primitive. `insert_ordered` runs `Range(1, n).loop` — **all** n−1 iterations,
every insertion, whether or not the element has already settled:

```groovy
insert_ordered = (out :: Vec<usize>, keys: Vec<String>, i: usize)
                 Res<(), AllocError> {
    out.add(i).try();
    n = out.len;
    Range(1, n).loop((h, k) {
        j    = n - k;
        prev = index_at(out, j - 1);
        cur  = index_at(out, j);
        earlier(keys, cur, prev).then(() { .. swap .. });
    });
```

It is therefore Θ(n²) *unconditionally*, not adaptively. Measured: 10,032 calls
to `insert_ordered` drive **20,727,600 full lexicographic comparisons**
(`str.before`) over mangled C symbol names that routinely exceed 100 characters,
which in turn drive 787,380,320 of the 860,436,866 `str.index` calls in the
whole build. At `-O2` that is `str.before` 23.70% + `view_at` 4.33% + `order`
1.60% = **29.63% of self time**.

**Its header carries the false premise that made it invisible**
(`gen_emit.zen:161-162`): *"Hundreds of top-level names per unit, never millions
— the simplest-to-verify version is the right one."* Ten thousand keys is not
hundreds, and an insertion sort with an early exit is no harder to verify than
one without. This is a ~10-line fix and it is worth more than every performance
item on the reviewer's checklist put together.

Two neighbours in the same family, both O(n²) over long mangled names, and both
among the top `str.eq` callers above: `CBackend.seen_function`
(`gen_c_state.zen:456-463`, 20.6M calls) and `CBackend.type_index`
(`gen_c_state.zen:220-227`, 9.8M).

**And the reason none of this was known: no bench measures a compiler hot
path.** `tests/bench/` holds four benches — `vec_add`, two field reads, a
stack-array fold. Nothing benchmarks name resolution, string comparison, AST
construction, or the emit sort. `Bencher.iter`, `BenchStats` and
`Builder.budget` are **bodiless declarations** wired to nothing, which
`DESIGN.md:3` states in writing. `make bench` reports compile time only as an
un-baselined informational `fmt_tree` line.

### "Layered IRs instead of AST → C"

**The reviewer is right that a cost is being paid, and wrong about the size of
the fix.**

There is no IR: `find src -iname '*ir*' -o -iname '*lower*' -o -iname
'*desugar*'` returns nothing, and `gen_c` reads the arena directly (50
`be.tree.expr_at` calls) while pulling 342 answers out of the live `Checker`.
The cost is not speculative; the backend documents it in its own headers:

- **`gen_c_infer.zen:1-15`** — *"Infers what sema didn't record. Sema records a
  call's instantiation and value type only inside bodies it checked (top-level
  decls). Calls inside MEMBER bodies get nothing recorded."* A whole file
  re-running unification in the backend.
- **`gen_c_member.zen:17-29`** — which member a dot resolved to is re-derived
  from the AST, because `call_memo` is `ExprId -> DeclId` and a `DeclId` cannot
  name a member. The file says so and names the fix: `MemberId`, which already
  exists in `sema_id.zen`.
- **`gen_c_flow.zen:481-511`** — a *second* variant-vs-binder oracle
  (`is_variant`/`enum_has`) beside sema's `is_case`/`cases_of`. It walks
  `Enum.variants` directly and does not consult `union_reading`, which sema's
  `variant_cases` does. `sema_case.zen:187` calls that exact divergence "this
  compiler's worst failure class".
- **`gen_c_expr.zen:156-171`** — the backend deliberately *overrides*
  `expr_memo`, because the memo key is a node id alone and an answer cached
  while lowering `Vec<Diag>.get` was read back for `Vec<TyId>.get`. `PLAN.md:369`
  already flags that key as owed.

**What a Typedtree would buy:** every one of those four disappears, because each
is the backend asking a question sema answered in a form the backend cannot
read.

**What it would cost, and it is the keystone.** `DESIGN.md:22` and `PLAN.md:276`
both name `gen_c` as one of the AST's *three* consumers, and say that is what
makes stage-5 `@meta` "free rather than a parallel universe". Put a Typedtree
between sema and `gen_c` and the count is two, and `@meta` — which hands back
`std.ast` node types — is describing a tree the backend no longer consumes.
Four layers (`AST → Typedtree → Lambda → Clambda`) also collides with
`PLAN.md:402`, "what not to build: an optimizer", since the last two layers of
OCaml's stack exist to optimise and Zen's stated answer is that C does that.

**The honest recommendation is the narrow one, and it is not an IR: make sema
record what it already computes.** Three concrete changes, each independently
landable — check member bodies and fill the memos for them, add `MemberId` to
`call_memo`'s answer, and key `expr_memo` on `(ExprId, instantiation)` (which
`PLAN.md:369` already owes). That deletes `gen_c_infer.zen`, closes the
`gen_c_member.zen` seam by name, and removes the `gen_c_flow.is_variant`
duplicate. It buys the whole of what the reviewer wants and costs the keystone
nothing.

---

## The five claimed strengths

**Four true, one overstated.** A false strength in a public review is worth
correcting, so each is stated as narrowly as the evidence supports.

**1. Leading bar `Shape = | A | B` closes grammar ambiguity without
backtracking — TRUE, with one word too many.** The rule is real, is implemented
(`parse_decl.zen:284-315` consumes and stores it as `Enum.leading_bar`), is
dispatched on (`parse_lookahead.zen:246-255`), and the grammar records what it
retires: *"This one decision retires FOUR ambiguities from
tests/parse/constructs.md at once: A-ALIAS, A-UNIONDECL, A-ENUMEND, and the enum
half of A-CONSTRUCT"* (`grammar/grammar.js:36-40`). **"Without backtracking" is
true; "without lookahead" — which `DESIGN.md:164` claims — is not.** The
`Name = <thing>` fork is still classified by bounded lookahead
(`parse_lookahead.zen:240-243`, `variant_ahead:293`), and `grammar.js:218-220`
still declares a GLR conflict `[$.enum_variant, $._callee]` for the same fork.
The bar closes the *alias-versus-one-variant-enum* fork specifically, which is
the fork it was designed for. It does not make the declaration parser
lookahead-free.

**2. Trivia stored on AST nodes makes `zen fmt` lossless — TRUE.** Every node
carries `leading` and `trailing` as a `TriviaRun { at, len }` into one flat list
on the arena (`ast_span.zen:36-68`, `ast_arena.zen:220-245`,
`AST_CONTRACT.md:98-106`). Comments are lexer tokens, whitespace deliberately is
not (`lex_token.zen:49-55`). Worth knowing, because it is not what the phrasing
suggests: **the formatter does not currently print declarations from the AST.**
It uses trivia for the material *between* declarations and copies each
declaration's own bytes verbatim from source (`fmt.zen:150-159`,
`fmt_src.zen:96`). Losslessness today is therefore mostly guaranteed by
byte-copying, with the trivia doing the boundary work — which is stronger, not
weaker, but it is a different claim.

**3. `MAX_DEPTH` bounds nesting so recursive descent cannot overflow — TRUE, and
better argued than the review knows.** One declaration (`parser.zen:82`,
`MAX_DEPTH*: usize = 304`), one enforcement point (`enter`, `:632-649`), and a
bound chosen by **bisection against measured segfault depths** for the hungriest
downstream phase, not for the parser (`parser.zen:38-81`: parens ~1,150 levels,
nested calls ~313, nested `.match` ~255). Verified live on this tree: 2,000
parens, 2,000 nested `Vec<>` types and 1,000 nested `Ok(...)` patterns each
produce `nesting too deep`, not a crash. **The scope is narrower than "recursive
descent":** `enter` is called from expression, block, type and pattern entry
only. Declarations, struct members and match arms are uncharged wrappers, and
the binary spine is explicitly unbounded — which the file says out loud
(`parser.zen:77-81`) and `sema_spine.zen` compensates for by walking the spine
iteratively. Confirmed: a 50,000-term `+` chain compiles.

**4. Zero-backtracking parsing with bounded token scans, O(N) — TRUE for
backtracking; "bounded" has one exception.** There is no rewind anywhere in
`src/std/parse/`: the only writes to the cursor are `self.at = self.at + 1` in
`bump` and a forward-only `self.at = stop` in `drain`. `parse_lookahead.zen:24-28`
states the invariant — *"NOTHING HERE MUTATES ... a wrong guess costs a rescan
and never a rewind"* — and the file honours it. The exception is `group_end_at`,
above: not unbounded, but not O(1) on malformed input, which is what makes the
overall claim O(N) only for well-formed files.

**5. `=` (sealed) vs `::=` (rebindable) simplifies parsing and sema — the sigils
are right, the gloss is the wrong axis.** `=` and `::=` are real tokens
(`lex_punct.zen:101-111`). But "sealed vs rebindable" is the **method** reading
only: `DESIGN.md:123-131` gives a four-row table where `= sig` is *required*,
`= sig {..}` *sealed*, `::= sig {..}` *default*, `::= sig` *hook*. On value
bindings the same two sigils mean immutable versus mutable
(`DESIGN.md:117, 252-256`), and the claim omits two further binder sigils
entirely: `:` and `::` on struct fields, where `: T = v` is a **constant on the
type** and `:: T = v` is a field with a default (`DESIGN.md:119`) — the one
place this syntax is genuinely subtle, and the one the review does not mention.
There are eight forms, not two.

---

## Found while auditing — not fixed, reported

Both are "sema admits it, `cc` rejects it", which is the failure mode a
differential oracle over two front ends is structurally blind to.

**1. A declared union used as an ordinary value type does not survive `gen_c`.**
Reproduced on `84b233f2` with `./zen build`:

```groovy
Ea = | Boom
Eb = | Bang
Both = Ea | Eb

main = (env: Env) Res<i32, AllocError> {
    b: Both = Eb.Bang;
    n = b.match({ Ea(x) => 1, Eb(y) => 2 });
    ...
}
```

Sema accepts it; the emitted C is

```c
zu_t2_4main4Both zu_l1b;
zu_l1b = (zu_t2_4main2Eb){ .zg_tag = zu_e3_4main2Eb4Bang };
```

— `error: incompatible types when assigning to type 'zu_t2_4main4Both' from
type 'zu_t2_4main2Eb'`. `gen_c_widen.zen` widens a member into a set for a `Res`
error set, and nothing widens one into a plain declared union. The only union
test in the corpus,
`tests/corpus/sema/match_union_member_carries_its_type.zen`, reaches unions
*only* through `Res<T, E>` propagation, and its own header says so: *"The values
arrive by propagation rather than by writing `Error.Torn(..)` at the call
site."* So the direct form is untested, not merely unlucky. `DESIGN.md` spends
five paragraphs (`:137-164`) specifying declared unions.

**2. `a + b` still takes the left operand's type and never checks the right.**
`DESIGN.md:426-432` already records this and correctly places the decision
upstream in the language rather than in `sema_type.zen`. Confirmed still live
today: `f = (a: i32, b: str) i32 { a + b }` compiles, and the user's first news
of the error is `incompatible type for argument 2 of 'zg_add_i32'`. Noted here
only because a review that scored the type system 9/10 did not mention it, and
it is the most common expression in any language.

**3. Not a bug, but worth saying: `make fmt` is not in `make test`, and there is
no CI.** `PLAN.md:321` requires "`zen fmt --check` over the whole tree, in CI,
failing the build". `Makefile:59` lists `test: parse design cap dupcomments
faults refmap ufcs style grammar-test editors bench-allocs` — no `fmt` — and
there is no `.github/`, no `.gitlab-ci.yml`, no CI configuration of any kind in
the repository. The per-file guard in `fmt.zen` still runs on every invocation,
so losslessness is protected; what is not protected is the tree staying
formatted. The Makefile has diagnosed this exact disease three times in its own
comments (`Makefile:48-58`).
