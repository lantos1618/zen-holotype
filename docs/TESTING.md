# Testing

Written before the compiler, not after. Everything here is a bug class that compilers reliably have — so the tests exist first and the code is written to pass them.

Companion to `PLAN.md`, which says which stage each gate arrives at.

---

## The oracles, strongest first

**1. Fixpoint.** `zen-1` and `zen-2` emit byte-identical C for the same source. A compiler reproducing its own output is almost certainly correct across an enormous surface, and it costs one script. Requires `gen_c` to be deterministic — see the determinism section, which is a test in its own right.

**2. ~~Differential, bootstrap vs self-hosted.~~ GONE, and knowingly.** During stage 1 there were *two* independent implementations of Zen, and every corpus program ran through both: any disagreement was a bug in one of them, and it told you *which program* exposed it. It found things nothing else could — a match arm with a hole in its type deciding the match's type, and a `x.f(..)` that a method and a free function both answered. It is deleted anyway, because the two had begun to disagree on real programs with `src` usually right, and because keeping it meant writing every rule twice. **What replaced it is nothing.** Oracles 1, 3 and 4 are what stands, and the gap this leaves is a bug both `src` and `seed/zen.c` share: no gate in this tree can see one. When a rule matters that much, the substitute is a hand-written twin in the corpus — a program somebody could have written by hand, sharing one `.expected` with the derived one (`docs/design_meta.md` M3).

**3. Corpus.** Program in, expected stdout and exit code out. Cheap, and the thing that catches regressions in behaviour rather than in structure.

**3b. `example/`, the same oracle pointed at the worked example.** The tree's own showcase program held **zero `.expected` files** and was compiled by nothing: `parse`, `grammar-test`, `lextile` and `fmt` all read its bytes and none handed them to the compiler. That is not a hypothetical gap — compiling `example/` is how the lambda-body hole was found (the same two statements give two diagnostics at statement level and *zero* inside a `.loop` or `.then` body, which means `cc` was the type checker there), and nothing in this repository compiled the file that showed it. `tests/run.py` now collects `example/` as a third suite, with the same directory shape and the same `.expected`/`.exit`/`.stage` sidecars as a corpus test — one mechanism, not two. `example/src` is stage 5 (it names `std.actor` and `pkg.*`), so it is *deferred* today rather than red, and a deferred test that starts passing is a failure telling you to delete its `.stage`. The suite asserts it is non-empty: collecting zero programs is exit 2, not a pass.

**4. `must-fail`.** Programs that must be rejected, each with the expected diagnostic *and its position*. A rejection with the wrong span is a failure. This is also the only suite that can ask what no valid program asks: the shipped compiler accepted `f = (b: bool) i32 { b.match({ true => 1, false => false }) }` — it emitted C, ran, and printed 0 — because a corpus test is a valid program and the differential oracle only compares programs somebody wrote down. `must-fail/sema/match_arms_disagree` and `match_arm_paren_form` went red on 2026-08-10 and were fixed the same day, in `check_arms` (`src/sema/sema_hoist.zen`) rather than in the join, which has no expectation to name. That rule reaches only positions that write a type down; the four `match_arms_disagree_at_a{n_untyped_binding,_type_parameter,_print,n_operand}` files are the same defect where nothing does, and they are answered by `check_arms_agree` in the arms' own voice. Those focused tests are the maintained record of the bug.

The same suite is the only one that could ask about a *pattern* naming a constant, closed 2026-08-17. `LIMIT => ..` is a fresh binding, so the arm matched every value and `n.match({ LIMIT => .., _ => .. })` took the wrong branch in silence; the sole symptom was `_` being reported unreachable, which names the consequence and not the cause, and a match with no `_` produced no diagnostic at all. `match_pattern_names_a_constant` pins both positions so the cause-before-effect ordering cannot regress, and `match_pattern_names_a_constant_alone` pins the shape that said nothing.

**5. Mutation.** Periodically: mutate the compiler (flip a comparison, drop a case, change a constant), rebuild, and assert some test goes red. A gate that survives mutation is not guarding anything. This is how you find out that a scanner fails open, and it is the only way to find out.

