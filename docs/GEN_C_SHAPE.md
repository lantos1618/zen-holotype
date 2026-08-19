# `gen/` shape — the parameter-threading campaign

A ledger, not an essay. Every row is one file, one agent, one commit.

---

## The measurement that started it

`src/gen` is 18,625 code lines — the largest subsystem in the tree, and
larger than TinyCC's entire C compiler while emitting *C text* rather than
machine code. Three hypotheses were tested, two were wrong:

| hypothesis | measured | verdict |
|---|---|---|
| comments are exploding | 5,541 comment lines, header essays 7.3% of code | **no** |
| it is hard-coded emitted C | only **6%** of lines contain a string literal at all | **no** |
| parameters are threaded by hand | **3,649 lines — 20% of all code — are one parameter on its own line** | **yes** |

Twelve names are **64%** of those parameter lines (2,325 lines, one in every
eight in `gen/`): `be`(556) `out`(384) `ctx`(374) `id`(211) `c`(189)
`want`(118) `rty`(99) `a`(87) `f`(87) `s`(82) `name`(70) `d`(68).

The same measure elsewhere: `sema/` 11.0%, `fmt/` 10.5%, `lsp/` 7.1%,
`std/` 6.5%. **`gen/` is triple the stdlib.** This is not the language.

**And the parameters are not independent values.** `rty` is derived from
`a.base`; `s = site_of(be, rty)`; `f`/`m` come from `s` + `a.name`. The list
GROWS as you descend a chain, because each link computes one more derived
value and hands the whole accumulated pile to the next. `lower_dot_call`
starts at 7 parameters and `lower_method` ends at 9.

**109 functions have a signature longer than their body** — 850 lines of
signature carrying 399 lines of body.

---

## The two moves

Rust, OCaml and Pony all answer this the same two ways, and neither is "a
struct with nine fields".

### Move 2 — classify, then dispatch  ← **DO THIS FIRST**

A chain of predicates is one classifier returning a sum type, matched once.
`gen_c_member.zen` has a six-link chain — `lower_method` →
`lower_written_method` → `lower_declared_method` → `lower_bound_or_method` →
`lower_floor_or_fat`/`lower_fat_or_method` → `lower_ordinary_method` —
**66 lines of signature carrying 43 lines of body**, every link forwarding
the identical nine values. It becomes one `MethodKind` enum whose variants
carry the derived values, computed once, and one `.match`.

**It goes first because every link is PRIVATE.** 52 of the 59 functions in
`gen_c_member.zen` are unexported. No signature crosses a file boundary, so
this parallelises one-agent-per-file with no merge coupling.

**It is a correctness change, not only a size one.** The precedence order of
the kinds — ptr before capability before door before floor before fat before
ordinary — exists today ONLY as the order of the call chain, explained in
scattered header comments. As one enum it is a readable list, and a new kind
cannot silently land in the wrong slot.

### Move 1 — receiver, not parameter  ← **AFTER Move 2, SERIALISED**

`be`/`ctx`/`out` become one `Lower` receiver: 1,251 parameter lines gone.
`CBackend` already holds `buf :: Emit` ("where a body is lowered") and
`check :: Checker` as fields, and already has `self :: @Self` methods — the
receiver exists, the lowering layer just does not use it. 622 call sites
forward literally `out`, unchanged, so this is safe; leaf emitters that write
into a temp (`ctype(be, v, cty)`, `write_vec_literal`) keep an explicit sink.

**This one changes exported signatures, so it is cross-file and must be one
agent at a time through the fixpoint.** `make build` is blind to
resolution-shaped changes; only fixpoint and the corpus see them.

---

## The gates every row must pass

Non-negotiable, in this order. A row is not done until all four are green.

