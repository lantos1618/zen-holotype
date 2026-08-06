# Testing

Written before the compiler, not after. Everything here is a bug class that compilers reliably have — so the tests exist first and the code is written to pass them.

Companion to `PLAN.md`, which says which stage each gate arrives at.

---

## The oracles, strongest first

**1. Fixpoint.** `zen-1` and `zen-2` emit byte-identical C for the same source. A compiler reproducing its own output is almost certainly correct across an enormous surface, and it costs one script. Requires `gen_c` to be deterministic — see the determinism section, which is a test in its own right.

**2. Differential, bootstrap vs self-hosted.** During stage 1 there are *two* independent implementations of Zen, and this is the only moment in the project's life when that is true. Run every corpus program through both toolchains and compare stdout and exit code. Any disagreement is a bug in one of them, and you get told *which program* exposes it. Do not skip this because the bootstrapper is "throwaway" — it is the most valuable it will ever be right before it is deleted.

**3. Corpus.** Program in, expected stdout and exit code out. Cheap, and the thing that catches regressions in behaviour rather than in structure.

**4. `must-fail`.** Programs that must be rejected, each with the expected diagnostic *and its position*. A rejection with the wrong span is a failure.

**5. Mutation.** Periodically: mutate the compiler (flip a comparison, drop a case, change a constant), rebuild, and assert some test goes red. A gate that survives mutation is not guarding anything. This is how you find out that a scanner fails open, and it is the only way to find out.

---

## The test file format

One format, so ten authors produce one suite. The runner reads only this.

```
tests/corpus/<area>/<name>.zen         the program
tests/corpus/<area>/<name>.expected    exact stdout, compared byte for byte
tests/corpus/<area>/<name>.exit        expected exit code; omit the file when it is 0
tests/corpus/<area>/<name>.stderr      expected stderr substring; omit when none

tests/must-fail/<area>/<name>.zen      must be rejected
tests/must-fail/<area>/<name>.expected the diagnostic, see below
```

A test needing several source files is a **directory** of the same name, holding its module tree plus `.expected` / `.exit` / `.stderr` at the directory root. Module trees inside it follow `<folder>/<folder>.zen`, and the entry point is `main.zen`.

**`.expected` in `must-fail` is line one, then one position per line after it:**

```
is not exported by module
main.zen:5:7
```

Line 1 is a **substring** of the message — loose enough to survive rewording, tight enough to catch the wrong error being reported. Every line after it is a position that must appear in the diagnostic, as `path:line:col` with the path relative to the test root. Several lines means the diagnostic must name several places, which `DESIGN.md` requires in at least two cases: an impl collision names both impls, and a duplicate signature names both declarations.

Positions are 1-based line, 1-based **byte** column, and point at the first byte of the smallest offending node.

**A single-file test may write `line:col` and omit the path**, which resolves against the test's entry file. Four suites reached for this independently before it was allowed, which is the tell that the long form was asking for something nobody wanted to write. A right-line/wrong-file match is still a failure.

**A test is compiled against the whole of `src/`, not just `src/std`.** From stage 1 the compiler's own modules — `lex`, `ast`, `parse`, `gen` — are siblings of `std` under one root, so staging only the prelude would mean no corpus test could ever import one and each subsystem would invent a private harness instead. The staged root *is* the compilation root, so `src/lex/lex.zen` is imported as `lex.lex`, exactly as `src/std/core/core.zen` is `std.core`.

**A test's compilation root is its own directory.** Every asserted path is relative to that, and so is every path the compiler emits — which is what makes the determinism check comparing two copies of a tree at different absolute paths meaningful.

**A directory test names its expectation `main.expected`**, matching the `main.zen` it already requires, and visible to `ls` in a way a dotfile is not. `.exit`, `.stderr`, `.count` and `.stage` follow the same rule.

**`.count` bounds the number of diagnostics.** Extra diagnostics are otherwise always allowed — one file legitimately produces two — so "a single syntax error must not cascade into fifty" is inexpressible without it. Only write one where the count is the property under test.

**`.stage` names the stage a test's feature arrives at**, and the tree is graded against the number in `STAGE` at the repo root. A test written for stage 5 cannot pass at stage 3, and leaving it red is not free: people learn to read past red, which does the same damage from the other direction as a gate that cannot fail. So it is reported as *deferred* and counted separately.

**A deferred test still runs.** Skipping it would make `.stage` a second gate that cannot fail — the day the feature landed, nothing would notice, and the file would sit there asserting a stage the project had left behind. Both outcomes carry information:

| outcome | verdict |
|---|---|
| it fails | deferred. Expected, on the record, not counted as a failure. |
| **it passes** | **a failure** — "delete the `.stage` file, the stage arrived". |

Write one only when the test is genuinely waiting on a stage, never to quiet a test you have not diagnosed. The difference is that a deferred test names *what* it is waiting for, and the harness tells you when the wait is over.

