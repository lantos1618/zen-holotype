"""The Zen bootstrapper's AST.

`bootstrap/CONTRACT.md` is frozen and this file is that contract as code. Five
agents work against these names at once, so:

    * the content fields of every node are EXACTLY the ones CONTRACT.md lists,
      in the order it lists them, and they are positional;
    * `span`, `leading` and `trailing` are keyword-only, so a node reads
      `Struct("Vec", True, tparams, fields, consts, span=sp)`;
    * every node is frozen. Nothing is ever mutated. `replace(node, **kw)`
      returns a new one.

Positions and trivia are attached by `bootstrap/cst.py` at parse time or never
(`PLAN.md` 0.2). The formatter is `parse |> print` over `leading` / `trailing`,
so nothing downstream may drop them.

ONE node is not in CONTRACT.md and is announced here rather than smuggled in:

    Record(entries)   an anonymous `{ name: value, .. }` literal in argument
                      position — `b.exe("x", { src: .., deps: .. })`,
                      `DESIGN.md:981`. It has the same entries an `Impl` body
                      has (`Arg` for a supplied value, `Function` for a
                      supplied method) and no other node in the contract can
                      hold it.

Four encodings carry things CONTRACT.md has no node for. They add no class and
no field, and each is a place to look first if something reads oddly:

    assignment          `self.len = self.len + 1;`  ->  ExprStmt(Binary("=", ..))
    unit value          `Ok(())`                    ->  Literal("unit", "()")
    a `+` bound list    `<K: Eq + Hash>`            ->  TParam(bound=Union(..))
                        (`+` is an intersection; `Union` is a stopgap here)
    variadic            `args: ...`                 ->  Named("...", ())
    parentheses         `(a + b) * c`               ->  dropped; the printer
                        re-inserts them from precedence

`Struct.fields` is heterogeneous, exactly as `Impl.entries` is: a storage field
is a `Field`, a method is a `Function` carrying its `form`. DESIGN.md's "there
are no traits, only structs — a struct whose fields happen to be functions" is
why they share one tuple, and `Function` rather than a function-typed `Field`
is what keeps `<T>` on a generic method and the required/sealed/default/hook
distinction from being lost. `Struct.consts` holds `MAX: i32 = 2147483647`.
"""

from __future__ import annotations

import os
import sys

# --- stdlib shield ---------------------------------------------------------
# CONTRACT.md fixes this file's name and `ast` is also a standard-library
# module. Run as `python3 bootstrap/bootstrap.py`, bootstrap/ lands on
# sys.path[0] and THIS file answers every `import ast` in the process —
# including the one `inspect`, and therefore `dataclasses`, performs. So when
# we are the one answering to that name, load the real module first, under its
# real name, then take the name back. `python3 -m bootstrap.bootstrap` from the
# repository root avoids the question entirely and is the recommended form.
if __name__ == "ast" and sys.modules.get("ast") is sys.modules.get(__name__):
    _self = sys.modules.pop("ast")
    _here = os.path.dirname(os.path.abspath(__file__))
    _path = sys.path[:]
    sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _here]
    try:
        import ast as _stdlib_ast  # noqa: F401  the real one
        import dataclasses  # noqa: F401  wants inspect, which wants the real ast
    finally:
        sys.path[:] = _path
        sys.modules["ast"] = _self

import dataclasses
from dataclasses import dataclass, field as _field
from typing import Any, Iterator