Two uses of it, both from 2026-08-17. **Proving an existing guard is load-bearing**: replacing `run_for_effect`'s dispatch in `gen_c_call.zen` with `Ok(())` — dropping a unit payload's side effect — still *built and bootstrapped cleanly*, `make build` exit 0, and reddened 113 corpus tests. The build is not an oracle for whether the compiler still does the thing; only the corpus is. **Proving a NEW rule is not vacuous**: `SemaFault.ConstPattern` reported zero sites across 60k lines of `src/`, which reads identically to a check that never fires, so it was mutated three ways before the zero was believed — an arm naming an *imported* constant was added to prove the cross-module path live, the rule was widened to any module-level declaration, and the local-shadow gate was removed. Zero each time. **A clean tree and a dead gate are the same observation until you make the gate go red on purpose.**

---

## The test file format

One format, so ten authors produce one suite. The runner reads only this.

```
tests/corpus/<area>/<name>.zen         the program
tests/corpus/<area>/<name>.expected    exact stdout, compared byte for byte
tests/corpus/<area>/<name>.exit        expected exit code; omit the file when it is 0
tests/corpus/<area>/<name>.stderr      expected stderr substring; omit when none
tests/corpus/<area>/<name>.stdin       bytes fed to the PROGRAM's stdin; omit when it reads none

tests/must-fail/<area>/<name>.zen      must be rejected
tests/must-fail/<area>/<name>.expected the diagnostic, see below
```

A test needing several source files is a **directory** of the same name, holding its module tree plus `.expected` / `.exit` / `.stderr` / `.stdin` at the directory root. Module trees inside it follow `<folder>/<folder>.zen`, and the entry point is `main.zen`.

**`.expected` in `must-fail` is line one, then one position per line after it:**

```
is not exported by module
main.zen:5:7
```

Line 1 is a **substring** of the message — loose enough to survive rewording, tight enough to catch the wrong error being reported. Every line after it is a position that must appear in the diagnostic, as `path:line:col` with the path relative to the test root. Several lines means the diagnostic must name several places, which `DESIGN.md` requires in at least two cases: an impl collision names both impls, and a duplicate signature names both declarations.

Positions are 1-based line, 1-based **byte** column, and point at the first byte of the smallest offending node.

**A single-file test may write `line:col` and omit the path**, which resolves against the test's entry file. Four suites reached for this independently before it was allowed, which is the tell that the long form was asking for something nobody wanted to write. A right-line/wrong-file match is still a failure.

**A test is compiled against the whole of `src/`, not just `src/std`.** The compiler's own modules — `sema`, `gen`, `fmt`, `lsp` — are siblings of `std` under one root, and its frontend — `lex`, `parse`, `ast` — lives INSIDE `std` so an ordinary program can say `= std.parse`; staging only the prelude would mean no corpus test could ever import one and each subsystem would invent a private harness instead. The staged root *is* the compilation root, so `src/std/lex/lex.zen` is imported as `std.lex.lex`, exactly as `src/std/core/core.zen` is `std.core`. Because `std` is staged whole, the harness then prunes `std/lex`, `std/parse` and `std/ast` from the copy unless the test's import closure names one — the one-half-written-module law above, applied one level down.

**A test's compilation root is its own directory.** Every asserted path is relative to that, and so is every path the compiler emits — which is what makes the determinism check comparing two copies of a tree at different absolute paths meaningful.

**A directory test names its expectation `main.expected`**, matching the `main.zen` it already requires, and visible to `ls` in a way a dotfile is not. `.exit`, `.stderr`, `.stdin`, `.count` and `.stage` follow the same rule.

**`.stdin` is the program's standard input, and it is the program's alone** — the compiler is never fed it. `std.env.Stdin` is a capability, and a capability is only tested by a program that exercises it, so without this file `zen lsp`'s transport would be gated by nothing. An **absent** `.stdin` is `/dev/null`; an **empty** one is a pipe that closes immediately, which is a different thing and the one a test of end-of-input needs.

