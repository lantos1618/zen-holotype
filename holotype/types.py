"""The type space: ONE trie + the pointer lattice (fits) + expression inference.

The trie is the namespace, import resolver, AND conflict checker.
fits() locks pointer direction and nullability.
infer() type-checks a body and triggers fits() at every call site.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, Struct, Fn, EnumDecl,
                  Lit, Bool, Var, Field, Bin, Call, StructLit, Let, EnumCtor)


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
        if not dir_fits(given.dir, want.dir):
            return False
        # Variance: a read-only target may be covariant in its pointee (you can only
        # observe through it). A writable/raw target must be INVARIANT — otherwise a
        # callee could store, say, a null through a MutPtr<Option<T>> into a slot the
        # caller guaranteed non-null (the classic array-covariance hole).
        if want.dir is Dir.READ:
            return fits(given.pointee, want.pointee)
        return given.pointee == want.pointee
    if isinstance(given, PrimT) and isinstance(want, PrimT):
        if given.prim is want.prim:
            return True
        return given.prim is Prim.I32 and want.prim is Prim.I64   # widening only
    return given == want                             # nominal/structural eq (paths canonical)


# ───────────────────────── generics: substitution + unification ─────────────
def subst(t, s):
    """Replace each type variable in `t` with its binding from `s` (name -> Type)."""
    if isinstance(t, TVar):
        return s.get(t.name, t)
    if isinstance(t, PtrT):
        return PtrT(t.dir, subst(t.pointee, s))
    if isinstance(t, NameT):
        return NameT(t.path, tuple(subst(a, s) for a in t.args))
    return t


def match_type(param, arg, s) -> None:
    """One-directional unification: bind the type vars in `param` to the matching
    subterms of the concrete `arg`. Shape-only — lattice fitness (direction,
    nullability) is enforced afterwards by fits() on the substituted types.
    Occurs-check is moot: `arg` is already concrete (var-free)."""
    if isinstance(param, TVar):
        prev = s.get(param.name)
        if prev is None or prev == arg:
            s[param.name] = arg
        return
    if isinstance(param, PtrT) and isinstance(arg, PtrT):
        match_type(param.pointee, arg.pointee, s)
    elif is_option(param) and not is_option(arg):     # Option<X> vs a nonnull -> peek
        match_type(param.args[0], arg, s)
    elif (isinstance(param, NameT) and isinstance(arg, NameT)
          and param.path == arg.path and len(param.args) == len(arg.args)):
        for p, a in zip(param.args, arg.args):
            match_type(p, a, s)


def solve_call(callee, arg_types):
    """Infer a generic function's type arguments from its call's argument types."""
    s = {}
    for p, at in zip(callee.params, arg_types):
        match_type(p.type, at, s)
    return s


# ───────────────────────── expression inference ─────────────────────────────
def infer(e, locals_, space, scope, expect=None):
    """Return the type of expression `e`; raise TypeErr on any call mismatch.

    `expect` is the type the surrounding context wants (return slot, parameter,
    field). It's how a leading-dot enum ctor like `.Some(x)` learns which enum
    it builds — the variant name alone is ambiguous across enums."""
    if isinstance(e, Lit):
        return PrimT(Prim.I32)
    if isinstance(e, Bool):
        return PrimT(Prim.BOOL)
    if isinstance(e, EnumCtor):
        return infer_enum_ctor(e, expect, locals_, space, scope)
    if isinstance(e, Var):
        if e.name not in locals_:
            raise TypeErr(f"unbound '{e.name}'")
        return locals_[e.name]
    if isinstance(e, Bin):
        lt = infer(e.l, locals_, space, scope)
        rt = infer(e.r, locals_, space, scope)
        if e.op == "==":
            if not (fits(lt, rt) or fits(rt, lt)):       # operands must be comparable
                raise TypeErr("'==' operands differ")
            return PrimT(Prim.BOOL)
        return PrimT(Prim.I32)                            # integer arithmetic
    if isinstance(e, Field):
        ot = infer(e.obj, locals_, space, scope)
        st = ot.pointee if isinstance(ot, PtrT) else ot     # auto-deref through a pointer
        if not isinstance(st, NameT):
            raise TypeErr("field access on non-struct")
        decl = space.walk(st.path).value
        for f in decl.fields:
            if f.name == e.name:
                # a field of a generic struct carries the instantiation's args
                return subst(f.type, dict(zip(decl.tparams, st.args))) if decl.tparams else f.type
        raise TypeErr(f"no field '{e.name}' on {st.path}")
    if isinstance(e, StructLit):
        qual = scope.get(e.type, e.type)
        decl = space.walk(qual).value
        ftypes = {f.name: f.type for f in decl.fields}
        for fname, fexpr in e.fields:
            if fname not in ftypes:
                raise TypeErr(f"no field '{fname}' on {qual}")
            given = infer(fexpr, locals_, space, scope, ftypes[fname])
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
        if callee.tparams:                               # generic: infer type-args, then check
            arg_types = [infer(a, locals_, space, scope) for a in e.args]
            s = solve_call(callee, arg_types)
            missing = [n for n in callee.tparams if n not in s]
            if missing:
                raise TypeErr(f"cannot infer type {', '.join(missing)} for '{e.callee}'")
            for given, p in zip(arg_types, callee.params):
                want = subst(p.type, s)
                if not fits(given, want):
                    raise TypeErr("pointer/null mismatch", given, want)
            return subst(callee.ret, s)
        for a, p in zip(e.args, callee.params):
            given = infer(a, locals_, space, scope, p.type)
            if not fits(given, p.type):
                raise TypeErr("pointer/null mismatch", given, p.type)
        return callee.ret
    raise TypeErr(f"unknown expr {e!r}")


def infer_enum_ctor(e, expect, locals_, space, scope):
    """`.Variant(payload)` — the expected type names which enum, then the
    variant's declared payload type is checked like any other slot."""
    if not isinstance(expect, NameT):
        raise TypeErr(f"cannot tell which enum '.{e.name}' builds (no expected type here)")
    decl = space.walk(expect.path).value
    if not isinstance(decl, EnumDecl):
        raise TypeErr(f"'.{e.name}' used where {expect.path} (not an enum) is wanted")
    var = next((v for v in decl.variants if v.name == e.name), None)
    if var is None:
        raise TypeErr(f"enum {expect.path} has no variant '.{e.name}'")
    if var.payload is None:
        if e.args:
            raise TypeErr(f"variant '.{e.name}' takes no payload")
    else:
        if len(e.args) != 1:
            raise TypeErr(f"variant '.{e.name}' takes one payload value")
        given = infer(e.args[0], locals_, space, scope, var.payload)
        if not fits(given, var.payload):
            raise TypeErr("enum payload", given, var.payload)
    return NameT(expect.path, ())


def infer_block(stmts, locals_, space, scope, expect=None):
    """Type a function body: `x := v` bindings extend locals in order; the value
    of the block is the type of its final expression statement (void if none).
    `expect` (the function's return type) reaches the final statement."""
    locals_ = dict(locals_)
    last = PrimT(Prim.VOID)
    for i, s in enumerate(stmts):
        exp = expect if i == len(stmts) - 1 else None
        if isinstance(s, Let):
            locals_[s.name] = infer(s.value, locals_, space, scope)
        else:
            last = infer(s, locals_, space, scope, exp)
    return last
