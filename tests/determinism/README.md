# Determinism

`gen_c` is deterministic: same input, byte-identical output. `DESIGN.md`
calls this a property "designed in rather than discovered", and everything
downstream leans on it —

- the **fixpoint oracle** (`stage2.c == stage3.c`) is not a test at all if
  the compiler can emit two different files from the same source;
- **seed regeneration** produces a reviewable diff only if the diff contains
  exactly what changed;
- **`allocs_op` / `bytes_op` budgets** are hard gates precisely because they
  are claimed to be identical on every machine.

So determinism is tested directly, and it is tested first. A nondeterministic
compiler does not announce itself: it produces a fixpoint that is green four
times out of five, and the day it is red you spend on the wrong hypothesis.

## The four sources, named so they are designed out

`TESTING.md` names these. They are listed here in the form an implementer
needs — as a rule about `gen_c`, not as a bug to look for later. Every one of
them is cheap to prevent at the point the code is written and expensive to
find afterwards, which is the entire argument for this directory existing
before `src/gen/gen_c.zen` does.

**1. Iterating a hash map without sorting.** The compiler is full of maps:
symbol tables, generic-instantiation caches, string-literal pools, the
memoized sema queries `type_of` / `defs_of`. Iterating any of them to *emit*
something puts the map's internal bucket order into the output file, and that
order depends on insertion history, capacity, and the hash function. **Rule:
a map may be a lookup structure, never an emission order.** Anything emitted
comes from a `Vec` in a defined order, or from a map whose keys were sorted
first. Note that `Map<K,V>` in `DESIGN.md` is an open-addressed `Vec<Entry>`,
so its iteration order is a function of insertion order *and* of collisions —
stable within a run, which is worse than obviously random, because it hides
until an unrelated change moves a key.

**2. Embedding a pointer value or address in a name.** Mangling a generic
instantiation, a lambda, or a temporary by its node's address is the fastest
way to get a unique name and it makes the output different under ASLR, under
a different allocator, and under a second compile in the same process.
**Rule: generated names are a function of the program, never of the run.**
A monotonic counter is only half a fix — the counter must be driven by a
deterministic traversal, or it just launders the nondeterminism through an
integer.

**3. Embedding a timestamp or a path.** No `__DATE__`, no `__TIME__`, no
build date in a banner comment, no absolute source path. Paths are the subtle
half: `DESIGN.md` requires a trap to print `file:line:col`, so paths *are* in
the output by design. **Rule: every path in the emitted C is relative to the
compilation root.** Two checkouts of the same commit at different absolute
paths must emit the same bytes; check 4 below enforces exactly that, and it
is the check most likely to be the first one red.

**4. Relying on filesystem enumeration order.** `readdir` order is not
sorted, is not creation order, and is not stable across filesystems — two
machines with identical trees enumerate them differently. Module discovery,
input globbing, and any "walk the source directory" step must sort. **Rule:
sort immediately after enumerating, before anything downstream can observe
the order.** Check 3 attacks the same property from the other side by passing
the files in a shuffled order explicitly.

**And a fifth, which is really the same rule stated once more:** any random
or time-seeded value — a hash seed, a temporary-name suffix, a
`HashMap::new()` in a language that randomizes seeds per process. Check 1
(twice in one process) and check 2 (two processes) exist as a pair because a
per-process seed is identical within a run and different between runs, so
only one of the two checks sees it.

## The checks

`check.sh` runs these against `fixture/`. Each is one line of `cmp` and one
sentence of reasoning.

| # | check | catches |
|---|---|---|
| 1 | compile the same input twice **in one process** | state carried between compilations, address-derived names, an accumulating counter |
| 2 | compile in **two processes**, under a different `TZ`, locale, `TMPDIR` and working directory | per-process hash seeds, timestamps, environment leakage |
| 3 | compile with the input file order **shuffled** | filesystem-enumeration dependence, first-seen-wins ordering in any emitted list |
| 4 | compile **two copies of the tree at different absolute paths** | absolute paths embedded in trap locations, `#line` directives, or banner comments |
| 5 | **scan the emitted C** for `__DATE__`, `__TIME__`, a work-directory path, or pointer-shaped hex | the same sources, statically, so it is caught even when checks 1–4 happen to agree |

Checks 1, 2 and 3 are the three `TESTING.md` names. Check 4 is the path half
of source 3, split out because it is the only one that needs two trees rather
than two runs. Check 5 is nearly free and it fails *informatively* — it names
the token, where `cmp` names a byte offset.

**The harness is itself deterministic.** The three permutations in check 3
are fixed (reverse, rotate-by-one, evens-then-odds), not `shuf` — a random
harness that fails once and passes on rerun teaches you to press rerun.

## What the compiler must provide

Two things, both small, both worth having anyway. They are stated here as a
contract because `check.sh` is written against them and `PLAN.md` does not
mention either.

**`--emit-c -o <path>`** — write the generated C to `<path>` and stop. It is
the artifact the fixpoint test compares, so it must be reachable without
invoking a C compiler.

**`--repeat N`** — run the entire pipeline `N` times in one process, writing
run 1 to `<path>` and run *i* to `<path>.<i>`. Without it, check 1 cannot be
written at all, and check 1 is the one that catches the address-derived name
— the failure that is invisible to every other check because it is stable
within a process. It is a debug flag; it costs a loop.

`zen build` must also accept an explicit list of `.zen` files as well as a
directory, or check 3 has no way to specify an order.

## Running it

```sh
ZEN=./zen tests/determinism/check.sh          # or just ./tests/determinism/check.sh
KEEP=1 ZEN=./zen tests/determinism/check.sh   # keep the work directory for inspection
```

Exit codes:

| code | meaning |
|---|---|
| 0 | every check passed |
| 1 | a check failed — `gen_c` is nondeterministic |
| 2 | the harness could not run: no `zen` binary, missing fixture, or an unsupported flag |

**2 is not a pass.** A missing compiler is reported as a setup error and not
as a skip, on purpose: a gate that silently succeeds when it cannot run is a
gate that reads as coverage and guards nothing (`STYLE.md`: "before trusting
a new gate, break the thing it guards on purpose and watch it go red"). Wire
this into CI at stage 0.4, when `gen_c` first emits anything — not earlier,
where it would be red for the whole of stage 0, and not later, because by
then the nondeterminism is already in and the fixpoint test is already the
thing you do not trust.

To convince yourself the gate can fail before you rely on it: make `gen_c`
emit declarations in map order instead of sorted order, and watch check 3 go
red. If it does not, the fixture is too small — add modules until it does.

## The fixture

`fixture/` is a small multi-module program chosen to give every source of
nondeterminism something to bite on:

- **four modules**, so file order is a real variable (check 3) and module
  discovery has to sort (source 4);
- **the same top-level name defined in three of them** (`name`, `total`),
  which `DESIGN.md` explicitly permits — so the mangled symbols must be
  emitted in a defined order rather than in whatever order the symbol table
  yields;
- **one generic instantiated at the same type from two different modules**
  (`Box<i32>`), so the instantiation cache is consulted twice and must emit
  once, in a place that does not depend on which module was compiled first;
- **one generic instantiated with a type from a third module**
  (`Box<Item>`) — `DESIGN.md`'s reason for whole-program compilation, and
  the case where "which module owns this definition" has no natural answer;
- **enough declarations and string literals** that a symbol table or literal
  pool iterated in hash order comes out visibly scrambled rather than
  coincidentally sorted.

It also runs and prints a fixed line, so it doubles as a corpus program if
the corpus runner is ever pointed at it.