**A must-fail test asserts a NUMBER of diagnostics: the count is bounded at the number of positions `.expected` asserts.** One complaint written down means one complaint emitted — one mistake must not cascade (`parse/one_error_no_cascade` exists to police exactly this), and an extra diagnostic nobody expected is a finding, not noise: it is either a compiler emitting something wrong beside the right answer, or a genuine multi-diagnostic case whose `.expected` should have said so. **`.count` states the number where it genuinely differs from the asserted positions** — several distinct mistakes of one kind, or a cascade the test deliberately tolerates. It overrides the default; absent it, the positions are the bound. On any breach the captured diagnostics are reported rather than discarded, so what else the compiler said is always on the record.

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
- compile with a permuted module walk — byte-identical

`make determinism` runs all three, plus two copies of the tree at different absolute paths and a static scan of the emitted C. It passes.

**It had never run.** `tests/determinism/check.sh` invoked `zen build --emit-c <file list>`, the bootstrapper's spelling; `zen build <root> --emit-c -o <file>` is the whole self-hosted CLI, because a build *is* a root and finding the entry inside it is the driver's job. So the gate exited 2 on its first compile and the strongest property in the plan was verified by hand on every stage-1 run instead of by its own script. The same mistake was in `tests/run.py`, where it read as 33 compiler bugs and was one harness bug.

**The shuffle axis moved into the compiler** rather than being retired. `--permute reverse|rotate|interleave` reorders each module's import list and so the breadth-first walk; the entry stays module 0, because the backend compiles module 0 and the `main` check asks it. Retiring the axis was arguable — `std.env.Fs` has no directory listing on purpose, so `readdir` order cannot enter this compiler — but that argument covers only the filesystem-enumeration source. The walk order is still the order the *imports are written in*, so adding one import shifts every module index after it, and `gen_c_decl.zen`'s header already claims the output is independent of that. It was a claim no gate read. `tests/determinism/README.md`, "the shuffle axis", is the full argument.

**Check 3 proves its instrument before it trusts it:** a compiler that accepted `--permute` and ignored it would pass by comparing a file with itself, so the script first breaks four modules and requires the diagnostic order — which is the walk order — to move. If it does not, that is a setup error and exit 2, not a pass.

The usual sources, all of which must be designed out rather than found later: iterating a hash map without sorting, embedding a pointer value or address in a name, embedding a timestamp or path, relying on filesystem enumeration order, and any use of a random or time-seeded value.

---

## Diagnostics are tested like output

A compiler is mostly a diagnostics engine that occasionally emits code. Every `must-fail` test asserts three things:

1. it fails
2. **the message** — matched loosely enough to survive rewording, tightly enough to catch the wrong error being reported
3. **the position** — `file:line:col`, exact

The third is the one everyone skips and the one that decays fastest. A correct diagnostic pointing at the wrong token is what makes a language feel unfinished.

---

## Performance is measured deliberately

The old per-operation benchmark drivers and their Python harness were removed:
they duplicated program bodies, produced machine-specific budgets, and added more
maintenance than signal. Performance work now starts from a reproducible compiler
workload and records wall time, peak RSS, emitted-byte hashes, and a `perf` profile.
A change is accepted only when output is byte-identical and the same workload gets
faster.

`make asan` and `make leak` remain explicit slow diagnostics for compiler memory
safety. They are not part of `make test`; a machine without their platform tools
must not turn an ordinary correctness run into a harness failure.

## Fuzzing, once the grammar is stable

Cheap and high-yield, in this order:

1. **Grammar-driven generation**: random valid programs from `grammar.js`, asserting `parse |> print |> parse` round-trips. Finds formatter and trivia bugs by the dozen.
2. **Mutation of valid programs**: flip bytes in corpus files, assert the compiler always terminates with either a binary or a diagnostic — never a crash, hang, or silent wrong answer.
3. **Derived-vs-hand-written twins** for generated features: the generated form
   and a direct Zen equivalent share one expected result.

The bar is not "finds bugs" — it is **the compiler never crashes and never hangs**, on any input. That is a property, and properties are what fuzzing is for.

---

## Two findings this document produced

Recorded here because they are gaps in `DESIGN.md`, not test cases:

1. **`i32.MIN / -1`** is an overflow, not a division by zero. `DESIGN.md` says `/ %` trap on a zero divisor and stops there. It needs a sentence.
2. **Signed overflow is UB in C**, so the trap has to be checked *before* the operation or via `__builtin_*_overflow`. This constrains `gen_c` and belongs in the design's failure-model section rather than being discovered during stage 0.4.
