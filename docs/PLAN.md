# Implementation plan

Companion to `DESIGN.md`. That file says what the language is and why; this one says what to build, in what order, and how you know a stage is done.

**Read `DESIGN.md` first, and treat its laws section as binding.** `STYLE.md` covers naming, code shape, where a helper belongs, and the house style these documents are written in. `TESTING.md` enumerates the bug classes each phase reliably has, and is written before the phase it tests. When this plan and the design disagree, the design wins — and the disagreement is a bug in this file. When the design is silent, do not invent: the "Still open" section at the end of `DESIGN.md` is the list of things deliberately undecided, and adding to it is better than guessing.

---

## The tree

The whole repository, with the stage each piece appears at. Nothing here is optional — every path is either in the tree or marked NOT WRITTEN, and a marked one is owed rather than optional.

```
zen/
├── README.md                        # what Zen is; how to build from seed
├── Makefile                         # the only entry point a newcomer needs
├── build.zen                        # this project's own build graph; benchmark
│                                    #   budget execution is still owed
│
├── docs/
│   ├── DESIGN.md                    # the language, and why. binding.
│   ├── PLAN.md                      # this file
│   ├── STYLE.md                     # how to write zen, and how to write about it
│   └── TESTING.md                   # bug classes, oracles, and gates. written FIRST.
│
├── grammar/                         # (0.1) written FIRST. its own dir because
│   ├── grammar.js                   #       `tree-sitter generate` writes to ./src/,
│   ├── package.json                 #       which here is the Zen compiler.
│   └── src/parser.c                 #       generated; second generated file in the tree
│
├── seed/
│   └── zen.c                        # (1) the committed generated c. THE artifact.
│                                    #     regenerate, THEN commit. never the reverse.
│
├── src/                             # the real compiler + stdlib, in zen
│   ├── zen/zen.zen                  # (1) thin cli: build / fmt / lsp;
│   │                                #     `zen test` is reserved but still owed
│   ├── zen/zen_cli.zen              # (1) argv -> Cli. touches no capability.
│   ├── zen/zen_build.zen            # (1) the build driver behind `zen build`
│   ├── sema/sema.zen                # (1)
│   ├── sema/sema_type.zen           # (1) type checking, generic instantiation
│   ├── sema/sema_match.zen          # (1) exhaustiveness
│   ├── sema/sema_depth.zen          # (1) the instantiation-depth bound
│   ├── sema/sema_own.zen            # (3) `consume` moves: the flow walk over places
│   ├── sema/sema_recv.zen           # (3) `self :: @Self`: who may write through a name
│   ├── sema/sema_scope.zen          # (3) `@scope` may not escape — all three ways
│                                    #     out. "Which closures escape" is read off
│                                    #     the callee's signature: a closure handed
│                                    #     to a call that also takes an `Alloc` may
│                                    #     be kept. Sendability (`iso` at a behavior
│                                    #     parameter) is stage 5.
│   ├── sema/sema_drop.zen           # (3) a `Drop` value cannot be copied
│   ├── gen/gen.zen                  # (1) backend-shared plumbing
│   ├── gen/gen_name.zen             # (1) the C symbol for everything
│   ├── gen/gen_c/gen_c.zen          # (1) the C backend and its phase modules
│   ├── fmt/fmt.zen                  # (2) parse |> print, plus the guard
│   ├── fmt/fmt_src.zen              # (2) a span, back to the bytes it names
│   ├── fmt/fmt_out.zen              # (2) where the formatted bytes go
│   ├── zen/zen_fmt.zen              # (2) `zen fmt`: read, compare, write —
│   │                                #     models the FILE, not yet the DECLARATION
│   ├── lsp/lsp.zen                  # (4) stdio server over compiler queries;
│   │                                #     the advertised surface is gated in corpus/lsp
│   ├── sema/sema_meta.zen           # (5) supported @meta reads and field walks;
│   │                                #     unsupported forms meet one named wall
│   ├── comptime/comptime.zen        # (5) the step-budgeted evaluator — NOT WRITTEN.
│   │                                #     design_meta.md §5 argues it belongs beside
│   │                                #     sema rather than here: its output is AST,
│   │                                #     and the residue has to be type-checked
│   │
│   └── std/                         # (0.6) the floor. written BEFORE the compiler.
│       ├── std.zen                  #       starred re-exports; the prelude assembles here
│       ├── lex/lex.zen              # (1)   the compiler's lexer, importable as std.lex
│       ├── parse/parse.zen          # (1)   the parser: parse_decl, parse_expr, parse_match
│       │                            #       siblings repeat the folder as a prefix
│       ├── ast/ast.zen              # (1)   THE ast. compiler, @meta and gen_c share it.
│       ├── core/core.zen            #       prelude root
│       ├── core/result.zen          #       Res<T>, Res<T,E>, .try()
│       ├── core/bool.zen            #       then
│       ├── core/loop/loop.zen       #       the loop family, find, filter, map
│       ├── core/drop.zen            #       Drop
│       ├── core/scope.zen           #       Scope / @scope / defer
│       ├── core/eq.zen              #       Eq
│       ├── core/hash.zen            #       Hash, Hasher
│       ├── core/display.zen         #       Display: dump (5), toString (1)
│       ├── core/io.zen              #       Sink, WriteError
│       ├── core/num.zen             #       the checked arithmetic floor
│       ├── core/byte.zen            #       core/path.zen, core/range.zen, core/time.zen
│       ├── mem/mem.zen              #       mem_alloc, mem_arena, mem_ptr
│       ├── env/env.zen              #       Env, Mem, Fs, Console — the capabilities
│       ├── text/text.zen            #       text_str, text_string, text_fmt, text_utf8
│       ├── collections/collections.zen   #  collections_vec, collections_map
│       ├── test/test.zen            #       Tester, Bencher, BenchStats
│       ├── build/build.zen          #       Builder, Package, Budget
│       ├── actor/actor.zen          #       Actor, Context, Ref and errors;
│       │                            #       pthread worker + bounded mailbox floor
│       └── thread/thread.zen        #       Threads, Thread, ThreadError live in
│                                    #       env.zen — a thread is authority, so
│                                    #       it hangs off Env. No file here, and
│                                    #       none owed; the pthread floor is gen_c_threads
│
└── tests/
    ├── parse/                       # (0.1) every DESIGN.md construct, transcribed
    │   ├── constructs.md            #       blind to grammar.js, so a disagreement
    │   │                            #       localises an ambiguity in DESIGN.md
    │   └── errors/                  #       must FAIL to parse
    ├── corpus/                      # (0.4) program + expected stdout + exit code
    │   ├── hello/
    │   ├── traps/                   #       one per trap: overflow, div0, index
    │   └── ...
    ├── must-fail/                   # must be rejected with exact diagnostics
    │   ├── lex/  parse/  sema/      #       by the phase that owes the diagnostic,
    │   ├── modules/  traps/         #       not one flat directory
    │   └── own/                     # (3) use_after_consume, immutable_receiver, send_ref
    └── bench/                       # sanitizer/leak harnesses; Zen benchmark
                                     # budget execution is NOT WRITTEN
```

