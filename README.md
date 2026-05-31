# zen-holotype

A tiny compiler for a small [Zen](https://github.com/lantos1618/zenlang)-flavoured
language, built to test one idea: **pin down what every value _is_ with type structure,
and you lock out everything it isn't.** Do that for pointers, modules, and functions
alike, and module imports, type-checking, and pointer safety all become the _same_
operation — checking that a signature fits in one shared space.

> In taxonomy a *holotype* is the single specimen that defines a name. Here,
> every path resolves to exactly **one** canonical node — and diamond imports
> collapse onto it.

## What we're actually doing: structure *is* the constraint

We're not writing checks that hunt for bad programs — no null pass, no borrow pass, no
separate linker. We do the opposite: **we describe exactly what each thing is, and that
description locks out everything it isn't.** A type is a closed door; "checking" is just
confirming the key fits the lock.

Take one annotation. `Ptr<Vec>` is not "a pointer" — it's three locks at once:

```
   Ptr < Vec >
    │     └──── points at THIS type only      (a different struct? rejected)
    ├──────── read-only   →  mutation locked out      (write needs MutPtr)
    └──────── non-null    →  absence locked out       (null needs Option<…>)
```

Every capability is **opt-in**. Didn't write `MutPtr`? You cannot mutate. Didn't write
`Option`? There is no null. Whatever you didn't permit isn't "checked for and rejected" —
it's *unrepresentable*. The same move scales: a **path** locks identity (`core.vec.Vec`
is one node, so you can't mean a different `Vec`), and a **function signature** locks its
call sites (only values whose locks match the parameter get in).

So the three things a compiler usually does separately — resolve names, check types, prove
pointer safety — are here the single act of **fitting a key to a lock**. That's why one
`fits()` does all of it, and why the legal program is exactly the shape the structure
allows, nothing more.

## How it works

```
   build.zen  ──interpret──►  { name: vecdemo,  entry: main,  out: build/ }   (drives the build)

   core/vec.zen   ops.zen   main.zen
        │
        ▼  tree-sitter  (grammar.js)
   ┌──────────┐
   │   AST    │   dataclasses + enums
   └────┬─────┘
        │  insert every decl at its path
        ▼
  ╔════════════ ONE TYPE SPACE — a trie ════════════╗
  ║  root                                            ║
  ║   ├─ core.vec.Vec         (struct)               ║     path = identity, so
  ║   ├─ ops.len   ops.cap    (fns)                  ║     diamond imports
  ║   └─ main.area   main.main  (fns)                ║     collapse to ONE node
  ╚═════════════════════╤════════════════════════════╝
                        │  resolve refs · infer() each body · fits() each call
                        ▼
              ┌─────────────────────┐
     PASS ✓ ◄─┤  fits(given, want)? ├─► FAIL ✗   reported, excluded from codegen
              └──────────┬──────────┘   null → nonnull ✗  ·  read → mut ✗
                         ▼               (rules: nonnull ≤ Option,  MutPtr ≤ Ptr)
              ┌─────────────────────┐
              │     lower to C      │   Ptr → const* ,  Option → *   (types erase away)
              └──────────┬──────────┘
                         ▼  cc -Wall -Wextra
                    build/vecdemo   ──►   12
```

## Why it pays off

Folding name-resolution, type-checking, and pointer-safety into one `fits()` isn't just
tidy — it buys real things:

- **Imports come for free.** A path *is* a type's identity, so importing is just a trie
  lookup. Diamond imports (A and B both import C) land on the same node automatically — no
  dedup, no conflict logic. The only way to clash is two files claiming one path, which the
  filesystem already forbids.
- **Pointer safety *is* type-checking.** Nullability (`Option<T>`) and direction
  (`Ptr`/`MutPtr`) are axes of the type, so a null flowing into a non-null — or a read-only
  pointer into a mutable slot — is caught by the *same* `fits()` that checks everything
  else. No separate null pass, no borrow checker to write or keep in sync.
- **Zero runtime cost.** The discipline is a compile-time fiction: `Ptr` erases to
  `const*`, `Option` to a bare pointer. Once it checks, the emitted C carries no tags and
  no guards — and `cc` re-verifies the const-correctness, a free second opinion.
- **It stays tiny.** The whole checker is one trie + a ~20-line `fits()`. That smallness
  *is* the result: three problems folded into one.

The trade: it leans on **nominal** identity (a type *is* its path) and asks you to write
every pointer's direction and nullability down. In return you delete two entire passes.

## The whole compiler, in four ideas

**1. One trie is the namespace, the import resolver, and the conflict checker.**
A path *is* an identity, so a diamond import resolves to a single node for free —
the only possible name conflict is two files claiming the same path.

```
root
├─ core
│  └─ vec
│     └─ Vec ─────── struct { len:i32, cap:i32 }   ← the holotype for "core.vec.Vec"
├─ ops
│  ├─ len ────────── fn (Ptr<Vec>) i32
│  └─ cap ────────── fn (Ptr<Vec>) i32
└─ main
   ├─ area ───────── fn (Ptr<Vec>) i32
   └─ main ───────── fn () i32
```

**2. Pointers are types. `fits()` is the only logic outside the trie.**
Direction (`Ptr`/`MutPtr`/`RawPtr`) and nullability (`Option<T>`, no bare null)
are axes of the type, so the same check that resolves everything else also locks
pointer direction and rejects nulls — no separate null pass, no separate borrow pass.

```
 DIRECTION              NULLABILITY
   MutPtr   (subtype)     Option<T>   nullable
     |                       |
    Ptr      read-only       T         nonnull
```

```
fits(given, want):
    nonnull T    where Option<T> wanted   -> ok      (T ≤ Option<T>)
    Option<T>    where plain    T wanted   -> REJECT  (the null guard)
    MutPtr<T>    where Ptr<T>   wanted     -> ok      (MutPtr ≤ Ptr)
    Ptr<T>       where MutPtr<T> wanted    -> REJECT  (direction locked)
```

**3. The type system erases to plain C.** `Ptr` → `const *`, `MutPtr` → `*`,
`Option<ptr>` → a bare pointer. All safety is proven *before* codegen, so the
output is zero-overhead and the C compiler re-checks the const-correctness for free.

**4. `build.zen` is the build graph, written in the language** (like Zig's `build.zig`):

```zen
{ Builder, BuildConfig, BuildError, Executable, Test } = @builtin.build

build = (b: Builder) Result<BuildConfig, BuildError> {
    b.add(Executable {
        name: "vecdemo",
        main: "main.zen",
        out_dir: "build",
    })
    .Ok(b.config())
}
```

## Run it

```sh
pip install -r requirements.txt        # tree_sitter (front end)
python3 -m holotype build examples     # read build.zen -> check -> emit C -> cc -> run
python3 -m holotype check examples     # type-check report + emit a C lib
```

Tests (the lattice is the whole safety argument, so it's the most-covered part):

```sh
pip install -r requirements-dev.txt    # adds pytest
python3 -m pytest                       # fits() lattice + laws, infer(), trie, parser,
                                        # Zen //~ PASS/FAIL fixtures, end-to-end build
```

The first run compiles the tree-sitter grammar (`tree-sitter-zen/src/parser.c`) into
`build/zen.so` with `cc` — no Node needed at runtime, only to regenerate the grammar.

Ill-typed functions are **excluded from codegen** — `holotype build` reports them and
builds only what type-checks:

```
── type checks ──
   PASS ✓  main.area
   FAIL ✗  main.bad       Option<Ptr<Vec>>  ⊀  Ptr<Vec>
   FAIL ✗  main.dirbad    Ptr<Vec>          ⊀  MutPtr<Vec>
   PASS ✓  main.main
   ...
vecdemo -> 12
```

## Layout

| file | role |
|---|---|
| `tree-sitter-zen/grammar.js` | the real grammar (a tree-sitter parser generator) |
| `holotype/parser.py` | converts the tree-sitter parse tree → AST |
| `holotype/ast.py`    | AST — dataclasses + enums (`Dir`, `Prim`; no stringly-typed kinds) |
| `holotype/types.py`  | the trie + `fits()` pointer lattice + `infer()` (the one type space) |
| `holotype/lower.py`  | transcribe to C (the type system erases here) |
| `holotype/main.py`   | driver + `build.zen` interpreter |
| `tests/`             | pytest suite — `fits()` lattice + laws, `infer()`, trie, parser, end-to-end build |
| `tests/cases/*.zen`  | type-checker tests written **in Zen** — inline `//~ PASS`/`//~ FAIL` verdicts |

(`ast.py` and `types.py` are safe as classic names because they live in a package —
stdlib `import ast` / `import types` still resolve to the real ones.)

The front end is a real **tree-sitter** grammar — a method call is just a `call`
whose callee is a field access, so there's no special rule for it. The language
now covers structs, **user enums** (lowered to C tagged unions, ctor `.Variant(x)`
type-checked against the expected type), **generic functions** (`id<T>` — type-args
inferred by unification at the call site, then **monomorphized** to specialized C),
**traits / constrained generics** (`trait`, `impl … for …`, `<T: Trait>` — bound
methods dispatch to the concrete impl at monomorphization; an unsatisfied bound is
a type error), **`match`** with payload-binding and exhaustiveness checking (the
arm `.Some(v)` narrows the payload), `Ptr/MutPtr/RawPtr` and `Option`,
`i32`/`i64`/`bool` with `i32→i64` widening, numeric-only `+ - *`, `==`, and
`x := v` let-bindings. Type errors carry `ns:line:col`. Still a subset of Zen (no
`::=`, higher-kinded types, or generic *data types* with literal type-args yet) —
the point is to test the type idea, which is exactly why the parser is someone
else's grammar generator rather than hand-rolled.

`build.zen` can declare a `Test { root: "test.zen" }`; `holotype build` then
compiles that root with the project and runs each no-arg `bool` test, printing
PASS/FAIL (SKIP if it doesn't type-check).

Inspired by treeform's [jsony](https://github.com/treeform/jsony) (parse straight
into typed objects, hook-based) and the syntax of
[zenlang](https://github.com/lantos1618/zenlang).