A `must-fail` test may also carry `.exit` and `.stderr`. An area directory may carry prose — a `README.md`, or a table of exact spans like `corpus/parse/POSITIONS.md`; the runner ignores it. Deeper than area level it is not prose beside the tests but a file inside one, where it lands in a module tree.

**Assumptions the whole corpus rests on**, stated here so no test has to restate them: `Ok(0)` from `main` exits 0; `println` appends exactly one `\n`; `{}` on an integer prints decimal with no separators; stdout is compared byte-exactly including the trailing newline.

---

## Bug classes, by phase

Each of these has produced real bugs in real compilers. Write the test when you write the phase.

### Lexer

- EOF in the middle of everything: string, comment, escape, number, identifier
- unterminated string; unterminated block comment; **nested block comments** (decide, then test)
- `'a'` char literals, escapes, `'\''`, `'\\'`, and a `'` with nothing after it
- numeric edges: `0`, leading zeros, a literal larger than its type, `i32.MIN` written as a literal (`-2147483648` is unary minus applied to a too-large positive — the classic)
- CRLF vs LF, tabs, trailing whitespace, no trailing newline, a BOM
- a 10MB single-line file; a file of only comments; an empty file

### Parser

- precedence and associativity, one test per operator pair, including `+%` against `+`
- **deep nesting** — 10,000 nested parens or blocks. A recursive-descent parser stack-overflows and this is a crash, not a diagnostic. Decide the depth limit and emit an error at it.
- **position accuracy**: for a sample of nodes, assert the exact `line:col` span. Off-by-one here is invisible until the LSP is unusable.
- **trivia attachment**: a comment before a declaration, after it, inside a match arm, between arms, at EOF. Each must survive `parse |> print`.
- the known ambiguities: `Alias = Shape` vs a one-variant enum; `A.impl(B, {..})` as a declaration in statement position; `[i32, 4](2, 3)` as type-applied-to-arguments
- error recovery: one syntax error must not cascade into fifty

### Modules

- import cycle; self-import; diamond re-export (`a` and `b` both re-export `c`)
- **the `*` gate**: an unexported name must be invisible outside its module. Test it directly — `grow` and `Entry` from `DESIGN.md` are the named cases. A leak here is silent.
- two modules defining the same top-level name, both imported, both used
- a re-export chain three deep
- shadowing: a local binding with the same name as an import

### Sema

- **infinite monomorphisation**: `f<T> = (x: T) { f<Vec<T>>(..) }`. Must terminate with an error, not consume all memory. Every monomorphising compiler has hit this.
- recursive types: `Node = { next: Ptr<Node> }` works; `Node = { next: Node }` must be rejected, not loop
- exhaustiveness with nested patterns, and with `_` in every position
- unreachable arms (an arm after `_`)
- impl collision resolved by the bound in scope; and the no-bound case, which must error naming both
- a bound not satisfied; a bound satisfied by an impl in another module
- inference order: `Res<Cfg, _>` inferred from a body containing a call whose own error set is inferred
- generic instantiation with a type from a third module (the `Vec<Circle>` case — whole-program compilation exists to make this work)

### Ownership (stage 3)

The interesting cases are all about control flow, not straight-line code:

- consumed in one match arm and not the other, then used after the match
- consumed inside a loop body (the second iteration uses a dead binding)
- consumed, then used only on a path that never executes — must still be an error, this is flow-sensitive not path-sensitive
- `consume` of a field; of an element; of something behind a handle
- drop order: reverse declaration order, and `@scope` defers run **before** drops
- partially-moved value going out of scope
- an escaping closure capturing a consumed binding
- a `ref` reaching a behavior parameter (must be rejected — only `val`/`iso` cross actors)

### Codegen

- **C keyword collisions.** A Zen identifier named `int`, `while`, `static`, `register`, `restrict`, `typedef`. Mangling must handle every C reserved word, and the test is the full list.
- identifier collisions after mangling: `foo_bar` and `foo::bar` mangling to the same symbol
- forward-declaration ordering for mutually recursive types and functions
- struct-return ABI; zero-field struct; struct larger than a register
- a literal at the exact type boundary; `u64` literals that do not fit `long`
- deeply nested expressions producing deeply nested C (some C compilers have their own limits)

### Traps

One corpus program each, asserting non-zero exit and the right message with position:

- `i32.MAX + 1`, `i32.MIN - 1`, `i32.MIN * -1`
- `x / 0`, `x % 0`
- **`i32.MIN / -1`** — this is *overflow*, not division by zero, and on x86 it faults the same way. `DESIGN.md` only names the zero divisor. It must trap, and the message must say overflow.
- fixed-array index at `len`, at `len + 1`, at a runtime-computed out-of-range value
- and the wrapping forms must *not* trap: `i32.MAX +% 1`