**A path marked NOT WRITTEN is a promise, not a description.** The paragraph above says nothing here is a placeholder — that is a statement about intent, and this sketch had drifted far enough from the tree to read as a statement about fact. Eight of its paths named files that do not exist and nine more named files under the wrong name, which is worse than listing nothing: a reader checking whether the ownership checker exists found a path for it and stopped looking. Where a stage has not arrived, the marker says so.

Three things about this tree that are decisions, not layout:

- **`src/std/core/` is written before `src/std/lex/`.** The compiler is a Zen program; it needs `Vec`, `Map`, `String`, `Res`, and `Alloc` to exist before its first line. This is stage 0.6 below, and it is the piece most likely to be underestimated.
- **`bootstrap/` and `src/` never shared code.** The bootstrapper was deleted after self-hosting; its remaining Python parser was later deleted with the script cleanup.
- **Two generated files.** `grammar/src/parser.c` is gated by `tree-sitter
  test`. `seed/zen.c` has an atomic regeneration target, corpus coverage, and a
  determinism gate, but its full freshness fixpoint is still owed. If a third
  generated file appears, ask what proves it fresh.

File naming and the 500/800-line review prompts are in `STYLE.md`. The short version, visible above: a folder's root file is its public surface and is nothing but starred re-exports; siblings repeat the folder as a prefix (`std/parse/parse_expr.zen`), so every filename is unique tree-wide and every editor tab says something.