__all__ = [
    "Span",
    "Trivia",
    "Diag",
    "Node",
    # declarations
    "Module",
    "Import",
    "Struct",
    "Enum",
    "Alias",
    "Function",
    "Impl",
    "Field",
    "Const",
    "Variant",
    "Param",
    "TParam",
    # types
    "Named",
    "Union",
    "FnType",
    "ArrayType",
    "Unit",
    "Infer",
    # expressions and statements
    "Block",
    "Let",
    "ExprStmt",
    "Call",
    "Arg",
    "Record",
    "Member",
    "Index",
    "Binary",
    "Unary",
    "Consume",
    "Lambda",
    "Match",
    "Arm",
    "Try",
    "Literal",
    "ArrayLit",
    "FixedArray",
    "Path",
    "MetaCall",
    "ScopeRef",
    # patterns
    "PatVariant",
    "PatWild",
    "PatLit",
    # helpers
    "walk",
    "replace",
    "FORMS",
]

# `Function.form`, from DESIGN.md's method table. Written out so a typo is a
# KeyError here rather than a wrong answer in sema.
FORMS = ("required", "sealed", "default", "hook")


# ---------------------------------------------------------------------------
# positions and trivia
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Span:
    """A half-open source range. `gen_c` emits these, so `file` is relative to
    the compilation root, always — an absolute path breaks determinism."""

    file: str
    start: tuple  # (line, col), 1-based; col is a BYTE offset
    end: tuple  # (line, col), exclusive

    def __str__(self) -> str:
        return f"{self.file}:{self.start[0]}:{self.start[1]}"


@dataclass(frozen=True)
class Trivia:
    span: Span
    text: str
    kind: str  # "line_comment" | "block_comment" | "blank"


@dataclass(frozen=True)
class Diag:
    """Collected, never raised: one bad file must not stop the run."""

    span: Span
    message: str
    notes: tuple = ()  # (Span, str) — an impl collision names BOTH impls

    def __str__(self) -> str:
        return f"{self.span}: {self.message}"


@dataclass(frozen=True)
class Node:
    span: Span = _field(kw_only=True)
    leading: tuple = _field(default=(), kw_only=True)
    trailing: tuple = _field(default=(), kw_only=True)


# ---------------------------------------------------------------------------
# declarations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Module(Node):
    name: str
    path: str
    decls: tuple
    imports: tuple


@dataclass(frozen=True)
class Import(Node):
    names: tuple  # ((name, exported), ..) — `exported` is the `*`
    path: str


@dataclass(frozen=True)
class Struct(Node):
    name: str
    exported: bool
    tparams: tuple
    fields: tuple  # Field — storage AND methods (a method is a function-typed field)
    consts: tuple  # Const — `MAX: i32 = 2147483647`, read as `i32.MAX`


@dataclass(frozen=True)
class Enum(Node):
    name: str
    exported: bool
    tparams: tuple
    variants: tuple


@dataclass(frozen=True)
class Alias(Node):
    name: str
    exported: bool
    target: Any  # Type


@dataclass(frozen=True)
class Function(Node):
    name: str
    exported: bool
    tparams: tuple
    params: tuple
    ret: Any  # Type
    body: Any  # Block | None
    form: str  # one of FORMS


@dataclass(frozen=True)
class Impl(Node):
    target: str
    trait: str
    entries: tuple  # Arg (a supplied value) | Function (a supplied method)


@dataclass(frozen=True)
class Field(Node):
    name: str
    exported: bool
    ty: Any  # Type
    mutable: bool  # the `::`
    default: Any  # Expr | None


@dataclass(frozen=True)
class Const(Node):
    name: str
    exported: bool
    ty: Any  # Type | None — None when no type was written
    value: Any  # Expr


@dataclass(frozen=True)
class Variant(Node):
    name: str
    payload: Any  # Type | None


@dataclass(frozen=True)
class Param(Node):
    name: str
    ty: Any  # Type | None — None only in a closure
    mutable: bool  # the `::` on a receiver


@dataclass(frozen=True)
class TParam(Node):
    name: str
    bound: Any  # Type | None


# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Named(Node):
    name: str
    args: tuple


@dataclass(frozen=True)
class Union(Node):
    members: tuple  # flat, never nested


@dataclass(frozen=True)
class FnType(Node):
    params: tuple  # Param — names REQUIRED
    ret: Any


