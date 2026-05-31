"""Zen v2 AST — one structure. Everything is a Decl; a Record is a bag of Decls.

Reflecting the grammar: a decl is `name [*] [<tparams>] [: type] [(= | :=) value]`.
Types and values share most node kinds (a Record is both a product type and a
product value), which is the whole point — `:` declares, `=`/`:=` provide.
"""
from __future__ import annotations
from dataclasses import dataclass, field


# ── the one declaration ──────────────────────────────────────────────────────
@dataclass
class Decl:
    name: tuple                 # path segments: ("main",) or ("Circle", "Area")
    pub: bool = False
    tparams: tuple = ()         # ((name, bound|None), …)
    type: object = None         # a type node, or None
    bind: str | None = None     # "=" (const) · ":=" (mutable) · None (requirement)
    value: object = None        # a value node, or None


# ── types ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class NamedT:
    path: tuple                 # ("vec", "Vec")
    args: tuple = ()            # type args


@dataclass(frozen=True)
class PtrT:
    dir: str                    # "Ptr" | "MutPtr" | "RawPtr"
    pointee: object


@dataclass(frozen=True)
class FnT:                      # a function signature (a requirement's type)
    params: tuple
    ret: object


# ── values (Record/Sum/Fn) ───────────────────────────────────────────────────
@dataclass
class Record:                   # a product — also serves as a record TYPE
    decls: tuple                # tuple[Decl]


@dataclass
class Sum:                      # a | b | c
    variants: tuple             # ((name, payload|None), …)


@dataclass
class Fn:
    params: tuple               # ((name, type), …)
    ret: object                 # type | None (inferred)
    body: tuple                 # tuple[stmt]  (Decl for a local bind, or an Expr)


# ── expressions ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Lit:
    n: int


@dataclass(frozen=True)
class Str:
    s: str


@dataclass(frozen=True)
class Bool:
    b: bool


@dataclass(frozen=True)
class Var:
    name: str                   # a bare identifier (incl. @self, @Self)


@dataclass(frozen=True)
class Field:
    obj: object
    name: str


@dataclass(frozen=True)
class Call:
    fn: object
    args: tuple = ()


@dataclass(frozen=True)
class Bin:
    op: str
    l: object
    r: object


@dataclass(frozen=True)
class RecordLit:
    type: str                   # the named type being built: Vec { … }
    fields: tuple = ()          # ((name, expr), …)


@dataclass(frozen=True)
class Match:
    subj: object
    arms: tuple = ()            # ((pat, body), …); pat is Ctor(name, bind?) | Lit | Bool | "_"


@dataclass(frozen=True)
class Ctor:                     # a match-arm pattern: Name or Name(bind)
    name: str
    bind: str | None = None
