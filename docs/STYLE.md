# Style

How to write Zen, and how to write about Zen. `DESIGN.md` says what the language is; this says what good code in it looks like.

The grammar, formatter, compiler tests, and line-cap gate enforce the
mechanical rules. The remaining conventions are review guidance.

---

## What checks what

| rule | gate |
|---|---|
| 500-line note, 800-line fail | `make cap` — `tests/gates/line_cap.zen` |
| a line is 80 columns; a list packed past it breaks one item per line; match arms align their `=>`; blank-line and comment placement | `make fmt` — the formatter owns the whole shape of a printed file, so it is the authority and this document does not restate its rules |
| every fault has a raise site | `make faults` |

**The syntax laws are the grammar's, not this document's.** No `if`, no ternary, no `?`, no `as` cast, no `while` — `loop(cond, body)` is the while form — no fourth `@` entry, no adjacent-string concatenation, and every parameter named *and* typed. `DESIGN.md` states them (control flow, line 235; the loop overloads, line 965) and `grammar/grammar.js` cannot express a violation, so `make parse` is where they fail. Each was checked against the real grammar: every one is a parse error. Nothing here repeats them, because two copies of a fact is one stale fact waiting to happen.

**A pipeline reports the wrong exit status.** `make test 2>&1 | tail -40` exits with `tail`'s status, which is 0 whether the build passed or died on the first target — and the error it died on scrolled off the top of the window you kept. This is the cheapest way in the repo to manufacture a green gate, and it costs nothing to avoid: redirect, then read.

```
make test > /tmp/g.log 2>&1; echo "exit $?"; tail -5 /tmp/g.log
```

`;` and not `&&`, so the `echo` runs on failure — which is the run you needed the number for. The same trap inside the build is closed at the top of the `Makefile`: recipes run under `bash -o pipefail`, because `/bin/sh` here is dash and dash has no `pipefail` to set. A gate whose file list arrives through a pipe — `find … | xargs ./zen fmt --check` — otherwise reports the status of `xargs`.

**And a check that scanned nothing must not exit 0.** A moved directory or
empty input set is a harness failure, not a clean result.

---

## Where things live

**The rule: a module contains what is *about* its subject, and nothing else.**

If the parser needs `hex_to_str`, that is not a parser function that happens to live in the parser — it is a string function that the parser noticed was missing. It belongs in `std/text/string.zen`. The parser importing it is correct; the parser *defining* it is the bug.

Three tests, in order of how often you will need them:

**1. The stranger test.** Write the function's one-line doc comment. If you can write it without naming the module it lives in, it does not belong to that module.

```groovy
// "converts a byte to two hex digits"          <- names no module. this is std.text.
// "reads the next token from the source"       <- unwritable without "lexer". stays.
```

**2. The second-caller rule.** The moment a helper acquires a caller in a *different* module, it moves. Not on the third caller, not "when we clean up" — the second one is the signal, and it is unambiguous.

**3. The direction test.** `std.parse` may depend on `std.text`. `std.text` may never depend on `std.parse`. If moving a helper down a layer would create an upward dependency, you have misjudged what the helper actually is — it is still carrying something specific to the caller. Split it: the general part goes down, the specific part stays.

**An impl goes with the type.** `A.impl(B, {..})` lives in `A`'s module, which imports `B`. This is the direction test applied to impls, and getting it backwards inverts the whole module graph — a trait sits *below* the types that satisfy it, so `std.core.eq` importing `str` is the layering already broken.

**The smell that catches all three:** a file with a `// helpers` section at the bottom. That section is a list of things that belong somewhere else, sorted by the order you needed them.

**Flat namespaces are what makes this cheap.** Modules are `<folder>/<folder>.zen`, names are qualified by path, and two modules may define the same top-level name without colliding. So moving a function between modules costs an import line, and nothing else. There is no reason to hoard.

**An import line is a claim about what the file depends on, so every name on it is used.** `A, B, C = some.module.path` binds three names; a name the file never writes again is a dependency it does not have, and the three tests above are read off exactly these lines. A file importing nine names and using two is not a small untidiness — it is eight false edges in the module graph, and the direction test cannot be applied to a graph that overstates. A `*` name is exported onward, which is a use: that is what a folder root is.