---

## The two rules that prevent drift

**1. Every stage ends at a gate that can fail.** Not "the code is written" — a command that exits non-zero when the stage is wrong. A stage without a red-capable gate is not done, it is unmeasured. Before trusting a new gate, break the thing it guards on purpose and watch it go red.

**2. The compiler is a library from commit one.** `zen build`, `zen fmt`, and
`zen lsp` are thin entry points into one artifact; `zen test` is the same target
shape but remains owed. Never a second parser, AST, or formatter-only path.

---

## Stage 0 — the bootstrapper

**Goal:** a throwaway Python program that compiles one Zen program (the real compiler) to C. It is a developer dependency, never shipped, and it is deleted after stage 1 is self-sustaining.

**Done, and deleted.** Everything below records a completed stage. Old bootstrap coordinates resolve only through git history and are not live tooling.

### 0.1 The grammar

`grammar/grammar.js`, tree-sitter. **This is written before any other code.** It lives in its own directory because `tree-sitter generate` emits to `./src/`, and in this tree `src/` is the compiler. It is the artifact that turns `DESIGN.md`'s examples into things a machine can disagree with, and it outlives the bootstrapper as the editor/LSP grammar.

Every example in `DESIGN.md` becomes a parse test. Expect the grammar to surface ambiguities the prose hides — one is already known:

```groovy
Alias = Shape                  // an alias?
Shape = Circle(Circle)         // or a one-variant enum?
```

Resolve each one *in `DESIGN.md`*, not in the parser. A parser that quietly picks a reading is how a language ends up with no specification.

Constructs the grammar must cover, all present in `DESIGN.md`:

- bindings: `x = e`, `x ::= e`, `x: T = e`, `x: T ::= e`
- struct decl `Name* = { field: T, field :: T, field: T = default, method* = sig {..} }`
- enum decl `Name* = A(T), B(T), C` — no braces, this is the asymmetry to get right
- function decl / lambda `(a: T, b: T) R { .. }`, generic `<T: Bound>`
- function *types* with named params: `(a: i32, b: i32) i32`
- `A.impl(B, {..})` — a call in statement position that declares
- `.match({ pat => expr, .. })`, patterns with payload binding `Ok(n) =>`
- fixed arrays `[i32, 4](2, 3, 5, 7)`, `[u8, 64]` in type position
- generics `Vec<T>`, `Map<K, V>`, error unions `A | B`
- `@Self`, `@meta`, `@scope`
- `consume e`, `e.try()`, `+% -% *%`
- module bindings and re-export: `Res*, Ok* = std.core.result`

**Gate:** `tree-sitter test` green on a corpus containing every **Zen** code block in `DESIGN.md` (the tree listing, the `.gitignore`, and the C source are not Zen), plus an `errors/` directory of things that must *fail* to parse. Both directions matter — a grammar that accepts everything is not a grammar.

### 0.2 Frontend

Python, walking the tree-sitter CST into an AST. **Positions and trivia are attached here or never.** Every node carries `file:line:col`; comments and whitespace attach to nodes rather than being discarded. Retrofitting either is a rewrite, and the formatter and LSP both die without them.

Module resolution: `<folder>/<folder>.zen`, per-module namespaces, `*` as the export gate, re-export as starred import bindings.

### 0.3 Sema

Written as **memoized queries** — `type_of(node)`, `defs_of(name)` — not as monolithic passes. This is the same machinery comptime memoization needs and the same machinery an LSP needs; building it three times is the mistake.

Checks required at stage 0:

- name resolution, module visibility (`*`)
- type checking, generic instantiation (monomorphise; whole-program, so every instantiation is emitted exactly once)
- **exhaustiveness of every `.match`** — this is a load-bearing correctness property, not a lint
- impl completeness: an impl supplies a value for every field the target declares
- impl-supplied fields are computed, read-only, non-addressable
- overload resolution on declared parameter types and arity; a duplicate signature is an error *at the declaration site*, with both declarations named
- `.try()` requires the enclosing function to return a compatible `Res`
- only success lifts into `Res`; `None` never becomes `Err`

### 0.4 `gen_c`

**Deterministic: same input, byte-identical output.** Everything downstream depends on this — the fixpoint test in stage 1 is worthless without it. Sort every map iteration, never emit a pointer value, never emit a timestamp.

