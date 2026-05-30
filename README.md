# zen-holotype

A tiny compiler for a small [Zen](https://github.com/lantos1618/zenlang)-flavoured
language, built to test one idea: **if everything is a type, then module imports,
type-checking, and pointer safety are all the _same_ operation** — checking that
signatures fit in one shared space.

> In taxonomy a *holotype* is the single specimen that defines a name. Here,
> every path resolves to exactly **one** canonical node — and diamond imports
> collapse onto it.

It takes the Zen syntax, type-checks it through one trie, and emits C.

```
examples/*.zen  ──parse──►  one trie  ──infer + fits──►  C  ──cc──►  ./vecdemo  ──►  12
```

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

The first run compiles the tree-sitter grammar (`tree-sitter-zen/src/parser.c`) into
`build/zen.so` with `cc` — no Node needed at runtime, only to regenerate the grammar.

Ill-typed functions are **excluded from codegen** — `zenc build` reports them and
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

(`ast.py` and `types.py` are safe as classic names because they live in a package —
stdlib `import ast` / `import types` still resolve to the real ones.)

The front end is a real **tree-sitter** grammar — a method call is just a `call`
whose callee is a field access, so there's no special rule for it. It's still a
subset of Zen (no `::=`, pattern matching, or generics-with-params yet). The point
is to test the type idea, not to write a parser — which is exactly why the parser is
someone else's grammar generator rather than hand-rolled.

Inspired by treeform's [jsony](https://github.com/treeform/jsony) (parse straight
into typed objects, hook-based) and the syntax of
[zenlang](https://github.com/lantos1618/zenlang).