---

## How files are named and split

**A file is too big when it has two subjects. The line count is how you find out.**

- **Over 500 lines: justify or split.** Not a failure, a prompt — read it and name its subjects out loud. Usually there are two.
- **Over 800 lines: fails the build** — `make cap`, and it is part of `make test`. An exception is a path listed in `tests/gates/line_cap.zen` **with a written reason**; the sentence is the point, because an exception you have to type one for is an exception someone will read, and a silent one is a file that grows forever. (This said `build.zen` for a long time and no such file existed, so nothing enforced it and a file crossed the cap unnoticed. One fact, one place — and the place has to be real.)
- Generated files (`seed/zen.c`) and test corpora are exempt. They are not read.

The cap is a trigger, never the rule. **You always split by subject, never by size.** `gen.zen` and `gen_c.zen` are backend-shared plumbing and the C backend — two subjects. `parse1.zen` and `parse2.zen` are one subject cut in half, which is worse than the file you started with, because now neither name means anything.

**Siblings repeat the folder name as a prefix:**

```
src/std/parse/parse.zen        // the root: the module's surface
src/std/parse/parse_expr.zen   // expressions
src/std/parse/parse_decl.zen   // declarations
src/std/parse/parse_match.zen  // match arms and patterns

src/gen/gen.zen            // backend-shared plumbing
src/gen/gen_c.zen          // the c backend
```

**The prefix is for names that would otherwise collide — it is not a tax on every file.** `expr`, `decl`, `iter`, `state`, `entry`, `node`, `util` are names three folders will all want, so they take the prefix and `grep -r parse_expr` finds exactly one thing. A name that is already unique and already says what it is does not need it:

```
src/std/core/loop/loop.zen          the root
src/std/core/loop/loop_iter.zen     `iter` alone would collide. prefixed.
src/std/core/loop/cursor.zen        `cursor` is specific. left alone.
src/std/core/loop/range.zen         so is `range`.
```

The question to ask is not "does this repeat the folder?" but **"if I grep this name, do I get one file or three?"** One file, leave it. Three, prefix it. That is the entire purpose: the rule exists so the same subject is never implemented twice under two names, and a prefix applied where nothing would collide buys nothing and costs a longer name.

**A prefix must name the file's own folder. If it names something else, that something is a folder waiting to happen.**

(Files with no prefix are untouched by this — see the naming rule below for when a prefix is wanted at all.)

This is the trigger the prefix rule needs, and it is mechanical:

```
src/std/mem/mem_alloc.zen           prefix mem, folder mem       -> right
src/std/text/text_str.zen           prefix text, folder text     -> right
src/std/collections/collections_vec.zen                          -> right

src/std/core/loop_find.zen          prefix loop, folder core     -> WRONG
src/std/core/loop_iter.zen          three files calling themselves `loop_`
src/std/core/loop_handle.zen        inside a folder called `core`

src/std/core/loop/loop.zen          -> the fix. the family was always a
src/std/core/loop/loop_find.zen        folder; only the folder was missing
src/std/core/loop/loop_iter.zen
src/std/core/loop/loop_handle.zen
```

A prefix family is a subject with a name. The moment it has **two or more** files, it has earned the folder — and once it has one, the module path (`std.core.loop`) says what the code is about instead of where it happened to be dropped. A lone `core/scope.zen` needs no folder; it is one file about one thing, and its name already says so.

Once the folder exists, the folder carries the subject and its files need not all repeat it — see the naming rule below.

The reason this matters beyond tidiness: a folder root is a file of starred re-exports, so a folder is the unit at which a subject controls its own surface. Files sharing a prefix in someone else's folder have no root, which means every consumer imports the individual files and every internal move breaks them.

**Each of those is an ordinary module**, not a nested one — per-module namespacing means `parse_expr` is a sibling of `parse`, and `parse.zen` pulls it into the module's surface with starred bindings:

```groovy
// src/std/parse/parse.zen
parse_expr*, parse_expr_list* = std.parse.parse_expr
parse_decl*                   = std.parse.parse_decl
```

