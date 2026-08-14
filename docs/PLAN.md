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
├── build.zen                        # this project's own build file — NOT WRITTEN,
│                                    #   and it is what `make bench` would stand on
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
├── bootstrap/                       # (0) python. throwaway. never shipped.
│   ├── bootstrap.py                 #     cli: bootstrap.py src/ -o out.c
│   ├── cst.py                       #     tree-sitter parse -> raw tree
│   ├── ast.py                       #     -> ast nodes, positions + trivia attached
│   ├── modules.py                   #     <folder>/<folder>.zen resolution, * gate
│   ├── sema.py                      #     memoized queries: type_of, defs_of
│   └── gen_c.py                     #     deterministic c emission
│
├── seed/
│   └── zen.c                        # (1) the committed generated c. THE artifact.
│                                    #     regenerate, THEN commit. never the reverse.
│
├── src/                             # the real compiler + stdlib, in zen
│   ├── zen/zen.zen                  # (1) thin cli: build / fmt / test / lsp
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
│   ├── gen/gen_c/gen_c.zen          # (1) the c backend: a folder, ~35 files
│   ├── fmt/fmt.zen                  # (2) parse |> print, plus the guard
│   ├── fmt/fmt_src.zen              # (2) a span, back to the bytes it names
│   ├── fmt/fmt_out.zen              # (2) where the formatted bytes go
│   ├── zen/zen_fmt.zen              # (2) `zen fmt`: read, compare, write —
│   │                                #     models the FILE, not yet the DECLARATION
│   ├── lsp/lsp.zen                  # (4) thin server over sema queries — PARTLY:
│   │                                #     transport, lifecycle, Full sync, hover,
│   │                                #     diagnostics, lexical semanticTokens.
│   │                                #     Everything else refused by name; the stdio
│   │                                #     transport, over std.env.Stdin
│   ├── meta/meta.zen                # (5) @meta over ast nodes — NOT WRITTEN
│   ├── comptime/comptime.zen        # (5) the step-budgeted evaluator — NOT WRITTEN
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
│       ├── actor/actor.zen          #       (5) Actor, Context, Ref — NOT WRITTEN
│       └── thread/thread.zen        #       (5) Threads, Thread — NOT WRITTEN
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
    ├── must-fail/                   # compiles today, must STOP compiling.
    │   ├── lex/  parse/  sema/      #       by the phase that owes the diagnostic,
    │   ├── modules/  traps/         #       not one flat directory
    │   └── own/                     # (3) use_after_consume, immutable_receiver, send_ref
    └── bench/                       # (1) Bencher functions; budgets in build.zen