Emit traps for the failure model: overflow on `+ - *`, zero divisor on `/ %`, out-of-range fixed-array index. `+% -% *%` compile to wrapping. A trap prints `file:line:col` and aborts.

**Name mangling is settled in `src/gen/gen_name.zen`.** User and generated
symbols have separate prefixes; module/name components are length-prefixed;
site kinds are explicit; and structural type arguments have canonical codes.
The result is a pure function of declarations and types, never traversal order.

**Gate:** a corpus of Zen programs with expected stdout, each compiled and run. Include one program per trap, asserting non-zero exit and the right message.

### 0.5 The seed subset

The compiler remains written in a conservative subset that the committed C
seed can compile. New language features may enter `src/` only after the
compiler that implements them has regenerated `seed/zen.c`; this is the same
landing-order rule `design_meta.md` states for `@meta`.

### 0.6 The standard library floor

The compiler depends on the standard library in layers: core values and
control flow, memory, collections, text, I/O, then higher-level facilities.
Those dependency directions remain live even though the bootstrapper is gone.
The corpus holds allocation, collection growth/collision, text lifetime,
display-through-`Sink`, and arena cleanup behavior.

---

## Stage 1 — self-host

**Goal:** the Zen compiler compiles itself from the committed C seed.

`make build` compiles `seed/zen.c`, emits one C file per module, compiles those
units in parallel, and replaces `./zen` only after the link succeeds. `make
determinism` checks that repeated and permuted emission is byte-identical.

`make seed` regenerates and stages `seed/zen.c` in one target. Regenerate after
source changes, never before them; a stale seed can still build a compiler and
therefore needs the corpus, not only a byte comparison, to expose it.

The retired Python bootstrapper is deliberately absent. Git history is the
recovery path if the committed seed becomes unusable; keeping a second frontend
alive would duplicate every language rule and let the implementations drift.

---

## Stage 2 — formatter

**Do this at self-host, before the tree grows.** Later means a flag day that touches every file.

The formatter is `parse |> print`, over the same parser and the same trivia the compiler uses. It is not a separate tool; it is one entry point plus a printer. If it needs anything the parser throws away, fix the parser.

Rules from `DESIGN.md`: align `=>` in match arms, short arms on one line, wrap long ones, trailing comma on the last arm, preserve comments, never change semantics.

**Gate:** `zen fmt --check` over the whole tree, in CI, failing the build. Plus idempotence — `fmt(fmt(x)) == fmt(x)` on the corpus.

`src/fmt/` owns the current whitespace-only rules: aligned match arrows and
binding operators, multiline parameters, and width-based breaks for calls,
declarations, unions, enums, and arrays. Token-moving match-arm rules remain
owed. `render` re-lexes its output and refuses any token-stream change; corpus
tests hold faithful output and idempotence.

---

## Stage 3 — the ownership checker

**This is the race checker, and it is the type system, not a pass bolted on.** Three features, one checker, one question: *what is this binding allowed to do?*

- `self :: @Self` — the method writes the receiver's own bytes. A handle's methods are `:` even when they change the world (see the bitwise-copy test in `DESIGN.md`).
- `consume` — moves. `Drop` runs exactly once, so a `Drop` value cannot be copied. Use-after-consume is an error.
- `iso` — sending consumes. Only `val` and `iso` cross actors.

**The syntax ships at stage 0 even though nothing checks it.** `self :: @Self` and `consume` cost nothing to parse and ignore. Every line of stdlib written before stage 3 without them has to be revised; written with them, nothing is lost.

Also here: escaping-closure analysis, which by then carries three jobs — an escaping closure needs an `Alloc`, may not use non-local exit, and may not capture `@scope`.

**Gate:** a `must-fail/` corpus. Every program in it compiles today and must stop compiling once the checker lands, each with the expected diagnostic. Write these *before* the checker.

---

## Stage 4 — LSP

Mostly falls out. If sema is memoized queries and every node has a position, the server is thin: hover is `type_of`, go-to-def is `defs_of`, diagnostics are what the compiler already produces, and formatting is stage 2.

If this stage turns out to be expensive, the cause is stage 0.3 — a batch compiler recompiling the world per keystroke — and the fix belongs there.