That is why re-export is what makes folders work: the root file *is* the folder's public surface, and it is nothing but a list of what the folder exports.

**Names that mean nothing, and what they actually indicate:**

| name | what it really is |
|---|---|
| `parse_utils.zen` | things that belong in `std` — apply the stranger test |
| `parse_helpers.zen` | same |
| `parse_common.zen` | either `std`, or the module root |
| `parse_misc.zen` | two or three subjects nobody has named yet |
| `parse2.zen` | one subject cut in half |

---

## Signatures

**The signature answers the question.** Someone reading only the first line should know: does this allocate, does it mutate, can it fail, does it escape.

```groovy
add*    = (self :: @Self, value: T) Res<(), AllocError>   // mutates, can fail
len*    = (self: @Self) usize                             // neither
map*<T, U> = (range: Range, alloc: Alloc, body: ..) Res<Vec<U>>   // allocates, and says so
```

- **No `Alloc` parameter, no allocation.** If a function starts allocating, its signature changes. That is the point, not an inconvenience.
- **`::` means it writes the receiver's own bytes.** A handle's methods are `:` even when they change the world. The test: would a bitwise copy of the receiver see the change? If yes, `:`.
- **Every parameter has a name and a type.** In function *types* too — `(a: i32, b: i32) i32`, never `(i32, i32) i32`. Names are documentation, not identity; resolution never sees them.
- **Errors are values.** `Res` for failure a caller can act on. A trap for a bug. Never both for the same thing.

---

## Naming

- **Say what it is, not what it does to you.** `view`, `add`, `grow`, `consume` — not `get_view`, `append_item`, `do_grow`.
- **`add` for one, `add_all` for many.** Not `append`, not `push`, not `insert` unless position is the point.
- **No abbreviations that aren't already words.** `alloc`, `cap`, `len`, `ptr`, `env` are words here. `blk`, `nd`, `tp` are not.
- **Prefix by role, not by type.** `src_line` and `dst_line`, not `line_str` and `line2`.
- **Types are nouns, functions are verbs, predicates read as questions.** `is_empty`, `has_next`, `can_send`.
- **A name that needs a comment is the wrong name.** Rename first, comment second.

---

## Code shape

**Smallest correct change.** Not the smallest diff — the smallest change that is actually correct. Deleting a special case is usually smaller than adding one.

**Method chains over nested calls.** `x.f(a).g(b)` reads left to right; `g(f(x, a), b)` reads inside out. Pick the natural receiver — the thing the operation is *about*.

**And call a free function on its receiver.** A free function whose first parameter is the module's principal type is a method someone declined to write inside the braces; call it as one. This is the rule above applied to the flat statement case, where nothing is nested and reading order is not the argument.

The argument is that the receiver column is the only visible record of an order. `gen_c_fs.zen`'s `lower_write` is eighteen statements and a tail. `be.next_tmp()` is a mutating counter, so the sequence of its consumptions fixes every C temporary the function emits — and of the four it consumes, two happen inside `path_args`, which is to say the order-critical subsequence is not in the source at all. Nothing marks those lines as unmovable. Written on the receiver they mark themselves: the lines that emit are exactly the lines that begin `be.`.

```groovy
// no
declare_temp(be, i32_ty, rc.view()).try();
open_rc_test(be, rc.view()).try();
fs_chain(be, ret, rc.view(), dst.view(), 1).try();
close_else(be).try();

// yes
be.declare_temp(i32_ty, rc.view()).try();
be.open_rc_test(rc.view()).try();
be.fs_chain(ret, rc.view(), dst.view(), 1).try();
be.close_else().try();
```

**Group by operation, and let the order-critical sequence show.** A formatter may never reorder statements, so grouping is the author's and nothing but this rule holds it. Statements that only build values are free to move and may be packed together. Statements that advance mutable state are a sequence, and `lower_write`'s is the whole example: renumber the `next_tmp` calls and the emitted C changes. One blank line between the phase that builds and the phase that emits is the entire tool.

