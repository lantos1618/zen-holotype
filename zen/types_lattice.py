"""The pure type lattice: rendering, fitness, and generic substitution/unification.

This is a leaf layer — it depends only on the AST node classes, never on the
inference core in types.py. `show` renders a type for diagnostics; `fits` locks
pointer direction + nullability; `subst`/`match_type`/`solve_call` are the
generic machinery (shape-only unification, with lattice fitness enforced
afterwards by `fits` on the substituted types).
"""
from __future__ import annotations
from .ast import Dir, Prim, PrimT, NameT, PtrT, TVar, FnT, SliceT


def show(t) -> str:
    """Source-level (pre-erasure) rendering of a type — for diagnostics."""
    if isinstance(t, TVar):
        return t.name
    if isinstance(t, PrimT):
        return t.prim.value
    if isinstance(t, PtrT):
        return f"{t.dir.value}<{show(t.pointee)}>"
    if isinstance(t, SliceT):
        return f"[{show(t.elem)}]"
    if isinstance(t, FnT):
        return f"({', '.join(show(p) for p in t.params)}) {show(t.ret)}"
    if isinstance(t, NameT):
        seg = t.path.rsplit(".", 1)[-1]
        return f"{seg}<{', '.join(show(a) for a in t.args)}>" if t.args else seg
    return "?"


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
    if isinstance(given, FnT) and isinstance(want, FnT):     # closures: inlined, so invariant params
        return (len(given.params) == len(want.params)
                and all(p == q for p, q in zip(given.params, want.params))
                and fits(given.ret, want.ret))
    if isinstance(given, PrimT) and isinstance(want, PrimT):
        if given.prim is want.prim:
            return True
        rank = {Prim.U8: 0, Prim.I32: 1, Prim.I64: 2}             # widening: u8 ≤ i32 ≤ i64
        if given.prim in rank and want.prim in rank:
            return rank[given.prim] <= rank[want.prim]
        return False
    return given == want                             # nominal/structural eq (paths canonical)


# ───────────────────────── generics: substitution + unification ─────────────
def subst(t, s):
    """Replace each type variable in `t` with its binding from `s` (name -> Type)."""
    if isinstance(t, TVar):
        return s.get(t.name, t)
    if isinstance(t, PtrT):
        return PtrT(t.dir, subst(t.pointee, s))
    if isinstance(t, SliceT):
        return SliceT(subst(t.elem, s))
    if isinstance(t, FnT):
        return FnT(tuple(subst(p, s) for p in t.params), subst(t.ret, s))
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
    elif isinstance(param, SliceT) and isinstance(arg, SliceT):
        match_type(param.elem, arg.elem, s)
    elif isinstance(param, FnT) and isinstance(arg, FnT) and len(param.params) == len(arg.params):
        for p, a in zip(param.params, arg.params):
            match_type(p, a, s)
        match_type(param.ret, arg.ret, s)
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


def _numeric(t) -> bool:
    return isinstance(t, PrimT) and t.prim in (Prim.U8, Prim.I32, Prim.I64)