@dataclass(frozen=True)
class ArrayType(Node):
    elem: Any
    count: Any  # Expr — comptime


@dataclass(frozen=True)
class Unit(Node):
    pass


@dataclass(frozen=True)
class Infer(Node):
    pass


# ---------------------------------------------------------------------------
# expressions and statements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Block(Node):
    stmts: tuple
    value: Any  # Expr | None — the tail expression, the one with no `;`


@dataclass(frozen=True)
class Let(Node):
    name: str
    ty: Any  # Type | None
    mutable: bool
    value: Any


@dataclass(frozen=True)
class ExprStmt(Node):
    expr: Any


@dataclass(frozen=True)
class Call(Node):
    callee: Any
    targs: tuple
    args: tuple  # Arg


@dataclass(frozen=True)
class Arg(Node):
    name: Any  # str | None — the name in `width: expr`
    value: Any


@dataclass(frozen=True)
class Record(Node):
    """NOT in CONTRACT.md — see the module docstring."""

    entries: tuple  # Arg | Function


@dataclass(frozen=True)
class Member(Node):
    base: Any
    name: str


@dataclass(frozen=True)
class Index(Node):
    base: Any
    index: Any


@dataclass(frozen=True)
class Binary(Node):
    op: str  # includes "+%" "-%" "*%", and "=" for an assignment
    lhs: Any
    rhs: Any


@dataclass(frozen=True)
class Unary(Node):
    op: str  # "!" "-" "&"
    operand: Any


@dataclass(frozen=True)
class Consume(Node):
    operand: Any


@dataclass(frozen=True)
class Lambda(Node):
    params: tuple
    ret: Any  # Type | None
    body: Any  # Block


@dataclass(frozen=True)
class Match(Node):
    scrutinee: Any
    arms: tuple


@dataclass(frozen=True)
class Arm(Node):
    pattern: Any
    body: Any


@dataclass(frozen=True)
class Try(Node):
    """`.try()` — the non-local-exit intrinsic, NOT a Call."""

    operand: Any


@dataclass(frozen=True)
class Literal(Node):
    kind: str  # "int" "float" "str" "char" "bool" (+ "unit" for `()`)
    text: str


@dataclass(frozen=True)
class ArrayLit(Node):
    elems: tuple


@dataclass(frozen=True)
class FixedArray(Node):
    ty: Any  # ArrayType
    elems: tuple


@dataclass(frozen=True)
class Path(Node):
    name: str  # a bare identifier


@dataclass(frozen=True)
class MetaCall(Node):
    arg: Any  # Expr | Type


@dataclass(frozen=True)
class ScopeRef(Node):
    pass


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatVariant(Node):
    name: str
    binder: Any  # str | None — "_" when the payload is discarded


@dataclass(frozen=True)
class PatWild(Node):
    pass


@dataclass(frozen=True)
class PatLit(Node):
    kind: str
    text: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def children(node: Node) -> Iterator[Node]:
    """Direct child nodes, in field order. Trivia is not a Node and is skipped,
    which is what keeps `walk` from wandering into comments."""
    for f in dataclasses.fields(node):
        if f.kw_only:  # span / leading / trailing
            continue
        value = getattr(node, f.name)
        if isinstance(value, Node):
            yield value
        elif isinstance(value, (tuple, list)):
            for item in value:
                if isinstance(item, Node):
                    yield item


def walk(node: Node) -> Iterator[Node]:
    """Pre-order over the tree: the node, then every descendant. Order is
    field order, which is source order, which is what `gen_c` needs it to be
    (`CONTRACT.md`: never a set, never a dict's insertion order)."""
    yield node
    for child in children(node):
        yield from walk(child)


def replace(node: Node, **kw: Any) -> Node:
    """A new node with some fields changed. Nodes are frozen; this is the only
    way to 'edit' one."""
    return dataclasses.replace(node, **kw)