**Codegen note that is really a correctness requirement:** signed overflow is undefined behaviour in C, so `gen_c` cannot emit `a + b` and check afterwards — the check has to happen before, or via compiler builtins (`__builtin_add_overflow`). Emitting the naive form and hoping means the C optimizer deletes the check.

### Formatter (stage 2)

- **idempotence**: `fmt(fmt(x)) == fmt(x)` over the whole corpus
- **semantic invariance**: `parse(fmt(x))` and `parse(x)` produce the same AST, ignoring positions
- comment preservation: no comment is lost, reordered, or reattached to a different node
- a file that is already formatted is byte-identical after formatting

---

## Determinism is a test, not an assumption

The fixpoint oracle is worthless if `gen_c` is nondeterministic, and nondeterminism is invisible until it wastes a day. Test it directly:

- compile the same input twice in one process — byte-identical
- compile in two processes — byte-identical
- compile with a shuffled input file order — byte-identical

The usual sources, all of which must be designed out rather than found later: iterating a hash map without sorting, embedding a pointer value or address in a name, embedding a timestamp or path, relying on filesystem enumeration order, and any use of a random or time-seeded value.

---

## Diagnostics are tested like output

A compiler is mostly a diagnostics engine that occasionally emits code. Every `must-fail` test asserts three things:

1. it fails
2. **the message** — matched loosely enough to survive rewording, tightly enough to catch the wrong error being reported
3. **the position** — `file:line:col`, exact

The third is the one everyone skips and the one that decays fastest. A correct diagnostic pointing at the wrong token is what makes a language feel unfinished.

---

## Performance is a test

**`tests/determinism/check.sh` cannot run against the self-hosted compiler.** It invokes `zen build --emit-c <file list>`, the bootstrapper's spelling; `zen build <root> --emit-c -o <file>` is the whole self-hosted CLI, because a build *is* a root and finding the entry inside it is the driver's job. So the strongest property in the plan has been verified by hand on every stage-1 run instead of by its own script. The same mistake was in `tests/run.py`, where it read as 33 compiler bugs and was one harness bug.

Fixing it is not a signature change: one axis deliberately **shuffles the input order**, which has no meaning when the driver is handed a root and decides the order itself. Either that axis moves into the compiler (a flag that permutes the walk) or it is retired with a written reason — and retiring it silently would leave a script that reads as three axes while checking two.

**Not yet run, and that is worth stating where the claims are made.** `tests/bench/` holds the four files and `src/std/test/test.zen` declares `Bencher` and `BenchStats`, but there is no `make bench`: the budgets are enforced by `b.bench(..)` in a project's own `build.zen`, and executing a build file needs stage 1 further along than it is. So the two load-bearing claims below are currently **asserted and unmeasured** — which is the same shape as a gate that cannot fail, and `src/std/core/loop/loop_iter.zen:21` already cites `bench_loop.zen` as the thing that justifies how the loop family is typed. The day `zen build` can run a build file, this is the first thing to point at it.

Because all allocation goes through `Alloc`, `allocs_op` and `bytes_op` are free to measure and **identical on every machine** — so they are hard gates. `ns_op` and build wall clock go to a rolling median.

Two budgets from `DESIGN.md` are load-bearing claims about the language, not micro-benchmarks:

```groovy
Budget(name: "stored_field_read",   ns_op: 2, allocs_op: 0),
Budget(name: "computed_field_read", ns_op: 2, allocs_op: 0),
```

If those diverge, uniform access is not free and the design needs to know. Same shape for the claim that loops never allocate: a fold over a stack array must bench at `allocs_op: 0`, and if it ever doesn't, an inliner regressed.

---

## Fuzzing, once the grammar is stable

Cheap and high-yield, in this order:

1. **Grammar-driven generation**: random valid programs from `grammar.js`, asserting `parse |> print |> parse` round-trips. Finds formatter and trivia bugs by the dozen.
2. **Mutation of valid programs**: flip bytes in corpus files, assert the compiler always terminates with either a binary or a diagnostic — never a crash, hang, or silent wrong answer.
3. **Differential fuzzing** during stage 1: the same random program through both implementations.

The bar is not "finds bugs" — it is **the compiler never crashes and never hangs**, on any input. That is a property, and properties are what fuzzing is for.

---

## Two findings this document produced

Recorded here because they are gaps in `DESIGN.md`, not test cases:

1. **`i32.MIN / -1`** is an overflow, not a division by zero. `DESIGN.md` says `/ %` trap on a zero divisor and stops there. It needs a sentence.
2. **Signed overflow is UB in C**, so the trap has to be checked *before* the operation or via `__builtin_*_overflow`. This constrains `gen_c` and belongs in the design's failure-model section rather than being discovered during stage 0.4.
