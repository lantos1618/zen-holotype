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
| 3 | compile with the **module walk permuted** (`--permute`) | discovery-order dependence in any emitted list, and any name derived from an index the walk hands out |
| 4 | compile **two copies of the tree at different absolute paths** | absolute paths embedded in trap locations, `#line` directives, or banner comments |
| 5 | **scan the emitted C** for `__DATE__`, `__TIME__`, a work-directory path, or pointer-shaped hex | the same sources, statically, so it is caught even when checks 1–4 happen to agree |

Checks 1, 2 and 3 are the three `TESTING.md` names. Check 4 is the path half
of source 3, split out because it is the only one that needs two trees rather
than two runs. Check 5 is nearly free and it fails *informatively* — it names
the token, where `cmp` names a byte offset.

**The harness is itself deterministic.** The three permutations in check 3
are fixed (reverse, rotate-by-one, evens-then-odds), not `shuf` — a random
harness that fails once and passes on rerun teaches you to press rerun.

## The shuffle axis, and why it moved into the compiler

Check 3 used to shuffle a **list of file arguments**. The self-hosted CLI
takes no such list: `zen build <root> --emit-c -o <file>` is the whole of it,
because a build *is* a root and finding the modules inside it is the driver's
job. `TESTING.md` states the fork — either the axis moves into the compiler
as a flag that permutes the walk, or it is retired with a written reason.

**It moved.** The reason to retire it is real but partial: `std.env.Fs` has
`read`, `exists`, `is_dir` and `write` and *no listing*, on purpose, so
`readdir` order — source 4 — cannot enter this compiler at all. The module
set is a closure computed from the entry by following imports, and the order
is a pure function of the root.

That argument covers source 4 and **only** source 4. It says nothing about
source 1 or source 2, and those are the ones that bite:

- **The walk order is not a constant even without `readdir`.** It is the
  order the imports are *written in*. Adding one import to one file shifts
  every module index after it — and with them the insertion order into every
  table sema and gen build, which is exactly the input a hash map's iteration
  order is a function of. That is a thing that happens on an ordinary Tuesday,
  and if it reorders the emitted C then "seed regeneration produces a
  reviewable diff" is false.
- **`gen_c_decl.zen`'s own header makes the claim this check tests**: "EVERY
  LIST IS SORTED BY MANGLED NAME. That is what makes the output independent
  of the order the modules were discovered in, which is the property the
  determinism gate and the fixpoint oracle both stand on." Nothing tested it.
  A claim in a header that no gate reads is the shape of defect this
  repository keeps finding.

So `--permute <mode>` reorders each module's import list, which reorders the
breadth-first walk. The entry is **not** permuted and cannot be: `walk` queues
it first, `emit_program(be, 0, out)` compiles module 0, and the `main` check
asks module 0. Only the modules an import reaches move. The permutation
cannot change *which* modules load — a closure does not depend on the order
it is computed in.

**Check 3 verifies its own instrument first.** A compiler that accepted
`--permute` and ignored it would make the check pass by comparing a file with
itself, which is this directory's own stated failure mode arrived at from the
other side. So check 3a appends a junk byte to four modules and reads the
order the lex faults come back in — the walk reports a module when it reaches
it, so that order *is* the walk order — and requires it to move under all
three permutations. If it does not, the run is a **setup error (exit 2)**,
not a pass.

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
within a process. It is a debug flag; it costs a loop. Each run builds a
**fresh** driver: a repeat that reused one would carry exactly the state it
exists to look for.

**`--permute <mode>`** — `reverse`, `rotate` or `interleave`: permute each
module's import list, and so the order the breadth-first walk reaches modules
in. Anything else, including nothing, is the order the imports are written
in. Without it check 3 has nothing to vary, because the CLI takes a root and
computes the order itself. See "the shuffle axis" above.

Neither flag appears in `USAGE`. They are specified here, in the document
that depends on them, and `src/zen/zen_cli.zen` says so where they are
parsed.

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

## Convincing yourself it can fail

`STYLE.md`: "before trusting a new gate, break the thing it guards on purpose
and watch it go red." Two mutations, both verified against this fixture on the
day check 3 first ran:

**Check 3 goes red on a name derived from an index the walk hands out.** In
`gen_name.zen`, make `sym_type` append the raw `TyId`:

```groovy
out.write_usize(id.index.to_usize()).try();
```

Rebuild and run: all three permutations differ from the baseline and the gate
exits **1**. This is source 2 in its most plausible local form — the README's
own warning that "a monotonic counter is only half a fix … or it just
launders the nondeterminism through an integer" — and check 3 is the only
check that sees it. Check 1 stays green, because such an index is stable
within a process.

**Check 3 goes red when `--permute` stops working.** Make `permuted` in
`zen_build.zen` return `i` unconditionally. Check **3a** fails and the gate
exits **2**, naming the instrument rather than reporting a determinism
result. That is the vacuity guard, and it is the one to re-run after any
change to the walk.

### The mutation that does NOT work, and why

This file used to say: *make `gen_c` emit declarations in map order instead
of sorted order, and watch check 3 go red; if it does not, the fixture is too
small — add modules until it does.* **That recipe is wrong, and growing the
fixture will never fix it.** Replacing `order`'s insertion sort with the
identity permutation leaves all five checks green.

The reason is structural. `be.fn_names` and `be.type_names` are filled by the
reachability walk in `gen_c_decl.zen`, which is seeded from **module 0's**
declarations and driven from there by the **call graph**. Module 0 is always
the entry, and a call graph is a property of the program — so insertion order
is *already* a pure function of the program, and permuting the module walk
does not move it. Removing the sort removes a defence without introducing
nondeterminism, and a gate that tests the property rather than the mechanism
is right not to fire.

Keep the sort: it is what makes the property robust to the reachability walk
ever changing, and it costs an insertion sort over a few hundred names. But
do not use its removal to convince yourself this gate works — use the two
mutations above, which are about the run rather than about the mechanism.

## The fixture

`fixture/` is a small multi-module program chosen to give every source of
nondeterminism something to bite on:

- **four modules, all imported by the entry**, so the walk order is a real
  variable (check 3): a permutation of a one-import root is the identity, and
  check 3a fails loudly rather than quietly passing if that ever becomes
  true here;
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
the corpus runner is ever pointed at it — `main.expected` is that line, and
it is checked by hand rather than by this script, which compares C and never
runs it.

**It is compiled STAGED, never where it sits.** A Zen program stands on the
prelude — `Env`, `Res`, `Ok` and `println` are `std.core` names that no
module imports — and the driver looks for `std/` beneath the root it is
given. So `check.sh` builds each tree it compiles as a fresh directory
holding `fixture/` and a copy of `src/std`, exactly as `tests/run.py` stages
every corpus test and for the same reason. A consequence worth knowing: the
gate compiles the whole of `std` too, which is most of the 22 kB it compares
and most of what makes the comparison worth making.