1. `make test` — **529 passed, 0 failed, 4 deferred**. Any other number is a red.
2. `make fixpoint` — `stage2.c == stage3.c`.
3. **THE FROZEN DIFFERENTIAL — two compilers, one frozen input.** This is
   the gate that makes the campaign safe: a pure reshaping must be a
   byte-identical translator.
   ```sh
   S=/tmp/purity; mkdir -p $S/frozen
   #   ./zen built from the PRE-change tree, copied aside as $S/zen-old
   #   ./zen built from your CHANGED tree,   copied aside as $S/zen-new
   git archive HEAD | tar -x -C $S/frozen        # ONE input both compilers read
   $S/zen-old build $S/frozen/src --emit-c -o $S/old.c
   $S/zen-new build $S/frozen/src --emit-c -o $S/new.c
   cmp $S/old.c $S/new.c        # MUST be byte-identical
   ```
   No `sed`, no erasing of position triples: byte-exact, all 108,020 lines.

   ⚠ **THE OBVIOUS VERSION OF THIS GATE IS ILL-POSED AND THIS DOCUMENT
   SHIPPED IT WRONG.** `./zen build src --emit-c` compiles `src` AS ITS
   INPUT, so reshaping a `src` file necessarily moves the C emitted for that
   file's own functions — before/after over a moving input is not a purity
   test. Lanes 1 and 3 both hit the false red (215 and 409 diff lines) and
   both independently ran the frozen version above and got byte-identical.
   The repo already recorded this lesson under "byte-identical C needs two
   compilers"; it was set up wrong here anyway. **That is the third time.**

   If you see a diff from the ill-posed form, it is expected. Attribute each
   changed line to its enclosing C definition before concluding anything: the
   owners must all be symbols from your own file, plus pure insertions into
   the shared tag `enum {}` for any new enum you introduced.
4. `make fmt` and `python3 scripts/style.py`.

**Do NOT gate on `make build`.** It is blind to every resolution-shaped
defect this tree has ever had; a 1,195-name cull passed `make build` and then
failed fixpoint with 5 diagnostics and the corpus with 16 more.

**Do not regenerate the seed.** The integrator does that once, at the end.

**`scripts/style.py` is the ONE file outside your lane you must touch.** It
holds `UFCS_OWED[<your file>] = <count>`; removing chain links removes free
function call sites, and `debt()` FAILS on a ledger that overstates, so the
number must come down with the code. Every one of the 27 lanes edits this one
dict — the integrator resolves the conflict by RE-MEASURING with
`python3 scripts/style.py`, never by picking a side.

**Do not edit your own row in this table.** 27 lanes editing one table is 27
conflicts. Report `after` and the commit sha; the integrator fills it in.

---

## Phase A — chain collapse, file by file

`before` is the file's total line count at campaign start. `chain fns` is the
count of private functions with ≥5 parameters and a body of ≤6 lines — the
shape being collapsed. `their lines` is what those functions occupy today.

| ☐ | file | before | code | param-lines | chain fns | their lines | after | commit |
|---|---|---:|---:|---:|---:|---:|---:|---|
| ☑ | `gen_c_member.zen` | 1110 | 787 | 87 | 6 | 77 | **1083** | `1d732fc7` |
| ☑ | `gen_c_op.zen` | 816 | 567 | 131 | 7 | 171 | **767** | `9a3c3838` |
| ☑ | `gen_c_expr.zen` | 878 | 597 | 84 | 6 | 118 | **865** | `1f147841` |
| ☐ | `gen_c_call.zen` | 1250 | 869 | 106 | 12+ | ~130 | | |
| ☐ | `gen_c_stmt.zen` | 519 | 378 | 66 | 10 | 112 | | |
| ☐ | `gen_c_flow.zen` | 619 | 475 | 85 | 9 | 100 | | |
| ☐ | `gen_c_try.zen` | 838 | 570 | 104 | 8 | 94 | | |
| ☐ | `gen_c_bound.zen` | 655 | 506 | 78 | 7 | 82 | | |
| ☐ | `gen_c_cap.zen` | 720 | 558 | 65 | 6 | 77 | | |
| ☐ | `gen_c_fat.zen` | 770 | 567 | 57 | 6 | 64 | | |
| ☐ | `gen_c_const.zen` | 261 | 184 | 41 | 5 | 61 | | |
| ☐ | `gen_c_ptr.zen` | 579 | 440 | 43 | 5 | 59 | | |
| ☐ | `gen_c_index.zen` | 248 | 199 | 39 | 4 | 52 | | |
| ☐ | `gen_c_impl.zen` | 395 | 237 | 31 | 4 | 43 | | |
| ☐ | `gen_c_alloc.zen` | 305 | 204 | 38 | 3 | 45 | | |
| ☐ | `gen_c_floor.zen` | 281 | 194 | 49 | 3 | 37 | | |
| ☐ | `gen_c_read.zen` | 627 | 452 | 48 | 3 | 35 | | |
| ☐ | `gen_c_display.zen` | 352 | 259 | 29 | 3 | 35 | | |
| ☐ | `gen_c_layout.zen` | 862 | 689 | 29 | 2 | 27 | | |
| ☐ | `gen_name.zen` | 507 | 301 | 33 | 2 | 22 | | |
| ☐ | `gen_c_mono.zen` | 425 | 247 | 14 | 2 | 20 | | |
| ☐ | `gen_c_fmt.zen` | 315 | 219 | 42 | 1 | 14 | | |
| ☐ | `gen_c_build.zen` | 683 | 504 | 22 | 1 | 14 | | |
| ☐ | `gen_c_sink.zen` | 938 | 659 | 21 | 1 | 13 | | |
| ☐ | `gen_c_range.zen` | 689 | 500 | 53 | 1 | 12 | | |
| ☐ | `gen_c_array.zen` | 325 | 217 | 50 | 1 | 12 | | |
| ☐ | `gen_c_settle.zen` | 622 | 463 | 17 | 1 | 9 | | |

