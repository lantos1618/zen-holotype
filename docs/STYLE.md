# Style

How to write Zen, and how to write about Zen. `DESIGN.md` says what the language is; this says what good code in it looks like.

Most of these are one rule with a test attached. A convention you cannot test is a preference, and preferences lose arguments.

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

**3. The direction test.** `parse` may depend on `std.text`. `std.text` may never depend on `parse`. If moving a helper down a layer would create an upward dependency, you have misjudged what the helper actually is — it is still carrying something specific to the caller. Split it: the general part goes down, the specific part stays.

**An impl goes with the type.** `A.impl(B, {..})` lives in `A`'s module, which imports `B`. This is the direction test applied to impls, and getting it backwards inverts the whole module graph — a trait sits *below* the types that satisfy it, so `std.core.eq` importing `str` is the layering already broken.

**The smell that catches all three:** a file with a `// helpers` section at the bottom. That section is a list of things that belong somewhere else, sorted by the order you needed them.

**Flat namespaces are what makes this cheap.** Modules are `<folder>/<folder>.zen`, names are qualified by path, and two modules may define the same top-level name without colliding. So moving a function between modules costs an import line, and nothing else. There is no reason to hoard.

---

## How files are named and split

**A file is too big when it has two subjects. The line count is how you find out.**

- **Over 500 lines: justify or split.** Not a failure, a prompt — read it and name its subjects out loud. Usually there are two.
- **Over 800 lines: fails the build** — `make cap`, and it is part of `make test`. An exception is a path listed in `scripts/line_cap.py` **with a written reason**; the sentence is the point, because an exception you have to type one for is an exception someone will read, and a silent one is a file that grows forever. (This said `build.zen` for a long time and no such file existed, so nothing enforced it and a file crossed the cap unnoticed. One fact, one place — and the place has to be real.)
- Generated files (`seed/zen.c`) and test corpora are exempt. They are not read.

The cap is a trigger, never the rule. **You always split by subject, never by size.** `gen.zen` and `gen_c.zen` are backend-shared plumbing and the C backend — two subjects. `parse1.zen` and `parse2.zen` are one subject cut in half, which is worse than the file you started with, because now neither name means anything.

**Siblings repeat the folder name as a prefix:**

```
src/parse/parse.zen        // the root: the module's surface
src/parse/parse_expr.zen   // expressions
src/parse/parse_decl.zen   // declarations
src/parse/parse_match.zen  // match arms and patterns

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
// src/parse/parse.zen
parse_expr*, parse_expr_list* = src.parse.parse_expr
parse_decl*                   = src.parse.parse_decl
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

**A `.then` inside a loop is usually a missing loop word.**

```groovy
// no
items.loop((h, v) { v.is_ready().then(() { h.break(v) }) })

// yes
items.find((v) { v.is_ready() })
```

**Guards close with a bare `_`.** Match is always exhaustive, in every position. If you find yourself wanting a partial match, you want `.then`, and it should be visible.

**Early return over a pyramid.** `.try()` exists so that failure does not indent.

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
