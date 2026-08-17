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

---

## 2. Gap one — there is no way to write a literal `{}`

`text_fmt.zen:14` states the cost rather than hiding it: *"THERE IS NO WAY TO
WRITE A LITERAL `{}`. `"{}"` is always a hole."* It is a deferred decision, not a
considered no.

**It is cheap to close.** Adopt the conventional `{{` → `{`, `}}` → `}`.

    grep -rn '{{' src --include='*.zen'      # 3 hits, ALL comments
    grep -rn '{{' tests --include='*.zen'    # 2 hits

The three `src/` hits are prose — `parse_stmt.zen:92` and `parser.zen:154`
illustrating parser nesting, and `text_fmt.zen:15` documenting the absence.
**Zero format strings in the tree change meaning.**

**One trap, and it is the plausible-wrong-answer class.** Ten string literals in
the LSP contain `}}` — JSON closers such as `"]}}"` and
`",\"full\":true}},\"serverInfo\":.."` in `lsp_reply.zen` and `lsp_diag.zen`.
They are safe *today* because they are `add_bytes` calls, which write bytes and
read no format meaning. The moment those sites become `fmt` calls, `"}}"`
silently becomes `}` — malformed JSON, no diagnostic. **The escape and the LSP
conversion must be sequenced deliberately**, or the conversion must escape them
in the same commit.

**Cost:** `text_fmt.fmt_next`, `bootstrap/gen_c.py:4558`'s own copy of the walk,
and a `DESIGN.md` sentence. Two implementations must agree, because a must-fail
expectation is read by both compilers.

---

## 3. Gap two — `{name}`, and why it is the interesting one

Repetition is the symptom:

    be.fmt("zg_scope {};\n{}.zg_n = 0;\n", name.view(), name.view())
    be.fmt("zg_scope {name};\n{name}.zg_n = 0;\n")               // wanted

**This is a compile-time feature, not a runtime one.** The compiler already steps
the format string at the call site, so a `{name}` hole is resolved by looking
`name` up in scope exactly as any other identifier is typed, emitting the same
writer call a positional hole would. No allocation, no runtime scan, no boxing.

It also composes with §2 — both are decisions inside the same twenty-line
parser.

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

**`...` is already a type syntactically.** `Variadic` is a `TypeKind` variant
(`ast_node.zen:107`) and sema types it as `c.types.prim("...")`
(`sema_type.zen:106`). But it is a **marker, not a description**: it says a
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

**The floor door (§1) does not have this bug** — it is sound by construction, not
by relabelling. Do not copy `write_failure_arm`'s pattern into new doors.

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
  corrupts output. The floor door currently **refuses every non-`str` hole**
  (`a format hole on this door that is not a str`), so these sites will not
  compile rather than misbehave. A `{c}` hole is the eventual fix and is a
  grammar change, i.e. §2's decision.
- **Embedded newlines and indentation.** `Emit.fresh` is set true in exactly one
  place (`gen_emit.zen:69`, inside `line()`), so a `\n` pushed through as bytes
  would drop indentation on every subsequent line. Fixed at the sink: `Emit.bytes`
  now ends a line on `\n`. For a `String` sink a `\n` is correctly just a byte —
  only `Emit` has indentation to re-arm.

**Sequencing.** The escape and `{name}` land first, in the parser and both
backends, with the LSP's ten `}}` literals handled in the same change. The
`add`/`fmt` collapse decides the final spelling. Only then do the conversion
lanes fan out — six units with no shared files, since two agents in one file read
each other's edits as their own bugs. `@meta`-driven dispatch is Stage 5 and
independent of all of it.