**Alignment needs a contiguous run.** A declaration column interrupted by a statement that declares nothing pads into a column with a hole, which buys a reader nothing. Regroup, and the column appears. Whether to align is the formatter's; whether the lines sit close enough to *be* a column is yours.

**A `.then` inside a loop is usually a missing loop word.**

```groovy
// no
items.loop((h, v) { v.is_ready().then(() { h.break(v) }) })

// yes
items.find((v) { v.is_ready() })
```

**Three `||` on one subject is a membership test.** A run of three or more `||` asking the same subject for equality against literals is one question with a list of answers. `x.is_in([..])` writes it that way — the subject once, the question once, the answers in a row. `is_in` is a prelude name and lives in `std.core.eq`, because membership is equality asked of a list.

```groovy
// no
name.eq("i8") || name.eq("i16") || name.eq("i32") || name.eq("i64")
    || name.eq("int")

// yes
name.is_in(["i8", "i16", "i32", "i64", "int"])
```

A *run*, not the whole expression: `is_c_integer(name) || name.eq("f32") || name.eq("f64")` is a predicate followed by a membership test, and the tail is still one.

Two exclusions, and both are why the rule says *equality against literals* and not *three `||`*:

- **A range is not a list.** `(b >= 'a' && b <= 'z') || (b >= 'A' && b <= 'Z') || b == '_'` (`gen_name.zen`) written out is fifty-three characters, which is worse than what it replaced.
- **Different questions about one subject are not a membership test.** `is_stdin_read(be, rty, name) || is_defer(be, rty, name)` (`gen_c_cap.zen`) shares a subject and asks two things about it.

And one the rule cannot reach yet: **a primitive cannot be the subject.**
`is_in` is bounded on `Eq`, no primitive implements `Eq`, so
`b == ' ' || b == '\t' || b == '\n'` has no writable `is_in` form. Whether
primitives carry trait impls is a language decision, not a formatting rule.

**A trailing comma says "this grouping is mine."** The formatter fills an array literal greedily to 80 columns, so a list of short names lands on one line and the order is the only thing left of what the author meant by it. When the items fall into groups the formatter cannot derive, a comma after the last item pins the layout exactly as written:

```groovy
name.is_in([
    "i8", "i16", "i32", "i64", "int",
    "u8", "u16", "u32", "u64", "usize",
])
```

Signed on one line, unsigned on the next — a fact about the C type system, not about column 80. Drop the comma and the same list packs onto one line with the two families run together.

Use it only where a *semantic* grouping is being recorded. It is not a general escape from the width rule: a list with no grouping in it and a trailing comma is a hand layout frozen forever, which is the thing the join pass was written to end.

The mechanism is a refusal and not a special case, and `src/fmt/fmt_break.zen`'s header states it under REFUSES: the comma sits in the gap between the last item and the `]`, that gap is then not whitespace, and the pass declines the list rather than overwrite a token it did not put there. Read it there before leaning on the edges of this.

**Guards close with a bare `_`.** Match is always exhaustive, in every position. If you find yourself wanting a partial match, you want `.then`, and it should be visible.

**Early return over a pyramid.** `.try()` exists so that failure does not indent. When the early exit carries a value rather than a failure, a one-shot `loop` is the breakable block: each guard is a `.then` whose closure calls `h.break(v)`, and the fall-through `h.break` is the default. Bind the loop to a typed variable before matching on it — a match on the call itself leaves `T` unresolved, which the now-deleted bootstrapper lowered to garbage instead of rejecting.

```groovy
// no
(lead < UTF8_ASCII_MAX).match({
    true  => 1,
    false => (lead < UTF8_LEAD_2_MIN).match({
        true  => 0,
        false => ..      // one level deeper per range
    }),
});

// yes
found: Res<usize> = loop((h) {
    (lead < UTF8_ASCII_MAX).then(() { h.break(1) });
    (lead < UTF8_LEAD_2_MIN).then(() { h.break(0) });
    h.break(2);          // the rest
});
found.match({ Ok(len) => len, None => 0 });
```

**No magic numbers.** `b == ':'`, never `b == 58`. Char literals exist.

**Comment density: low, and about *why*.** The code says what. A comment earns its place when it records a decision, a law, or a trap — "handle is `:` because the arena lives behind it", not "increment the length". If a block needs a paragraph, it probably needs a function with a name.

