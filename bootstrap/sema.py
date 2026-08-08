"""Zen bootstrapper — sema.

Memoized queries over the module graph, not passes. `PLAN.md` 0.3: the same
machinery comptime memoization and the LSP both need, built once. Everything
public here is a query on the graph:

    Sema(modules).check()            -> tuple[Diag, ...]     (drives the CLI)
    sema.type_of(node, ctx)          -> Ty
    sema.defs_of(name, module)       -> tuple[decl, ...]
    sema.impls_of(type_qname)        -> tuple[ImplDef, ...]
    sema.members_of(ty)              -> dict[str, Member]
    sema.error_set_of(fn)            -> Ty
    sema.fn_instances / type_instances                       (gen_c's worklist)

Nothing is raised: every finding is a `Diag`, collected, so one bad file does
not stop the run and a file may legitimately produce several.

Imports only `ast.py` and `modules.py`, per `CONTRACT.md`. Both are read
defensively — this file never touches `cst.py` or `gen_c.py`.

The termination guard is written first and is not optional. A monomorphising
compiler that recurses on `f<T> -> f<Vec<T>>` eats the machine; so every
instantiation, of a function or of a type, goes through a depth budget with a
frame stack, and the blame lands on the call/field that WIDENS the type
argument rather than on whichever frame happened to hit the ceiling.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass, field as dcfield, replace as dataclasses_replace

# ---------------------------------------------------------------------------
# knobs
# ---------------------------------------------------------------------------

#: how deep a chain of DISTINCT instantiations may go before sema calls it
#: divergence. Mirrors the step budget the comptime evaluator gets at stage 5:
#: a bad program fails the build, it never hangs and never eats the machine.
INSTANTIATION_DEPTH_BUDGET = 24

#: `DESIGN.md`, failure model: a trap the compiler can PROVE will fire is a
#: compile error. `tests/corpus/traps/index_at_len` and `index_past_len`
#: contradict this for the index case (see the report); flip this to False to
#: let those two run as runtime traps.
PROVEN_TRAPS_ARE_ERRORS = True

#: An unexported name used across a module boundary. `modules.py` owns that
#: diagnostic (its required position is inside the import list, and the AST's
#: `Import` carries no per-name span), so sema resolves it to a silent error
#: type instead of double-reporting. Flip on if modules.py does not.
ENFORCE_IMPORT_VISIBILITY_AT_USE = False


# ---------------------------------------------------------------------------
# sibling modules, loaded defensively
#
# `bootstrap/` may be run as a package (`python -m bootstrap.bootstrap`) or as
# loose scripts (`bootstrap.py src/`). `import ast` means two different modules
# in those two worlds — the second is the stdlib's. So: try the package, then
# an already-imported module, then load the file next to this one by path, and
# in every case demand a sentinel attribute before believing it.
# ---------------------------------------------------------------------------


def _sibling(name, sentinel):
    here = os.path.dirname(os.path.abspath(__file__))
    if __package__:
        try:
            m = importlib.import_module("." + name, __package__)
            if hasattr(m, sentinel):
                return m
        except Exception:
            pass
    m = sys.modules.get(name)
    if m is not None and hasattr(m, sentinel):
        return m
    try:
        m = importlib.import_module(name)
        if hasattr(m, sentinel):
            return m
    except Exception:
        pass
    path = os.path.join(here, name + ".py")
    if os.path.exists(path):
        try:
            spec = importlib.util.spec_from_file_location("_zen_bootstrap_" + name, path)
            m = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = m
            spec.loader.exec_module(m)
            if hasattr(m, sentinel):
                return m
        except Exception:
            pass
    return None


A = _sibling("ast", "Span")


# Fallbacks, so `import sema` works before ast.py lands and so the type
# checker can always build a Span/Diag. If ast.py exists these are unused.
if A is None:  # pragma: no cover - only before ast.py exists

    @dataclass(frozen=True)
    class Span:  # type: ignore[no-redef]
        file: str
        start: tuple
        end: tuple

    @dataclass(frozen=True)
    class Diag:  # type: ignore[no-redef]
        span: object
        message: str
        notes: tuple = ()

else:
    Span = getattr(A, "Span")
    Diag = getattr(A, "Diag", None)
    if Diag is None:  # ast.py without a Diag: define the contract's shape

        @dataclass(frozen=True)
        class Diag:  # type: ignore[no-redef]
            span: object
            message: str
            notes: tuple = ()


# ---------------------------------------------------------------------------
# node access
#
# Node classes are matched by NAME, never by isinstance: this file must keep
# working whatever class hierarchy ast.py chose, and must not crash on a node
# shape CONTRACT.md left underspecified.
# ---------------------------------------------------------------------------


def _k(n):
    return type(n).__name__ if n is not None else "None"


def _g(n, *names, default=None):
    for nm in names:
        if hasattr(n, nm):
            v = getattr(n, nm)
            if v is not None:
                return v
    return default


def _tup(v):
    if v is None:
        return ()
    if isinstance(v, (tuple, list)):
        return tuple(v)
    return (v,)


def _bare_name(name):
    """A type's name without its arguments: `Range<T>` is an impl of `Range`."""
    if not isinstance(name, str):
        return name
    return name.split("<", 1)[0].strip()


def _name_of(v):
    """A declaration name may be a str or a `declaration_name`-ish node."""
    if v is None:
        return None
    if isinstance(v, str):
        return v
    inner = _g(v, "name")
    if isinstance(inner, str):
        return inner
    if inner is not None and not isinstance(inner, (tuple, list)):
        return _name_of(inner)
    return None


# ---------------------------------------------------------------------------
# spans
# ---------------------------------------------------------------------------


def _span(n):
    return getattr(n, "span", None)


def _mkspan(base, start, end=None):
    if base is None:
        return None
    try:
        return Span(base.file, tuple(start), tuple(end if end is not None else start))
    except Exception:
        return base


def _start(sp):
    if sp is None:
        return ("", 0, 0)
    try:
        return (sp.file, sp.start[0], sp.start[1])
    except Exception:
        return ("", 0, 0)


def _earlier(a, b):
    """The earlier of two spans, for deterministic blame."""
    if a is None:
        return b
    if b is None:
        return a
    return a if _start(a) <= _start(b) else b


def _after_dot(base_node, own_span=None, width=1):
    """The span of the identifier that follows `base.`

    `Member(base, name)` and `Try(operand)` both carry a name-shaped token the
    AST has no span for, and both must-fail suites point AT that token
    (`t.width` blames column of `width`, `x.try()` blames column of `try`).
    Spans are half-open, so `base.span.end.col` is the dot and `+1` is the
    token. Takes the later of that and the node's own start, so an ast.py that
    already points at the token wins.
    """
    bsp = _span(base_node)
    if bsp is None:
        return own_span
    try:
        line, col = bsp.end[0], bsp.end[1] + 1
    except Exception:
        return own_span or bsp
    if own_span is not None:
        try:
            oline, ocol = own_span.start
            if (oline, ocol) > (line, col):
                line, col = oline, ocol
        except Exception:
            pass
    return _mkspan(bsp, (line, col), (line, col + width))


# ---------------------------------------------------------------------------
# types
#
# Sema's own type language. `pnames` is deliberately excluded from equality and
# hashing: "parameter names are documentation, not identity" (DESIGN.md,
# Overloading) — the one rule that must be structural in the representation
# rather than remembered at every comparison site.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ty:
    kind: str
    name: str = ""
    args: tuple = ()
    ret: object = None
    pnames: tuple = dcfield(default=(), compare=False)


ANY = Ty("any")          # unknown / inference hole: unifies with everything
ERR = Ty("error")        # poison: a diagnostic was already reported here
UNIT = Ty("unit")
NEVER = Ty("never")      # the empty error set
VARIADIC = Ty("variadic")  # the `args: ...` tail: zero or more of anything
INTLIT = Ty("intlit")
FLOATLIT = Ty("floatlit")
BOOL = Ty("prim", "bool")
STR = Ty("prim", "str")
USIZE = Ty("prim", "usize")

_INT_PRIMS = {
    "i8": (8, True), "i16": (16, True), "i32": (32, True), "i64": (64, True),
    "isize": (64, True),
    "u8": (8, False), "u16": (16, False), "u32": (32, False), "u64": (64, False),
    "usize": (64, False),
}
_FLOAT_PRIMS = {"f32", "f64"}
_PRIMS = set(_INT_PRIMS) | _FLOAT_PRIMS | {"bool", "str", "char", "void"}


def prim(name):
    return Ty("prim", name)


def named(qname, args=()):
    return Ty("named", qname, tuple(args))


def fn_ty(params, ret, pnames=()):
    return Ty("fn", "", tuple(params), ret, tuple(pnames))


def res_ty(t, e=None):
    return Ty("res", "", (t,) if e is None else (t, e))


def arr_ty(elem, count=None):
    return Ty("array", "" if count is None else str(count), (elem,))


def var_ty(name):
    return Ty("var", name)


def union_ty(members):
    flat = []
    for m in members:
        if m is None or m == NEVER:
            continue
        if m.kind == "union":
            flat.extend(m.args)
        else:
            flat.append(m)
    seen, out = set(), []
    for m in flat:
        if m in seen:
            continue
        seen.add(m)
        out.append(m)
    out.sort(key=show)  # sorted: gen_c and the fixpoint both need determinism
    if not out:
        return NEVER
    if len(out) == 1:
        return out[0]
    return Ty("union", "", tuple(out))


def base_name(qname):
    return qname.rsplit("::", 1)[-1].lstrip("@")


def show(t):
    if t is None:
        return "?"
    k = t.kind
    if k == "prim":
        return t.name
    if k == "intlit":
        return "int"
    if k == "floatlit":
        return "float"
    if k == "unit":
        return "()"
    if k == "any":
        return "_"
    if k == "never":
        return "never"
    if k == "variadic":
        return "..."
    if k == "error":
        return "<error>"
    if k == "var":
        return t.name
    if k == "named":
        n = base_name(t.name)
        return n + ("<" + ", ".join(show(a) for a in t.args) + ">" if t.args else "")
    if k == "res":
        return "Res<" + ", ".join(show(a) for a in t.args) + ">"
    if k in ("ok", "err", "none"):
        return {"ok": "Ok", "err": "Err", "none": "None"}[k] + (
            "(" + show(t.args[0]) + ")" if t.args else ""
        )
    if k == "union":
        return " | ".join(show(a) for a in t.args)
    if k == "fn":
        names = t.pnames or tuple("_" for _ in t.args)
        ps = ", ".join(
            "%s: %s" % (n, show(a)) for n, a in zip(names, t.args)
        )
        return "(%s) %s" % (ps, show(t.ret))
    if k == "array":
        return "[%s, %s]" % (show(t.args[0]), t.name or "_")
    return k


def tsize(t):
    """Structural size — the growth signal the depth budget blames on."""
    if t is None:
        return 0
    n = 1
    for a in t.args:
        n += tsize(a)
    if t.ret is not None:
        n += tsize(t.ret)
    return n


def targs_size(args):
    return sum(tsize(a) for a in args)


def subst_ty(t, sub):
    if t is None or not sub:
        return t
    if t.kind == "var":
        return sub.get(t.name, t)
    if not t.args and t.ret is None:
        return t
    args = tuple(subst_ty(a, sub) for a in t.args)
    ret = subst_ty(t.ret, sub) if t.ret is not None else None
    if t.kind == "union":
        return union_ty(args)
    return Ty(t.kind, t.name, args, ret, t.pnames)


def settle(t):
    """Give an open `Ok(..)` / `Err(..)` / `None` a concrete Res shape."""
    if t is None:
        return ANY
    if t.kind == "ok":
        return res_ty(t.args[0] if t.args else UNIT, ANY)
    if t.kind == "err":
        return res_ty(ANY, t.args[0] if t.args else ANY)
    if t.kind == "none":
        return res_ty(ANY)
    return t


def is_res(t):
    return t is not None and t.kind in ("res", "ok", "err", "none")


# ---------------------------------------------------------------------------
# assignability
# ---------------------------------------------------------------------------


#: Set by the live `Sema`. Assignability is otherwise a pure function of two
#: types, but "a concrete type is assignable to a trait it impls" needs the
#: impl table, and that lives on the graph.
_TRAIT_COERCION = None


def _impls_trait(a, b):
    return bool(_TRAIT_COERCION) and _TRAIT_COERCION(a, b)


def assignable(a, b):
    """Is a value of type `a` acceptable where `b` is wanted?"""
    if a is None or b is None:
        return True
    if a.kind in ("error", "any") or b.kind in ("error", "any"):
        return True
    if a.kind == "never" or b.kind == "variadic":
        return True
    if a.kind == "var" or b.kind == "var":
        # unsubstituted parameters: leniency here beats a false positive in a
        # body that has not been instantiated yet.
        return True
    if b.kind == "union":
        return any(assignable(a, m) for m in b.args)
    if a.kind == "union":
        return all(assignable(m, b) for m in a.args)
    # An unannotated literal has no width yet, so it fits any numeric type —
    # and the rule is SYMMETRIC: a checked `i32` reaching a position sema only
    # knows as "an integer literal" is the same non-event.
    if a.kind == "intlit" or b.kind == "intlit":
        other = b if a.kind == "intlit" else a
        return other.kind in ("intlit", "floatlit") or (
            other.kind == "prim" and (other.name in _INT_PRIMS
                                      or other.name in _FLOAT_PRIMS))
    if a.kind == "floatlit" or b.kind == "floatlit":
        other = b if a.kind == "floatlit" else a
        return other.kind == "floatlit" or (other.kind == "prim"
                                            and other.name in _FLOAT_PRIMS)
    if a.kind in ("ok", "err", "none"):
        if b.kind not in ("res",):
            return False
        if a.kind == "ok":
            payload = a.args[0] if a.args else UNIT
            return assignable(payload, b.args[0])
        if a.kind == "none":
            # law 4 / DESIGN Errors: a None never becomes an Err.
            return len(b.args) == 1
        if a.kind == "err":
            if len(b.args) != 2:
                return False
            return err_subset(a.args[0] if a.args else ANY, b.args[1])
    if b.kind in ("ok", "err", "none"):
        return assignable(a, settle(b))
    if a.kind != b.kind:
        return b.kind == "named" and _impls_trait(a, b)
    if a.kind == "prim":
        return a.name == b.name
    if a.kind == "unit":
        return True
    if a.kind == "named":
        if a.name != b.name or len(a.args) != len(b.args):
            return _impls_trait(a, b)
        return all(assignable(x, y) for x, y in zip(a.args, b.args))
    if a.kind == "res":
        if len(a.args) != len(b.args):
            return False
        if not assignable(a.args[0], b.args[0]):
            return False
        if len(a.args) == 2:
            return err_subset(a.args[1], b.args[1])
        return True
    if a.kind == "array":
        if a.name and b.name and a.name != b.name:
            return False
        return assignable(a.args[0], b.args[0])
    if a.kind == "fn":
        if len(a.args) != len(b.args):
            return False
        if not all(assignable(x, y) for x, y in zip(a.args, b.args)):
            return False
        return assignable(a.ret or UNIT, b.ret or UNIT)
    return a == b


def err_members(e):
    if e is None or e.kind == "never":
        return ()
    if e.kind == "union":
        return tuple(e.args)
    return (e,)


def err_subset(a, b):
    """Error sets: propagation merges, it never converts (DESIGN.md, Errors)."""
    if a is None or b is None:
        return True
    if a.kind in ("never", "error", "any") or b.kind in ("error", "any"):
        return True
    for m in err_members(a):
        if m.kind in ("any", "error", "var"):
            continue
        if not any(m == n or n.kind in ("any", "var") for n in err_members(b)):
            return False
    return True


# ---------------------------------------------------------------------------
# declarations, normalised
#
# The surface has several spellings for one thing: a module-level `f = (x: T) R
# {..}` is a Function, and so is an `ast.Function`. Normalising once here keeps
# every query below shape-agnostic.
# ---------------------------------------------------------------------------


@dataclass
class FnDef:
    name: str
    exported: bool
    tparams: tuple
    params: tuple
    ret: object
    body: object
    span: object
    node: object
    mod: object
    form: str = "sealed"

    @property
    def arity(self):
        return len(self.params)


@dataclass
class TypeDef:
    name: str
    qname: str
    exported: bool
    kind: str            # "struct" | "enum" | "union" | "alias"
    tparams: tuple
    node: object
    span: object
    mod: object
    fields: tuple = ()   # struct: ast Field nodes
    consts: tuple = ()
    variants: tuple = () # enum: ast Variant nodes
    target: object = None  # alias: ast Type


@dataclass
class ImplDef:
    target: str          # resolved qname of the implementing type
    trait: str           # resolved qname of the bound
    target_name: str
    trait_name: str
    entries: tuple
    span: object
    node: object
    mod: object


@dataclass
class Member:
    name: str
    ty: Ty
    kind: str            # "field" | "computed" | "method" | "const" | "variant"
    mutable: bool = False
    owner: object = None
    impl: object = None
    span: object = None
    ambiguous: tuple = ()   # ((span, note), ..) when two impls supply the name
    alts: tuple = ()        # ((ImplDef, Member), ..) — what a bound may select
    overloads: tuple = ()   # every method of this name: `toString` is two


@dataclass
class ModInfo:
    name: str
    path: str
    node: object
    decls: tuple
    dotted: str
    types: dict = dcfield(default_factory=dict)      # name -> the FIRST decl
    type_all: dict = dcfield(default_factory=dict)   # name -> [TypeDef, ..]
    type_arity: dict = dcfield(default_factory=dict) # (name, n tparams) -> TypeDef
    fns: dict = dcfield(default_factory=dict)
    consts: dict = dcfield(default_factory=dict)
    impls: list = dcfield(default_factory=list)
    imports: dict = dcfield(default_factory=dict)   # local name -> (dotted, orig)
    info: object = None      # the modules.ModuleInfo, when sema was given one


@dataclass
class Sym:
    kind: str            # "value" | "type" | "fns" | "builtin_fn" | "error"
    ty: Ty = ANY
    decl: object = None
    defs: tuple = ()
    mutable: bool = False


class Scope:
    __slots__ = ("vars", "parent")

    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent

    def get(self, name):
        s = self
        while s is not None:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None

    def put(self, name, sym):
        self.vars[name] = sym

    def child(self):
        return Scope(self)


