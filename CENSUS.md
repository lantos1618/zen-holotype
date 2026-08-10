# Census: .zen files under tests/ and example/ that no build compiles

**Rule under audit** (docs/DESIGN.md:404): "A name that is not imported is not
visible, and the prelude is the only exception." The prelude is `std.core`; its
exact surface is src/std/core/core.zen:13-64 — `Res, Ok, Err, None, ok_or, then,
Drop, Scope, i8..i64, u8..u64, usize, f32, f64`, the `is_*/to_*/hex_*` byte
functions, `loop, find, filter, map, pairs, LoopHandle, Range, Eq, Hash, Hasher,
Display, IoError, WriteError, Sink, Path, Duration`, plus the re-exported
`str, String` (std.text), `Vec, Map` (std.collections),
`Alloc, AllocError, Arena, Mem, Ptr, null_ptr` (std.mem) and `Env, ArgError`
(std.env). `println` is compiler sugar, `bool` is a primitive. The name→module
map is src/std/std.zen:14-41.

**Summary.** The first pass of this census found seven files with missing
import lines and a grammar gate that passed on an empty set. The second pass
fixed both. What changed and what is still open, in one paragraph: all seven
files now carry their import lines (or, for `std.actor`, a comment naming the
stage-5 import that cannot be written yet); `make grammar-test` is now a real
gate (`scripts/grammar_test.py`) that asserts 23 parse-negatives fail and 391
positive files parse, and its first run caught three misclassified fixtures,
which moved to the suite where their rejection is actually asserted. Still
open: nothing compiles `tests/bench/` or `example/`, `example/build.zen`'s
`Function` has no importable home anywhere in std, and four implementation
comments in src/ and bootstrap/ cite `bench_loop.zen`'s unrun `allocs_op: 0`
budget as load-bearing justification.

---

## What the fix pass changed

### 1. `make grammar-test` is a gate again

Was: `cd grammar && npx tree-sitter test`, which reported `Total parses: 0`
and exited 0 — grammar/ has no test/corpus directory, so the target passed on
an empty set.

Now: `scripts/grammar_test.py` (wired at Makefile `grammar-test`), in the
house style of scripts/line_cap.py and scripts/refmap.py:

- **Negative half:** every tests/parse/errors/*.zen (23 files) must FAIL
  `tree-sitter parse`. A file that parses is reported by name as a grammar
  bug, not deleted or excused.
- **Positive half:** every .zen under tests/corpus/ and example/ (391 files)
  must parse. src/ is deliberately excluded — `make parse` already gates it,
  and a grammar check should not redden over a half-written compiler module.
- Exit 2 if grammar/zen.so is missing or either fixture set comes up empty —
  the empty-set failure mode this script exists to kill.
- Verified: first run went red (3 failures, named files, exit 1); after the
  fixture migration below it reports
  `23/23 negative(s) rejected, 391/391 positive(s) parsed, 0 failure(s)`.

**The gate's first catch.** Three of the 26 parse/errors fixtures parsed
clean. Investigation showed all three are grammar.js decision D13 (lines
147-153): parameter types are optional in the grammar because closures infer
them, so these shapes are rejected one stage later, in cst.py/sema —
"reported", as D13 says. A file that parses is not a parse-negative, so they
were moved to where their rejection is real and is now asserted with exact
diagnostics and positions:

| fixture | bootstrap rejection (verified by running it) | new home |
|---|---|---|
| bare_self_param.zen | `11:9: parameter 'self' needs a type: only a closure infers its parameter types` | tests/must-fail/parse/bare_self_param.zen + .expected |
| match_arm_paren_form.zen | `13:5, 14:15, 15:16: expected i32, found (n: _) _` — the arm-body-is-a-closure type error its own header predicted | tests/must-fail/sema/match_arm_paren_form.zen + .expected |
| fn_type_unnamed_params.zen | already gated: tests/must-fail/parse/fn_type_unnamed_params.zen + .expected cover the same rule | deleted as a stale duplicate |

Both moved files were re-run through the bootstrapper from their new
locations; the diagnostics match the written `.expected` files exactly.
`tests/lint.py` reports 456 tests, 0 errors, 0 warnings, with the two new
tests collected.

### 2. The import lines

Added, in the repo's own style (`Marked, label = alpha.alpha`;
`Leaf, leaf_value = pair` for a same-directory sibling):

- tests/bench/bench_vec.zen, bench_loop.zen, bench_field.zen:
  `Bencher, TestError = std.test`
- tests/bench/bench_budgets.zen: `Budget = std.build`
- example/src/main_test.zen:
  `Bencher, TestError, Tester = std.test` and `Circle, Rect, Shape = main`
  (`c.area()` needed nothing — UFCS travels with the type, DESIGN.md:406)
- example/build.zen:
  `Budget, Builder, BuildError, Package = std.build` and
  `Bencher, Tester = std.test`
- example/src/main.zen: no import added. `Actor, Context, Ref` come from
  `std.actor`, which does not exist (src/std/std.zen:43-44 defers it to
  stage 5), and a broken import is worse than a missing one. A comment at
  the import block names the line to add when stage 5 lands.

Verified: `make parse` — 560/560 successful parses, 0 failed. The fmt gate's
own command (`find src example tests/corpus … | xargs ./zen fmt --check`)
exits 0. (`make fmt` itself was not invoked because it depends on `build`,
which rebuilds ./zen from a src/ tree another fleet is editing; the command
above is the target's own check run against the existing binary.)

### 3. docs/TESTING.md

The "Performance is a test" section now states at the top, unambiguously,
that nothing runs the benches and names the four sites that cite
`bench_loop.zen`'s `allocs_op: 0` as justification:
src/std/core/loop/loop_iter.zen:14, src/std/core/range.zen:19,
src/gen/gen_c/gen_c_inline.zen:16, bootstrap/gen_c.py:4028. It says the
budgets are asserted and unmeasured until `zen build` can execute a build
file — no fix is claimed.

---

## What remains open

- **tests/bench/ still compiles under nothing.** The import lines make the
  files correct, not gated. No target compiles, parses, formats, or lints
  the directory. This is the load-bearing one: see the four citing sites
  above, now named in docs/TESTING.md.
- **example/ is never compiled.** Its only gates remain tree-sitter parse
  (`make parse`) and `zen fmt --check` — syntax and whitespace, never name
  resolution. The imports added there are verified by hand against
  src/std/std.zen and the sibling file, not by a compiler run.
- **`Function` has no importable home.** example/build.zen:55,67 names it;
  it is the compiler's AST node (src/ast/ast_node.zen:516), no std module
  exports it, and src/std/build/build.zen itself uses `Function` and
  `Module` bare (lines 100, 113, 156) with no import. Fixing that means
  editing src/, which was out of bounds for this pass.
- **grammar.js:152 is now stale.** Its comment says "Two fixtures in
  tests/parse/errors/ therefore fail one stage later" — those two files
  moved to tests/must-fail/. grammar/ was outside the editable set.
- **docs/LEXER_BOOTSTRAP_FIXES.md:475 says "twenty-five files"** for
  tests/parse/errors/; it now holds 23. Left alone as a dated fix log.
- **The must-fail migrations were verified against the bootstrap toolchain
  only** (the default for `make test`). Whether the self-hosted `./zen`
  rejects them identically is unverified — `make test-zen` needs a build
  from the in-flux src/ tree, so it was not run.
- **`make grammar-test` going red on a real grammar regression** was
  verified only in its failure reporting (its first run failed correctly
  with named files and exit 1). The end-to-end check — mutate grammar.js,
  regenerate, watch the gate fail — was left for the reviewer, since
  regenerating the parser mid-flight was out of scope.

## Gate coverage map (current state)

| directory | compiled? | mechanism |
|---|---|---|
| tests/corpus | yes | tests/run.py (`make test`, `make test-zen`); also `make parse`, `make fmt` |
| tests/must-fail | yes (expecting rejection) | tests/run.py, same targets; 2 tests added this pass |
| tests/determinism/fixture | yes | tests/determinism/check.sh (`make determinism`) |
| tests/parse/errors (23 .zen) | parse-negative gate | `make grammar-test` → scripts/grammar_test.py (new this pass) |
| tests/bench (4 .zen) | **no** | nothing — imports now correct, gate still absent |
| example (3 .zen) | **no** | `make parse` + `zen fmt --check` only; never compiled |

Outside tests/: editors/ (extension.ts, zen.lua) and Zen code blocks in
docs/*.md other than DESIGN.md remain ungated; only DESIGN.md's fences are
parsed (scripts/design_examples.py:54).