---

## The `@` namespace

Three entries: `@Self`, `@meta`, `@scope`. **Adding a fourth is a design change, not an implementation detail** — it means the compiler now knows something user code cannot express, and every one of those is a hole in "everything is a value."

Before proposing one, answer: what ordinary binding would have to exist for this not to be needed? If the answer is "none, it is genuinely compiler knowledge", it may qualify. If the answer is "a parameter someone did not want to thread", it does not.

---

## Tests

- **The function name is the test name.** No annotations, no `test_` prefix required by the compiler — `build.zen` finds tests because their single parameter is a `Tester`. Name them as sentences: `vec_grows`, `map_handles_collision`, `arena_frees_everything`.
- **One behaviour per test.** A test that needs "and" in its name is two tests.
- **Every trap gets a corpus program** asserting non-zero exit and the right message. A trap you cannot demonstrate is a trap you have not implemented.
- **Before trusting a new gate, break the thing it guards on purpose and watch it go red.** A gate that cannot fail is worse than no gate: it reads as coverage.
- **`must-fail/` tests are written before the checker that rejects them.** Written after, you only write the tests that already pass.

---

## Writing the documents

`DESIGN.md` and `PLAN.md` have a house style, and it is load-bearing — it is what lets someone (or something) implement from them without re-deciding everything.

**Every decision names the law that forces it.** Not "we chose D because it feels better" — "A is ruled out by the hoisting law, which says failure stays visible." A decision with a reason can be revisited when the reason changes. A decision without one gets re-litigated forever.

**Options are written as code, so they can be compared directly.**

```groovy
// A — a conversion, declared once, applied by .try()
// B — no conversion. you write it, every time
```

**State the cost of what you picked.** Every real decision has one. "Cost to accept knowingly: `@meta` is now the most expensive thing on this page to bootstrap." A document that only lists upsides is a sales pitch.

**Deliberately-undecided goes in "Still open", never into the prose as a hedge.** An implementer needs to know the difference between "this is settled" and "nobody has decided". Adding to that list is always better than guessing.

**One fact, one place.** When `DESIGN.md` and `PLAN.md` both described the file tree, they immediately disagreed. Now the design shows the shape and points at the plan, which is the authority. Two copies of a fact is one stale fact waiting to happen.

**Correct the document, not the parser.** When an ambiguity surfaces during implementation — the grammar cannot tell an alias from a one-variant enum — the fix goes in `DESIGN.md` first. A parser that quietly picks a reading is how a language ends up with no specification.

---

## What the tree owes this document

Measured, once, against all 162 files of `src/`. Every rule above was counted rather than assumed — the interesting result is how few were being broken, which is worth writing down because it is what makes the gate cheap to keep.

**A free function called on its receiver — 1153 sites measured in 40 files.** By a long way the largest debt on this page, and the least like a judgement: every site is a mechanical edit. `src/std/` obeys the rule outright now. `gen_c/`, `sema/`, and `lsp/` still reflect older authoring styles; clean them up by subject, with compiler tests proving the change.

