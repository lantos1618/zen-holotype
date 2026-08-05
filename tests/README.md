# tests

`docs/TESTING.md` says which bug classes exist and why. This file says how the
tests are stored, how to run them, and how to add one.

Two programs live here and neither is a test:

| file | what it is |
|---|---|
| `run.py` | the gate. Compiles and runs `corpus/`, compiles and rejects `must-fail/`. |
| `lint.py` | the format checker. Validates every test against `TESTING.md`, and writes `FORMAT-VIOLATIONS.md`. |

---

## The tree

```
tests/
├── corpus/        program in, exact stdout + exit code out          run.py
│   ├── lex/  parse/  modules/  sema/  own/  codegen/  traps/  std/
├── must-fail/     programs that must be rejected, with the diagnostic
│   ├── lex/  parse/  modules/  sema/  own/  traps/               run.py
├── parse/         tree-sitter corpus (stage 0.1)              tree-sitter test
├── bench/         Bencher functions; budgets in build.zen        zen test
└── determinism/   gen_c emits the same bytes twice               check.sh
```

`run.py` covers `corpus/` and `must-fail/` only. The other three have their own
runners, listed above; `tests/determinism/README.md` documents its own.

---

## The format

Authoritative in `docs/TESTING.md` § "The test file format". Restated here
because that is where you will look.

**A single-file test** is a `.zen` and its siblings:

```
corpus/<area>/<name>.zen         the program
corpus/<area>/<name>.expected    exact stdout, compared byte for byte
corpus/<area>/<name>.exit        expected exit code; OMIT the file when it is 0
corpus/<area>/<name>.stderr      substring(s) that must appear on stderr; omit when none

must-fail/<area>/<name>.zen      must be rejected
must-fail/<area>/<name>.expected the diagnostic, below
```

A `.zen` file is a test **iff** a sibling `.expected` with the same basename
exists. Anything else is reported by `run.py` as *uncollected* and fails the
run — a test that cannot run cannot go red.

**A multi-file test** is a directory of the same shape:

```
corpus/<area>/<name>/main.zen         the entry point
corpus/<area>/<name>/<mod>/<mod>.zen  the module tree
corpus/<area>/<name>/.expected        the expectation, at the directory root
```

The directory is the compilation root, so `alpha/alpha.zen` is imported as
`alpha`. `.exit` and `.stderr` sit beside `.expected`.

**`must-fail/*.expected` is a message line, then one position per line:**

```
is not exported by module
main.zen:5:7
```

Line 1 is a **substring** of the diagnostic — loose enough to survive
rewording, tight enough to catch the wrong error being reported. Every line
after it is a position that must appear, as `path:line:col` relative to the
test root, or `line:col` for a single-file test. Lines are 1-based; columns are
1-based **bytes**. Several lines means the diagnostic must name several places.

**Extra diagnostics are allowed.** You assert the ones that must be there, not
the ones that must not.

**Assumptions the whole corpus rests on**, so no test restates them: `Ok(0)`
from `main` exits 0; `println` appends exactly one `\n`; `{}` on an integer
prints decimal with no separators; stdout is compared byte-exactly including
the trailing newline.

---

## Running

```sh
tests/run.py                            # everything, through bootstrap/bootstrap.py
tests/run.py --list                     # names only; needs no compiler
tests/run.py --filter 'corpus/traps/*'  # glob over the test id
tests/run.py --filter consume           # a plain word is a substring match
tests/run.py -j 8 -v
tests/run.py --toolchain zen --zen ./zen        # after stage 1
tests/run.py --keep                             # keep the generated C
```

A test id is its path under `tests/` without the extension:
`corpus/lex/bom_utf8`, `must-fail/modules/import_cycle`.

| exit | meaning |
|---|---|
| 0 | every selected test passed |
| 1 | a test failed, or a `.zen` file belongs to no test |
| 2 | the harness could not run: no compiler, no `cc`, an unreadable test, or a selection that matched nothing |

**2 is not a pass.** A missing compiler is a setup error, never a skip. The same
rule as `tests/determinism/check.sh`, for the same reason.

Both toolchains are driven through one CLI contract — `--emit-c -o <path>`,
from `bootstrap/CONTRACT.md` — and the emitted C is then compiled with `cc`. A
C compiler rejecting the generated C is a **codegen failure**, reported as a
red test with the C diagnostic attached, not as infrastructure noise.

### Checking the format

```sh
tests/lint.py                 # human-readable, all findings
tests/lint.py --errors-only
tests/lint.py --markdown > tests/FORMAT-VIOLATIONS.md
```

Exit 0 clean, 1 on any ERROR, 2 if the tree cannot be read. `FORMAT-VIOLATIONS.md`
is the current report: what does not conform, grouped by suite, with the fix.

---

## Adding a test

**A corpus test.** Write the program, run it, and record what it did — do not
hand-write the expectation and hope:

```sh
$EDITOR tests/corpus/std/vec_grows_across_realloc.zen
tests/run.py --filter vec_grows_across_realloc
# run.py: no test matched ['vec_grows_across_realloc']
# run.py: but this file is uncollected: corpus/std/vec_grows_across_realloc.zen
```

Then write `.expected` with the exact stdout. Add `.exit` only when the exit
code is non-zero. Add `.stderr` only when a message must appear there — it is a
substring check, one per line.

**A must-fail test.** Write the program that must be rejected, then write
`.expected` as the message substring and the position(s). Keep the message
short: it survives rewording, and a whole sentence does not.

**A multi-file test.** Make a directory, put the entry in `main.zen`, put each
module in `<folder>/<folder>.zen`, and put `.expected` at the directory root.

Then run `tests/lint.py` before you commit. It is faster than the review.

---

## The rule this whole directory rests on

From `docs/PLAN.md`:

> **Before trusting a new gate, break the thing it guards on purpose and watch
> it go red.**

A gate that cannot fail is worse than no gate, because it reads as coverage.
When you add a test, prove it can fail before you believe it passes — change
one digit of the expected output, or delete the check in the compiler that the
test exists for, and watch the run go red. Then put it back.

`run.py` was built that way. Each of these was induced against a stand-in
compiler and observed to fail, with the failure named:

| broken on purpose | what came back |
|---|---|
| one byte of `.expected` | `stdout does not match .expected`, with a byte offset and a diff |
| `.exit` set to the wrong code | `exit code 134, expected 0 [trap.exit]` |
| `.stderr` substring changed | `.stderr substring not found: ...` |
| a `must-fail` program made to compile | `the program compiled; it must be rejected` |
| the diagnostic's wording | `message substring not found: ...` |
| the diagnostic's position, message intact | `position not reported: 3:7` |
| the compiler made to crash on a `must-fail` test | `a crash is not a diagnostic` |
| the compiler made to hang | `the compiler hung for 2.0s; a rejection must terminate` |
| a `must-fail` `.expected` stripped of its position | `asserts no position` |
| a `.zen` file with no `.expected` | `uncollected`, exit 1 |
| the compiler removed | exit 2, not exit 0 |
| a `--filter` matching nothing | exit 2, not "0 passed" |

The last three are the ones that matter most: they are how a harness fakes a
pass. If you change `run.py`, re-break them.