@dataclass
class Ctx:
    mod: ModInfo
    scope: Scope
    fn: object = None
    ret: Ty = ANY
    subst: tuple = ()      # ((name, Ty), ..) — hashable, so it can key a memo
    bounds: tuple = ()     # ((name, (Ty, ..)), ..)
    frame: object = None
    quiet: bool = False    # suppress name resolution errors (lost binders)

    @property
    def sub(self):
        return dict(self.subst)

    def with_scope(self, sc):
        return Ctx(self.mod, sc, self.fn, self.ret, self.subst, self.bounds,
                   self.frame, self.quiet)

    @property
    def key(self):
        return (id(self.mod), self.subst, self.quiet)


@dataclass
class Frame:
    """One instantiation on the stack. `widens` is the whole point."""
    what: str            # "fn" | "type"
    key: tuple
    label: str
    targs: tuple
    site: object         # the call / field span that asked for it
    parent: object = None

    @property
    def depth(self):
        n, f = 0, self
        while f is not None:
            n += 1
            f = f.parent
        return n

    def widens(self):
        if self.parent is None or self.site is None:
            return False
        return targs_size(self.targs) > targs_size(self.parent.targs)


# ---------------------------------------------------------------------------
# patterns, normalised for the usefulness algorithm
# ---------------------------------------------------------------------------


@dataclass
class P:
    kind: str            # "wild" | "ctor" | "lit"
    name: str = ""
    subs: tuple = ()
    binder: object = None
    span: object = None
    #: the AST lost this sub-pattern (CONTRACT.md's `PatVariant.binder` is a
    #: str, which cannot hold `Left(Full(n))`). Covers everything for
    #: exhaustiveness — the permissive direction — and disables the
    #: unreachable-arm check, which is the other permissive direction. Never
    #: invent a diagnostic out of missing information.
    opaque: bool = False


WILD = P("wild")

_PAT_TOK = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|\(|\)|,")


@dataclass
class _Raw:
    """A sub-pattern recovered from a binder written as source text."""
    name: str
    subs: object = None      # tuple[_Raw] | None


def _parse_pats(text):
    """`PatVariant.binder` is a string. cst.py fills it with the source text of
    the payload, so `Left(Full(n))` arrives as the binder `"Full(n)"` — parse
    it back rather than throwing the nesting away."""
    toks = _PAT_TOK.findall(text or "")
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def one():
        nm = peek()
        if nm is None or nm in "(),":
            pos[0] += 1
            return _Raw("_")
        pos[0] += 1
        if peek() == "(":
            pos[0] += 1
            subs = []
            while peek() is not None and peek() != ")":
                subs.append(one())
                if peek() == ",":
                    pos[0] += 1
            if peek() == ")":
                pos[0] += 1
            return _Raw(nm, tuple(subs))
        return _Raw(nm, None)

    out = []
    while peek() is not None:
        out.append(one())
        if peek() == ",":
            pos[0] += 1
    return tuple(out)


# ---------------------------------------------------------------------------
# the builtin floor
#
# `src/std/` is stage 0.6 and does not exist yet, but the sema corpus is
# written against `Env`, `Alloc`, `Vec`, `Map`, `Res` and `println` today. So
# the floor lives here as data, and any name a real module defines shadows it.
# ---------------------------------------------------------------------------

BUILTIN_TYPES = {
    "Ptr": dict(arity=1, methods={
        "read": "(self: @Self, i: usize) T0",
        "write": "(self: @Self, i: usize, value: T0) ()",
    }),
    "Vec": dict(arity=1, fields={
        "len": "usize", "capacity": "usize", "data": "Ptr<T0>", "alloc": "Alloc",
    }, methods={
        "add": "(self: @Self, value: T0) Res<(), AllocError>",
        "get": "(self: @Self, i: usize) Res<T0>",
        "take": "(self: @Self, i: usize) Res<T0>",
    }),
    "Map": dict(arity=2, methods={
        "set": "(self: @Self, key: T0, value: T1) Res<(), AllocError>",
        "get": "(self: @Self, key: T0) Res<T1>",
    }),
    "Entry": dict(arity=2, fields={"hash": "u64", "key": "T0", "value": "T1"}),
    "String": dict(arity=0, fields={"data": "Vec<u8>"}, methods={
        "add": "(self: @Self, fmt: str, args: ...) Res<(), WriteError>",
        "view": "(self: @Self) str",
        "write": "(self: @Self, bytes: str) Res<(), WriteError>",
        "write_byte": "(self: @Self, b: u8) Res<(), WriteError>",
        "toString": "(self: @Self, out: Sink) Res<(), WriteError>",
    }),
    "Alloc": dict(arity=0, methods={
        "raw": "(self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>",
        "realloc": "(self: @Self, p: Ptr<G0>, count: usize) Res<Ptr<G0>, AllocError>",
        "free": "(self: @Self, p: Ptr<G0>) ()",
        "create": "(self: @Self) Res<Ptr<G0>, AllocError>",
        "Vec": "(self: @Self) Vec<G0>",
        "Map": "(self: @Self) Map<G0, G1>",
        "String": "(self: @Self, fmt: str, args: ...) Res<String, AllocError>",
    }),
    "Arena": dict(arity=0, methods={}),
    "Mem": dict(arity=0, methods={"alloc": "(self: @Self) Alloc"}),
    "Console": dict(arity=0, methods={
        "println": "(self: @Self, fmt: str, args: ...) ()",
        "print": "(self: @Self, fmt: str, args: ...) ()",
        "eprintln": "(self: @Self, fmt: str, args: ...) ()",
    }),
    "Env": dict(arity=0, fields={
        "argv": "Vec<str>", "vars": "Map<str, str>", "out": "Console",
        "mem": "Mem", "fs": "Fs", "net": "Net", "threads": "Threads",
    }, methods={
        "args": "(self: @Self) Res<G0, ArgError>",
        "spawn": "(self: @Self, actor: G0) Ref<G0>",
    }),
    "Range": dict(arity=0, methods={}),
    "LoopHandle": dict(arity=0, methods={
        "next": "(self: @Self) ()",
    }),
    "Tester": dict(arity=0, fields={"env": "Env", "alloc": "Alloc"}, methods={
        "expect": "(self: @Self, cond: bool) Res<(), TestError>",
        "expect_eq": "(self: @Self, a: G0, b: G0) Res<(), TestError>",
    }),
    "Bencher": dict(arity=0, fields={"env": "Env", "alloc": "Alloc"}, methods={
        "iter": "(self: @Self, f: () ()) BenchStats",
    }),
    "BenchStats": dict(arity=0, fields={
        "ns_op": "u64", "allocs_op": "u64", "bytes_op": "u64"}),
    "Budget": dict(arity=0, fields={
        "name": "str", "ns_op": "u64", "allocs_op": "u64", "bytes_op": "u64"}),
    "Package": dict(arity=0, fields={"url": "str", "version": "str", "hash": "str"}),
    "Scope": dict(arity=0, methods={"defer": "(self: @Self, f: () ()) ()"}),
    "Hasher": dict(arity=0, methods={}),
    "Thread": dict(arity=0, fields={"id": "u64"}, methods={}),
    "Threads": dict(arity=0, methods={"sleep": "(self: @Self, ms: u64) ()"}),
    "Ref": dict(arity=1, fields={"id": "u64"}, methods={}),
    "Context": dict(arity=0, fields={"env": "Env", "alloc": "Alloc"}),
    "Duration": dict(arity=0, methods={}),
    "Path": dict(arity=0, methods={}),
    "Builder": dict(arity=0, fields={
        "os": "Os", "arch": "Arch", "env": "Env", "alloc": "Alloc"}),
    # opaque, but nameable
    "Fs": dict(arity=0), "Net": dict(arity=0), "Exe": dict(arity=0),
    "Lib": dict(arity=0), "Dep": dict(arity=0), "Actor": dict(arity=0),
    "Display": dict(arity=0), "Eq": dict(arity=0), "Hash": dict(arity=0),
    "Drop": dict(arity=0), "Module": dict(arity=0), "Struct": dict(arity=0),
    "Enum": dict(arity=0), "Function": dict(arity=0), "Field": dict(arity=0),
    "Other": dict(arity=0), "Opts": dict(arity=0),
}

BUILTIN_ENUMS = {
    "AllocError": {"OutOfMemory": None},
    "IoError": {"Eof": None, "Closed": None, "Failed": None},
    "ArgError": {"Missing": "str", "Parse": "str"},
    "TestError": {"Failed": "str"},
    "BuildError": {"NotFound": None, "FetchFailed": None,
                   "VersionConflict": None, "HashMismatch": None},
    "ActorError": {"Closed": None, "Full": None},
    "ThreadError": {"SpawnFailed": None, "Panicked": None},
    "Os": {"Macos": None, "Linux": None, "Windows": None},
    "Arch": {"X86_64": None, "Arm64": None},
}

#: free functions the prelude supplies. `loop`/`find`/`filter`/`map`/`then`
#: are deliberately lenient: their real signatures are overload sets in
#: `std/core/loop.zen`, and guessing them here would invent diagnostics.
BUILTIN_FNS = {
    "println", "print", "eprintln", "loop", "map", "find", "filter", "then",
    "Range", "Hasher", "assert",
}


# ---------------------------------------------------------------------------
# a tiny type-expression reader, for the builtin table only
# ---------------------------------------------------------------------------

_TOKRE = re.compile(r"@Self|\.\.\.|[A-Za-z_][A-Za-z0-9_]*|<|>|\(|\)|\[|\]|,|\||:|_|[0-9]+")


class _TypeReader:
    def __init__(self, sema, text, env):
        self.s = sema
        self.t = _TOKRE.findall(text)
        self.i = 0
        self.env = env

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def eat(self, tok=None):
        v = self.peek()
        if tok is not None and v != tok:
            return None
        self.i += 1
        return v

    def starts_type(self):
        v = self.peek()
        return v is not None and (
            v == "(" or v == "[" or v == "@Self" or v == "_" or v == "..."
            or re.match(r"^[A-Za-z_]", v)
        )

    def read(self):
        t = self.atom()
        members = [t]
        while self.peek() == "|":
            self.eat("|")
            members.append(self.atom())
        return union_ty(members) if len(members) > 1 else t

    def atom(self):
        v = self.peek()
        if v == "(":
            self.eat("(")
            if self.peek() == ")":
                self.eat(")")
                if self.starts_type():
                    return fn_ty((), self.read(), ())
                return UNIT
            names, ptys = [], []
            while True:
                nm = self.eat()
                names.append(nm)
                if self.peek() == ":":
                    self.eat(":")
                    ptys.append(self.read())
                else:
                    ptys.append(ANY)
                if self.peek() == ",":
                    self.eat(",")
                    continue
                break
            self.eat(")")
            ret = self.read() if self.starts_type() else UNIT
            return fn_ty(tuple(ptys), ret, tuple(names))
        if v == "[":
            self.eat("[")
            elem = self.read()
            self.eat(",")
            cnt = self.eat()
            self.eat("]")
            return arr_ty(elem, cnt)
        if v == "...":
            self.eat()
            return VARIADIC
        if v == "_":
            self.eat()
            return ANY
        if v == "@Self":
            self.eat()
            return self.env.get("@Self", ANY)
        nm = self.eat()
        if nm is None:
            return ANY
        args = ()
        if self.peek() == "<":
            self.eat("<")
            got = [self.read()]
            while self.peek() == ",":
                self.eat(",")
                got.append(self.read())
            self.eat(">")
            args = tuple(got)
        if nm in self.env:
            return self.env[nm]
        if re.match(r"^[GT][0-9]+$", nm):
            # G0/G1: the type arguments written AT the call
            # (`alloc.create<Node>()`); T0/T1 when the receiver had none.
            return var_ty(nm)
        return self.s.builtin_named(nm, args)


# ---------------------------------------------------------------------------
# Sema
# ---------------------------------------------------------------------------