**`gen_c_member.zen` and `gen_c_call.zen` carry `+` because the counter that
built this table miscounts them** — it balances braces and a `{` inside a
string literal (`be.fmt("if (..) {\n")`) throws it off. Their chains were
read by hand instead. Trust the file, not the number.

**Phase A total: ~113 functions, ~1,328 lines, over 27 files.**

### What the first two rows actually yielded, and the correction it forces

`gen_c_member.zen` 1110 → 1083 (**−27**, −2.4%). `gen_c_expr.zen` 878 → 865
(**−13**, −1.5%), with its parameter lines 84 → 63.

`gen_c_op.zen` 816 → 767 (**−49**, −6.0%), parameter lines 131 → 95.

**That is far less than the 2,000–2,500 lines this campaign was pitched at,
and the pitch was wrong, not the work.** The enum, the classifier and the
preserved reasoning cost most of what the deleted signatures save. Extrapolated
over 27 files, Phase A is worth **roughly 500 lines, not 2,000.**

**So Phase A's value is not size — it is that the precedence becomes
readable.** `gen_c_member.zen`'s six method kinds, whose order was previously
recoverable only by following a call chain through six files' worth of header
comments, are now one commented list above one enum. `gen_c_expr.zen` did the
same for four conversion doors and for the type-authority precedence. That is
worth having; it is not a line-count win, and this document should not have
claimed otherwise.

**The lines are in Phase B.** `be`/`ctx`/`out` are 1,251 parameter lines and
they do not come back as anything.

### What the chains were HIDING, which is the better argument for Phase A

`gen_c_op.zen`'s lane found three things that a line count does not show and
that were invisible for as long as the chain existed:

- **Two parameters threaded and never read.** `node: Expr` into
  `lower_logical` and `prim: str` into `lower_compare` — each computed by a
  caller and carried one or two frames to nothing. The threading habit does
  not only cost verbosity, it costs dead work, and a chain hides it because
  no single link looks wrong.
- **The same precedence written a THIRD time.** `infix_shaped` and
  `helper_shaped` in the spine walk restated the operator precedence the
  chain already encoded. Proven equivalent case by case, `helper_shaped`
  deleted; the list now exists once in the tree. A duplicated rule is a rule
  that can drift, and nothing was comparing the two copies.
- **A predicate that already existed.** `literal_or` was
  `is_literal_ty(lhs)==false && is_unknown(lhs)==false`, which is exactly the
  neighbouring `usable(be, lhs)`.

So Phase A's real return is: the precedence stated once, in one readable
list, with the dead parameters and duplicate predicates that were hiding
behind it removed. Budget it as a correctness pass that happens to shrink
files, never as a line-count campaign.

### A better shape than the one the first lanes produced

Both lanes turned the chain into a NESTED `.match` staircase — seven deep in
`gen_c_member.zen`, four in `gen_c_expr.zen`. That is fewer lines than the
chain but it is still a pyramid, and `STYLE.md` already names the fix:

> **Early return over a pyramid.** [..] When the early exit carries a value
> rather than a failure, a one-shot `loop` is the breakable block: each guard
> is a `.then` whose closure calls `h.break(v)`, and the fall-through
> `h.break` is the default. Bind the loop to a typed variable before matching
> on it.

A classifier written that way is a FLAT list of guards, one line each, in
precedence order — which is exactly what a classifier should look like. The
idiom is live in the tree (`parser.zen`, `parse_lookahead.zen`,
`collections_map.zen`, `zen_cli.zen`, `fmt.zen`). **Later lanes should write
the classifier as a breakable block, and the first two rows are owed a
follow-up pass.**

---

## Phase B — the `Lower` receiver

Not started. Blocked on Phase A landing, because the two moves touch the same
signatures and doing them together makes every conflict a three-way one.

---

## Phase C — the rule that stops it coming back

A `style.py` rule: a signature with **≥6 parameters** is a violation,
ledgered by file with a count like `UFCS_OWED`, so it can shrink and cannot
grow. Without this the campaign is a one-off and the shape returns.
