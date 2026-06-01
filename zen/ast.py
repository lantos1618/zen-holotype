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
    U8   = "u8"       # a byte — the substrate for buffers and strings
    BOOL = "bool"
    VOID = "void"
    STR  = "str"      # a comptime string (names/ops in the reified AST); C `const char*`


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
    pointee: Type


@dataclass(frozen=True)
class TVar:
    """A type parameter standing in for an unknown type, e.g. the `T` of Box<T>.
    Resolved away by substitution once a concrete type-arg is known."""
    name: str


@dataclass(frozen=True)
class SliceT:
    """A slice `[T]` — a (ptr, len) view. Lowers to `struct { T* ptr; int64_t len; }`."""
    elem: Type


@dataclass(frozen=True)
class FnT:
    """A closure/function type — `(A, T) A`. Only ever a parameter type: a function
    that takes one is an *inline template* (monomorphized + inlined per call site,
    never a C function pointer). So `FnT` has no runtime C type — it reaches lower.py
    only to be recognised, never emitted."""
    params: tuple = ()        # tuple[Type, ...]
    ret: "Type | None" = None  # always set in practice (a function type has a result)


# ───────────────────────── expressions ──────────────────────────────────────
# `pos` is the (row, col) of the node in source, set by the parser. It's excluded
# from equality/repr so it never affects type comparisons — purely for diagnostics.
_pos = lambda: field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Lit:
    n: int
    pos: object = _pos()


@dataclass(frozen=True)
class Bool:
    b: bool
    pos: object = _pos()


@dataclass(frozen=True)
class Var:
    name: str
    pos: object = _pos()


@dataclass(frozen=True)
class Field:
    obj: Expr
    name: str
    pos: object = _pos()


@dataclass(frozen=True)
class SliceLit:
    elems: tuple = ()         # tuple[Expr] — [a, b, c]
    pos: object = _pos()


@dataclass(frozen=True)
class Index:
    seq: Expr                 # a slice
    idx: Expr                 # numeric
    pos: object = _pos()


@dataclass(frozen=True)
class Bin:
    op: str                   # + - * == < > <= >= && ||
    l: Expr
    r: Expr
    pos: object = _pos()


@dataclass(frozen=True)
class Not:
    operand: Expr             # logical !
    pos: object = _pos()


@dataclass(frozen=True)
class Call:
    callee: str
    args: tuple = ()          # tuple[Expr, ...]
    pos: object = _pos()


@dataclass(frozen=True)
class Str:
    s: str


@dataclass(frozen=True)
class StructLit:
    type: str                 # type name (resolved later)
    fields: tuple = ()        # tuple[(name, Expr), ...]
    pos: object = _pos()


@dataclass(frozen=True)
class MethodCall:
    recv: object              # Expr  (e.g. the builder `b`)
    method: str
    args: tuple = ()


@dataclass(frozen=True)
class EnumCtor:
    name: str                 # leading-dot ctor, e.g. .Ok(x)
    args: tuple = ()
    pos: object = _pos()


@dataclass(frozen=True)
class Let:
    name: str                 # x := value   (a local binding; type inferred)
    value: Expr
    pos: object = _pos()


@dataclass(frozen=True)
class Assign:
    target: object            # an lvalue: Var (reassign local) or Field (set a struct field)
    value: object             # Expr
    pos: object = _pos()


@dataclass(frozen=True)
class While:
    # the structured loop PRIMITIVE — lowers to C `for(; cond; step)`. `step` runs
    # each iteration (incl. on continue) and keeps it a clean counted loop the C
    # compiler can auto-vectorize. Surface: @while(cond){body} (step is None);
    # the `loop` sugar desugars onto it (with a step for the count form).
    cond: object              # Expr (bool)
    body: tuple = ()          # tuple[stmt]
    step: object = None       # optional stmt run each iteration (the for-loop's 3rd slot)
    pos: object = _pos()


@dataclass(frozen=True)
class Loop:
    # the everyday surface — desugared onto While before check (see desugar_loops).
    count: object             # Expr (numeric count) — None for an iterless loop((h){…})
    params: tuple = ()        # (handle,) or (handle, index) — binding names
    body: tuple = ()          # tuple[stmt]
    pos: object = _pos()


@dataclass(frozen=True)
class Closure:
    # an anonymous function value `(a, x) { a + x }` — only ever a call argument to
    # a template's FnT param. Params get their types from the expected FnT (no
    # annotations); free variables are captured from the enclosing scope. It is
    # inlined at the call site, so captures (read AND mutate) just resolve there.
    params: tuple = ()        # tuple[str] — parameter names
    body: tuple = ()          # tuple[stmt]
    pos: object = _pos()


@dataclass(frozen=True)
class Arm:
    variant: str | None       # ctor variant name (None for a literal/wildcard arm)
    binding: str | None       # payload binding, e.g. the `v` of .Some(v)
    body: Expr
    lit: object = None        # literal pattern value (Lit/Bool); None for ctor/wildcard


@dataclass(frozen=True)
class Match:
    subject: Expr
    arms: tuple = ()          # tuple[Arm, ...]
    pos: object = _pos()


# ───────────────────────── declarations (each = one trie node) ──────────────
@dataclass
class Field_:                  # struct field (distinct from the Field expr)
    name: str
    type: Type


@dataclass
class Struct:
    name: str
    fields: list              # list[Field_]
    pub: bool = False
    tparams: tuple = ()        # type-parameter names, e.g. ("T",)


@dataclass
class Variant:
    name: str
    payload: "Type | None" = None


@dataclass
class EnumDecl:
    name: str
    variants: list            # list[Variant]
    pub: bool = False
    tparams: tuple = ()        # type-parameter names


@dataclass
class Param:
    name: str
    type: Type


@dataclass
class Fn:
    name: str
    params: list              # list[Param]
    ret: "Type | None"        # None until inferred from the body
    body: object = None       # list[Expr] | None
    pub: bool = False
    tparams: tuple = ()        # type-parameter names
    bounds: dict = field(default_factory=dict)   # tparam name -> trait path (the <T: Area>)
    scope: dict | None = None  # defining scope (set in resolve; for return-type inference)
    extern: bool = False       # a foreign C binding: a bodyless fn, C symbol = the bare name


@dataclass
class MethodSig:
    name: str
    params: tuple             # tuple[Type] (types only; Self is the implementor)
    ret: Type


@dataclass
class TraitDecl:
    name: str
    methods: list             # list[MethodSig]
    pub: bool = False


@dataclass
class Impl:
    trait: str                # trait name (resolved to a path later)
    type: str                 # implementing type name (resolved later)
    methods: list             # list[Fn]


@dataclass
class Emit:
    value: object             # Expr — a comptime (Ast)->Ast call; its result is spliced in
    pos: object = None


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


# ───────────────────────── the closed unions ────────────────────────────────
# The structural type space and the expression grammar, named so the checker's
# annotations document exactly which nodes are legal (and mypy can check them).
Type = PrimT | NameT | PtrT | TVar | SliceT | FnT
Expr = (Lit | Bool | Var | Field | Bin | Not | Call | Str | StructLit
        | MethodCall | EnumCtor | Let | Match | Closure)