class Sema:
    def __init__(self, modules, root="", depth_budget=INSTANTIATION_DEPTH_BUDGET):
        self.diags = []
        self.root = root
        self.budget = depth_budget

        self.graph = None
        self.mods = []
        self.by_dotted = {}
        self.by_name = {}
        self.by_node = {}        # id(decl node) -> TypeDef | FnDef
        self.types = {}          # qname -> TypeDef
        self.prim_decls = {}     # "i32" -> the prelude's declaration of it
        self.global_by_name = {} # (name, arity|None) -> TypeDef, tree-wide
        self.impls_by_target = {}
        self.node_type = {}      # id(expr) -> Ty as CHECKED  [gen_c, LSP]
        self.call_target = {}    # id(Call | callee) -> FnDef  [gen_c, LSP]
        self.fn_instances = {}   # (id(fn), targs) -> (FnDef, targs)  [gen_c]
        self.type_instances = {} # (qname, args)   -> TypeDef         [gen_c]

        self._memo = {}
        self._keep = []
        self._checked = set()
        self._layout_done = {}
        self._reported = set()
        self._errset_state = {}
        self._members_memo = {}
        self._ufcs_index = None
        self._muted = 0
        self._resolving = set()

        # accepts an ast.Module, a modules.ModuleInfo, or the whole Graph —
        # `bootstrap.py` hands sema whatever `modules.py` built.
        if hasattr(modules, "modules") and hasattr(modules, "order"):
            self.graph = modules
            modules = list(modules)
        elif not isinstance(modules, (list, tuple)):
            modules = list(modules or ())
        for m in modules or ():
            self._add_module(m)
        self._index()
        self.activate()

    # -- construction -------------------------------------------------------

    def _add_module(self, m):
        info = None
        if _k(m) != "Module" and _g(m, "node") is not None:
            info, m = m, _g(m, "node")          # a modules.ModuleInfo
        if m is None:
            return
        name = _g(m, "name", default="") or (_g(info, "name", default="") if info else "")
        path = (_g(info, "path", default="") if info else "") or _g(m, "path", default="") or ""
        dotted = (_g(info, "dotted", default="") if info else "") or self._dotted(name, path)
        mi = ModInfo(name=name, path=path, node=m, decls=_tup(_g(m, "decls")),
                     dotted=dotted)
        mi.info = info
        self.mods.append(mi)
        self.by_dotted[dotted] = mi
        self.by_dotted.setdefault(name, mi)
        self.by_name.setdefault(name, mi)
        # a dotted suffix also resolves: `std.core.result` may be reached as
        # `core.result` from inside the tree it lives in.
        parts = dotted.split(".")
        for i in range(1, len(parts)):
            self.by_dotted.setdefault(".".join(parts[i:]), mi)

    @staticmethod
    def _dotted(name, path):
        if path:
            p = str(path).replace("\\", "/")
            if p.endswith(".zen"):
                p = p[:-4]
            parts = [x for x in p.split("/") if x not in ("", ".")]
            if parts:
                return ".".join(parts)
        return name or ""

    def _index(self):
        for mi in self.mods:
            for imp in _tup(_g(mi.node, "imports")):
                dotted = _g(imp, "path", default="") or ""
                for entry in _tup(_g(imp, "names")):
                    if isinstance(entry, (tuple, list)) and entry:
                        nm = _name_of(entry[0])
                    else:
                        nm = _name_of(entry)
                    if nm:
                        mi.imports[nm] = (dotted, nm)
            for d in mi.decls:
                self._index_decl(mi, d)
        for mi in self.mods:
            for name, cands in mi.type_all.items():
                if name in _PRIMS:
                    for td in cands:
                        if td.kind == "struct":
                            self.prim_decls.setdefault(name, td)
                # The prelude declares the names the builtin floor below also
                # knows — Res, Alloc, Vec, AllocError, LoopHandle. Whole-program
                # compilation means there is one of each, so a signature the
                # floor supplies and a signature the source declares must be
                # the SAME type: two nominal `AllocError`s produce the
                # unimprovable diagnostic "AllocError is not AllocError".
                for td in cands:
                    prev = self.global_by_name.get((name, len(td.tparams)))
                    if prev is None or (td.exported and not prev.exported):
                        self.global_by_name[(name, len(td.tparams))] = td
                    self.global_by_name.setdefault((name, None), td)
        # impls are whole-program: a bound declared in one module may be
        # satisfied by an impl in another (tests/corpus/sema/bound_third_module).
        for mi in self.mods:
            for im in mi.impls:
                # A prelude name is visible without an import, so `Key.impl(Eq,
                # ..)` has to register under `Eq`'s own qname or the bound
                # `<K: Eq>` never meets it.  `_impl_from` runs before the
                # tree-wide table exists, which is why the fixup is here.
                im.target = self._requalify(mi, im.target, im.target_name)
                im.trait = self._requalify(mi, im.trait, im.trait_name)
                self.impls_by_target.setdefault(im.target, []).append(im)
        for k in self.impls_by_target:
            self.impls_by_target[k].sort(key=lambda i: _start(i.span))

    def _index_decl(self, mi, d):
        k = _k(d)
        if k == "Struct":
            nm = _name_of(_g(d, "name"))
            if not nm:
                return
            td = TypeDef(nm, mi.dotted + "::" + nm, bool(_g(d, "exported", default=False)),
                         "struct", _tup(_g(d, "tparams")), d, _span(d), mi,
                         fields=_tup(_g(d, "fields")), consts=_tup(_g(d, "consts")))
            self._register_type(mi, td, d)
        elif k == "Enum":
            nm = _name_of(_g(d, "name"))
            if not nm:
                return
            td = TypeDef(nm, mi.dotted + "::" + nm, bool(_g(d, "exported", default=False)),
                         "enum", _tup(_g(d, "tparams")), d, _span(d), mi,
                         variants=_tup(_g(d, "variants")))
            self._register_type(mi, td, d)
        elif k == "Alias":
            nm = _name_of(_g(d, "name"))
            if not nm:
                return
            td = TypeDef(nm, mi.dotted + "::" + nm, bool(_g(d, "exported", default=False)),
                         "alias", _tup(_g(d, "tparams")), d, _span(d), mi,
                         target=_g(d, "target", "ty", "type"))
            self._register_type(mi, td, d)
        elif k == "Function":
            fd = self._fn_from_function(mi, d)
            if fd:
                mi.fns.setdefault(fd.name, []).append(fd)
                self.by_node[id(d)] = fd
        elif k == "Impl":
            im = self._impl_from(mi, d)
            if im:
                mi.impls.append(im)
        elif k == "Const":
            nm = _name_of(_g(d, "name"))
            if nm:
                mi.consts[nm] = d
        elif k in ("Let", "Binding"):
            # a module-level `f = (x: T) R {..}` is a declaration in every
            # sense that matters here.
            val = _g(d, "value")
            nm = _name_of(_g(d, "name", "target"))
            if nm and _k(val) in ("Lambda", "Function"):
                fd = self._fn_from_lambda(mi, d, nm, val)
                if fd:
                    mi.fns.setdefault(fd.name, []).append(fd)
                    self.by_node[id(d)] = fd
                    self.by_node[id(val)] = fd
            elif nm and _k(val) == "Call" and self._impl_call_parts(val):
                im = self._impl_from_call(mi, val)
                if im:
                    mi.impls.append(im)
            elif nm:
                mi.consts[nm] = d
        elif k == "ExprStmt":
            e = _g(d, "expr")
            if _k(e) == "Call" and self._impl_call_parts(e):
                im = self._impl_from_call(mi, e)
                if im:
                    mi.impls.append(im)

    def _register_type(self, mi, td, node):
        """A type name may be declared at several ARITIES — the prelude does
        it (`Res<T>` and `Res<T, E>`), and DESIGN.md's overloading rule is
        silent about types only because it never occurred to it that they
        differ. One name, several declarations, selected by the count of type
        arguments at the use site, exactly as a function is selected by its
        argument count."""
        n = len(td.tparams)
        if td.qname in self.types:
            td = dataclasses_replace(td, qname="%s#%d" % (td.qname, n))
        mi.type_all.setdefault(td.name, []).append(td)
        mi.type_arity.setdefault((td.name, n), td)
        mi.types.setdefault(td.name, td)     # first declared wins a bare use
        self.types[td.qname] = td
        self.by_node[id(node)] = td

    def _fn_from_function(self, mi, d):
        nm = _name_of(_g(d, "name"))
        if not nm:
            return None
        return FnDef(nm, bool(_g(d, "exported", default=False)),
                     _tup(_g(d, "tparams")), _tup(_g(d, "params")),
                     _g(d, "ret"), _g(d, "body"), _span(d), d, mi,
                     _g(d, "form", default="sealed") or "sealed")

    def _fn_from_lambda(self, mi, outer, nm, lam):
        return FnDef(nm, bool(_g(outer, "exported", default=False)),
                     _tup(_g(lam, "tparams")) or _tup(_g(outer, "tparams")),
                     _tup(_g(lam, "params")), _g(lam, "ret"), _g(lam, "body"),
                     _span(outer) or _span(lam), lam, mi,
                     _g(outer, "form", default="sealed") or "sealed")

    @staticmethod
    def _impl_call_parts(call):
        callee = _g(call, "callee", "function")
        if _k(callee) != "Member" or _g(callee, "name", "property") != "impl":
            return None
        base = _g(callee, "base", "object")
        tname = _g(base, "name") if _k(base) in ("Path", "Identifier") else None
        if not isinstance(tname, str):
            return None
        args = _tup(_g(call, "args", "arguments"))
        if len(args) < 2:
            return None
        first = args[0]
        first = _g(first, "value", default=first)
        trait = _g(first, "name") if _k(first) in ("Path", "Identifier") else None
        rec = args[1]
        rec = _g(rec, "value", default=rec)
        return tname, trait, _tup(_g(rec, "entries", "fields", "elems"))

    def _impl_from_call(self, mi, call):
        parts = self._impl_call_parts(call)
        if not parts:
            return None
        tname, trait, entries = parts
        if not isinstance(trait, str):
            return None
        return ImplDef(self._qualify(mi, tname), self._qualify(mi, trait),
                       tname, trait, entries, _span(call), call, mi)

    def _impl_from(self, mi, d):
        # `Vec.impl(Range<T>, ..)` names the bound with its arguments applied,
        # and the arguments are not part of its NAME: this is an impl of
        # Range, at T. (cst.py hands both sides over as source text.)
        tname = _bare_name(_name_of(_g(d, "target")))
        trait = _bare_name(_name_of(_g(d, "trait")))
        if not tname or not trait:
            return None
        return ImplDef(self._qualify(mi, tname), self._qualify(mi, trait),
                       tname, trait, _tup(_g(d, "entries")), _span(d), d, mi)

    def _qualify(self, mi, name):
        td = self.lookup_type(mi, name)
        return td.qname if td else "@" + name

    def _requalify(self, mi, qname, name):
        """A qname `_qualify` could not resolve, tried again against the
        tree-wide table -- which is where a prelude name lives."""
        if not isinstance(qname, str) or not qname.startswith("@"):
            return qname
        td = self.lookup_type(mi, name) or self.global_by_name.get((name, None))
        return td.qname if td is not None else qname

    # -- diagnostics --------------------------------------------------------

    def error(self, span, message, notes=()):
        if self._muted:
            return      # an external query (the LSP, gen_c) reports nothing
        self.diags.append(Diag(span=span, message=message, notes=tuple(notes)))

    def _once(self, tag):
        if tag in self._reported:
            return False
        self._reported.add(tag)
        return True

    # ======================================================================
    # queries
    # ======================================================================

    def defs_of(self, name, module=None):
        """Every declaration a name can mean, in `module`'s view."""
        mods = [module] if module is not None else self.mods
        out = []
        for mi in mods:
            if mi is None:
                continue
            if name in mi.fns:
                out.extend(f.node for f in mi.fns[name])
            for td in mi.type_all.get(name, ()):
                out.append(td.node)
            if name in mi.consts:
                out.append(mi.consts[name])
            if name in mi.imports:
                tgt = self.by_dotted.get(mi.imports[name][0])
                if tgt is not None and tgt is not mi:
                    out.extend(self.defs_of(name, tgt))
        return tuple(out)

    def impls_of(self, qname):
        return tuple(self.impls_by_target.get(qname, ()))

    def _decl_qname(self, ty):
        """The declaration a value's type belongs to, for impl lookup. A
        primitive's impls (`str.impl(Eq, ..)`) hang off the prelude's
        declaration of it."""
        if ty is None:
            return None
        if ty.kind == "named":
            return ty.name
        if ty.kind == "prim":
            td = self.prim_decls.get(ty.name)
            return td.qname if td is not None else None
        return None

    def coerces_to_trait(self, a, b):
        """DESIGN.md, "A trait value is a fat value": a concrete type is
        acceptable where a trait it impls is expected, and the record — a
        receiver plus one function pointer per method — is built AT that
        coercion site, by value, with no allocation.

        This is not the bound case. `<A: Alloc>(a: A)` monomorphises and no
        record exists; `(a: Alloc)` builds one. Keeping the two apart is what
        the no-allocation claim rests on, so they are two code paths here:
        `satisfies` for the bound, this for the coercion."""
        if a is None or b is None or a == b:
            return False
        if b.kind != "named":
            return False
        trait = self.types.get(b.name)
        if trait is None or trait.kind != "struct":
            return False
        target = self._decl_qname(a)
        if target is None:
            return False
        for im in self.impls_of(target):
            if im.trait == b.name:
                return True
        return False

    def _from_scope(self, mi, name, want):
        """What `modules.py` says this name means here. Its scope already has
        the `*` gate and every re-export chain applied, so this is the module
        graph enforcing visibility rather than sema guessing at it."""
        info = mi.info if mi is not None else None
        scope = getattr(info, "scope", None) if info is not None else None
        if not scope:
            return ()
        out, seen = [], set()

        def add(d):
            if isinstance(d, want) and id(d) not in seen:
                seen.add(id(d))
                out.append(d)

        for b in scope.get(name, ()) or ():
            ent = getattr(b, "entity", None)
            node = getattr(ent, "node", None) if ent is not None else None
            d = self.by_node.get(id(node)) if node is not None else None
            if d is None:
                continue
            # An overload set and an arity-overloaded type are ONE name with
            # several declarations; a scope that binds a name to a single
            # entity necessarily loses the rest. The declaring module is the
            # authority on how many there are, the binding on whether they are
            # visible — so take the set, gated by the `*` the binding crossed.
            owner = self.by_dotted.get(getattr(ent, "module", "") or "")
            if owner is not None and owner is not mi:
                group = (owner.fns.get(d.name, ()) if isinstance(d, FnDef)
                         else owner.type_all.get(d.name, ()))
                for sibling in group:
                    if sibling is d or sibling.exported:
                        add(sibling)
            add(d)
        return tuple(out)

    @staticmethod
    def _pick_arity(cands, nargs):
        """The declaration whose type-parameter count matches the use site."""
        if not cands:
            return None
        if nargs is not None:
            for td in cands:
                if len(td.tparams) == nargs:
                    return td
        return cands[0]

    def _follow_import(self, mi, name, want, seen=None):
        """Walk the re-export chain to the DECLARING module and take the whole
        candidate set at every hop.

        A folder root is a file of nothing but starred re-exports (`STYLE.md`),
        so it declares none of the names it publishes: stopping after one hop,
        or taking one declaration per hop, silently drops every overload but
        the first — and the prelude is two hops deep, so that would hit every
        exported overloaded name in the language."""
        seen = seen if seen is not None else set()
        if mi is None or mi.dotted in seen:
            return ()
        seen.add(mi.dotted)
        out, ids = [], set()

        def add_all(group):
            for d in group:
                if id(d) not in ids:
                    ids.add(id(d))
                    out.append(d)

        add_all(mi.fns.get(name, ()) if want is FnDef else mi.type_all.get(name, ()))
        imp = mi.imports.get(name)
        if imp:
            tgt = self.by_dotted.get(imp[0])
            if tgt is not None and tgt is not mi:
                add_all(d for d in self._follow_import(tgt, imp[1], want, seen)
                        if d.exported or not ENFORCE_IMPORT_VISIBILITY_AT_USE)
        return tuple(out)

    def defs_visible(self, mi, name, want):
        """Every declaration of `name` this module can see, merged: its own,
        the re-export chain's, and whatever `modules.py`'s scope resolved.

        Memoized: this is on the hot path of every call site, and the chain it
        walks is the same one the LSP will ask about per keystroke."""
        key = ("visible", id(mi), name, want is FnDef)
        hit = self._memo.get(key, _MISS)
        if hit is not _MISS:
            return hit
        out, ids = [], set()
        for d in self._follow_import(mi, name, want) + self._from_scope(mi, name, want):
            if id(d) not in ids:
                ids.add(id(d))
                out.append(d)
        self._memo[key] = tuple(out)
        return self._memo[key]

    def lookup_type(self, mi, name, nargs=None):
        if mi is None:
            return None
        if nargs is not None:
            td = mi.type_arity.get((name, nargs))
            if td is not None:
                return td
        td = mi.types.get(name)
        if td is not None and (nargs is None or len(td.tparams) == nargs):
            return td
        return self._pick_arity(self.defs_visible(mi, name, TypeDef), nargs) or td

    def lookup_fns(self, mi, name):
        if mi is None:
            return ()
        return self.defs_visible(mi, name, FnDef)

    def builtin_named(self, name, args=()):
        # A name the program itself declares beats the floor, always: the floor
        # exists only because `src/std/` is stage 0.6 and the sema corpus is
        # written against `Env` and `Vec` today.
        td = self.global_by_name.get((name, len(args)))
        if td is None:
            td = self.global_by_name.get((name, None))
        if td is not None and name not in self._resolving:
            self._resolving.add(name)
            try:
                return self.type_from_def(td, args, Ctx(td.mod, Scope()))
            finally:
                self._resolving.discard(name)
        if name in _PRIMS:
            return prim(name)
        if name == "Res":
            if not args:
                return res_ty(ANY)
            return Ty("res", "", tuple(args[:2]))
        if name in BUILTIN_ENUMS:
            return named("@" + name, ())
        spec = BUILTIN_TYPES.get(name)
        if spec is not None:
            ar = spec.get("arity", 0)
            args = tuple(args)
            if len(args) < ar:
                args = args + tuple(ANY for _ in range(ar - len(args)))
            return named("@" + name, args[:ar] if ar else ())
        return named("@" + name, tuple(args))

    def is_builtin_type(self, name):
        return (name in _PRIMS or name == "Res" or name in BUILTIN_ENUMS
                or name in BUILTIN_TYPES)

    # -- types from syntax --------------------------------------------------

    def resolve_type(self, tnode, ctx, want_error=True):
        """A `Type` node -> Ty, in `ctx`'s module and substitution."""
        if tnode is None:
            return ANY
        k = _k(tnode)
        if k == "Unit":
            return UNIT
        if k == "Infer":
            return ANY
        if k == "Union":
            return union_ty([self.resolve_type(m, ctx) for m in _tup(_g(tnode, "members"))])
        if k == "FnType":
            ps = _tup(_g(tnode, "params"))
            return fn_ty(tuple(self.resolve_type(_g(p, "ty", "type"), ctx) for p in ps),
                         self.resolve_type(_g(tnode, "ret"), ctx),
                         tuple(_name_of(_g(p, "name")) or "_" for p in ps))
        if k == "ArrayType":
            cnt = self.const_value(_g(tnode, "count", "length"), ctx)
            return arr_ty(self.resolve_type(_g(tnode, "elem", "element"), ctx), cnt)
        if k in ("Named", "Path", "Identifier", "SelfType"):
            name = _g(tnode, "name", default=None)
            if k == "SelfType" or name == "@Self":
                return dict(ctx.subst).get("@Self", ANY)
            args = tuple(self.resolve_type(a, ctx) for a in _tup(_g(tnode, "args")))
            return self.resolve_named(name, args, ctx, tnode, want_error)
        if k == "Lambda" or k == "Function":
            ps = _tup(_g(tnode, "params"))
            return fn_ty(tuple(self.resolve_type(_g(p, "ty", "type"), ctx) for p in ps),
                         self.resolve_type(_g(tnode, "ret"), ctx),
                         tuple(_name_of(_g(p, "name")) or "_" for p in ps))
        return ANY

    def resolve_named(self, name, args, ctx, node=None, want_error=True):
        if not isinstance(name, str):
            return ANY
        if name == "...":
            return VARIADIC
        sub = dict(ctx.subst)
        if name in sub:
            return sub[name]
        for tp, _b in ctx.bounds:
            if tp == name:
                return var_ty(name)
        td = self.lookup_type(ctx.mod, name, len(args))
        if td is not None:
            return self.type_from_def(td, args, ctx)
        if self.is_builtin_type(name):
            return self.builtin_named(name, args)
        if name in ctx.mod.imports:
            return ERR      # modules.py owns the unexported/unknown import diag
        return ANY

    def type_from_def(self, td, args, ctx):
        # The prelude DECLARES the builtins: `i32` is a struct in
        # std/core/num.zen because it has to carry MIN/MAX/BITS, `str` is a
        # struct in std/text, and `Res` is two enum declarations. Those
        # declarations ARE the builtin — a nominal `i32` beside the primitive
        # `i32` makes every literal, every trap check and every `.try()`
        # disagree with the standard library.
        if td.kind == "struct" and td.name in _PRIMS:
            return prim(td.name)
        if td.kind == "enum" and td.name == "Res":
            args = tuple(args)[:2]
            return Ty("res", "", args or (ANY,))
        if td.kind == "alias":
            inner = Ctx(td.mod, Scope(), subst=ctx.subst, bounds=ctx.bounds)
            return self.resolve_type(td.target, inner)
        if td.kind == "enum" and self.enum_is_union(td):
            return union_ty([self.resolve_named(_name_of(_g(v, "name")), (),
                                                Ctx(td.mod, Scope()))
                             for v in td.variants])
        want = len(td.tparams)
        args = tuple(args)
        if len(args) < want:
            args = args + tuple(ANY for _ in range(want - len(args)))
        return named(td.qname, args[:want] if want else ())

    def enum_is_union(self, td):
        """`Error = LookupError | AllocError` is a union of existing types;
        `Signal = Start, Stop, Reset` is nominal. The only thing that tells
        them apart is whether every variant name is itself a type."""
        key = ("union?", td.qname)
        if key in self._memo:
            return self._memo[key]
        self._memo[key] = False   # guard against a variant naming its own enum
        if td.kind != "enum" or len(td.variants) < 2:
            return False
        ok = True
        for v in td.variants:
            if _g(v, "payload") is not None:
                ok = False
                break
            nm = _name_of(_g(v, "name"))
            if not nm:
                ok = False
                break
            if self.lookup_type(td.mod, nm) is None and not self.is_builtin_type(nm):
                ok = False
                break
        self._memo[key] = ok
        return ok

    # -- variants / constructors -------------------------------------------

    def ctors_of(self, ty):
        """(name, payload types) for every case of `ty`, or None if `ty` has
        no case analysis (only `_` can cover it)."""
        if ty is None:
            return None
        if ty.kind == "prim" and ty.name == "bool":
            return [("true", ()), ("false", ())]
        if ty.kind in ("res", "ok", "err", "none"):
            t = settle(ty)
            if len(t.args) == 1:
                return [("Ok", (t.args[0],)), ("None", ())]
            return [("Ok", (t.args[0],)), ("Err", (t.args[1],))]
        if ty.kind == "named":
            if ty.name.startswith("@"):
                spec = BUILTIN_ENUMS.get(base_name(ty.name))
                if spec is None:
                    return None
                return [(n, () if p is None else (self._read_type(p, {}),))
                        for n, p in spec.items()]
            td = self.types.get(ty.name)
            if td is None or td.kind != "enum" or self.enum_is_union(td):
                return None
            sub = {}
            for tp, a in zip(td.tparams, ty.args):
                nm = _name_of(_g(tp, "name"))
                if nm:
                    sub[nm] = a
            inner = Ctx(td.mod, Scope(), subst=tuple(sorted(sub.items(), key=lambda x: x[0])))
            out = []
            for v in td.variants:
                nm = _name_of(_g(v, "name"))
                pl = _g(v, "payload")
                if pl is None:
                    out.append((nm, ()))
                else:
                    out.append((nm, tuple(self.resolve_type(p, inner) for p in _tup(pl))))
            return out
        if ty.kind == "union":
            # an anonymous enum of its members: each member is one case
            return [(base_name(m.name) if m.kind == "named" else show(m), (m,))
                    for m in ty.args]
        return None

    def _read_type(self, text, env):
        return _TypeReader(self, text, env).read()

    # -- members ------------------------------------------------------------

    def members_of(self, ty, ctx=None):
        """Everything reachable through a dot on `ty`: its own fields and
        methods, plus every impl-supplied field (computed, read-only) and every
        method the implemented bound declares."""
        if ty is None:
            return {}
        key = ("members", ty, ctx.bounds if (ctx is not None and ty.kind == "var") else ())
        if key in self._members_memo:
            return self._members_memo[key]
        out = {}
        self._members_memo[key] = out

        if ty.kind == "var" and ctx is not None:
            # a bound in scope is the disambiguator, and it is the only one
            for tp, bounds in ctx.bounds:
                if tp == ty.name:
                    for b in bounds:
                        for k, v in self.members_of(b, ctx).items():
                            out.setdefault(k, v)
                    break
            return out

        if ty.kind == "named" and ty.name.startswith("@"):
            spec = BUILTIN_TYPES.get(base_name(ty.name))
            if spec:
                env = {"@Self": ty}
                for i, a in enumerate(ty.args):
                    env["T%d" % i] = a
                for nm, tt in (spec.get("fields") or {}).items():
                    out[nm] = Member(nm, self._read_type(tt, env), "field", True)
                for nm, sig in (spec.get("methods") or {}).items():
                    out[nm] = Member(nm, self._read_type(sig, env), "method")
            return out

        if ty.kind in ("res", "ok", "err", "none"):
            t = settle(ty)
            out["ok_or"] = Member(
                "ok_or",
                fn_ty((t, ANY), res_ty(t.args[0], ANY), ("self", "err")),
                "method")
            return out

        if ty.kind == "prim":
            # `str` and `i32` are declared structs in the prelude; the members
            # they declare belong to the primitive they are.
            td = self.prim_decls.get(ty.name)
            if td is None:
                return out
            impl_key = td.qname
        elif ty.kind == "named":
            td = self.types.get(ty.name)
            impl_key = ty.name
        else:
            return out

        if td is None:
            return out
        sub = {}
        for tp, a in zip(td.tparams, ty.args):
            nm = _name_of(_g(tp, "name"))
            if nm:
                sub[nm] = a
        sub["@Self"] = ty
        inner = Ctx(td.mod, Scope(), subst=tuple(sorted(sub.items(), key=lambda x: x[0])))

        if td.kind == "struct":
            for f in td.fields:
                nm = _name_of(_g(f, "name"))
                if not nm:
                    continue
                m = Member(nm, self._field_type(f, inner),
                           "method" if self._is_method_field(f) else "field",
                           bool(_g(f, "mutable", default=False)),
                           owner=td, span=_span(f))
                prev = out.get(nm)
                if prev is not None and prev.kind == "method" and m.kind == "method":
                    # a method declared twice is an overload set, not a
                    # redefinition: `toString(sb: String)` and
                    # `toString(a: Alloc)` are DESIGN.md's own example
                    m.overloads = (prev.overloads or (prev,)) + (m,)
                out[nm] = m

        # impl-supplied members. Two impls supplying one name is ambiguous
        # unless a bound selects — never file order (DESIGN.md, Declarations).
        supplied = {}
        for im in self.impls_of(impl_key):
            trait = self.types.get(im.trait)
            tnames = set()
            for e in im.entries:
                nm = _name_of(_g(e, "name"))
                if not nm:
                    continue
                tnames.add(nm)
                mty = ANY
                if trait is not None:
                    tf = self._trait_field(trait, nm, e)
                    if tf is not None:
                        mty = self._field_type(tf, Ctx(trait.mod, Scope(), subst=inner.subst))
                supplied.setdefault(nm, []).append((im, Member(
                    nm, mty, "method" if self._is_method_field_entry(e) else "computed",
                    False, owner=trait, impl=im, span=_span(e))))
            if trait is not None:
                for f in trait.fields:
                    nm = _name_of(_g(f, "name"))
                    if not nm or not self._is_method_field(f):
                        continue
                    if nm in tnames and not self._is_sealed_method(f):
                        continue
                    # A SEALED method comes along even when the impl supplies
                    # that name: `Display` declares `toString(sb :: String)`
                    # outlined and `toString(a: Alloc)` sealed and derived
                    # from it, and an impl defining the first must not lose
                    # the second -- they are one overload set.
                    fty = self._field_type(f, Ctx(trait.mod, Scope(), subst=inner.subst))
                    supplied.setdefault(nm, []).append(
                        (im, Member(nm, fty, "method", False, owner=trait,
                                    impl=im, span=_span(f))))

        for nm, cands in supplied.items():
            if nm in out:
                continue        # the type's own storage wins over an impl
            impls, seen = [], set()
            for c in cands:
                if id(c[0]) not in seen:
                    seen.add(id(c[0]))
                    impls.append(c[0])
            if len(cands) == 1:
                out[nm] = cands[0][1]
            elif len(impls) == 1:
                # ONE impl supplying the name twice is an overload set, not a
                # collision: `Display` declares `toString` outlined and
                # sealed, and both arrive through the same impl.
                m = cands[0][1]
                m.overloads = tuple(c[1] for c in cands)
                out[nm] = m
            else:
                impls.sort(key=lambda i: _start(i.span))
                first = cands[0][1]
                # a fresh Member: the candidates themselves stay unmarked, so a
                # bound in scope can select one and it is not still "ambiguous"
                m = Member(first.name, first.ty, first.kind, first.mutable,
                           first.owner, first.impl, first.span)
                m.ambiguous = tuple(
                    (i.span, "impl of %s here" % i.trait_name) for i in impls)
                m.alts = tuple(cands)
                out[nm] = m
        return out

    def _trait_field(self, trait, name, entry=None):
        """The bound's declaration of `name` that `entry` supplies.

        A bound may declare one name TWICE -- `Display` has `toString`
        outlined and sealed -- so returning the first match types an impl's
        member with the OTHER overload's signature. That is how a sink form
        supplied by an impl came out declared `(self, a: Alloc)`, and the
        call then resolved by declaration order rather than by parameter
        type. Arity separates them when it can; when it cannot, prefer the
        one the impl is actually overriding, which is the one WITHOUT a
        body -- a sealed method is derived and is not what an impl supplies.
        """
        found = [f for f in trait.fields if _name_of(_g(f, "name")) == name]
        if not found:
            return None
        if len(found) == 1 or entry is None:
            return found[0]
        want = len(_g(entry, "params", default=()) or ())
        same = [f for f in found
                if len(_g(f, "params", default=()) or ()) == want]
        pool = same or found
        open_ = [f for f in pool if not self._is_sealed_method(f)]
        return (open_ or pool)[0]

    @staticmethod
    def _is_method_field(f):
        """`Struct.fields` is heterogeneous: a storage field is a `Field`, a
        method is a `Function` carrying its form (ast.py's own words)."""
        if _k(f) == "Function":
            return True
        ty = _g(f, "ty", "type")
        if _k(ty) in ("FnType", "Lambda", "Function"):
            return True
        val = _g(f, "default", "value")
        return _k(val) in ("Lambda", "Function")

    @staticmethod
    def _is_sealed_method(f):
        """`= sig {..}`: provided, and an impl may not override it."""
        if _k(f) != "Function":
            return False
        if _g(f, "body") is None:
            return False
        return (_g(f, "form", default="required") or "required") == "sealed"

    @staticmethod
    def _is_method_field_entry(e):
        if _k(e) == "Function":
            return True
        val = _g(e, "value", "default")
        return _k(val) in ("Lambda", "Function")

    @staticmethod
    def _field_required(f):
        """Does an impl have to supply this member?"""
        if _k(f) == "Function":
            form = _g(f, "form", default="required") or "required"
            return form == "required"
        if _g(f, "default", "value") is not None:
            return False        # `verbose :: bool = false` is optional
        ty = _g(f, "ty", "type")
        if _k(ty) in ("FnType",):
            return True
        return True

    def _field_type(self, f, ctx):
        if _k(f) == "Function":
            return self.resolve_type(f, ctx)
        ty = _g(f, "ty", "type")
        if ty is not None:
            return self.resolve_type(ty, ctx)
        val = _g(f, "default", "value")
        if _k(val) in ("Lambda", "Function"):
            return self.resolve_type(val, ctx)
        return ANY

    # ======================================================================
    # the check
    # ======================================================================

    def activate(self):
        """Make this graph the one `assignable` asks about impls. One program
        per process in the bootstrapper; the hook is re-pointed on every
        construction and before every check so the answer can never come from
        a stale graph."""
        global _TRAIT_COERCION
        _TRAIT_COERCION = self.coerces_to_trait

    def check(self):
        self.activate()
        for mi in self.mods:
            self._check_module_decls(mi)
        for mi in self.mods:
            for name in sorted(mi.fns):
                for fd in mi.fns[name]:
                    if fd.tparams:
                        continue    # checked at each instantiation
                    try:
                        self.check_function(fd, {}, None)
                    except RecursionError:
                        # the bar is that the compiler never crashes and never
                        # hangs, on any input (TESTING.md, Fuzzing)
                        self.error(fd.span,
                                   "expression nests too deeply for sema to check "
                                   "`%s`" % fd.name)
        return self.results()

    def results(self):
        seen, out = set(), []
        for d in self.diags:
            key = (_start(d.span), d.message)
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        out.sort(key=lambda d: (_start(d.span), d.message))
        return tuple(out)

    # -- declaration-level checks ------------------------------------------

    def _check_module_decls(self, mi):
        base = Ctx(mi, Scope())

        for name in sorted(mi.type_all):
            for td in mi.type_all[name]:
                if td.mod is not mi:
                    continue
                if td.kind == "struct" and not td.tparams:
                    self.require_type(named(td.qname, ()), None, None)
                    self._check_methods(td)

        for name in sorted(mi.fns):
            fns = mi.fns[name]
            self._check_overload_set(name, fns)
            for fd in fns:
                self._check_signature(fd, base)

        for im in mi.impls:
            self._check_impl(im, base)

    def _check_methods(self, td, self_ty=None):
        """A method is a `Function` in the struct's own field tuple — one
        declaration form, so it is checked exactly like a free function, with
        `@Self` bound."""
        self_ty = self_ty or named(td.qname, ())
        for f in td.fields:
            if _k(f) != "Function" or _g(f, "body") is None or _tup(_g(f, "tparams")):
                continue
            fd = self._fn_from_function(td.mod, f)
            if fd is None:
                continue
            self.check_function(fd, {"@Self": self_ty}, None)

    def _check_signature(self, fd, base):
        ctx = self._fn_ctx(fd, {}, None)
        if fd.exported:
            for node in self._infer_nodes(fd.ret):
                self.error(_span(node),
                           "inferred error set on an exported function: `*` means "
                           "this name crosses a module boundary, so its type is "
                           "written, not inferred")
        if not fd.tparams:
            for p in fd.params:
                self.require_type(self.resolve_type(_g(p, "ty", "type"), ctx),
                                  _span(p), None)
            self.require_type(self.fn_ret(fd, ctx), fd.span, None)

    @staticmethod
    def _infer_nodes(tnode, acc=None):
        acc = [] if acc is None else acc
        if tnode is None:
            return acc
        if _k(tnode) == "Infer":
            acc.append(tnode)
            return acc
        for a in _tup(_g(tnode, "args")):
            Sema._infer_nodes(a, acc)
        for m in _tup(_g(tnode, "members")):
            Sema._infer_nodes(m, acc)
        for p in _tup(_g(tnode, "params")):
            Sema._infer_nodes(_g(p, "ty", "type"), acc)
        if _g(tnode, "ret") is not None:
            Sema._infer_nodes(_g(tnode, "ret"), acc)
        return acc

    def _check_overload_set(self, name, fns):
        """Resolution is on declared parameter types and arity. Two candidates
        differing only in parameter names are the SAME signature."""
        if len(fns) < 2:
            return
        sigs = []
        for fd in fns:
            ctx = self._fn_ctx(fd, {}, None)
            ps = tuple(self.resolve_type(_g(p, "ty", "type"), ctx) for p in fd.params)
            sigs.append((fd, ps, bool(fd.tparams)))
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, pa, ga = sigs[i]
                b, pb, gb = sigs[j]
                if len(pa) != len(pb):
                    continue
                ta = {_name_of(_g(t, "name")) for t in a.tparams}
                tb = {_name_of(_g(t, "name")) for t in b.tparams}
                if self._same_signature(pa, pb):
                    if self._once(("dupsig", _start(a.span), _start(b.span))):
                        self.error(a.span,
                                   "duplicate signature for `%s`: parameter names are "
                                   "documentation, not identity" % name,
                                   ((b.span, "the other declaration is here"),))
                elif (ga or gb) and self._swallows(pa, pb, ta if ga else (),
                                                   tb if gb else ()):
                    if self._once(("swallow", _start(a.span), _start(b.span))):
                        self.error(a.span,
                                   "ambiguous overload for `%s`: a generic parameter "
                                   "swallows a concrete one, so these two can never be "
                                   "told apart at a call site" % name,
                                   ((b.span, "the other declaration is here"),))

    @staticmethod
    def _same_signature(pa, pb):
        for x, y in zip(pa, pb):
            if x.kind == "var" and y.kind == "var":
                continue        # <T>(a: T) and <U>(a: U) are one signature
            if x != y:
                return False
        return True

    @staticmethod
    def _swallows(pa, pb, ta, tb):
        """"A generic parameter swallows a concrete one, so these two can never
        be told apart at a call site."

        Only a type parameter belonging to the CANDIDATE BEING TESTED is a
        wildcard. Without that, `loop<R, T>(range: R, body: (h, index, value) ())`
        and `loop<K, V>(map: Map<K,V>, body: (h, key, value) ())` look
        interchangeable because each has a three-parameter closure — and the
        prelude declares both."""

        def eats(x, y, names):
            if x.kind == "var" and x.name in names:
                return True
            if x.kind == "fn" and y.kind == "fn":
                if len(x.args) != len(y.args):
                    return False
                return (all(eats(i, j, names) for i, j in zip(x.args, y.args))
                        and eats(x.ret or UNIT, y.ret or UNIT, names))
            if x.kind == y.kind and x.name == y.name and len(x.args) == len(y.args):
                return all(eats(i, j, names) for i, j in zip(x.args, y.args))
            return x == y

        def all_eat(g, c, names):
            return names and all(eats(x, y, names) for x, y in zip(g, c))

        return all_eat(pa, pb, ta) or all_eat(pb, pa, tb)

    def _check_impl(self, im, base):
        trait = self.types.get(im.trait)
        if trait is None or trait.kind != "struct":
            return
        given = set()
        for e in im.entries:
            nm = _name_of(_g(e, "name"))
            if nm:
                given.add(nm)
        for f in trait.fields:
            nm = _name_of(_g(f, "name"))
            if not nm or nm in given:
                continue
            if not self._field_required(f):
                continue        # sealed, defaulted, or an optional hook
            self.error(im.span,
                       "impl of %s is missing field `%s`: an impl supplies a value "
                       "for every field the target declares"
                       % (im.trait_name, nm))
        # the entries themselves are checked with `self` bound to the target
        self_ty = named(im.target, ()) if im.target in self.types else ANY
        ctx = Ctx(im.mod, Scope(),
                  subst=(("@Self", self_ty),) if self_ty is not ANY else ())
        ctx.scope.put("self", Sym("value", self_ty))
        for e in im.entries:
            if _k(e) == "Function":
                if _g(e, "body") is not None and not _tup(_g(e, "tparams")):
                    fd = self._fn_from_function(im.mod, e)
                    if fd is not None:
                        self.check_function(fd, {"@Self": self_ty}, None)
                continue
            val = _g(e, "value", "default")
            if val is not None:
                self.type_of(val, ctx)

    # -- layout / recursive types ------------------------------------------

    def require_type(self, ty, span, frame):
        """Naming a type in a signature is enough to require its layout."""
        if ty is None or ty.kind != "named" or ty.name.startswith("@"):
            for a in (ty.args if ty is not None else ()):
                self.require_type(a, span, frame)
            return
        td = self.types.get(ty.name)
        if td is None or td.kind != "struct":
            return
        key = (ty.name, ty.args)
        if key in self._layout_done:
            return
        self.type_instances.setdefault(key, td)
        self._layout(td, ty.args, Frame("type", key, td.name, ty.args, span, frame))

    def _layout(self, td, args, frame):
        key = (td.qname, tuple(args))
        if key in self._layout_done:
            return
        # a cycle: the same instantiation already on the stack has no finite size
        f, chain = frame.parent, [frame]
        while f is not None:
            chain.append(f)
            if f.key == key:
                blame = None
                for x in chain:
                    blame = _earlier(blame, x.site)
                cycle = " -> ".join(x.label for x in reversed(chain)) + " -> " + td.name
                if self._once(("infsize", _start(blame))):
                    self.error(blame,
                               "infinite size: the field cycle %s never reaches an "
                               "indirection, so the layout does not terminate "
                               "(`Ptr<%s>` is the finite form)" % (cycle, td.name))
                self._layout_done[key] = True
                return
            f = f.parent

        if frame.depth > self.budget:
            self._blame_depth(frame, "type")
            self._layout_done[key] = True
            return

        sub = {}
        for tp, a in zip(td.tparams, args):
            nm = _name_of(_g(tp, "name"))
            if nm:
                sub[nm] = a
        sub["@Self"] = named(td.qname, tuple(args))
        ctx = Ctx(td.mod, Scope(), subst=tuple(sorted(sub.items(), key=lambda x: x[0])))
        for fl in td.fields:
            if self._is_method_field(fl):
                continue
            fty = self._field_type(fl, ctx)
            if fty is None or fty.kind != "named" or fty.name.startswith("@"):
                # a builtin (Ptr, Vec, ..) is an indirection or opaque: stop
                continue
            sub_td = self.types.get(fty.name)
            if sub_td is None or sub_td.kind != "struct":
                continue
            self.type_instances.setdefault((fty.name, fty.args), sub_td)
            self._layout(sub_td, fty.args,
                         Frame("type", (fty.name, fty.args), sub_td.name,
                               fty.args, _span(fl), frame))
        self._layout_done[key] = True

    def _blame_depth(self, frame, what):
        """Blame the innermost frame that WIDENED its type arguments — not
        whichever frame happened to hit the ceiling. That is what makes the
        mutual case (`ping<T> -> pong<Vec<T>> -> ping<Vec<T>>`) point at the
        call that grows rather than at the one that merely forwards."""
        f, fallback = frame, frame
        while f is not None:
            if f.widens():
                break
            if f.site is not None:
                fallback = f
            f = f.parent
        blame = f if f is not None else fallback
        names = []
        g = frame
        while g is not None:
            names.append(g.label)
            g = g.parent
        tag = ("depth", tuple(sorted(set(names))))
        if not self._once(tag):
            return
        self.error(blame.site,
                   "instantiation depth exceeded (%d): %s keeps widening its type "
                   "argument, so the instantiation set is infinite"
                   % (self.budget, blame.label))

    # -- functions ----------------------------------------------------------

    def _fn_ctx(self, fd, sub, frame):
        bounds = []
        base = Ctx(fd.mod, Scope(), subst=tuple(sorted(sub.items(), key=lambda x: x[0])))
        for tp in fd.tparams:
            nm = _name_of(_g(tp, "name"))
            if not nm:
                continue
            bounds.append((nm, self._bounds_of(tp, base)))
        ctx = Ctx(fd.mod, Scope(), fn=fd, ret=ANY,
                  subst=tuple(sorted(sub.items(), key=lambda x: x[0])),
                  bounds=tuple(bounds), frame=frame)
        return ctx

    def fn_ret(self, fd, ctx):
        """The declared return type, with an inferred error set filled in."""
        ret = self.resolve_type(fd.ret, ctx) if fd.ret is not None else UNIT
        if fd.ret is not None and _k(fd.ret) in ("Named", "Path", "Identifier"):
            if _g(fd.ret, "name") == "Res":
                args = _tup(_g(fd.ret, "args"))
                if len(args) == 2 and _k(args[1]) == "Infer":
                    ret = res_ty(ret.args[0] if ret.args else ANY,
                                 self.error_set_of(fd))
        return ret

    def check_function(self, fd, sub, frame):
        key = (id(fd.node), tuple(sorted(sub.items(), key=lambda x: x[0])))
        if key in self._checked:
            return
        self._checked.add(key)
        self._keep.append(fd.node)
        self.fn_instances[key] = (fd, tuple(v for _, v in sorted(sub.items())))

        ctx = self._fn_ctx(fd, sub, frame)
        ret = self.fn_ret(fd, ctx)
        ctx = Ctx(ctx.mod, Scope(), fd, ret, ctx.subst, ctx.bounds, frame)
        for p in fd.params:
            nm = _name_of(_g(p, "name"))
            if not nm:
                continue
            pty = self.resolve_type(_g(p, "ty", "type"), ctx)
            self.require_type(pty, _span(p), frame)
            ctx.scope.put(nm, Sym("value", pty, mutable=bool(_g(p, "mutable", default=False))))
        self.require_type(ret, fd.span, frame)
        if fd.body is not None:
            self.check_block(fd.body, ctx, expect=ret, is_fn_body=True)

    # -- statements ---------------------------------------------------------

    def check_block(self, blk, ctx, expect=None, is_fn_body=False):
        if blk is None:
            return UNIT
        stmts = list(_tup(_g(blk, "stmts", "statements")))
        tail = _g(blk, "value")
        promoted = False
        if tail is None and stmts:
            # `Ok(0);` closes a function: a trailing expression statement is
            # the block's value, semicolon or not.
            last = stmts[-1]
            if _k(last) == "ExprStmt":
                tail = _g(last, "expr")
                stmts = stmts[:-1]
                promoted = True
        inner = ctx.with_scope(ctx.scope.child())
        for s in stmts:
            self.check_stmt(s, inner)
        if tail is None:
            if is_fn_body and expect is not None and expect.kind not in (
                    "unit", "any", "error", "never"):
                pass    # a body with no value: gen_c's problem, not sema's
            return UNIT
        ty = self.type_of(tail, inner, expect=expect)
        if expect is not None:
            if promoted and ty is not None and ty.kind == "unit":
                return ty   # a last statement that yields nothing is not a value
            self.coerce(ty, expect, _span(tail), tail)
        return ty

    def check_stmt(self, s, ctx):
        k = _k(s)
        if s is None:
            return
        if k == "Block":
            self.check_block(s, ctx)
            return
        if k == "ExprStmt":
            self.type_of(_g(s, "expr"), ctx)
            return
        if k in ("Let", "Binding"):
            self._check_let(s, ctx)
            return
        if k in ("Assign", "Set", "Store"):
            tgt = _g(s, "target", "lhs")
            val = _g(s, "value", "rhs")
            self._check_assign(tgt, val, ctx)
            return
        if k in ("Struct", "Enum", "Alias", "Function", "Impl", "Const", "Import"):
            return      # declarations inside a body: indexed at module level
        # anything else that is an expression
        if hasattr(s, "span"):
            self.type_of(s, ctx)

    def _check_let(self, s, ctx):
        name = _g(s, "name", "target")
        val = _g(s, "value")
        if not isinstance(name, str) and name is not None and _k(name) in (
                "Member", "Index", "Path", "Identifier"):
            self._check_assign(name, val, ctx)
            return
        nm = _name_of(name)
        tnode = _g(s, "ty", "type")
        declared = self.resolve_type(tnode, ctx) if tnode is not None else None
        if _k(val) in ("Lambda", "Function") and declared is None:
            fty = self._lambda_type(val, ctx, None)
            if nm:
                ctx.scope.put(nm, Sym("value", fty,
                                      mutable=bool(_g(s, "mutable", default=False))))
            self._check_lambda_body(val, ctx, None)
            return
        ty = self.type_of(val, ctx, expect=declared) if val is not None else ANY
        if declared is not None:
            self.require_type(declared, _span(s), ctx.frame)
            self.coerce(ty, declared, _span(val) or _span(s), val)
            ty = declared
        else:
            # An unannotated integer binding keeps the literal's own type:
            # `n ::= 0` counting into a `usize` is not a type error, and
            # DESIGN.md gives no widening rule that would make it one. Pinning
            # it to i32 here invents a conversion the language does not have.
            ty = settle(ty) if ty.kind in ("ok", "err", "none") else ty
        if nm:
            ctx.scope.put(nm, Sym("value", ty,
                                  mutable=bool(_g(s, "mutable", default=False))))

    def _check_assign(self, target, value, ctx):
        vty = self.type_of(value, ctx) if value is not None else ANY
        if target is None:
            return
        if _k(target) == "Member":
            base = _g(target, "base", "object")
            nm = _g(target, "name", "property")
            bty = self.type_of(base, ctx)
            m = self._member(bty, _name_of(nm) or nm, ctx)
            if m is not None and m.kind == "computed":
                self.error(_span(target),
                           "cannot assign to computed field `%s`: an impl-supplied "
                           "field has no storage, so there is nothing to assign into"
                           % m.name)
                return
            if m is not None:
                self.coerce(vty, m.ty, _span(value) or _span(target), value)
            return
        tty = self.type_of(target, ctx)
        self.coerce(vty, tty, _span(value) or _span(target), value)

    # -- coercion, hoisting -------------------------------------------------

    def coerce(self, ty, expect, span, node=None):
        if ty is None or expect is None:
            return
        if expect.kind in ("any", "error") or ty.kind in ("any", "error", "never"):
            return
        if expect.kind == "unit":
            # a `()` position discards the value — statement position, and a
            # function declared `()` whose body ends in an expression
            return
        if assignable(ty, expect):
            if node is not None:
                self._check_literal_fits(node, ty, expect, span)
                # `Ok(0)` in a `Res<i32, Error>` position IS a Res<i32, Error>:
                # the expectation is the only thing that knows the error set,
                # and gen_c needs the whole type to lay the value out.
                if ty.kind in ("ok", "err", "none", "intlit", "floatlit"):
                    self._record_type(node, expect)
            return
        if expect.kind == "res":
            self._hoist(ty, expect, span)
            return
        if is_res(ty) and expect.kind == "res":
            self._hoist(ty, expect, span)
            return
        self.error(span, "expected %s, found %s" % (show(expect), show(ty)))

    def _hoist(self, ty, expect, span):
        """A bare `T` lifts into `Res<T>` only when exactly ONE variant carries
        the type — and only success lifts."""
        if ty.kind in ("ok", "err", "none", "res"):
            # a Res that does not fit the expected Res: say why precisely
            got = settle(ty)
            if len(got.args) == 1 and len(expect.args) == 2:
                self.error(span, "%s is not %s: a None never becomes an Err"
                           % (show(got), show(expect)))
            elif not assignable(got.args[0], expect.args[0]):
                # blame what actually mismatched: the payload, not the set
                self.error(span, "expected %s, found %s"
                           % (show(expect.args[0]), show(got.args[0])))
            elif len(got.args) == 2 and len(expect.args) == 2:
                self.error(span, "no implicit error conversion: %s is not %s"
                           % (show(got.args[1]), show(expect.args[1])))
            else:
                self.error(span, "expected %s, found %s" % (show(expect), show(got)))
            return
        cands = [(nm, ptys) for nm, ptys in (self.ctors_of(expect) or [])
                 if len(ptys) == 1 and assignable(ty, ptys[0])]
        if len(cands) == 1:
            if cands[0][0] == "Ok":
                return
            self.error(span,
                       "only success lifts into Res: `%s` must be written out, "
                       "failure stays visible" % cands[0][0])
            return
        if len(cands) > 1:
            self.error(span,
                       "%s cannot be hoisted into %s: hoisting fires only when "
                       "exactly one variant carries the type, so write the variant "
                       "out" % (show(ty), show(expect)))
            return
        self.error(span, "expected %s, found %s" % (show(expect), show(ty)))

    def _check_literal_fits(self, node, ty, expect, span):
        if not PROVEN_TRAPS_ARE_ERRORS:
            return
        if expect is None or expect.kind != "prim" or expect.name not in _INT_PRIMS:
            return
        v = self.const_int(node)
        if v is None:
            return
        if not self._fits(v, expect.name):
            lo, hi = self._limits(expect.name)
            self.error(_span(node) or span,
                       "literal %d does not fit %s: %s holds %d..%d, so the "
                       "value is out of range" % (v, expect.name, expect.name, lo, hi))

    @staticmethod
    def _limits(primname):
        """What the type holds, named in the diagnostic. A reader who has to
        go look up the range of `u8` to understand the error is being told
        the value is wrong without being told what right would have been."""
        bits, signed = _INT_PRIMS[primname]
        return (-(1 << (bits - 1)), (1 << (bits - 1)) - 1) if signed else (0, (1 << bits) - 1)

    @staticmethod
    def _fits(v, primname):
        bits, signed = _INT_PRIMS[primname]
        if signed:
            return -(1 << (bits - 1)) <= v <= (1 << (bits - 1)) - 1
        return 0 <= v <= (1 << bits) - 1

    # -- constants ----------------------------------------------------------

    def const_int(self, node, ctx=None):
        """Fold literals only. A binding is never folded through: the trap
        corpus deliberately routes `i32.MAX` through a variable so the compiler
        cannot see it."""
        if node is None:
            return None
        k = _k(node)
        if k == "Literal":
            if _g(node, "kind") == "int":
                try:
                    return int(str(_g(node, "text", default="")).replace("_", ""))
                except Exception:
                    return None
            return None
        if k == "Unary":
            op = _g(node, "op", "operator")
            v = self.const_int(_g(node, "operand"), ctx)
            if v is None:
                return None
            return -v if op == "-" else None
        if k == "Member":
            base = _g(node, "base", "object")
            nm = _name_of(_g(node, "name", "property")) or _g(node, "name", "property")
            bn = _g(base, "name") if _k(base) in ("Path", "Identifier") else None
            if isinstance(bn, str) and bn in _INT_PRIMS and isinstance(nm, str):
                bits, signed = _INT_PRIMS[bn]
                if nm == "BITS":
                    return bits
                if nm == "MAX":
                    return (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1
                if nm == "MIN":
                    return -(1 << (bits - 1)) if signed else 0
            return None
        if k == "Binary":
            op = _g(node, "op", "operator")
            a = self.const_int(_g(node, "lhs", "left"), ctx)
            b = self.const_int(_g(node, "rhs", "right"), ctx)
            if a is None or b is None:
                return None
            try:
                if op == "+":
                    return a + b
                if op == "-":
                    return a - b
                if op == "*":
                    return a * b
                if op == "/":
                    return None if b == 0 else int(a / b)
                if op == "%":
                    return None if b == 0 else a - int(a / b) * b
            except Exception:
                return None
        return None

    def const_value(self, node, ctx=None):
        return self.const_int(node, ctx)

    # ======================================================================
    # type_of
    # ======================================================================

    def type_of(self, node, ctx=None, expect=None):
        """The query.

        With no `ctx` this is an outside caller — gen_c asking what an
        expression is, the LSP asking for a hover — so it answers quietly (no
        diagnostic escapes a question) and in the AST's own vocabulary, which
        is what `gen_c.py` documents it wants: `sema.type_of(expr) -> a Type
        node, or None`. `ty_of` is the same query in sema's richer type
        language, for callers that want error sets and open `Ok`s.
        """
        if node is None:
            return ANY
        if ctx is None:
            return self.as_ast_type(self.ty_of(node), _span(node))
        key = (id(node), ctx.key, expect)
        hit = self._memo.get(key, _MISS)
        if hit is not _MISS:
            return hit
        self._keep.append(node)
        self._memo[key] = ANY      # recursion guard
        try:
            ty = self._type_of(node, ctx, expect)
        except RecursionError:
            ty = ERR
        except Exception as exc:   # never raise: one bad node is not the run
            self.error(_span(node), "internal error in sema: %s" % (exc,))
            ty = ERR
        self._memo[key] = ty
        self._record_type(node, ty)
        return ty

    @staticmethod
    def _vagueness(ty):
        """How much of a type is still unknown. Used to keep the most
        informative answer when a node is checked more than once — a generic
        body is checked per instantiation, and the instantiated answer is the
        one gen_c and the LSP want."""
        if ty is None:
            return 99
        if ty.kind in ("any", "error", "never", "var", "variadic", "intlit",
                       "floatlit", "ok", "err", "none"):
            return 1 + sum(Sema._vagueness(a) for a in ty.args)
        n = sum(Sema._vagueness(a) for a in ty.args)
        if ty.ret is not None:
            n += Sema._vagueness(ty.ret)
        return n

    def _record_type(self, node, ty):
        if node is None or ty is None or self._muted:
            return
        prev = self.node_type.get(id(node))
        if prev is None or self._vagueness(ty) < self._vagueness(prev):
            self._keep.append(node)
            self.node_type[id(node)] = ty

    def _quiet_ctx(self, node):
        """A best-effort context for an outside query: the module the node was
        written in, if its span says which."""
        mi = None
        sp = _span(node)
        f = getattr(sp, "file", None) if sp is not None else None
        if f:
            for m in self.mods:
                if m.path == f or m.path.endswith("/" + str(f)):
                    mi = m
                    break
        if mi is None:
            mi = self.mods[0] if self.mods else ModInfo("", "", None, (), "")
        return Ctx(mi, Scope(), quiet=True)

    def ty_of(self, node, ctx=None):
        """`type_of` in sema's own type language: error sets, open `Ok`s, and
        the literal types the AST has no node for."""
        if node is None:
            return ANY
        if ctx is not None:
            return self.type_of(node, ctx)
        got = self.node_type.get(id(node))
        if got is not None:
            return got      # what checking concluded, in the context it had
        self._muted += 1
        try:
            return self.type_of(node, self._quiet_ctx(node))
        finally:
            self._muted -= 1

    def ast_type_of(self, node):
        """`type_of` as an ast Type node. Kept as the explicit spelling."""
        return self.as_ast_type(self.ty_of(node), _span(node))

    @staticmethod
    def _concrete(ty):
        """gen_c documents `type_of -> a Type node, or None`. None is the
        honest answer for anything still carrying a type parameter or an
        inference hole: handing gen_c a bare `T` makes it report `unknown type
        T` where it would otherwise have resolved the type itself."""
        if ty is None:
            return False
        if ty.kind in ("var", "any", "error", "never", "variadic"):
            return False
        if not all(Sema._concrete(a) for a in ty.args):
            return False
        return ty.ret is None or Sema._concrete(ty.ret)

    def as_ast_type(self, ty, span=None):
        if ty is None or A is None or not self._concrete(ty):
            return None
        mk = lambda cls, *a: cls(*a, span=span or Span("", (1, 1), (1, 1)))
        if ty.kind == "unit":
            return mk(getattr(A, "Unit"))
        if ty.kind in ("any", "error", "never"):
            return None
        if ty.kind in ("prim", "var"):
            return mk(getattr(A, "Named"), ty.name, ())
        if ty.kind == "intlit":
            return mk(getattr(A, "Named"), "i32", ())
        if ty.kind == "floatlit":
            return mk(getattr(A, "Named"), "f64", ())
        if ty.kind == "named":
            return mk(getattr(A, "Named"), base_name(ty.name),
                      tuple(x for x in (self.as_ast_type(a, span) for a in ty.args)
                            if x is not None))
        if ty.kind in ("res", "ok", "err", "none"):
            t = settle(ty)
            return mk(getattr(A, "Named"), "Res",
                      tuple(x for x in (self.as_ast_type(a, span) for a in t.args)
                            if x is not None))
        if ty.kind == "union":
            return mk(getattr(A, "Union"),
                      tuple(x for x in (self.as_ast_type(a, span) for a in ty.args)
                            if x is not None))
        if ty.kind == "array":
            elem = self.as_ast_type(ty.args[0], span)
            cnt = mk(getattr(A, "Literal"), "int", ty.name or "0")
            return mk(getattr(A, "ArrayType"), elem, cnt) if elem is not None else None
        if ty.kind == "fn":
            names = ty.pnames or tuple("p%d" % i for i in range(len(ty.args)))
            ps = []
            for nm, a in zip(names, ty.args):
                ps.append(mk(getattr(A, "Param"), nm, self.as_ast_type(a, span), False))
            return mk(getattr(A, "FnType"), tuple(ps), self.as_ast_type(ty.ret, span))
        return None

    def resolve(self, node, module=None):
        """The declaration a Path or Member names — go-to-definition.

        A call resolved during checking answers from the table: overload
        resolution already decided, and the name alone cannot say which."""
        if node is None:
            return None
        fd = self.call_target.get(id(node))
        if fd is not None:
            return fd.node
        k = _k(node)
        mi = module or self._quiet_ctx(node).mod
        if k in ("Path", "Identifier"):
            name = _g(node, "name")
            td = self.lookup_type(mi, name)
            if td is not None:
                return td.node
            fns = self.lookup_fns(mi, name)
            if fns:
                return fns[0].node
            return None
        if k == "Member":
            self._muted += 1
            try:
                bty = self.type_of(_g(node, "base"), self._quiet_ctx(node))
            finally:
                self._muted -= 1
            m = self.members_of(bty).get(_g(node, "name"))
            return getattr(m, "owner", None).node if (m and m.owner) else None
        return None

    def _type_of(self, node, ctx, expect):
        k = _k(node)
        fn = getattr(self, "_t_" + k, None)
        if fn is None:
            return ANY
        return fn(node, ctx, expect)

    # -- leaves -------------------------------------------------------------

    def _t_Literal(self, node, ctx, expect):
        kind = _g(node, "kind", default="")
        if kind == "int":
            return INTLIT
        if kind == "float":
            return FLOATLIT
        if kind == "str":
            return STR
        if kind == "char":
            return prim("u8")
        if kind == "bool":
            return BOOL
        if kind == "unit":      # ast.py encodes `()` as a literal
            return UNIT
        return ANY

    def _t_Unit(self, node, ctx, expect):
        return UNIT

    def _t_ScopeRef(self, node, ctx, expect):
        return self.builtin_named("Scope")

    def _t_MetaCall(self, node, ctx, expect):
        return ANY

    def _t_Consume(self, node, ctx, expect):
        # stage 3 owns the move checker; sema must merely not choke on it
        return self.type_of(_g(node, "operand", "value"), ctx)

    def _t_SelfType(self, node, ctx, expect):
        return dict(ctx.subst).get("@Self", ANY)

    def _t_Path(self, node, ctx, expect):
        name = _g(node, "name")
        sym = self.resolve_name(name, ctx, node)
        if sym is None:
            return ERR
        if sym.kind == "module":
            return self.module_not_a_value(name, sym.decl, node)
        if sym.kind == "type":
            td = sym.decl
            if isinstance(td, TypeDef):
                return self.type_from_def(td, (), ctx)
            return sym.ty
        if sym.kind == "fns":
            defs = sym.defs
            if len(defs) == 1 and not defs[0].tparams:
                c = self._fn_ctx(defs[0], {}, ctx.frame)
                return fn_ty(tuple(self.resolve_type(_g(p, "ty", "type"), c)
                                   for p in defs[0].params),
                             self.fn_ret(defs[0], c),
                             tuple(_name_of(_g(p, "name")) or "_" for p in defs[0].params))
            return ANY
        return sym.ty

    _t_Identifier = _t_Path

    def resolve_name(self, name, ctx, node=None, quiet=False):
        if not isinstance(name, str):
            return None
        s = ctx.scope.get(name)
        if s is not None:
            return s
        sub = dict(ctx.subst)
        if name in sub:
            return Sym("type", sub[name])
        for tp, _b in ctx.bounds:
            if tp == name:
                return Sym("type", var_ty(name))
        td = self.lookup_type(ctx.mod, name)
        if td is not None:
            mi = self.module_alias(td)
            if mi is not None:
                return Sym("module", ERR, decl=mi)
            return Sym("type", ANY, decl=td)
        fns = self.lookup_fns(ctx.mod, name)
        if fns:
            return Sym("fns", ANY, defs=fns)
        if name in ctx.mod.consts:
            c = ctx.mod.consts[name]
            tnode = _g(c, "ty", "type")
            if tnode is not None:
                return Sym("value", self.resolve_type(tnode, ctx))
            val = _g(c, "value")
            return Sym("value", self.type_of(val, Ctx(ctx.mod, Scope())) if val is not None else ANY)
        if name in ("Ok", "Err", "None", "Some"):
            return Sym("builtin_fn", ANY, decl=name)
        if name in BUILTIN_FNS:
            return Sym("builtin_fn", ANY, decl=name)
        if self.is_builtin_type(name):
            return Sym("type", self.builtin_named(name), decl=name)
        if name in ctx.mod.imports:
            return Sym("error", ERR)     # modules.py reports this one
        if name == "self":
            return Sym("value", sub.get("@Self", ANY))
        if not quiet and not ctx.quiet:
            self.error(_span(node), "undefined name `%s`" % name)
        return None

    def module_alias(self, td):
        """The ModuleInfo `sh = shape` names, or None if it is a type alias.

        Grammar R1a makes a single bare name on the right an ALIAS rather than
        an import, so that `Alias = Shape` needs no lookahead. That decision
        leaves the two readings sharing one node, and this is what tells them
        apart: an alias whose target names a module and no type is a MODULE
        alias, and a module is a namespace, not a type and not a value.

        The distinction is load-bearing for the `*` gate. Every other spelling
        of an import goes through `modules.py`, which checks exportedness; a
        bare alias went through `lookup_type` instead, where nothing thought a
        module was involved -- so `reseat = vec` beside an unstarred `reseat`
        in `vec` made the unexported name callable."""
        if td is None or td.kind != "alias" or td.tparams:
            return None
        target = td.target
        if _k(target) not in ("Named", "Path", "Identifier"):
            return None
        if _tup(_g(target, "args")):
            return None
        name = _g(target, "name", default=None)
        if not isinstance(name, str):
            return None
        mi = self.by_dotted.get(name)
        if mi is None or mi is td.mod or self.is_builtin_type(name):
            return None
        # a type of that name wins: `Alias = Shape` is a type alias even in a
        # tree that also has a module called `Shape`.
        other = self.lookup_type(td.mod, name)
        return None if other is not None and other is not td else mi

    def module_not_a_value(self, name, mi, node):
        self.error(_span(node),
                   "`%s` names module `%s`: a module is only usable qualified, "
                   "as `%s.<name>`" % (name, mi.name, name))
        return ERR

    # -- member -------------------------------------------------------------

    def _member(self, bty, name, ctx):
        if bty is None or not isinstance(name, str):
            return None
        m = self.members_of(bty, ctx).get(name)
        if m is not None and m.ambiguous and ctx is not None:
            sel = self._select_by_bound(m, ctx)
            if sel is not None:
                return sel
        return m

    def _select_by_bound(self, m, ctx):
        """"When two impls declare the same name, the bound in scope selects
        which is in view" — and after monomorphisation the receiver is the
        concrete type, so the bound has to do the selecting here rather than
        through the type."""
        traits = set()
        for _tp, bounds in ctx.bounds:
            for b in bounds:
                if b is not None and b.kind == "named" and not b.name.startswith("@"):
                    td = self.types.get(b.name)
                    if td is not None and any(
                            _name_of(_g(f, "name")) == m.name for f in td.fields):
                        traits.add(b.name)
        if len(traits) != 1:
            return None
        want = traits.pop()
        picked = [alt for im, alt in m.alts if im.trait == want]
        return picked[0] if len(picked) == 1 else None

    def _t_Member(self, node, ctx, expect):
        base = _g(node, "base", "object")
        name = _name_of(_g(node, "name", "property")) or _g(node, "name", "property")
        if not isinstance(name, str):
            return ANY

        # `Type.NAME` — a variant, or a constant on a type
        static = self._static_base(base, ctx)
        if static is not None:
            return self._static_member(static, name, node, ctx)

        bty = self.type_of(base, ctx)
        if bty.kind in ("error", "any"):
            return ERR if bty.kind == "error" else ANY
        m = self._member(bty, name, ctx)
        if m is None:
            # UFCS: a free function whose first parameter is this type travels
            # with the type and calls as a method.
            fns = self.lookup_fns(ctx.mod, name)
            if fns:
                return ANY
            return ANY
        if m.ambiguous:
            self.error(_after_dot(base, _span(node), len(name)),
                       "field `%s` is ambiguous: two impls supply it and no bound in "
                       "scope selects one" % name,
                       m.ambiguous)
        return m.ty

    def _static_base(self, base, ctx):
        """`Slot` in `Slot.Gone` / `i32` in `i32.MAX`: a TYPE, not a value.
        Or `sh` in `sh.Bag` after `sh = shape`: a MODULE, which is a namespace
        and reaches only what the module starred."""
        if _k(base) not in ("Path", "Identifier"):
            return None
        name = _g(base, "name")
        if not isinstance(name, str):
            return None
        if ctx.scope.get(name) is not None:
            return None
        td = self.lookup_type(ctx.mod, name)
        if td is not None:
            mi = self.module_alias(td)
            return ("module", mi) if mi is not None else ("user", td)
        if self.is_builtin_type(name):
            return ("builtin", name)
        return None

    def _static_member(self, static, name, node, ctx):
        kind, what = static
        if kind == "module":
            # `modules.py` gates members and free functions by name, wherever
            # they are reached from. A TYPE has no such gate, so qualifying
            # through a module alias was the one way to name an unstarred one.
            td = what.types.get(name) or self.lookup_type(what, name)
            if td is None:
                return ANY
            if not td.exported and td.mod is not ctx.mod:
                self.error(_after_dot(_g(node, "base", "object"), _span(node), len(name)),
                           "%s is not exported by module %s" % (name, what.name))
                return ERR
            return self.type_from_def(td, (), ctx)
        if kind == "builtin":
            if what in _INT_PRIMS and name in ("MIN", "MAX"):
                return prim(what)
            if what in _INT_PRIMS and name == "BITS":
                return USIZE
            if what in _FLOAT_PRIMS and name in ("MIN", "MAX"):
                return prim(what)
            spec = BUILTIN_ENUMS.get(what)
            if spec is not None and name in spec:
                pl = spec[name]
                ety = self.builtin_named(what)
                if pl is None:
                    return ety
                return fn_ty((self._read_type(pl, {}),), ety, ("payload",))
            return ANY
        td = what
        if td.kind == "enum":
            for v in td.variants:
                if _name_of(_g(v, "name")) == name:
                    ety = self.type_from_def(td, (), ctx)
                    pl = _g(v, "payload")
                    if pl is None:
                        return ety
                    inner = Ctx(td.mod, Scope(), subst=ctx.subst)
                    return fn_ty(tuple(self.resolve_type(p, inner) for p in _tup(pl)),
                                 ety, tuple("p%d" % i for i in range(len(_tup(pl)))))
            return ANY
        if td.kind == "struct":
            for c in td.consts:
                if _name_of(_g(c, "name")) == name:
                    tnode = _g(c, "ty", "type")
                    return self.resolve_type(tnode, Ctx(td.mod, Scope())) if tnode else ANY
            m = self.members_of(named(td.qname, ()), ctx).get(name)
            if m is not None:
                return m.ty
        return ANY

    # -- unary / binary / index --------------------------------------------

    def _t_Unary(self, node, ctx, expect):
        op = _g(node, "op", "operator")
        operand = _g(node, "operand", "value")
        if op == "&":
            if _k(operand) == "Member":
                base = _g(operand, "base", "object")
                nm = _name_of(_g(operand, "name", "property")) or _g(operand, "name", "property")
                bty = self.type_of(base, ctx)
                m = self._member(bty, nm, ctx)
                if m is not None and m.kind == "computed":
                    self.error(_span(node),
                               "cannot take the address of computed field `%s`: "
                               "there is no storage, so no address exists" % m.name)
                    return ERR
            t = self.type_of(operand, ctx)
            return self.builtin_named("Ptr", (t,))
        t = self.type_of(operand, ctx)
        if op == "!":
            return BOOL
        return t

    _CMP = {"==", "!=", "<", ">", "<=", ">="}
    _LOGIC = {"&&", "||"}
    _WRAP = {"+%", "-%", "*%"}

    def _t_Binary(self, node, ctx, expect):
        op = _g(node, "op", "operator") or ""
        lhs = _g(node, "lhs", "left")
        rhs = _g(node, "rhs", "right")
        if op == "=":
            # ast.py encodes `self.len = self.len + 1;` as Binary("=", ..)
            self._check_assign(lhs, rhs, ctx)
            return UNIT
        lt = self.type_of(lhs, ctx)
        rt = self.type_of(rhs, ctx)
        if op in self._LOGIC:
            return BOOL
        if op in self._CMP:
            if op in ("==", "!="):
                self._check_eq_operands(node, lt, rt)
            return BOOL
        res = lt
        if lt.kind in ("intlit", "floatlit") and rt.kind not in ("intlit", "floatlit"):
            res = rt
        if PROVEN_TRAPS_ARE_ERRORS and op not in self._WRAP:
            self._proven_trap(node, op, lhs, rhs, res, ctx)
        return res

    def _check_eq_operands(self, node, lt, rt):
        """`==` is `Eq.eq`, so a type with no `Eq` cannot be compared with it.

        gen_c already lowers `==` on a named type to the `eq` its impl
        supplies — `str.impl(Eq, ..)` is where str's bytewise equality is
        written. With no impl there is nothing to call, and a C `==` on a
        struct or an enum is not legal C, so the operator is refused here
        rather than reaching the C compiler.

        Comparing tags and payloads structurally is the alternative and it is
        worse: DESIGN.md lets an impl override `eq` for custom equality, and a
        `==` that compared bytes instead would disagree with `.eq()` on the
        same two values — which is exactly what the sealed law "ne is always
        !eq, they can never diverge" exists to prevent.
        """
        ty = settle(lt)
        if ty.kind in ("any", "error", "never", "variadic"):
            ty = settle(rt)
        # primitives and pointers compare with C's own `==`; a type parameter
        # is re-checked at every instantiation, where it is concrete
        if ty.kind not in ("named", "res", "union", "array"):
            return
        if ty.kind == "named" and (not ty.name or ty.name.startswith("@")):
            return
        if self._impls_eq(ty):
            return
        fix = ("write `%s.impl(Eq, { .. })`" % base_name(ty.name)
               if ty.kind == "named" else "match on it")
        self.error(_span(node),
                   "`==` needs an `Eq`, and %s does not impl one: equality is a "
                   "trait, so %s or compare the parts" % (show(ty), fix))

    def _impls_eq(self, ty):
        if ty.kind != "named":
            return False  # Res, an anonymous union, an array: nothing owns them
        target = self._decl_qname(ty)
        if target is None:
            return True  # nothing is known about it; do not invent an error
        for im in self.impls_of(target):
            if im.trait_name == "Eq" or base_name(im.trait) == "Eq":
                return True
        # a type that declares its own `eq` satisfies `Eq` without an impl
        # block — "you satisfy requirements", and an impl is not the only way
        return "eq" in self.members_of(ty)

    def _proven_trap(self, node, op, lhs, rhs, res, ctx):
        if op in ("/", "%"):
            b = self.const_int(rhs, ctx)
            if b == 0:
                self.error(_span(node),
                           "divide by zero: this trap is provable at compile time")
                return
            a = self.const_int(lhs, ctx)
            if a is not None and b is not None and res.kind == "prim" \
                    and res.name in _INT_PRIMS:
                bits, signed = _INT_PRIMS[res.name]
                if signed and b == -1 and a == -(1 << (bits - 1)):
                    self.error(_span(node),
                               "integer overflow: %s.MIN / -1 is an overflow wearing "
                               "division's clothes" % res.name)
            return
        if op in ("+", "-", "*"):
            a = self.const_int(lhs, ctx)
            b = self.const_int(rhs, ctx)
            if a is None or b is None:
                return
            v = a + b if op == "+" else (a - b if op == "-" else a * b)
            name = res.name if res.kind == "prim" and res.name in _INT_PRIMS else "i32"
            if not self._fits(v, name):
                self.error(_span(node),
                           "integer overflow: %d %s %d does not fit %s, and a trap the "
                           "compiler can prove will fire is a compile error"
                           % (a, op, b, name))

    def _t_Index(self, node, ctx, expect):
        base = _g(node, "base", "array")
        idx = _g(node, "index")
        bty = self.type_of(base, ctx)
        self.type_of(idx, ctx)
        if bty.kind == "array":
            if PROVEN_TRAPS_ARE_ERRORS and bty.name:
                i = self.const_int(idx, ctx)
                try:
                    n = int(bty.name)
                except Exception:
                    n = None
                if i is not None and n is not None and (i < 0 or i >= n):
                    self.error(_span(node),
                               "index out of bounds: %d is past the end of [%s, %d]"
                               % (i, show(bty.args[0]), n))
            return bty.args[0]
        return ANY

    def _t_ArrayLit(self, node, ctx, expect):
        elems = _tup(_g(node, "elems", "elements"))
        want = expect.args[0] if expect is not None and expect.kind == "array" else None
        ety = ANY
        for e in elems:
            t = self.type_of(e, ctx, expect=want)
            if ety.kind == "any":
                ety = t
        if ety.kind == "intlit":
            ety = prim("i32")
        return arr_ty(ety, len(elems))

    def _t_FixedArray(self, node, ctx, expect):
        tnode = _g(node, "ty", "type")
        ty = self.resolve_type(tnode, ctx)
        elem = ty.args[0] if ty.kind == "array" else ANY
        for e in _tup(_g(node, "elems", "elements", "args")):
            ety = self.type_of(e, ctx, expect=elem)
            # An element is a value in the element type's position, and
            # `expect` only offers a type -- nothing coerces to it. So
            # `[i32, 2](1, 3000000000)` wrapped to -1294967296 here as
            # well as in the self-hosted compiler, which is why no
            # differential run could see it.
            self._check_literal_fits(e, ety, elem, _span(e))
        return ty

    def _t_Lambda(self, node, ctx, expect):
        fty = self._lambda_type(node, ctx, expect)
        self._check_lambda_body(node, ctx, expect)
        return fty

    _t_Function = _t_Lambda

    def _lambda_type(self, node, ctx, expect):
        ps = _tup(_g(node, "params"))
        want = expect.args if expect is not None and expect.kind == "fn" else ()
        ptys = []
        for i, p in enumerate(ps):
            t = _g(p, "ty", "type")
            if t is not None:
                ptys.append(self.resolve_type(t, ctx))
            elif i < len(want):
                ptys.append(want[i])
            else:
                ptys.append(ANY)
        rnode = _g(node, "ret")
        ret = self.resolve_type(rnode, ctx) if rnode is not None else (
            expect.ret if expect is not None and expect.kind == "fn" else ANY)
        return fn_ty(tuple(ptys), ret or ANY,
                     tuple(_name_of(_g(p, "name")) or "_" for p in ps))

    def _check_lambda_body(self, node, ctx, expect):
        fty = self._lambda_type(node, ctx, expect)
        sc = ctx.scope.child()
        for p, t in zip(_tup(_g(node, "params")), fty.args):
            nm = _name_of(_g(p, "name"))
            if nm:
                sc.put(nm, Sym("value", t, mutable=bool(_g(p, "mutable", default=False))))
        inner = ctx.with_scope(sc)
        body = _g(node, "body")
        if body is not None:
            # a non-escaping closure returns through its caller, so `.try()`
            # inside it still answers to the enclosing function's Res.
            self.check_block(body, inner,
                             expect=fty.ret if fty.ret.kind not in ("any",) else None)

    # -- try ----------------------------------------------------------------

    def _t_Try(self, node, ctx, expect):
        operand = _g(node, "operand", "value", "expr")
        span = _after_dot(operand, _span(node), 3)
        ty = settle(self.type_of(operand, ctx))
        ret = ctx.ret
        if ret is None or ret.kind in ("any", "error"):
            return ty.args[0] if ty.kind == "res" and ty.args else ANY
        if ret.kind != "res":
            self.error(span,
                       "`.try()` in a function that does not return Res: try unwraps "
                       "Ok or returns the failure from the enclosing function, so the "
                       "enclosing function must have somewhere to return it to")
            return ty.args[0] if ty.kind == "res" and ty.args else ANY
        if ty.kind != "res":
            if ty.kind not in ("any", "error"):
                self.error(span, "`.try()` needs a Res, found %s" % show(ty))
            return ANY
        if len(ty.args) == 1 and len(ret.args) == 2:
            self.error(span,
                       "%s is not %s: a None never becomes an Err, so name the reason "
                       "with `.ok_or(..)`"
                       % (show(ty), "Res<%s, E>" % show(ty.args[0])))
            return ty.args[0]
        if len(ty.args) == 2:
            # An operand whose error set is still an open variable has no error
            # to carry: `Ok(n + 1)` is a Res with an unconstrained `_`, and a
            # bare `Ok` raises nothing.  Propagating THAT into a `Res<T>` is not
            # a conversion, it is the absence of one -- and rejecting it made
            # the natural spelling of a fallible walk illegal in every function
            # whose failure is an absence rather than a reason.
            if len(ret.args) == 1 and ty.args[1].kind in ("var", "any", "never"):
                return ty.args[0]
            if len(ret.args) == 1:
                self.error(span,
                           "no implicit error conversion: %s cannot propagate into %s"
                           % (show(ty), show(ret)))
            elif not err_subset(ty.args[1], ret.args[1]):
                self.error(span,
                           "no implicit error conversion: %s is not part of %s — widen "
                           "the declared set, there is no From"
                           % (show(ty.args[1]), show(ret.args[1])))
        return ty.args[0]

    # -- match --------------------------------------------------------------

    def _t_Match(self, node, ctx, expect):
        scrut = _g(node, "scrutinee", "subject", "value")
        sty = settle(self.type_of(scrut, ctx))
        arms = _tup(_g(node, "arms"))
        span = _earlier(_span(node), _span(scrut))

        norm = [(arm, self.norm_pattern(_g(arm, "pattern"), sty, ctx)) for arm in arms]
        lossy = any(self._has_opaque(p) for _arm, p in norm)

        rows = []
        for arm, p in norm:
            if not lossy and not self._useful(rows, (p,), (sty,)):
                self.error(_span(_g(arm, "pattern")) or _span(arm),
                           "unreachable match arm: every value it could match is "
                           "already covered above")
            rows.append((p,))

        if sty.kind not in ("any", "error", "var", "never"):
            if self._useful(rows, (WILD,), (sty,)):
                self.error(span,
                           "match is not exhaustive: cover every case or write `_` — "
                           "match is exhaustive in every position")

        result = None
        for arm, p in norm:
            sc = ctx.scope.child()
            self._bind_pattern(p, sty, sc, ctx)
            body = _g(arm, "body", "value")
            actx = ctx.with_scope(sc)
            if self._has_opaque(p):
                # the binders this arm introduces were lost with the pattern;
                # do not report their uses as undefined names
                actx = Ctx(actx.mod, actx.scope, actx.fn, actx.ret, actx.subst,
                           actx.bounds, actx.frame, True)
            if _k(body) == "Block":
                t = self.check_block(body, actx, expect=expect)
            else:
                t = self.type_of(body, actx, expect=expect)
                if expect is not None:
                    # every arm produces the match's value, so every arm is
                    # checked against it — and an `Ok(..)` arm learns the error
                    # set from it, which is the only place that knows
                    self.coerce(t, expect, _span(body), body)
            if result is None or result.kind in ("any", "error"):
                result = t
        return result if result is not None else UNIT

    # -- calls --------------------------------------------------------------

    def _t_Call(self, node, ctx, expect):
        callee = _g(node, "callee", "function")
        args = _tup(_g(node, "args", "arguments"))
        targ_nodes = _tup(_g(node, "targs", "type_arguments"))
        targs = tuple(self.resolve_type(t, ctx) for t in targ_nodes)
        span = _span(node)

        # `A.impl(B, {..})` in statement position is a declaration
        if self._impl_call_parts(node):
            return UNIT

        ck = _k(callee)
        if ck in ("Path", "Identifier"):
            name = _g(callee, "name")
            return self._call_named(name, node, callee, args, targs, ctx, expect, span)
        if ck == "Member":
            return self._call_member(node, callee, args, targs, ctx, expect, span)
        cty = self.type_of(callee, ctx)
        for a in args:
            self.type_of(self._arg_value(a), ctx)
        if cty.kind == "fn":
            return cty.ret or UNIT
        return ANY

    @staticmethod
    def _arg_value(a):
        return _g(a, "value", default=a) if _k(a) == "Arg" else a

    @staticmethod
    def _arg_name(a):
        return _name_of(_g(a, "name")) if _k(a) == "Arg" else None

    def _call_named(self, name, node, callee, args, targs, ctx, expect, span):
        if not isinstance(name, str):
            return ANY
        sym = self.resolve_name(name, ctx, callee)
        if sym is None:
            for a in args:
                self.type_of(self._arg_value(a), ctx)
            return ERR
        if sym.kind == "module":
            for a in args:
                self.type_of(self._arg_value(a), ctx)
            return self.module_not_a_value(name, sym.decl, callee)
        if sym.kind == "builtin_fn":
            return self._call_builtin(sym.decl, node, args, targs, ctx, expect)
        if sym.kind == "type":
            td = sym.decl
            if isinstance(td, TypeDef):
                return self._construct(td, node, args, targs, ctx, span)
            for a in args:
                self.type_of(self._arg_value(a), ctx)
            return sym.ty if sym.ty is not None else ANY
        if sym.kind == "fns":
            return self._call_overload(name, sym.defs, node, args, targs, ctx, span)
        if sym.kind == "value" and sym.ty is not None and sym.ty.kind == "fn":
            for a, p in zip(args, sym.ty.args):
                self.coerce(self.type_of(self._arg_value(a), ctx, expect=p), p,
                            _span(self._arg_value(a)), self._arg_value(a))
            for a in args[len(sym.ty.args):]:
                self.type_of(self._arg_value(a), ctx)
            return sym.ty.ret or UNIT
        for a in args:
            self.type_of(self._arg_value(a), ctx)
        return ANY

    def _call_builtin(self, which, node, args, targs, ctx, expect):
        vals = [self._arg_value(a) for a in args]
        if which == "Ok":
            t = self.type_of(vals[0], ctx,
                             expect=expect.args[0] if expect is not None
                             and expect.kind == "res" and expect.args else None) \
                if vals else UNIT
            return Ty("ok", "", (t,))
        if which == "Err":
            t = self.type_of(vals[0], ctx) if vals else ANY
            return Ty("err", "", (t,))
        if which == "None":
            return Ty("none")
        for v in vals:
            self.type_of(v, ctx)
        if which in ("println", "print", "eprintln", "assert"):
            return UNIT
        if which == "Range":
            return self.builtin_named("Range")
        if which == "Hasher":
            return self.builtin_named("Hasher")
        if which in ("loop", "map", "filter", "find", "then"):
            return res_ty(ANY)
        return ANY

    def _construct(self, td, node, args, targs, ctx, span):
        ty = self.type_from_def(td, targs, ctx)
        if td.kind == "enum":
            for a in args:
                self.type_of(self._arg_value(a), ctx)
            return ty
        if td.kind != "struct":
            for a in args:
                self.type_of(self._arg_value(a), ctx)
            return ty
        self.require_type(ty, span, ctx.frame)
        members = self.members_of(ty, ctx)
        storage = [f for f in td.fields if not self._is_method_field(f)]
        for i, a in enumerate(args):
            v = self._arg_value(a)
            nm = self._arg_name(a)
            want = None
            if nm is not None:
                m = members.get(nm)
                if m is not None and m.kind in ("field", "computed"):
                    want = m.ty
            elif i < len(storage):
                fnm = _name_of(_g(storage[i], "name"))
                m = members.get(fnm) if fnm else None
                want = m.ty if m is not None else None
            t = self.type_of(v, ctx, expect=want)
            if want is not None:
                self.coerce(t, want, _span(v), v)
        return ty

    def _call_member(self, node, callee, args, targs, ctx, expect, span):
        base = _g(callee, "base", "object")
        name = _name_of(_g(callee, "name", "property")) or _g(callee, "name", "property")
        vals = [self._arg_value(a) for a in args]

        static = self._static_base(base, ctx)
        if static is not None:
            mty = self._static_member(static, name, callee, ctx)
            if mty is not None and mty.kind == "fn":
                for v, p in zip(vals, mty.args):
                    self.coerce(self.type_of(v, ctx, expect=p), p, _span(v), v)
                for v in vals[len(mty.args):]:
                    self.type_of(v, ctx)
                return mty.ret or UNIT
            for v in vals:
                self.type_of(v, ctx)
            return mty if mty is not None else ANY

        bty = self.type_of(base, ctx)
        if name in ("break", "next") and bty.kind == "named" \
                and base_name(bty.name) == "LoopHandle":
            for v in vals:
                self.type_of(v, ctx)
            return UNIT
        # The candidates are the RECEIVER's: what its type declares, what its
        # impls supply, and the free functions whose first parameter is that
        # type. A member of an unrelated type that happens to share the name
        # is not one of them, and never was.
        m = self._member(bty, name, ctx)
        fns = self._ufcs_fns(name, bty, ctx)
        # "a method is a UFCS function whose first parameter happens to be
        # named self" — so the two are ONE overload set, and the arity picks
        # between them exactly as it does between two free functions.
        if m is not None and (not fns or self._method_fits(m, len(vals))):
            if m.ambiguous:
                self.error(_after_dot(base, _span(callee), len(name)),
                           "method `%s` is ambiguous: two impls supply it and no bound "
                           "in scope selects one" % name, m.ambiguous)
            mty = self._pick_method(m, vals, ctx)
            if mty is not None and mty.kind == "fn":
                mty = self._apply_call_targs(mty, targs)
                # the receiver is the first parameter; the rest line up
                ps = self._spread(list(mty.args[1:]) if mty.args else [], len(vals))
                for v, p in zip(vals, ps):
                    t = self.type_of(v, ctx, expect=p)
                    self.coerce(t, p, _span(v), v)
                for v in vals[len(ps):]:
                    self.type_of(v, ctx)
                return mty.ret or UNIT
            for v in vals:
                self.type_of(v, ctx)
            return mty if mty is not None else ANY

        if fns:
            return self._call_overload(name, fns, node, args, targs, ctx, span,
                                       receiver=(base, bty))
        for v in vals:
            self.type_of(v, ctx)
        if self._answers_for(bty):
            self.error(_after_dot(base, _span(callee), len(name)),
                       "no method `%s` on `%s`" % (name, show(bty)))
            return ERR
        return ANY

    def _method_fits(self, m, nargs):
        """Does any candidate in this method set take `nargs` arguments?
        The receiver is the first parameter, so the rest line up after it."""
        for cand in (m.overloads or ((m,) if m.ty is not None else ())):
            t = cand.ty
            if t is not None and t.kind == "fn" and t.args \
                    and self._fits_arity(list(t.args[1:]), nargs):
                return True
        return False

    def _ufcs_fns(self, name, bty, ctx):
        """The free functions this receiver reaches through a dot.

        Two sources, and the second is DESIGN.md's own sentence: "importing a
        type pulls its world along: its methods, its trait impls, and exported
        ufcs functions (a free function whose first param is the type is
        callable as a method)". A name visible here counts, and so does any
        EXPORTED free function anywhere whose first parameter is this type —
        it travelled with the type, so naming the type is what reaches it.
        `to_u64` is on no prelude line and `add(out :: Sink, ..)` lives a
        layer above the `Sink` it takes; both are reached this way.

        The first parameter is the whole gate. It is what makes a free
        function a method at all, and sharing the name never was."""
        if bty is None or bty.kind in ("error", "any"):
            return ()
        out, ids = [], set()
        for fd in self.lookup_fns(ctx.mod, name) + self._exported_fns(name):
            if id(fd) in ids or not self._takes_receiver(fd, bty, ctx):
                continue
            ids.add(id(fd))
            out.append(fd)
        return tuple(out)

    def _exported_fns(self, name):
        """Every exported free function of this name in the tree, in module
        order. The receiver's type is what narrows it; this is only the pool
        that filter runs over."""
        if self._ufcs_index is None:
            index = {}
            for mi in self.mods:
                for nm, group in mi.fns.items():
                    for fd in group:
                        if fd.exported:
                            index.setdefault(nm, []).append(fd)
            self._ufcs_index = {k: tuple(v) for k, v in index.items()}
        return self._ufcs_index.get(name, ())

    def _takes_receiver(self, fd, bty, ctx):
        """The FIRST PARAMETER is what makes a free function reachable through
        a dot, and a receiver whose type is not yet known reaches nothing."""
        if not fd.params:
            return False
        fctx = self._fn_ctx(fd, {}, ctx.frame)
        p0 = self.resolve_type(_g(fd.params[0], "ty", "type"), fctx, want_error=False)
        return p0 is not None and self._unify(p0, bty, {}, None, ctx)

    def _answers_for(self, ty):
        """Is this receiver concrete enough that "it has no such method" is a
        fact rather than a guess? A declared struct, enum or primitive knows
        everything it has; a type parameter, a builtin or an unresolved type
        does not, and a diagnostic from one of those would be about a program
        that is fine."""
        if ty is None:
            return False
        if ty.kind == "prim":
            return self.prim_decls.get(ty.name) is not None
        if ty.kind != "named" or ty.name.startswith("@"):
            return False
        td = self.types.get(ty.name)
        return td is not None and td.kind in ("struct", "enum")

    def _pick_method(self, m, vals, ctx):
        """Overload resolution over a method set — same rule as a free
        function: declared parameter types and arity, closures included."""
        cands = m.overloads or ((m,) if m.ty is not None else ())
        if len(cands) < 2:
            return m.ty
        best = None
        for cand in cands:
            t = cand.ty
            if t is None or t.kind != "fn":
                continue
            ps = list(t.args[1:])
            if not self._fits_arity(ps, len(vals)):
                continue
            ps = self._spread(ps, len(vals))
            self._muted += 1
            try:
                ok = all(assignable(self.type_of(v, ctx, expect=p), p)
                         for v, p in zip(vals, ps))
            finally:
                self._muted -= 1
            if ok:
                return t
            if best is None:
                best = t
        return best if best is not None else m.ty

    @staticmethod
    def _apply_call_targs(mty, targs):
        """Builtin generic methods (`alloc.create<Node>()`) carry their type
        arguments at the call, spelled G0/G1 in the builtin table."""
        if not targs:
            return mty
        sub = {}
        for i, t in enumerate(targs):
            sub["G%d" % i] = t
        return subst_ty(mty, sub)

    # -- overload resolution ------------------------------------------------

    def _call_overload(self, name, cands, node, args, targs, ctx, span, receiver=None):
        vals = [self._arg_value(a) for a in args]
        arg_nodes = ([receiver[0]] if receiver else []) + vals
        arg_types = ([receiver[1]] if receiver else []) + [
            self.type_of(v, ctx) for v in vals]

        n_args = len(arg_types)
        sigs = []
        for fd in cands:
            fctx = self._fn_ctx(fd, {}, ctx.frame)
            ptys = [self.resolve_type(_g(p, "ty", "type"), fctx) for p in fd.params]
            sigs.append((fd, ptys, self._fits_arity(ptys, n_args)))

        viable = []
        for fd, ptys, fits in sigs:
            if not fits:
                continue
            sub = {}
            ok = True
            for want, got, n in zip(self._spread(ptys, n_args), arg_types, arg_nodes):
                if not self._unify(want, got, sub, n, ctx):
                    ok = False
                    break
            if not ok:
                continue
            score = sum(0 if p.kind == "var" else 1 for p in ptys)
            viable.append((score, fd, ptys, sub))

        if not viable:
            same_arity = [(fd, ptys) for fd, ptys, fits in sigs if fits]
            if len(same_arity) == 1:
                # one candidate, wrong argument: say which argument, not "no
                # overload matches". The re-check below reports it precisely.
                fd, ptys = same_arity[0]
                sub = {}
                for want, got, n in zip(self._spread(ptys, n_args), arg_types, arg_nodes):
                    self._unify(want, got, sub, n, ctx)
                viable = [(0, fd, ptys, sub)]
            elif not cands:
                # "no overload matches" with nothing to match against is a
                # misleading diagnostic: say the honest thing.
                self.error(span, "unknown function `%s`" % name)
                return ERR
            else:
                arities = sorted({self._arity_text(p) for _f, p, _x in sigs})
                self.error(span,
                           "no overload matches `%s`: resolution is on declared "
                           "parameter types and arity — %d argument%s given, "
                           "%d declaration%s taking %s"
                           % (name, n_args, "" if n_args == 1 else "s",
                              len(cands), "" if len(cands) == 1 else "s",
                              " or ".join(arities)))
                return ERR
        viable.sort(key=lambda v: (-v[0], _start(v[1].span)))
        _score, fd, ptys, sub = viable[0]

        # explicit type arguments win over inference
        for tp, t in zip(fd.tparams, targs):
            nm = _name_of(_g(tp, "name"))
            if nm:
                sub[nm] = t
        fctx = self._fn_ctx(fd, sub, ctx.frame)

        # re-check the arguments against the substituted parameter types, so a
        # closure gets its parameter types from the signature it is passed to
        for want, n in zip(self._spread(ptys, n_args), arg_nodes):
            w = subst_ty(want, sub)
            if n is None:
                continue
            t = self.type_of(n, ctx, expect=w)
            self.coerce(t, w, _span(n), n)

        self._check_bounds(fd, sub, span, ctx)
        self._record_target(node, fd)

        if fd.tparams:
            key_args = tuple(sub.get(_name_of(_g(tp, "name")) or "", ANY)
                             for tp in fd.tparams)
            self._instantiate(fd, sub, key_args, span, ctx)
        else:
            self.check_function(fd, {}, ctx.frame)
        return self.fn_ret(fd, fctx)

    @staticmethod
    def _is_variadic(ptys):
        return bool(ptys) and ptys[-1].kind == "variadic"

    @classmethod
    def _fits_arity(cls, ptys, n):
        """`add* = (self :: @Self, fmt: str, args: ...)` takes two arguments or
        twenty. A variadic tail is zero-or-more, so it is a MINIMUM arity, and
        treating it as one required parameter rejects every call that passes
        nothing for it — which is most of them."""
        if cls._is_variadic(ptys):
            return n >= len(ptys) - 1
        return n == len(ptys)

    @classmethod
    def _spread(cls, ptys, n):
        """The parameter types laid out against `n` arguments, the variadic
        tail repeated for each argument it swallows."""
        if not cls._is_variadic(ptys):
            return list(ptys)
        fixed = list(ptys[:-1])
        return fixed + [VARIADIC] * max(0, n - len(fixed))

    @classmethod
    def _arity_text(cls, ptys):
        return ("%d+" % (len(ptys) - 1)) if cls._is_variadic(ptys) else str(len(ptys))

    def _record_target(self, call, fd):
        """Which declaration a CALL selected — overload resolution's answer,
        which is not recoverable from the callee name alone. gen_c's
        `sema.resolve(expr)` and the LSP's go-to-definition both need the
        answer for the call, not the first declaration of the name."""
        if call is None or fd is None:
            return
        self._keep.append(call)
        self.call_target[id(call)] = fd
        callee = _g(call, "callee", "function")
        if callee is not None:
            self._keep.append(callee)
            self.call_target.setdefault(id(callee), fd)

    def _unify(self, want, got, sub, node, ctx):
        """One-way match of an argument against a declared parameter type,
        solving type parameters as it goes."""
        if want is None or got is None:
            return True
        if want.kind == "var":
            prev = sub.get(want.name)
            if prev is None or prev.kind == "any":
                sub[want.name] = settle(got) if got.kind in ("ok", "err", "none") else got
                return True
            return assignable(got, prev) or assignable(prev, got)
        if want.kind == "fn":
            if node is not None and _k(node) in ("Lambda", "Function"):
                ps = _tup(_g(node, "params"))
                if len(ps) != len(want.args):
                    return False
                for p, w in zip(ps, want.args):
                    tn = _g(p, "ty", "type")
                    if tn is not None:
                        if not self._unify(w, self.resolve_type(tn, ctx), sub, None, ctx):
                            return False
                return True
            if got.kind != "fn" or len(got.args) != len(want.args):
                return False
            for w, g in zip(want.args, got.args):
                if not self._unify(w, g, sub, None, ctx):
                    return False
            return True
        if want.args and got.kind == want.kind and len(want.args) == len(got.args):
            for w, g in zip(want.args, got.args):
                self._unify(w, g, sub, None, ctx)
        return assignable(got, subst_ty(want, sub))

    def _bounds_of(self, tp, base):
        """`<K: Eq + Hash>` arrives as a Union (ast.py's stopgap for an
        intersection), so a union bound is every bound, not a choice."""
        out = []
        for b in _tup(_g(tp, "bound", "bounds")):
            if b is None:
                continue
            bty = self.resolve_type(b, base)
            if bty is not None and bty.kind == "union":
                out.extend(bty.args)
            elif bty is not None:
                out.append(bty)
        return tuple(out)

    def _check_bounds(self, fd, sub, span, ctx):
        base = Ctx(fd.mod, Scope())
        for tp in fd.tparams:
            nm = _name_of(_g(tp, "name"))
            if not nm:
                continue
            got = sub.get(nm)
            if got is None or got.kind in ("any", "error", "var"):
                continue
            for bty in self._bounds_of(tp, base):
                if bty is None or bty.kind in ("any", "error", "var"):
                    continue
                if not self.satisfies(got, bty):
                    self.error(span,
                               "bound not satisfied: %s has no impl of %s, so it has "
                               "none of the fields the bound promises"
                               % (show(got), show(bty)))

    def satisfies(self, ty, bound):
        if ty == bound:
            return True
        if ty.kind != "named" or bound.kind != "named":
            return True
        if ty.name.startswith("@") or bound.name.startswith("@"):
            return True
        for im in self.impls_of(ty.name):
            if im.trait == bound.name:
                return True
        btd = self.types.get(bound.name)
        if btd is None:
            return True
        # a type that already declares the bound's storage satisfies it
        mine = self.members_of(ty)
        for f in btd.fields:
            nm = _name_of(_g(f, "name"))
            if not nm:
                continue
            if self._is_method_field(f):
                val = _g(f, "default", "value")
                if _k(val) in ("Lambda", "Function"):
                    continue
            if nm not in mine:
                return False
        return True

    # -- instantiation, with the budget ------------------------------------

    def _instantiate(self, fd, sub, targs, span, ctx):
        key = (id(fd.node), tuple(sorted((k, v) for k, v in sub.items())))
        if key in self._checked:
            return
        frame = Frame("fn", key, fd.name, tuple(targs), span, ctx.frame)
        if frame.depth > self.budget:
            self._blame_depth(frame, "fn")
            self._checked.add(key)      # stop: divergence is already reported
            return
        self.check_function(fd, sub, frame)

    # ======================================================================
    # patterns and exhaustiveness
    # ======================================================================

    def norm_pattern(self, pnode, ty, ctx):
        if pnode is None:
            return WILD
        if isinstance(pnode, _Raw):
            return self._norm_raw(pnode, ty, ctx)
        k = _k(pnode)
        span = _span(pnode)
        if k == "PatWild":
            return P("wild", span=span)
        if k == "PatLit":
            kind = _g(pnode, "kind", default="")
            text = str(_g(pnode, "text", default=""))
            if kind == "bool" or text in ("true", "false"):
                return P("ctor", text, (), span=span)
            return P("lit", text, span=span)
        if k in ("PatVariant", "PatCtor", "PatPath", "Pattern"):
            raw = _name_of(_g(pnode, "name")) or _g(pnode, "name")
            name = str(raw).rsplit(".", 1)[-1] if raw is not None else ""
            table = {c[0]: c[1] for c in (self.ctors_of(ty) or [])}
            subs_nodes = self._pat_subs(pnode)
            if name not in table:
                if not subs_nodes:
                    # a bare name that is not a case of this type: a binder
                    return P("wild", binder=name, span=span)
                return P("ctor", name, tuple(
                    self.norm_pattern(s, ANY, ctx) for s in subs_nodes), span=span)
            payload = table[name]
            if not payload:
                return P("ctor", name, (), span=span)
            if subs_nodes is None:
                # the payload pattern did not survive the AST: stay permissive
                return P("ctor", name,
                         tuple(P("wild", opaque=True) for _ in payload),
                         span=span, opaque=True)
            subs = []
            for i, pt in enumerate(payload):
                subs.append(self.norm_pattern(subs_nodes[i], pt, ctx)
                            if i < len(subs_nodes) else WILD)
            return P("ctor", name, tuple(subs), span=span)
        if k in ("Path", "Identifier"):
            raw = _g(pnode, "name")
            name = str(raw).rsplit(".", 1)[-1] if raw else ""
            ctors = {c[0] for c in (self.ctors_of(ty) or [])}
            if name in ctors:
                return P("ctor", name, (), span=span)
            return P("wild", binder=name, span=span)
        if k == "Literal":
            kind = _g(pnode, "kind", default="")
            text = str(_g(pnode, "text", default=""))
            if kind == "bool":
                return P("ctor", text, (), span=span)
            return P("lit", text, span=span)
        return P("wild", span=span)

    def _norm_raw(self, raw, ty, ctx):
        name = str(raw.name).rsplit(".", 1)[-1]
        if name == "_":
            return P("wild")
        table = {c[0]: c[1] for c in (self.ctors_of(ty) or [])}
        if name not in table:
            if raw.subs:
                return P("ctor", name,
                         tuple(self._norm_raw(s, ANY, ctx) for s in raw.subs))
            return P("wild", binder=name)
        payload = table[name]
        subs = []
        for i, pt in enumerate(payload):
            got = raw.subs[i] if raw.subs and i < len(raw.subs) else None
            subs.append(self._norm_raw(got, pt, ctx) if got is not None else WILD)
        return P("ctor", name, tuple(subs))

    @staticmethod
    def _pat_subs(pnode):
        """CONTRACT.md's `PatVariant(name, binder: str|None)` cannot express
        `Left(Full(n))`, which three corpus tests need. Accept every shape an
        ast.py might have chosen — a tuple of sub-patterns, one sub-pattern, or
        the payload's source text — and return None when the information is
        simply not there."""
        for attr in ("subs", "args", "patterns", "subpatterns", "fields"):
            v = getattr(pnode, attr, None)
            if v is None:
                continue
            if isinstance(v, (tuple, list)):
                return tuple(v)
            if not isinstance(v, str):
                return (v,)
        b = getattr(pnode, "binder", None)
        if b is None:
            return None
        if isinstance(b, str):
            return _parse_pats(b)
        if isinstance(b, (tuple, list)):
            return tuple(b)
        return (b,)

    @staticmethod
    def _has_opaque(p):
        if p is None:
            return False
        if p.opaque:
            return True
        return any(Sema._has_opaque(s) for s in p.subs)

    def _bind_pattern(self, p, ty, scope, ctx):
        if p is None:
            return
        if p.kind == "wild":
            if p.binder:
                scope.put(p.binder, Sym("value", ty if ty is not None else ANY))
            return
        if p.kind != "ctor":
            return
        table = {c[0]: c[1] for c in (self.ctors_of(ty) or [])}
        payload = table.get(p.name, ())
        for i, sp in enumerate(p.subs):
            self._bind_pattern(sp, payload[i] if i < len(payload) else ANY, scope, ctx)

    # -- usefulness (Maranget), the exhaustiveness engine -------------------

    def _useful(self, matrix, q, types):
        if not types:
            return len(matrix) == 0
        ty0 = types[0]
        p = q[0]
        if p.kind == "ctor":
            payload = self._payload_of(ty0, p.name, len(p.subs))
            sm = self._specialise(matrix, p.name, len(payload))
            subs = tuple(p.subs) + tuple(
                WILD for _ in range(max(0, len(payload) - len(p.subs))))
            return self._useful(sm, subs[:len(payload)] + tuple(q[1:]),
                                tuple(payload) + tuple(types[1:]))
        if p.kind == "lit":
            sm = [row[1:] for row in matrix
                  if row[0].kind == "wild"
                  or (row[0].kind == "lit" and row[0].name == p.name)]
            return self._useful(sm, tuple(q[1:]), tuple(types[1:]))
        # wildcard
        ctors = self.ctors_of(ty0)
        roots = {row[0].name for row in matrix if row[0].kind == "ctor"}
        if ctors and roots >= {c[0] for c in ctors}:
            for cname, payload in ctors:
                sm = self._specialise(matrix, cname, len(payload))
                if self._useful(sm, tuple(WILD for _ in payload) + tuple(q[1:]),
                                tuple(payload) + tuple(types[1:])):
                    return True
            return False
        default = [row[1:] for row in matrix if row[0].kind == "wild"]
        return self._useful(default, tuple(q[1:]), tuple(types[1:]))

    def _payload_of(self, ty, cname, fallback):
        for n, p in (self.ctors_of(ty) or []):
            if n == cname:
                return tuple(p)
        return tuple(ANY for _ in range(fallback))

    @staticmethod
    def _specialise(matrix, cname, arity):
        out = []
        for row in matrix:
            head = row[0]
            if head.kind == "wild":
                out.append(tuple(WILD for _ in range(arity)) + tuple(row[1:]))
            elif head.kind == "ctor" and head.name == cname:
                subs = tuple(head.subs)
                if len(subs) < arity:
                    subs = subs + tuple(WILD for _ in range(arity - len(subs)))
                out.append(subs[:arity] + tuple(row[1:]))
        return out

    # ======================================================================
    # error sets
    # ======================================================================

    def error_set_of(self, fd):
        """`Res<T, _>`: inferred inside the module, written at the boundary.
        Inference is a least fixed point, so a call whose own set is inferred
        (and a cycle) both terminate."""
        key = id(fd.node)
        state = self._errset_state.get(key)
        if state == "running":
            return NEVER
        if isinstance(state, Ty):
            return state
        self._errset_state[key] = "running"
        self._keep.append(fd.node)
        acc = []
        try:
            self._prime(fd)
            self._walk_errors(fd.body, fd, acc)
        except RecursionError:
            pass
        out = union_ty(acc)
        self._errset_state[key] = out
        return out

    def _prime(self, fd):
        """Type the body once with the error position left OPEN, so every node
        carries a recorded type before the sets are collected.

        Without this, "what can this `.try()` raise" has to be answered from
        the shape of the call -- and a guess by method name says `AllocError`
        for `String.add`, which fails on the sink and raises `IoError`.  The
        set is the union of what the body can raise, so it is read off the
        body, not inferred from its spelling.

        Open, not final: the run below is the least-fixed-point's first
        iteration, so `.try()` has nothing to check against yet and every
        diagnostic it could raise would be about a program the real check has
        not looked at.  They are dropped; the real check reports.
        """
        if fd.body is None or fd.tparams:
            return
        n = len(self.diags)
        try:
            base = self._fn_ctx(fd, {}, None)
            ret = self.resolve_type(fd.ret, base) if fd.ret is not None else UNIT
            payload = ret.args[0] if (ret.kind == "res" and ret.args) else ANY
            ctx = Ctx(base.mod, Scope(), fd, res_ty(payload, ANY), base.subst,
                      base.bounds, base.frame, quiet=True)
            for p in fd.params:
                nm = _name_of(_g(p, "name"))
                if not nm:
                    continue
                ctx.scope.put(nm, Sym("value", self.resolve_type(_g(p, "ty", "type"), ctx),
                                      mutable=bool(_g(p, "mutable", default=False))))
            self.check_block(fd.body, ctx, expect=ctx.ret, is_fn_body=True)
        except RecursionError:
            pass
        except Exception:  # never raise: a body that will not type is not the run
            pass
        finally:
            del self.diags[n:]

    def error_set_ast(self, node):
        """The inferred set of a `Res<T, _>` function, as an ast Type node.

        gen_c's question, and the only one it can ask: `_` is an `Infer` node
        and `resolve_type` has nothing to resolve it to, so the set has to
        arrive already spelled in the ast's own vocabulary. `None` when the
        node is not a function this pass knows, or when the set is empty — a
        body that cannot fail has nothing to write in the error position, and
        inventing a type there would be inventing a reason.
        """
        fd = self.by_node.get(id(node))
        if not isinstance(fd, FnDef):
            return None
        ty = self.error_set_of(fd)
        if ty is None or ty == NEVER:
            return None
        return self.as_ast_type(ty, _span(fd.ret) or fd.span)

    def _walk_errors(self, node, fd, acc):
        if node is None:
            return
        k = _k(node)
        if k == "Call":
            parts = self._impl_call_parts(node)
            if parts is None:
                callee = _g(node, "callee", "function")
                if _k(callee) in ("Path", "Identifier") and _g(callee, "name") == "Err":
                    args = _tup(_g(node, "args", "arguments"))
                    if args:
                        v = self._arg_value(args[0])
                        acc.append(self._static_type(v, fd))
        elif k == "Try":
            e = self._error_of_expr(_g(node, "operand", "value", "expr"), fd)
            if e is not None:
                acc.append(e)
        for child in self._children(node):
            self._walk_errors(child, fd, acc)

    def _error_of_expr(self, expr, fd):
        """The E of whatever this expression produces.

        What `_prime` recorded, when it recorded anything; the shape-based
        fallbacks below are for a generic body, which is not primed, and for
        an expression the first iteration could not type.
        """
        if expr is None:
            return None
        got = self.node_type.get(id(expr))
        if got is not None:
            got = settle(got)
            if got.kind == "res" and len(got.args) == 2 and got.args[1] != ANY:
                return got.args[1]
        k = _k(expr)
        if k == "Call":
            callee = _g(expr, "callee", "function")
            if _k(callee) in ("Path", "Identifier"):
                name = _g(callee, "name")
                for cand in self.lookup_fns(fd.mod, name):
                    return self._declared_error(cand)
            elif _k(callee) == "Member":
                nm = _name_of(_g(callee, "name", "property")) or _g(callee, "name", "property")
                if nm == "ok_or":
                    # "you name the reason": `ok_or(reason: E) Res<T, E>`, so
                    # the argument IS the set.  Not a guess -- DESIGN.md makes
                    # this the required form for turning a None into an Err.
                    args = _tup(_g(expr, "args", "arguments"))
                    if args:
                        return self._static_type(self._arg_value(args[0]), fd)
                if nm in ("add", "set", "String", "create", "raw", "realloc"):
                    return self.builtin_named("AllocError")
                for cand in self.lookup_fns(fd.mod, nm):
                    return self._declared_error(cand)
            return ANY
        if k == "Member":
            nm = _name_of(_g(expr, "name", "property"))
            if nm == "ok_or":
                return ANY
        return ANY

    def _declared_error(self, fd):
        ret = fd.ret
        if ret is None:
            return NEVER
        if _k(ret) in ("Named", "Path", "Identifier") and _g(ret, "name") == "Res":
            args = _tup(_g(ret, "args"))
            if len(args) == 2:
                if _k(args[1]) == "Infer":
                    return self.error_set_of(fd)
                return self.resolve_type(args[1], Ctx(fd.mod, Scope()))
            return NEVER
        return ANY

    def _static_type(self, expr, fd):
        """A type for an expression that needs no local scope — enough for
        `Err(CfgError.Bad)` during error-set inference."""
        ctx = Ctx(fd.mod, Scope())
        k = _k(expr)
        if k == "Member":
            static = self._static_base(_g(expr, "base", "object"), ctx)
            if static is not None:
                nm = _name_of(_g(expr, "name", "property")) or _g(expr, "name", "property")
                t = self._static_member(static, nm, expr, ctx)
                if t is not None and t.kind == "fn":
                    return t.ret
                return t
        if k in ("Path", "Identifier"):
            name = _g(expr, "name")
            td = self.lookup_type(ctx.mod, name)
            if td is not None:
                return self.type_from_def(td, (), ctx)
            if self.is_builtin_type(name):
                return self.builtin_named(name)
        if k == "Call":
            callee = _g(expr, "callee", "function")
            if _k(callee) in ("Path", "Identifier"):
                td = self.lookup_type(ctx.mod, _g(callee, "name"))
                if td is not None:
                    return self.type_from_def(td, (), ctx)
            if _k(callee) == "Member":
                static = self._static_base(_g(callee, "base", "object"), ctx)
                if static is not None:
                    nm = _name_of(_g(callee, "name", "property")) or _g(callee, "name", "property")
                    t = self._static_member(static, nm, callee, ctx)
                    if t is not None and t.kind == "fn":
                        return t.ret
                    return t
        return ANY

    @staticmethod
    def _children(node):
        out = []
        for f in getattr(node, "__dataclass_fields__", {}) or {}:
            if f in ("span", "leading", "trailing"):
                continue
            v = getattr(node, f, None)
            if v is None or isinstance(v, (str, int, float, bool)):
                continue
            if isinstance(v, (tuple, list)):
                for x in v:
                    if hasattr(x, "span"):
                        out.append(x)
                    elif isinstance(x, (tuple, list)):
                        out.extend(y for y in x if hasattr(y, "span"))
            elif hasattr(v, "span"):
                out.append(v)
        return out


_MISS = object()


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------


def check_program(modules, root="", depth_budget=INSTANTIATION_DEPTH_BUDGET):
    """Check a whole program. Whole-program by construction: every module in
    one graph, so `Vec<Circle>` belongs to the program rather than to either
    module that named half of it."""
    s = Sema(modules, root=root, depth_budget=depth_budget)
    return s.check()


def analyse(modules, root="", depth_budget=INSTANTIATION_DEPTH_BUDGET):
    """Same, but hand back the Sema so gen_c can read `fn_instances` /
    `type_instances` and the LSP can ask `type_of` / `defs_of` afterwards."""
    s = Sema(modules, root=root, depth_budget=depth_budget)
    diags = s.check()
    return s, diags