**"Falls out" is a claim with preconditions, so they are listed and checked as they land.** Discovering at stage 4 that one quietly broke is the expensive version of this stage; checking them while stage 1 is being written is the cheap one.

| precondition | state |
|---|---|
| sema is memoized queries | **holds** — `type_of` / `type_from_ast` memoized on AST ids |
| every node carries a half-open span with a 1-based byte column | **holds** — `AST_CONTRACT.md`, gated by `corpus/parse/parser_spans` and `POSITIONS.md` |
| go-to-def is a query | **holds** — `defs_of` |
| diagnostics are values carrying positions | **holds** — every phase, no exceptions |
| **a cursor position finds its node** | **holds** — `ast_find.zen`'s `node_at` / `expr_node_at`, gated by `corpus/sema_zen/a_cursor_position_finds_its_node` |

That last one was the only primitive an LSP needs that nothing else does, and that is exactly why it was the one absent: every other consumer walks the tree downward from a root, while an editor arrives holding a byte offset and nothing else. It has since landed, and with it **every precondition above holds** — so "mostly falls out" has been tested rather than assumed.

**What has been built against them: `src/lsp/`.** It advertises hover,
definition, document symbols, formatting, completion, code actions, and full
semantic tokens. `tests/corpus/lsp/` is the current executable capability map;
`docs/design_lsp.md` records the ownership and protocol decisions.

**And one precondition that was NOT on this list turned out to gate the whole stage: there was no stdin.** It has since landed — `Env` carries `in: Stdin`, a byte-counted `read` with no line discipline, floored in `src/gen/gen_c/gen_c_stdin.zen` — so **`zen lsp` with no arguments is a real stdio server an editor can launch.** `zen lsp <requests> <replies>` stays because it is what the corpus drives: a test cannot hold a pipe open. `design_lsp.md` §4 records what the capability cost and the one thing it required that nobody had written down — a reader over a blocking `fread` must ask for exactly what the envelope says is missing, or it deadlocks against the client it is answering.

One correctness note that is now load-bearing for this stage as well: `type_of`'s memo key is the node id alone, which is sound only while a generic body is checked once. `src/sema/sema.zen` says it must become `(ExprId, instantiation)` in the same change that makes `T` resolve to an argument. Monomorphisation has since landed, so that key is on the critical path for hover being *correct* inside a generic, not merely fast.

---

## Stage 5 — actors, runtime, `@meta`

Orthogonal to everything above; it constrains nothing in the compiler.

- **`@meta` and the comptime evaluator: `docs/design_meta.md`.** Type-name and
  field-count reads plus field walks have landed; unsupported forms still meet
  the M0 diagnostic wall. The remaining evaluator milestones live there.
- actor and thread runtime slices have landed: one worker and bounded mailbox
  per actor, enqueue-only sends, stop/join, per-actor arenas, and thread
  sleep/spawn/join. Deep sendability, scheduler policy, and full quiescence
  semantics remain stage-5 work.

Compiler use of a new `@meta` form must follow support in the compiler used to
regenerate `seed/zen.c`; otherwise the next clean build cannot compile `src/`.

---

## Continuous, from stage 1 onward

| gate | fails when |
|---|---|
| corpus | any program's stdout or exit code changes |
| fixpoint | **owed**: `stage2.c != stage3.c` (there is no Make target yet) |
| `zen fmt --check` | any file is unformatted |
| `must-fail/` | anything that should be rejected compiles |

---

## What not to build

An optimizer (C is the backend; the C compiler optimizes). A second backend. A package manager beyond the hash-locked `Package` already in `DESIGN.md`. Incremental codegen. Each of these is a trap that consumes a stage and returns nothing until the language is real.

---

## Known-open, do not guess

Listed at the end of `DESIGN.md` and repeated here because an implementer will hit them:

- **`println` resolving `Env` by type** gives `Env` a privileged position in name resolution. It is the one place a law bends for ergonomics. If it becomes load-bearing in a bad way, the fallback is no sugar: `env.out.println(..)`.
- **Supervision.** A trap aborts the process. Killing only the offending actor is the Pony answer and needs a design that does not exist yet.
- **`env.threads.spawn` vs `env.blocking.run`.** If the only legitimate use of a thread is blocking work off the scheduler, the honest capability makes the misuse unrepresentable.
- **Comptime file reads.** Excluded from v1 for reproducibility.
