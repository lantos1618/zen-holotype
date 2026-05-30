"""The type space: ONE trie + the pointer lattice (fits) + expression inference.

The trie is the namespace, import resolver, AND conflict checker.
fits() locks pointer direction and nullability.
infer() type-checks a body and triggers fits() at every call site.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from nodes import (Dir, Prim, PrimT, NameT, PtrT, Struct, Fn,
                   Lit, Var, Field, Bin, Call, StructLit)


class Conflict(Exception):   ...
class Unresolved(Exception): ...


class TypeErr(Exception):
    def __init__(self, msg, given=None, want=None):
        super().__init__(msg)
        self.given, self.want = given, want


# ───────────────────────── the namespace trie ───────────────────────────────
@dataclass
class Node:
    path: str = ""
    kids: dict = field(default_factory=dict)
    value: object = None


class Space:
    def __init__(self):
        self.root = Node()

    def insert(self, path: str, decl) -> None:
        n = self.root
        for seg in path.split("."):
            child = n.kids.get(seg)
            if child is None:
                child = Node(path=(n.path + "." + seg).lstrip("."))
                n.kids[seg] = child
            n = child
        if n.value is not None:
            raise Conflict(f"two decls claim '{path}'")
        n.value = decl

    def walk(self, path: str) -> Node:
        n = self.root
        for seg in path.split("."):
            nxt = n.kids.get(seg)
            if nxt is None:
                raise Unresolved(f"no such path '{path}'")
            n = nxt
        return n


# ───────────────────────── the pointer lattice ──────────────────────────────
def is_option(t) -> bool:
    return isinstance(t, NameT) and t.path == "Option"


_CAP = {Dir.READ: 1, Dir.MUT: 2}    # MutPtr is more capable, so it's the subtype


def dir_fits(given: Dir, want: Dir) -> bool:
    if given is Dir.RAW or want is Dir.RAW:
        return given is want                 # raw only fits raw — no silent escape
    return _CAP[given] >= _CAP[want]         # MutPtr can stand in where Ptr is asked


def fits(given, want) -> bool:
    if is_option(want) and not is_option(given):     # T ≤ Option<T>  (nonnull ok as nullable)
        return fits(given, want.args[0])
    if is_option(given) and is_option(want):
        return fits(given.args[0], want.args[0])
    if is_option(given) and not is_option(want):     # nullable into nonnull: REJECT
        return False
    if isinstance(given, PtrT) and isinstance(want, PtrT):
        return dir_fits(given.dir, want.dir) and fits(given.pointee, want.pointee)
    return given == want                             # nominal/structural eq (paths canonical)


# ───────────────────────── expression inference ─────────────────────────────
def infer(e, locals_, space, scope):
    """Return the type of expression `e`; raise TypeErr on any call mismatch."""
    if isinstance(e, Lit):
        return PrimT(Prim.I32)
    if isinstance(e, Var):
        if e.name not in locals_:
            raise TypeErr(f"unbound '{e.name}'")
        return locals_[e.name]
    if isinstance(e, Bin):
        infer(e.l, locals_, space, scope)
        infer(e.r, locals_, space, scope)
        return PrimT(Prim.I32)               # integer arithmetic
    if isinstance(e, Field):
        ot = infer(e.obj, locals_, space, scope)
        st = ot.pointee if isinstance(ot, PtrT) else ot     # auto-deref through a pointer
        if not isinstance(st, NameT):
            raise TypeErr("field access on non-struct")
        decl = space.walk(st.path).value
        for f in decl.fields:
            if f.name == e.name:
                return f.type
        raise TypeErr(f"no field '{e.name}' on {st.path}")
    if isinstance(e, StructLit):
        qual = scope.get(e.type, e.type)
        decl = space.walk(qual).value
        ftypes = {f.name: f.type for f in decl.fields}
        for fname, fexpr in e.fields:
            if fname not in ftypes:
                raise TypeErr(f"no field '{fname}' on {qual}")
            given = infer(fexpr, locals_, space, scope)
            if not fits(given, ftypes[fname]):
                raise TypeErr("field type", given, ftypes[fname])
        return NameT(qual, ())
    if isinstance(e, Call):
        if e.callee == "addr":                            # addr(x): take a mutable pointer
            return PtrT(Dir.MUT, infer(e.args[0], locals_, space, scope))
        callee = space.walk(scope[e.callee]).value
        if not isinstance(callee, Fn):
            raise TypeErr(f"'{e.callee}' is not callable")
        if len(e.args) != len(callee.params):
            raise TypeErr(f"'{e.callee}' wants {len(callee.params)} args, got {len(e.args)}")
        for a, p in zip(e.args, callee.params):
            given = infer(a, locals_, space, scope)
            if not fits(given, p.type):
                raise TypeErr("pointer/null mismatch", given, p.type)
        return callee.ret
    raise TypeErr(f"unknown expr {e!r}")