```

**A path marked NOT WRITTEN is a promise, not a description.** The paragraph above says nothing here is a placeholder — that is a statement about intent, and this sketch had drifted far enough from the tree to read as a statement about fact. Eight of its paths named files that do not exist and nine more named files under the wrong name, which is worse than listing nothing: a reader checking whether the ownership checker exists found a path for it and stopped looking. Where a stage has not arrived, the marker says so.

Three things about this tree that are decisions, not layout:

- **`src/std/core/` is written before `src/std/lex/`.** The compiler is a Zen program; it needs `Vec`, `Map`, `String`, `Res`, and `Alloc` to exist before its first line. This is stage 0.6 below, and it is the piece most likely to be underestimated.
- **`bootstrap/` and `src/` never share code.** Two implementations of the same language, deliberately, with the fixpoint test as the referee. Any "shared helper" between them is the beginning of the drift this plan exists to prevent.
- **Two generated files, both with a gate.** `seed/zen.c` is proven fresh by the fixpoint; `grammar/src/parser.c` by `tree-sitter test`. If a third ever appears, ask what proves it fresh — an ungated generated file is a fork nobody is reading.

File naming and the 500/800-line split rule are in `STYLE.md`. The short version, visible above: a folder's root file is its public surface and is nothing but starred re-exports; siblings repeat the folder as a prefix (`std/parse/parse_expr.zen`), so every filename is unique tree-wide and every editor tab says something.

---

## The two rules that prevent drift

**1. Every stage ends at a gate that can fail.** Not "the code is written" — a command that exits non-zero when the stage is wrong. A stage without a red-capable gate is not done, it is unmeasured. Before trusting a new gate, break the thing it guards on purpose and watch it go red.

**2. The compiler is a library from commit one.** `zen build`, `zen fmt`, `zen lsp`, `zen test` are thin entry points into one artifact. Never a second parser, never a second AST, never a "just for the formatter" path. Two grammars is the failure this plan exists to avoid.

---

## Stage 0 — the bootstrapper

**Goal:** a throwaway Python program that compiles one Zen program (the real compiler) to C. It is a developer dependency, never shipped, and it is deleted after stage 1 is self-sustaining.

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

**Name mangling is unspecified and has to be decided here.** C has one flat namespace; Zen lets two modules define the same top-level name. Joining path components with `_` is *provably* ambiguous, and `STYLE.md`'s own sibling-prefix convention (`std/parse/parse_expr`) triggers it in the compiler's own tree. Decide, in this order:

1. **The scheme** — length-prefixed (Itanium-style), a separator no Zen identifier can contain, or escaping (`_` doubles). Not naive joining.
2. **A reserved prefix** for compiler-generated names (temporaries, trap helpers, monomorphised instances, closure records, the comptime-derived actor message enums), unreachable by any mangled user name. The trap: `__zen_` and `_Zen_` are themselves reserved to the C implementation by C11 §7.1.3, and bare `zen_` collides with a user writing `zen_trap`.
3. **Which sites mangle** — locals, parameters, **struct members**, enum constants, function names, struct tags, labels, instantiation names. Members are the one always missed, and the one standard-header macros break (`x.errno`).
4. **Which reserved list** — handle the reserved *identifier class* (`_Uppercase`, leading `__`) rather than a hand-maintained keyword list, which subsumes every future `_Atomic` for free. State which C standard `gen_c` targets.
5. **How type arguments render** in an instantiation name, including nesting, as a pure function of the type rather than of instantiation order — otherwise determinism dies here.

**Gate:** a corpus of Zen programs with expected stdout, each compiled and run. Include one program per trap, asserting non-zero exit and the right message.

### 0.5 The seed subset

The bootstrapper must implement every feature the compiler itself uses — so the compiler is written in a deliberately smaller language than the one it implements.

**In the seed subset** (the compiler may use these):

structs, enums with payloads, generics, functions, lambdas, non-escaping closures, `.match`, `bool.then`, `Res` + `.try()`, the `loop` family, `str`, `Vec`, `Map`, `String`, modules + `*` + re-export, `A.impl(B, ..)`, `@Self`, overloading, `Alloc` threading, traps.

**Not in the seed subset** (user code gets these; the compiler adopts them only after self-hosting):

`@meta` in any form, comptime type-returning functions, actors, threads, `@scope` / `defer`, `iso` and sendability, error *unions* (the seed uses one nominal error enum per function — `Res<T, CompileError>`).

Every item on the second list is a feature the Python bootstrapper would otherwise have to implement. `@meta` alone would roughly double it.

### 0.6 The standard library floor

**The most underestimated stage.** The compiler is a Zen program: before its first line runs it needs `Res`, `.try()`, `Vec`, `Map`, `String`, `str`, `Alloc`, `Drop`, and the `loop` family. All of it written in the seed subset, all of it compiled by Python, all of it debugged with no debugger and no LSP.

Order matters, because each layer needs the one below:

1. `core/result.zen`, `core/bool.zen` — `Res`, `.try()`, `then`. No allocation, no dependencies.
2. `core/num.zen` — the extremes and width of every primitive numeric type, and the checked arithmetic floor. Depends on nothing but the trap.
3. `mem/mem.zen` — `Alloc`, `AllocError`, the arena. Everything above allocates through this.
4. `collections/vec.zen` — `Vec<T>`. The first real generic, and the first `Drop` user.
5. `text/string.zen` — `str` (bytes, borrowed), `String` (`Vec<u8>`, owned).
6. `core/loop.zen` — the `loop` family, `find`, `filter`, `map`. Inlined at the call site; only `map`/`filter` take an `Alloc`.
7. `collections/map.zen` — needs `Eq` + `Hash`, so those come with it.
8. `core/io.zen` — `Sink`, `WriteError`. Below `display`, whose signatures name both.
9. `core/display.zen` — `toString` only, writing into the caller's `Sink`. `dump` is `@meta` and waits for stage 5.

**Gate:** each of these has tests in `tests/corpus/` that the bootstrapper compiles and runs. `Vec` growing across a realloc, `Map` colliding on hash, a `String` outliving the loop that built it, an arena freeing everything at once.

Two traps to expect here, both consequences of laws in `DESIGN.md`:

- **The `Alloc` receiver.** `Vec.alloc` is a `:` field and `grow` calls `realloc` through it, which only compiles because a handle's methods are `:`. If the stdlib is written with `Alloc.raw` as `:: @Self`, every collection needs a mutable allocator field and the shallowness buys nothing. Get this right in `mem/mem.zen` first, or fix it everywhere later.
- **`Drop` before the checker exists.** Stage 3 is where use-after-consume becomes an error. Until then the arena's exactly-once guarantee is a convention the stdlib must honour by hand — which is precisely why the `consume` *syntax* ships at stage 0 even unchecked.

**The `Sink` migration has landed, and it moved as one change.** `DESIGN.md` types `Display.toString` on a `Sink` so that printing allocates nothing; `src/std/core/display.zen`, the sink dispatch in `gen_c` (`gen_c_sink.zen`), and the `display_*` corpus signatures moved together — migrating the corpus first would have turned three green tests red against a compiler with no `Sink`, and migrating `std` first the same. The one mistake that migration ordering cannot see is pinned instead: `tests/must-fail/sema/display_sink_overload_is_not_the_allocating_one` rejects a resolver that stops at arity and hands back the sealed allocating form's `Res<String, WriteError>` where the call meant the sink.

**Gate for stage 0:** the bootstrapper compiles and runs hello-world, the std corpus, and the trap corpus. Nothing about the real compiler yet.

---

## Stage 1 — self-host

**Goal:** the Zen compiler, written in Zen's seed subset, compiling itself.

Layout, per `DESIGN.md`:

```
src/zen/zen.zen      // thin CLI: build / fmt / test / lsp
src/zen/zen_build.zen // the build logic
src/std/ast/ast.zen  // THE ast — @meta, DumpAst and gen_c all consume these nodes
src/std/lex/lex.zen
src/std/parse/parse.zen
src/sema/sema.zen
src/gen/gen.zen
src/gen/gen_c/gen_c.zen
```

`src/std/ast/ast.zen` is the keystone. One AST with three consumers — the compiler, `@meta`, and `gen_c` — and `@meta` returning these exact node types is what makes stage 5's metaprogramming free rather than a parallel universe.

Order: lexer → parser → sema → gen_c, each with its own tests, in one pass. Do not build a second frontend to "get started faster."

**The gate, and it is the strongest one in this plan:**

```
bootstrap.py  src/*.zen  ->  stage1.c  ->  cc  ->  zen-1
zen-1         src/*.zen  ->  stage2.c  ->  cc  ->  zen-2
zen-2         src/*.zen  ->  stage3.c

assert stage2.c == stage3.c        # byte-identical: the fixpoint
```

A compiler that reproduces its own output byte-for-byte is almost certainly correct about an enormous surface. This costs one script and catches more than any test suite you would write by hand.

**Then: commit `stage2.c` as the seed.** Regenerate first, commit second — and make that impossible to get backwards by putting it in one target:

```make
seed:                    # regenerate THEN stage; never two separate commands
	./zen build src/ -o seed/zen.c
	git add seed/zen.c

build:                   # what a newcomer runs. only needs a c compiler.
	cc -O2 seed/zen.c -o zen
	./zen build src/ -o zen-new && mv zen-new zen

fixpoint:                # the gate
	./scripts/fixpoint.sh
```

Commit-then-regenerate ships a seed one change stale, and only a full feature test catches it — never `cmp`. This is a mistake that gets made twice if the two steps are ever two commands.

**Retiring the bootstrapper: not yet.** The instinct is to delete it the moment the fixpoint is green, and that is one stage too early — until stage 2's format gate is running and seed regeneration is routine, the Python implementation is the only thing that can rebuild the world if the seed goes bad. Delete it at the end of stage 2, and delete it properly: out of the tree, into git history, with no CI job keeping it alive. A second implementation that still builds is a second implementation that drifts.

---

## Stage 2 — formatter

**Do this at self-host, before the tree grows.** Later means a flag day that touches every file.

The formatter is `parse |> print`, over the same parser and the same trivia the compiler uses. It is not a separate tool; it is one entry point plus a printer. If it needs anything the parser throws away, fix the parser.

Rules from `DESIGN.md`: align `=>` in match arms, short arms on one line, wrap long ones, trailing comma on the last arm, preserve comments, never change semantics.

**Gate:** `zen fmt --check` over the whole tree, in CI, failing the build. Plus idempotence — `fmt(fmt(x)) == fmt(x)` on the corpus.

**What landed, and what it deliberately does not do.** `src/fmt/` prints the FILE: declarations in source order, each comment at the column it was written in, a run of blank lines collapsed to one, the whitespace behind a declaration gone, exactly one newline at the end. Every declaration's own text is then copied byte for byte with ONE exception, and the exception is the first of the match-arm rules above: `fmt_decl.zen` sets the width of the run of spaces in front of an arm's `=>`, so a list of arms lines up on its arrows. It went first because it is the only one of the four that moves no token — the other three move one or add one, and each of those needs an argument the guard below does not already supply. It refuses an arm that shares its line with another, one whose pattern and `=>` are not on one line, and one with a comment where the pad would go; `tests/corpus/fmt/arms_line_up_on_their_arrows` is those refusals, plus a `=>` inside a string literal and a commented-out arm. Applied to the tree it moved 371 lines in 39 files, because 92% of the arms were already written this way.

**A formatting rule cannot leave the emitted C byte-identical, and should not.** The obvious gate for "changes no semantics" is: format the tree, rebuild, `cmp` the C. Run against arrow alignment it reports 8 differing lines, and all 8 are the column in a `"file.zen", line, col` trap triple whose expression moved sideways. That is the gate passing, not failing: the C embeds source positions, so a rule that moved a token and left those columns alone would be a rule that made every trap message point at the wrong place. The gate to run is `cmp` **after erasing the `file:line:col` triples from both**, plus the reading that every surviving difference is a column that moved exactly as far as its token did. Line numbers must not move at all, and under a rule that only changes the width of a gap they cannot.

**The guard is what makes shipping a subset safe.** Whitespace is not a token and a comment is one, so formatting must leave the token stream identical — same count, same kind, same bytes. `render` re-lexes its own output and checks exactly that before returning it; a file that fails is left untouched and the build goes red. Every rule added to the printer later is checked by the same three lines, which is why the next form can be added one at a time instead of all at once. It caught its first bug within a minute of existing: a trailing comment belongs to the outermost node whose span ends before it, which for a multi-line enum is the last VARIANT and not the declaration, so a slice cut to `Decl.span` dropped the sentence in eight files.

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

**What has been built against them: `src/lsp/`, and it is L1 of `docs/design_lsp.md` plus one query.** `initialize`, `shutdown`, Full document sync and `textDocument/hover` — the last one being `expr_node_at` into `expr_memo` into `Types.name_of`, with no new sema — and every other method refused by name with `-32601`. Gated by `corpus/lsp/`, three tests: the UTF-16/byte position conversion driven both ways, a JSON round trip with its rejections, and a recorded frame-by-frame session.

**And one precondition that was NOT on this list turned out to gate the whole stage: there was no stdin.** It has since landed — `Env` carries `in: Stdin`, a byte-counted `read` with no line discipline, floored in `src/gen/gen_c/gen_c_stdin.zen` — so **`zen lsp` with no arguments is a real stdio server an editor can launch.** `zen lsp <requests> <replies>` stays because it is what the corpus drives: a test cannot hold a pipe open. `design_lsp.md` §4 records what the capability cost and the one thing it required that nobody had written down — a reader over a blocking `fread` must ask for exactly what the envelope says is missing, or it deadlocks against the client it is answering.

One correctness note that is now load-bearing for this stage as well: `type_of`'s memo key is the node id alone, which is sound only while a generic body is checked once. `src/sema/sema.zen` says it must become `(ExprId, instantiation)` in the same change that makes `T` resolve to an argument. Monomorphisation has since landed, so that key is on the critical path for hover being *correct* inside a generic, not merely fast.

---

## Stage 5 — actors, runtime, `@meta`

Orthogonal to everything above; it constrains nothing in the compiler.

- `@meta` over `src/std/ast/ast.zen` nodes: builds and reads, memoized on (function, arguments), declared types stay nominal
- the comptime evaluator: language minus io and actors, may allocate, **step-budgeted so a bad `@meta` fails the build rather than hanging**, no file reads in v1
- actors: per-actor arena rooted in the runtime (not `main`'s), one message at a time, causal ordering, quiescence exit
- `main` returning is not the program exiting

Only after this does the compiler start using `@meta` on itself.

---

## Continuous, from stage 1 onward

| gate | fails when |
|---|---|
| corpus | any program's stdout or exit code changes |
| fixpoint | `stage2.c != stage3.c` |
| `zen fmt --check` | any file is unformatted |
| `must-fail/` | anything that should be rejected compiles |
| `allocs_op` / `bytes_op` budgets | **hard fail** — deterministic, so a regression is real |
| `ns_op`, build wall clock | sustained shift past a rolling median — reported, not flaky-fatal |

Benches take a `Bencher` and are discovered by `build.zen` walking the parsed module tree, the same way tests are. Because all allocation goes through `Alloc`, alloc counting is free.

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
