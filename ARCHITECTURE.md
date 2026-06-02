# Architecture

How the compiler is shaped, and the path from Python-hosted to self-hosting. For *what*
the language does see [FEATURES](FEATURES.md); for the *why* see [README](README.md); for
the long-term language see [VISION](VISION.md).

## The pipeline

```
.zen source
  → parse            (tree-sitter grammar → ast.py dataclasses)        zen/parser.py
  → build_namespace  (one trie: the namespace + import resolver)       zen/resolve.py
  → build_scopes     (per-file local-name → qualified-path map)        zen/resolve.py
  → resolve          (resolve refs, check visibility, desugar loops)   zen/resolve.py
  → fold_comptime    (evaluate comptime(...) into constants)           zen/comptime.py
  → run_emits        (run @emit generators, graft the spliced decls)   zen/main.py + comptime.py
  → check            (infer types, fits() at every call site)          zen/types.py
  → emit_c           (monomorphize reachable, lower to C)              zen/emit.py + lower.py
  → cc               (the system C compiler)
```

Only well-typed functions are lowered. An executable emits only what's reachable from its
entry (dead-code elimination); a `check` build emits every function that type-checks.

## The three ASTs — by role, not by accident

There are three AST/value models. They are **not** redundant; they serve three different
roles. Conflating them is the standing risk, so the boundaries are explicit:

| model | where | role |
|---|---|---|
| **`ast.py`** dataclasses | `zen/ast.py` | the **source AST** — what the host parser produces and the checker/lowerer consume. The Python compiler's working representation. |
| **reified `Ast`** | `zen/prelude/derive.zen` | the **comptime metaprogramming model** — zen *values* a comptime generator reads/builds, so `@emit(gen(reflect(T)))` can splice real declarations. The language reflecting on itself. |
| **`std.genc` `Expr/Stmt/Decl`** | `zen/std/genc.zen` | the **backend IR** — what the *Zen-written* code generator (`genC`) lowers to C at runtime. This is the self-hosted equivalent of `lower.py`/`emit.py`. |

**Decision: `std.genc` is the backend IR (lowering), written in Zen** — not a second source
AST. `std.parse` (the Zen-written parser) targets it directly today for the subset it
covers, so front (lexer/parser) and back (genc) meet there into a tiny but complete
self-hosted compiler.

## The bootstrap path

The goal is to move codegen — then the whole front end — into Zen, without breaking the
working Python compiler, gated by parity tests every step:

1. **Backend in Zen** — `std.genc` walks an AST and emits C at runtime. ✅ (a subset:
   scalars, structs, enums + `match`, pointers, control flow, recursion).
2. **Front end in Zen** — `std.lex` (lexer) + `std.parse` (recursive-descent parser),
   building `std.genc`'s AST. ✅ for arithmetic + `let`; the loop closes:
   `"(1 + 2) * 3"` → scan → parse → genC → `cc` → `f() == 9`, all in Zen.
3. **Parity gates** (before retiring any Python) — `tests/test_parity.py` (Zen `genC` vs
   Python `emit_c` agree), `tests/test_lex_parity.py` (`std.lex` vs tree-sitter tokens),
   and `zen/astdump.py` / `zen dump` (a canonical, formatting-invariant AST hash — the
   reference a Zen parser is diffed against).
4. **Grow the Zen front end up to the full `ast.py`** (the real remaining gap), then
   **bootstrap**: Python compiles the Zen compiler to C, the compiled `zenc` re-emits
   byte-identical C (a deterministic **fixpoint**), commit the C, release the binary, and
   retire the host.

What's intentionally deferred: a typed IR boundary (lowering still re-runs inference — it's
entangled with monomorphization), deleting Python, new backends (JS/wasm), and the future
keyword-free "one structure" syntax.
