# Lint-parser contract

This was the Python bootstrapper's AST, frozen before any of it was written. The bootstrapper is gone — `src/` compiles itself, and the corpus, the must-fail suite and the fixpoint all run against `./zen`. What survives is the FRONT of it: a tree-sitter parse lowered to these nodes, which is how the lint gates read `src/` with the real grammar instead of a regex.

**Nothing here is Zen's design.** `docs/DESIGN.md` is the law and `src/AST_CONTRACT.md` is the AST that ships; this is a reader, and where it disagrees with either, it is the bug.

---

## Module boundaries

```
tools/parse/cst.py    grammar/ parse tree  ->  AST nodes  (owns tree-sitter node names)
tools/parse/ast.py    the node definitions below          (owns the dataclasses)
tools/parse/lex.py    the scanner, for diagnostics only
```

`cst.py` imports the other two; neither imports it. The consumers are `scripts/style.py`, `scripts/ufcs_collisions.py` and `scripts/signatures.py`.

---

## AST — `tools/parse/ast.py`

Every node is a frozen dataclass with a `span`. **No node is ever mutated**; transformations return new nodes.

```python
@dataclass(frozen=True)
class Span:
    file: str          # relative to the compilation root, always. gen_c emits these.
    start: tuple       # (line, col) 1-based, col is a BYTE offset
    end: tuple         # half-open

@dataclass(frozen=True)
class Node:
    span: Span
    leading: tuple = ()    # Trivia attached before this node
    trailing: tuple = ()   # Trivia on the same line after it

@dataclass(frozen=True)
class Trivia:
    span: Span
    text: str
    kind: str          # "line_comment" | "block_comment" | "blank"
```

Trivia attaches at parse time or never (`PLAN.md` §0.2). The formatter is `parse |> print` over these fields.

### Declarations

```python
Module      (name: str, path: str, decls: tuple, imports: tuple)
Import      (names: tuple[tuple[str, bool]], path: str)   # (name, exported) — the `*`
Struct      (name: str, exported: bool, tparams: tuple, fields: tuple, consts: tuple)
Enum        (name: str, exported: bool, tparams: tuple, variants: tuple)
Alias       (name: str, exported: bool, target: "Type")
Function    (name: str, exported: bool, tparams: tuple, params: tuple,
             ret: "Type", body: "Block | None", form: str)
Impl        (target: str, trait: str, entries: tuple)

Field       (name: str, exported: bool, ty: "Type", mutable: bool, default: "Expr | None")
Const       (name: str, exported: bool, ty: "Type", value: "Expr")   # Type.NAME
Variant     (name: str, payload: "Type | None")
Param       (name: str, ty: "Type | None", mutable: bool)   # ty None only in a closure
TParam      (name: str, bound: "Type | None")
```

`Function.form` is one of `required` (`= sig`), `sealed` (`= sig {..}`), `default` (`::= sig {..}`), `hook` (`::= sig`). `Param.mutable` is the `::` on a receiver.

### Types

```python
Named       (name: str, args: tuple)          # Vec<T>, i32, @Self
Union       (members: tuple)                  # A | B — flat, never nested
FnType      (params: tuple, ret: "Type")      # params are Param, names REQUIRED
ArrayType   (elem: "Type", count: "Expr")     # [u8, 64]
Unit        ()                                # ()
Infer       ()                                # the `_` in Res<Cfg, _>
```

### Expressions and statements

```python
Block       (stmts: tuple, value: "Expr | None")
Let         (name: str, ty: "Type | None", mutable: bool, value: "Expr")
ExprStmt    (expr: "Expr")

Call        (callee: "Expr", targs: tuple, args: tuple)
Arg         (name: str | None, value: "Expr")     # name for `width: expr`
Member      (base: "Expr", name: str)
Index       (base: "Expr", index: "Expr")
Binary      (op: str, lhs: "Expr", rhs: "Expr")   # op includes "+%" "-%" "*%"
Unary       (op: str, operand: "Expr")            # "!" "-" "&"
Consume     (operand: "Expr")
Lambda      (params: tuple, ret: "Type | None", body: "Block")
Match       (scrutinee: "Expr", arms: tuple)
Arm         (pattern: "Pattern", body: "Expr")
Try         (operand: "Expr")                     # .try() — NOT a Call
Literal     (kind: str, text: str)                # "int" "float" "str" "char" "bool"
ArrayLit    (elems: tuple)
FixedArray  (ty: "ArrayType", elems: tuple)       # [i32, 4](2, 3, 5, 7)
Path        (name: str)                           # a bare identifier
MetaCall    (arg: "Expr | Type")                  # @meta(...) — special, see DESIGN
ScopeRef    ()                                    # @scope

PatVariant  (name: str, binder: str | None)       # Ok(n) / Unit / Ok(_)
PatWild     ()                                    # _
PatLit      (kind: str, text: str)                # true / false / 3
```

`.try()` is `Try`, not a method call — `DESIGN.md` makes it the non-local-exit intrinsic. Likewise `h.break(v)`: parse as `Call`, and let sema recognise it.

---

## The four decisions the grammar now depends on

These were open until today. If code disagrees with them, the code is wrong.

1. **Sum types use `|`.** `Shape = A(T) | B(T) | C`. One variant takes a leading bar: `AllocError* = | OutOfMemory`. No bar at all means `Alias`. Enums may be declared anywhere.
2. **A statement ends with `;`; a declaration does not.** No newline sensitivity.
3. **`ref`/`val`/`iso` have no syntax.** Capabilities are inferred; only `consume` is written.
4. **A struct body may hold constants**, read as `Type.NAME`. Primitives carry `MIN`/`MAX`/`BITS`.

---

## Determinism, binding on `gen_c.py`

`PLAN.md` §0.4 and `tests/determinism/` gate this:

- iterate **sorted** keys, never a dict's insertion order, never a set
- never emit a pointer value, an address, a timestamp, or an absolute path
- paths in emitted C are **relative to the compilation root** (traps print them)
- a monomorphised instance's name is a pure function of the type, never of instantiation order

Mangling is specified in `PLAN.md` §0.4. Use a scheme that cannot collide: length-prefixed components. Reserve one prefix for generated names that no mangled user name can reach — and not `__zen_` or `_Zen_`, which C11 §7.1.3 reserves to the implementation.

---

## Errors

One `Diag` type, collected not raised, so one bad file does not stop the run:

```python
@dataclass(frozen=True)
class Diag:
    span: Span
    message: str
    notes: tuple = ()      # (Span, str) — an impl collision names BOTH impls
```

`tests/must-fail/**/*.expected` is a message substring on line 1 then one `path:line:col` per line after, and **every** listed position must appear across `span` + `notes`. Format is specified in `docs/TESTING.md`.
