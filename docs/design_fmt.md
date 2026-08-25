# The format language — what it is, what it is missing, and where `@meta` meets it

Written 2026-08-17, after the format door landed. Everything below is measured
against the tree at that date; the counts are reproducible with the commands in
each section.

`DESIGN.md` owns the format language's rules. This document owns the *gaps* in
them, the sequencing to close those gaps, and one open fork that is a semantic
decision rather than an implementation choice.

---

## 1. What exists today

**The grammar, in full** (`src/std/text/text_fmt.zen:5-23`): `{}` is a hole,
`{` not followed by `}` is a literal brace, `}` is always a literal byte. No
width, no precision, no index, no name. The parser is two functions — `hole_at`
and `fmt_next`, about twenty lines.

**A hole is expanded where it is written, not walked at runtime.** The compiler
steps `fmt_next` over the format string at the call site and emits one literal
write per run plus one writer call per hole. There is no runtime format state and
no allocation. `make bench-allocs` gates that.

**A hole's writer is found, not hard-coded.** `gen_c_sink.zen:24` — *"`add_i64` /
`add_u64` / `add_bool` are FOUND, not written here — ordinary Zen functions."* A
hole on a primitive resolves to one of those three; a hole on anything else goes
through the type's own `toString`. So dispatch is already type-directed, and the
writers are already library code. What `gen_c` hard-codes is only the *choice* —
about fifteen lines (`gen_c_sink.zen:710-727`).

**Three doors, and the newest one is the general mechanism.**

| door | declared in | answers |
|---|---|---|
| `alloc.String(fmt, ..)` | `text_string.zen` | `Res<String, AllocError>` |
| `<sink>.add(fmt, ..)` | `text_string.zen:37` | `Res<(), WriteError>` |
| `<recv>.fmt(fmt, ..)` | `text_string.zen:44`, `gen_c_state.zen:396` | the receiver's floor error |

The third writes through **the receiver's own concrete byte writer** —
`add_bytes`, else `write` — and is *required to answer exactly what the door
declares*. `String.fmt` → `String.add_bytes` → `AllocError`; `CBackend.fmt` →
`CBackend.write` → `AllocError`. A type whose only writer is a `Sink` impl
returning `WriteError` is **refused by name**, never relabelled. That answer test
is what makes it sound rather than hopeful.

This matters because a `Sink`-typed receiver cannot narrow: `Sink.write` is a
trait slot fixed at `WriteError`. The floor door sidesteps the slot rather than
lying about it.