**The count is a floor, not a census.** The rule fires only on a module's *principal type* — the strict-majority first-parameter type declared in the same folder — so three classes of site escape it, all found by the 2026-08-23 spot check: a folder with no principal type at all (`src/fmt/` splits its receivers across `Alloc`/`Src`/`Out`, so the gate can never fire there no matter how the calls are written — some sixty sites a reader would flag); a second receiver in a principal type's shadow (`sema_own.zen`'s nine free functions on `o :: Own`, called function-style nineteen times; `sema_match.zen`'s on `ps :: Pats`, six more); and calls from a module the type is not principal in (`FrameFault`'s facts, from `lsp_stdio.zen`). The ledger cannot record these — `debt()` fails an entry that overstates what the rule finds — so closing them means either widening the rule or applying the dividing rule instead: `find_var`/`kill`/`revive` are facts intrinsic to `Own` and want struct-body methods, which retires the sites rather than re-spelling them.

**An imported name the file never uses — 1208 names, 89 files, 1195 of them gone in the change that wrote the rule.** The largest single thing this document was silent about: nearly a quarter of the 5191 imported names in `src/` named a dependency the file did not have, `gen_c_loop.zen` declaring nine from `std.ast` and using two. Removing them is provably inert — the emitted C is byte-identical modulo the shifted `file, line, col` triples, all 2982 changed lines of it.

**The residue was 13 names, and it is zero.** All 13 were one defect, and it belonged to the Python bootstrapper: **it resolved a method reached through a FIELD by the field's type NAME as the importing file spells it — but only when that method name had a competitor reachable in the same compilation.** `c.types.at(..)` needed nothing; `c.types.write_name(..)` needed `Types`, because `sema_diag.zen:336` declares a *free function* of that name and the bootstrapper picked it. `make build` was blind to every one of them — the self-hosted compiler resolved them all correctly — so the only gates that could see it were the two that compiled `src/` *with* `bootstrap/`, and both are gone. The 13 imports were deleted and the result measured rather than assumed: `make test` 529/0/4, `make fixpoint` green. **`IMPORT_OWED` is now an empty ledger, which is a stricter gate than a stocked one** — the next unused import anywhere in `src/` is a build failure with no allowance to hide behind.

**Abbreviations — 147 sites were measured in 18 files.** `blk`, `tp`, and `tps` remain ordinary naming debt in `gen_c/`, `sema/`, `std/parse/`, and `std/ast/`.

**`.then` inside a `.loop` — 29 of the 141 `.then` calls.** "Usually a missing loop word", and *usually* is load-bearing, which is why this is a list to read and not a gate. Two of the 29 prove why: `std/core/loop/loop_find.zen:45` **is** the definition of `find` and cannot be written any other way, and `lsp/lsp_pos.zen:80` carries a comment arguing the case — "a break would buy a shorter walk and cost the one thing worth having here — a body with a single exit." A gate that reports a decision its author already defended is the gate people switch off. The two clearest genuine finds: `gen_c/gen_c_const.zen:181`, where `pure_args` hand-rolls `.all(..)` with an `every ::=` accumulator, and `sema/sema_def.zen:729`, where `keep_exported` hand-rolls `.filter(..)`.

**`add` for one, `add_all` for many — 18 sites named otherwise, and mostly defensible.** `push_method`, `push_loop`, `push_tvar`, `push_bound` and friends are stack pushes, where position *is* the point and the rule's own exception applies; `insert_ordered` says so in its name. Two are worth a second look: `collections_map.zen`'s `Map.append` — a map has no order, so `add` is the word — and `sema_supply.zen`'s `add_all_members`, where the rule spells the plural `add_all`. Against 78 correct `add*` names, the rule is alive, not dead.

**Rules that are real and at 100%, now guarded so they stay there:** every one of the 130 prefixed files names its own folder; all 18 folders have their root; all 260 imports written by a `std` module import `std`, and none of plain std's reach the compiler sublayer (`std.lex`, `std.parse`, `std.ast`); all 22 impls sit with their type; none of the 3628 functions is a `get_*` or a `do_*`; no file has a `// helpers` section; no comparison in the tree writes an ASCII code where a char literal exists.

**Membership — 10 runs, 6 files, all closed in the change that wrote the rule.** Measured over the tree's 131 `||` chains: ten were one subject asked for equality against three or more literals, the longest `is_c_integer`'s ten, and every one is now `is_in([..])`. Closed rather than written down, because unlike the abbreviations no other lane holds these files open — the whole debt was an afternoon, and a ledger nobody needs is a ledger that outlives its reason.

Reading `==` as well as `.eq` finds four more, and all four compare BYTES: `std/core/byte.zen:49`, `std/lex/lex_byte.zen:33`, `std/json/json_read.zen`, and the punctuation tail of `gen/gen_c/gen_c_fat.zen:797`. They are blocked on `Eq` for primitives, not on anyone's time — which is why the number to watch is 10 and not 14.

**Rules that cannot be checked are left to review.** The stranger test, the second-caller rule, the direction test, natural receivers, comment density, one behavior per test, and the smallest correct change all require judgement.
