"""AST: dataclasses + enums. Mirrors Zen surface syntax.

Named things (Struct/Enum/Fn) become trie nodes.
Structural things compose from the Type union (PrimT/NameT/PtrT).
Expressions compose from the Expr union (Lit/Var/Field/Bin/Call).
No stringly-typed kinds — directions and primitives are enums.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


# ───────────────────────── enums (no "ptr" strings) ─────────────────────────
class Dir(Enum):
    READ = "Ptr"      # read-only, lowers to  const T*   (Zen: Ptr<T>)
    MUT  = "MutPtr"   # read + write                      (Zen: MutPtr<T>)
    RAW  = "RawPtr"   # unchecked escape hatch            (Zen: RawPtr<T>)


class Prim(Enum):
    I32  = "i32"
    I64  = "i64"
    BOOL = "bool"
    VOID = "void"


# ───────────────────────── types (the structural space) ─────────────────────
@dataclass(frozen=True)
class PrimT:
    prim: Prim


@dataclass(frozen=True)
class NameT:
    """Nominal, possibly-generic ref. After resolution `path` is fully-qualified,
    so equality of NameT == sameness-of-meaning."""
    path: str
    args: tuple = ()          # tuple[Type, ...]


@dataclass(frozen=True)
class PtrT:
    """A pointer IS a type. Direction is locked in an enum, not a comment."""
    dir: Dir
    pointee: object           # Type


@dataclass(frozen=True)
class TVar:
    """A type parameter standing in for an unknown type, e.g. the `T` of Box<T>.
    Resolved away by substitution once a concrete type-arg is known."""
    name: str


# ───────────────────────── expressions ──────────────────────────────────────
@dataclass(frozen=True)
class Lit:
    n: int


@dataclass(frozen=True)
class Bool:
    b: bool


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Field:
    obj: object               # Expr
    name: str


@dataclass(frozen=True)
class Bin:
    op: str                   # + - *
    l: object                 # Expr
    r: object                 # Expr


@dataclass(frozen=True)
class Call:
    callee: str
    args: tuple = ()          # tuple[Expr, ...]


@dataclass(frozen=True)
class Str:
    s: str


@dataclass(frozen=True)
class StructLit:
    type: str                 # type name (resolved later)
    fields: tuple = ()        # tuple[(name, Expr), ...]


@dataclass(frozen=True)
class MethodCall:
    recv: object              # Expr  (e.g. the builder `b`)
    method: str
    args: tuple = ()


@dataclass(frozen=True)
class EnumCtor:
    name: str                 # leading-dot ctor, e.g. .Ok(x)
    args: tuple = ()


@dataclass(frozen=True)
class Let:
    name: str                 # x := value   (a local binding; type inferred)
    value: object             # Expr


# ───────────────────────── declarations (each = one trie node) ──────────────
@dataclass
class Field_:                  # struct field (distinct from the Field expr)
    name: str
    type: object              # Type


@dataclass
class Struct:
    name: str
    fields: list              # list[Field_]
    pub: bool = False
    tparams: tuple = ()        # type-parameter names, e.g. ("T",)


@dataclass
class Variant:
    name: str
    payload: object = None    # Type | None


@dataclass
class EnumDecl:
    name: str
    variants: list            # list[Variant]
    pub: bool = False
    tparams: tuple = ()        # type-parameter names


@dataclass
class Param:
    name: str
    type: object              # Type


@dataclass
class Fn:
    name: str
    params: list              # list[Param]
    ret: object               # Type
    body: object = None       # Expr | None
    pub: bool = False
    tparams: tuple = ()        # type-parameter names


@dataclass
class Import:
    names: list               # list[str]
    module: str               # dotted path, e.g. "core.vec"


@dataclass
class File:
    ns: str                   # namespace from path: core/vec.zen -> "core.vec"
    imports: list
    decls: list
    scope: dict = field(default_factory=dict)   # local name -> fully-qualified path