**Except for a hole that is not a `str`** — closed 2026-08-24 (#755). The floor
has no `add_bytes` for a number, so a wider hole was refused outright: the same
format string wrote `n=7` through `alloc.String(..)` and was a diagnostic through
`buf.fmt(..)`. It now goes through a `Sink` record over *the same receiver*, with
`gen_c_sink.value_call` picking the writer exactly as it does for the sink door,
and a failing wider write reported as `OutOfMemory` — §6's bargain, now shared by
two doors. A receiver that is **not** a `Sink` still gets the refusal by name,
because a record over one has a NULL `write` slot. Nothing else moved: a `str`
hole and every literal run still go straight through the floor and still carry
their own `Err`, and the emitted C for an existing floor-door site is unchanged
byte for byte.

Why it WAS the keystone — closed 2026-08-25 (#755, fixed by d9c02c14d): the
refusal used to be why nothing in `src/` implemented `Display`. Measured
2026-08-25: `src/` held 0 impls and repo-wide 25 (tests/corpus mostly), with
402 hand-rolled `add_bytes` runs in `src/`, 375 sites taking an
`out :: String` param, and only 7 real `:: Sink` params. The door is open:
the first impl under `src/` is `Pos.impl(Display, ..)` in
`src/std/ast/ast_span.zen`, whose seven hand-rolled renderings across sema,
gen, parse and the driver are `{}` holes now. What remains of the ~400 runs
is a campaign to finish one type family at a time, not a blockade; the
pattern is the Pos impl and its call sites, and the recount above is the
number to beat when quoting debt — do not re-quote this paragraph's old
0 / 591 / 378 figures as today's.

---

## 2. Gap one — CLOSED 2026-08-17: `{{` writes `{`

`text_fmt.zen` used to state the cost rather than hide it: *"THERE IS NO WAY TO
WRITE A LITERAL `{}`."* It was a deferred decision, not a considered no, and it
is now closed with the conventional doubling: **`{{` writes `{`, `}}` writes
`}`, so `{{}}` writes `{}`.** `DESIGN.md`'s "The format language, in full"
paragraph is the rule's home; `text_fmt.zen`'s header is the parser's.

**The two rules at one position cannot collide,** which is what makes the
grammar decidable without lookahead or backtracking: `{{` is not `{}`, so which
is tested first cannot change what a format means. The walk is left to right and
never backs up, which settles the only two shapes that read either way — `{}}`
is a hole then a literal `}`, and `{{}` is a literal `{` then a literal `}`.
Both are pinned by `tests/corpus/std/a_doubled_brace_writes_one`.

**How it is implemented, in one sentence, because it is the reason it cost
nothing:** a doubled brace ends the literal run **on the first brace of the
pair** and resumes past the second, so the run stays a *slice* of the format
string and the emitted C still copies it verbatim — no decoded copy, no second
escape table. Four walks carry it: `text_fmt.fmt_next` (the reference),
`gen_c_print.is_doubled_brace` (shared by `println` and every sink door), and
`bootstrap/gen_c.py`'s `fmt_pieces`. The bootstrapper's `println` used to keep
its own `split(b"{}")`, which agreed only while the language had a single rule;
it now goes through `fmt_pieces`, so there is one implementation of two rules
rather than two of them.

**Compatibility, measured:** `grep -rn '{{' src --include='*.zen'` is 3 hits and
all three are prose — `parse_stmt.zen:92` and `parser.zen:154` illustrating
parser nesting, and `text_fmt.zen` documenting the absence. **Zero format
strings in the tree changed meaning**, and both compilers agree at
512 passed / 0 failed / 4 deferred.

### The trap, and why it is guarded rather than commented

**A byte writer reads no format meaning.** So `add_bytes("]}}")` writes two
braces and `add("]}}")` writes one — not a wart of the escape but what
"expanded at the call site" means. That makes **converting a byte writer into a
format call a silent change of output wherever the bytes hold a doubled brace**,
which is the plausible-wrong-answer class: no diagnostic, no crash, malformed
JSON.

Escaping those literals *now* would be wrong — they are `add_bytes` calls, so
`"}}}}"` would immediately write four braces. Commenting ~100 sites would be a
guard a conversion lane can walk past. So the question asked instead was
**whether anything would notice**, and it was answered by mutation rather than by
reading: each of the six `}}` literals in `src/lsp/` was replaced with a single
`}`, one at a time, and the LSP corpus re-run.

| site | corpus tests reddened |
|---|---|
| `lsp_reply.zen:86` (`failed`) | 4 |
| `lsp_reply.zen:106` (`parse_error`) | 1 |
| `lsp_reply.zen:155` (`write_hover`) | 5 |
| `lsp_reply.zen:192` (`write_capabilities`) | 9 |
| `lsp_diag.zen:412` | 7 |
| `lsp_def.zen:477` | 3 |

Every site is pinned; none is silent. The `.expected` files hold the exact reply
bytes, `}}` included, so a conversion lane that changed them would go red on the
same run that made the change. **The rule a conversion lane owes** is therefore
narrow and stated in `text_fmt.zen`'s header: a lane converting bytes that are
*not* under a corpus expectation owes the escape at that site. The corpus in
`tests/corpus/lsp/` holds ~100 further `}}` literals and is self-guarding for
the same reason.

---

## 3. Gap two — CLOSED 2026-08-17: `{name}` reads the scope

Repetition was the symptom:

    be.fmt("zg_scope {};\n{}.zg_n = 0;\n", name.view(), name.view())
    be.fmt("zg_scope {name};\n{name}.zg_n = 0;\n")               // now legal

**It is a compile-time feature and nothing about it is runtime.** The compiler
already steps the format at the call site, so the walk reaches `{name}`, looks
`name` up in the frame it is standing in exactly as it resolves a bare
identifier, and emits the write a positional hole would have emitted. Proved by
reading the emitted C rather than asserted — `println("{name} is {n}")` becomes

    zg_print_str((zu_l4name));
    zg_print_bytes(" is ", 4u);
    zg_print_i64((int64_t)(zu_l1n));

three calls, no allocation, no format state, no scan. `make bench-allocs` is
unchanged to the digit.

### The three decisions, and what each one buys

**Positional and named holes mix freely, and a named hole consumes no
positional argument.** `add("{a} of {}", n)` passes the one argument its one
positional hole wants. Counting a named hole would make that call claim two, and
the arity diagnostic would then be a lie about which of the two spellings was
wrong. `gen_c_print.arguments_taken` and the bootstrapper's `holes` sum are the
one place this is decided in each compiler.

**A name not in scope is `codegen cannot resolve \`total\`` at the hole's own
column** — not "wrong argument count", which is silent about which of the two
things is wrong. The column is exact rather than approximate because **a string
literal cannot span source lines** (a raw newline inside one is
`LexFault.UnterminatedString`), so a byte offset into the literal's raw text
*is* a column offset. Both compilers compute it that way —
`gen_c_print.report_in_format` and `bootstrap/gen_c.py`'s `fmt_span` — and
`must-fail/codegen/format_hole_names_nothing` holds them to the same answer,
since a must-fail expectation names the position and is read by whichever
compiler ran.

**A name is the identifier grammar, and `{p.x}` / `{f()}` are REFUSED.** A hole
is not an expression language: a field read or a call would give a format string
a second parser with its own precedence and diagnostics, bought for nothing. The
rule that makes the refusal statable instead of a special case is that **a `{`
followed by an identifier character always meant a hole** — so a near miss
cannot fall back to printing itself, which is the wrong answer nobody reads
twice, since `{p.x}` appearing verbatim in the output looks like the author's own
text. `{{p.x}` is the fix, and §2's escape is why the refusal costs nothing.

*Measured before adopting it, because it widens what a `{` can mean:* across
every `.zen` file in the tree, **four** string literals contain a `{` followed by
an identifier character, and **none is in a format position** — `"a{b}c"` and
`"<.. {k:null}..>"` are arguments, and two are the new tests' own `{{ok}}` /
`{{f}}`. Note what the last two show: a doubled brace is classified *before* a
name is looked for, so `{{name}}` is a `{`, the bytes `name`, and a `}`. The
identifier grammar itself is `std.core.byte`'s `is_ident_start` /
`is_ident_cont`, not a second spelling of it.

### One walk, four readers, and the reference parser made honest

The classification lives in **one** function per compiler —
`gen_c_print.fmt_at`, returning a `FmtAt` that carries `keep` (where the run
before it ends) and `next` (where the walk resumes), and `fmt_pieces` in the
bootstrapper. `println` and every sink door read it, so they cannot drift on what
a position means; what each still owns is only *where the bytes go*.

The bootstrapper's walk moved from the decoded bytes to the **raw source text**
for the diagnostic's sake: an offset into decoded bytes is not a column. That is
the one structural change on that side, and it makes the two walks the same
shape as well as the same rules.

**`text_fmt.fmt_next` had no caller, and a reference implementation nobody runs
is prose.** Both backends expand at the call site and never step it, so `{name}`
could have been added to both while the reference still read `{n}` as literal
bytes and every test would have stayed green — the gate-that-cannot-fail shape.
It now carries `name` and `bad`, and
`tests/corpus/std/the_reference_format_parser_runs` prints every step of nine
inputs, the same shapes the backend tests pin. Its `FmtStep.hole` no longer
implies "last step": a doubled brace ends a run without being a hole, so **the
walk is spent when `next == f.len`.**

### Why the runtime shape does not work

A sketched alternative was a runtime `fmt(a: Alloc, s: String, eles: [T])` that
scans for `{`, collects positions into a `Vec`, and dispatches per element on
type info. Three reasons it cannot be the compile-time door, worst first:

1. **`[T]` cannot hold format arguments.** An array is homogeneous. `fmt("{} {}",
   "str", 42)` is heterogeneous. Putting mixed types in one runtime list requires
   boxing — fat pointers, an allocation, every writer reached through a vtable.
   That cost is exactly what compile-time expansion exists to avoid. *This is the
   fundamental objection; the other two are consequences.*
2. **It moves the walk to runtime** — a `Vec` allocation and a string scan per
   call, in the C backend's hottest path. `make bench-allocs` would go red.
3. Smaller: there is no `if` (match-only law), `[T]` is not a type at all (array
   types are `[element, length]`; a generic sequence is `R: Range<T>`), and
   `loop` does not return an accumulator.

**A genuinely runtime `fmt` is still a legitimate want** — a format string read
from a config file cannot be expanded at compile time. That is a *separate*
function taking the boxed path deliberately, and it must not disturb the door.

---

## 4. Gap three — `String.add` and `String.fmt` are the same door twice

    add* = (self :: @Self, fmt: str, args: ...) Res<(), WriteError>   // :37
    fmt* = (self :: @Self, fmt: str, args: ...) Res<(), AllocError>   // :44

Identical signatures, differing only in error set. Redundant now that the floor
mechanism *derives* the error from the receiver, so one name can serve both:
concrete `String` → `AllocError`, generic `out :: Sink` → `WriteError`.

**Cost to collapse: 15 call sites** (`grep -rn '\.add("' src --include='*.zen'`).

Naming, since `fmt` is overloaded three ways in this tree — `src/fmt/` is the
*source* formatter behind `./zen fmt`, `text_fmt.zen` is the format-string
machinery, and `.fmt()` is now a method. Choosing `add` as the single door name
leaves `fmt` meaning only "formatter". The counter-argument is that one mechanism
with two spellings (`String.add`, `CBackend.fmt`) is its own inconsistency.

**`fmt` cannot be folded into `write`.** `write` must stay a plain byte writer,
because `gen_c_print.zen:219` emits `zg_print_bytes("{}", 2);` — the compiler
emitting code *about* a stray hole — which would be inexpressible if `write`
read format meaning. Two sites in `src/gen` + `src/lsp` contain a literal `{}`;
65 contain a bare `{`, already literal by the grammar.

---

## 5. Where `@meta` meets this

`@meta` is designed, not speculative: `DESIGN.md:453` ("Comptime and `@meta`"),
`PLAN.md:367` (Stage 5), and it is **already lexed and parsed** — `AtMeta`
(`lex_token.zen:123`), `parse_expr.zen:541-547`. Its spelling is `@meta(n)` and
`@meta(self: @Self)`, returning the **compiler's own `std.ast` nodes** — one AST,
three consumers — not a parallel `typeinfo` universe. `@` is a closed namespace:
exactly `@Self`, `@meta`, `@scope`; a fourth is a design change (`DESIGN.md:111`).

It is deliberately deferred. `PLAN.md:220-222`: `@meta` is outside the seed
subset, and *"`@meta` alone would roughly double"* what the bootstrapper must
implement. Stage 5 also carries the step-budgeted comptime evaluator, without
which `@meta` cannot run.

**What `@meta` buys the format language, stated honestly: it replaces the fifteen
lines of writer-name picking, not the mechanism.** Dispatch is already
type-directed and the writers are already ordinary Zen functions; `@meta` moves
the *choice* out of `gen_c` and into Zen, so the door stops being compiler magic
and becomes library code. That is a real architectural win — it is not what
delivers `{name}`.

**What `@meta` genuinely unblocks** is elsewhere and already written down as
waiting on it: `Display.dump`'s field-wise walk (`display.zen:28-34`), the `Eq`
and `Hash` defaults (`hash.zen:31`), `Env`'s typed-args schema fill
(`env.zen:153`), and `build.zen`'s real nodes (`build.zen:30-34`).

### Varargs as a type — the same feature from the other side

**SUPERSEDED THE SAME DAY, and the pricing below is what was wrong.**
`docs/design_vararg.md` owns this subject now: `vararg<T>` landed as an
**ordinary declared struct** (a borrowed run of `T` and its length, packed at
the call site as a C compound literal), which is neither of the two paths priced
below. It is forwardable, it needs no tuple, no boxing and no comptime
evaluator, and it does not touch the `...` doors — they coexist, because a
homogeneous pack cannot type a heterogeneous format call. The paragraphs below
are kept as the record of what was believed before the code existed; the
sentence they got wrong is that a runtime-representable pack must be structural.

**`...` is already a type syntactically.** `Variadic` is a `TypeKind` variant
(`ast_node.zen:107`) and sema types it as `c.types.prim("...")`
(`sema_denote.zen:84`). But it is a **marker, not a description**: it says a
parameter is variadic and carries nothing about the pack's element types or
arity. Six uses in the whole tree.

That is exactly why forwarding fails. A plain function that takes `args: ...` and
passes them on reports `codegen cannot spell the type` — there is no C type for
`"..."`, because there is no information to spell. Verified 2026-08-17.

Making it a real type means describing a heterogeneous sequence, `(str, i32,
bool)`. Two coherent paths:

- **(a) A runtime-representable pack** — a tuple or anonymous struct. Buys
  forwarding and a genuine runtime `fmt`. Costs a *structural* type in a language
  whose declared types stay nominal (`PLAN.md:371`), and then either
  monomorphising every consumer per pack shape or boxing every element behind a
  vtable. `DESIGN.md` has no `Tuple`; tuples were considered and rejected.
- **(b) A comptime-only pack** — exists during monomorphisation, erased before
  codegen: forwardable and iterable, with no C representation. Zig's `anytype`.
  **This is what Stage 5 already promises.**

**(b) is the answer, and it is what makes the runtime sketch in §3 writable after
all** — as comptime code rather than runtime code:

    fmt = (out :: S, f: str, args: ...) Res<(), E> {
        @meta(args).loop((h, arg) { .. })   // unrolled per call site
    }

No boxing, no tuple, no runtime scan. The loop is unrolled at each call site,
which is what the compiler does by hand today — so `fmt` stops being compiler
magic and becomes library code, and §5's fifteen lines of writer-picking move into
Zen. `typeinfo`-style dispatch and varargs-as-a-type are the same Stage 5 feature
seen from two sides; both wait on the step-budgeted comptime evaluator.

---

## 6. Open fork — the allocating door mislabels every failure

`gen_c_fmt.zen:294` (`write_failure_arm`) assigns `OutOfMemory` unconditionally.
Its comment is the false premise: *"the only thing that can go wrong writing into
a String this door just made is that it couldn't GROW."* True of the buffer, but
a `{}` hole runs **user** code.

Verified: a `Display` whose `toString` returns `Err(WriteError.IoError(IoError.Closed))`,
formatted through `alloc.String("x{}", v)`, comes back as an `AllocError` — whose
only variant is `OutOfMemory`. **A closed pipe is reported as out of memory.**

Three options, none obviously right:

- **(a) widen the door to `Res<String, WriteError>`.** Honest. But there is no
  `From`, so the 112 corpus mains returning `AllocError` that call it cannot
  narrow — they must match. Large cascade.
- **(b) carry the `AllocError` arm across, trap on the `IoError` arm.** One
  branch, failing path only. The argument: `toString` is handed its sink, and
  here that sink is a `String`, which *cannot* produce `IoError` — so one
  appearing is the user's `Display` inventing it, i.e. a program error.
- **(c) document and leave.** The lie stays.

**The floor door (§1) had the bug only by not compiling.** Since #755 it shares
the bargain, on exactly one path: a hole that is not a `str`. Everything else it
writes still carries its own `Err`, so the fork's blast radius on that door is a
wider hole whose `Display` invents an `IoError`, and not every failure. Two doors
now wait on one decision instead of one door waiting alone — which is an argument
for settling it, not for copying `write_failure_arm` a third time.

Worth stating precisely, because it is easy to over-read: `AllocError` has
exactly ONE variant, so on the arm that actually occurs — the buffer failing to
grow — "carry the error across" and "name `OutOfMemory`" build the *same value*.
The lie is only ever on the `IoError` arm, which for a `String` sink can come
from nowhere but a user's `toString`.

This fork also gates a separate cleanup: collapsing consecutive `add_bytes` runs
would **double this bug's blast radius**, from doors that own their buffer to
doors handed one. Fix the fork first.

---

## 7. The conversion this all serves

`src/gen` and `src/lsp` emit text one fragment at a time, because they predate
the format machinery. Measured 2026-08-17: **352 calls collapse across 172 runs**
— 31% of all 1,115 emit calls in the two directories. 163 runs / 321 calls are
purely mechanical; 9 runs / 31 calls need judgement.

The judgement cases are worth naming, because they are traps:

- **`add_byte` writing a character** — 5 runs, and 21 further sites outside runs.
  `{}` on a `u8` prints a **number**, so a mechanical conversion silently
  corrupts output. **This trap is now live.** The floor door used to refuse every
  non-`str` hole (`a format hole on this door that is not a str`) and those sites
  would not compile; since #755 a `u8` hole compiles and writes a number. A `{c}`
  hole is the fix and is a grammar change, i.e. §2's decision — until it lands,
  a conversion lane owes `add_byte` at every one of those 26 sites, and the
  refusal is no longer the thing that catches it.
- **Embedded newlines and indentation.** `Emit.fresh` is set true in exactly one
  place (`gen_emit.zen:69`, inside `line()`), so a `\n` pushed through as bytes
  would drop indentation on every subsequent line. Fixed at the sink: `Emit.bytes`
  now ends a line on `\n`. For a `String` sink a `\n` is correctly just a byte —
  only `Emit` has indentation to re-arm.

**Sequencing.** The escape and `{name}` have landed (§2, §3), in the reference
parser and both backends, with the LSP's `}}` literals proved pinned by mutation
rather than commented. **What a conversion lane owes now is two lines, not a
list:** escape a doubled brace in any bytes it converts that are *not* under a
corpus expectation, and read `text_fmt.zen`'s header for the grammar rather than
this file. A lane will also find `{p.x}` refused where it was previously literal
— loudly, at the hole's column, with `{{p.x}` as the fix; the tree contains zero
such sites today.

`{c}`-style holes are still owed and are what the `add_byte` judgement cases in
this section need — a `u8` hole printing a *number* is the trap named above.
`{name}` did not open that door: a hole holds an identifier, and a format spec is
a separate grammar decision.

The `add`/`fmt` collapse (§4) decides the final spelling. Only then do the
conversion lanes fan out — six units with no shared files, since two agents in
one file read each other's edits as their own bugs. `@meta`-driven dispatch is
Stage 5 and independent of all of it.
