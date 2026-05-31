"""The type space: ONE trie + the pointer lattice (fits) + expression inference.

The trie is the namespace, import resolver, AND conflict checker.
fits() locks pointer direction and nullability.
infer() type-checks a body and triggers fits() at every call site.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, Fn, EnumDecl, MethodSig,
                  Lit, Bool, Var, Field, Bin, Not, Call, StructLit, Let, EnumCtor, Match)


class Conflict(Exception):   ...
class Unresolved(Exception): ...


@dataclass
class TraitMethod:
    """A scope entry for a trait method reachable via a bound `T: Trait`."""
    tparam: str               # the bound type-parameter (the method's Self)
    sig: "MethodSig"
    trait: str                # fully-qualified trait path


class TypeErr(Exception):
    def __init__(self, msg, given=None, want=None):
        super().__init__(msg)
        self.given, self.want = given, want
        self.pos = None              # (row, col) of the offending expr, filled in by infer()


# ───────────────────────── the namespace trie ───────────────────────────────
@dataclass
class Node:
    path: str = ""
    kids: dict = field(default_factory=dict)
    value: object = None


class Namespace:
    """Immutable-after-resolve data: the namespace trie + the trait-impl registry.
    Nothing is written to it during the checking phase — checking state lives on
    the AST (memoized `fn.ret`) and in the per-run `passing` set."""
    def __init__(self):
        self.root = Node()
        self.impls = {}              # (trait_path, type_path) -> {method: (Fn, scope)}; built in resolve

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
def _numeric(t) -> bool:
    return isinstance(t, PrimT) and t.prim in (Prim.I32, Prim.I64)


def infer(e, locals_, space, scope, expect=None):
    """Type `e`, tagging any TypeErr with the innermost offending expr's position
    (the deepest frame catches first, so the most specific location wins)."""
    try:
        return _infer(e, locals_, space, scope, expect)
    except TypeErr as ex:
        if ex.pos is None:
            ex.pos = getattr(e, "pos", None)
        raise


def _infer(e, locals_, space, scope, expect=None):
    """Return the type of expression `e`; raise TypeErr on any call mismatch.

    `expect` is the type the surrounding context wants (return slot, parameter,
    field). It's how a leading-dot enum ctor like `.Some(x)` learns which enum
    it builds — the variant name alone is ambiguous across enums."""
    match e:
        case Lit():
            return PrimT(Prim.I32)
        case Bool():
            return PrimT(Prim.BOOL)
        case EnumCtor():
            return infer_enum_ctor(e, expect, locals_, space, scope)
        case Match():
            return infer_match(e, expect, locals_, space, scope)
        case Var(name):
            if name not in locals_:
                raise TypeErr(f"unbound '{name}'")
            return locals_[name]
        case Not(operand):
            if infer(operand, locals_, space, scope) != PrimT(Prim.BOOL):
                raise TypeErr("'!' needs a bool operand")
            return PrimT(Prim.BOOL)
        case Bin(op, l, r):
            lt = infer(l, locals_, space, scope)
            rt = infer(r, locals_, space, scope)
            if op in ("&&", "||"):                       # logical: bool, bool -> bool
                if lt != PrimT(Prim.BOOL) or rt != PrimT(Prim.BOOL):
                    raise TypeErr(f"'{op}' needs bool operands")
                return PrimT(Prim.BOOL)
            if op == "==":
                if not (fits(lt, rt) or fits(rt, lt)):   # operands must be comparable
                    raise TypeErr("'==' operands differ")
                return PrimT(Prim.BOOL)
            if op in ("<", ">", "<=", ">="):             # ordering: numeric -> bool
                if not (_numeric(lt) and _numeric(rt)):
                    raise TypeErr(f"'{op}' needs numeric operands")
                return PrimT(Prim.BOOL)
            if not (_numeric(lt) and _numeric(rt)):      # + - * are numeric-only
                raise TypeErr(f"'{op}' needs numeric operands")
            return PrimT(Prim.I64 if Prim.I64 in (lt.prim, rt.prim) else Prim.I32)  # widen
        case Field(obj, name):
            ot = infer(obj, locals_, space, scope)
            st = ot.pointee if isinstance(ot, PtrT) else ot     # auto-deref through a pointer
            if not isinstance(st, NameT):
                raise TypeErr("field access on non-struct")
            decl = space.walk(st.path).value
            for f in decl.fields:
                if f.name == name:
                    # a field of a generic struct carries the instantiation's args
                    return subst(f.type, dict(zip(decl.tparams, st.args))) if decl.tparams else f.type
            raise TypeErr(f"no field '{name}' on {st.path}")
        case StructLit():
            return _infer_struct_lit(e, locals_, space, scope)
        case Call():
            return _infer_call(e, expect, locals_, space, scope)
        case _:
            raise TypeErr(f"unknown expr {e!r}")


def _infer_struct_lit(e, locals_, space, scope):
    qual = scope.get(e.type, e.type)
    decl = space.walk(qual).value
    ftypes = {f.name: f.type for f in decl.fields}
    givens, s = {}, {}
    for fname, fexpr in e.fields:                # pass 1: infer values, solve type-args
        if fname not in ftypes:
            raise TypeErr(f"no field '{fname}' on {qual}")
        givens[fname] = infer(fexpr, locals_, space, scope)
        if decl.tparams:
            match_type(ftypes[fname], givens[fname], s)
    missing = [t for t in decl.tparams if t not in s]
    if missing:
        raise TypeErr(f"cannot infer type {', '.join(missing)} for {qual.rsplit('.', 1)[-1]}")
    for fname, given in givens.items():          # pass 2: check against substituted field types
        want = subst(ftypes[fname], s)
        if not fits(given, want):
            raise TypeErr("field type", given, want)
    return NameT(qual, tuple(s[t] for t in decl.tparams))


def _infer_call(e, expect, locals_, space, scope):
    if e.callee == "addr":                                # addr(x): take a mutable pointer
        return PtrT(Dir.MUT, infer(e.args[0], locals_, space, scope))
    target = scope.get(e.callee)
    if isinstance(target, TraitMethod):                   # a bound's method, e.g. area(x)
        return infer_trait_call(e, target, locals_, space, scope)
    if target is None:
        raise TypeErr(f"unbound function '{e.callee}'")
    callee = space.walk(target).value
    if not isinstance(callee, Fn):
        raise TypeErr(f"'{e.callee}' is not callable")
    if len(e.args) != len(callee.params):
        raise TypeErr(f"'{e.callee}' wants {len(callee.params)} args, got {len(e.args)}")
    if callee.tparams:                                    # generic: infer type-args, then check
        arg_types = [infer(a, locals_, space, scope) for a in e.args]
        s = solve_call(callee, arg_types)
        missing = [n for n in callee.tparams if n not in s]
        if missing:
            raise TypeErr(f"cannot infer type {', '.join(missing)} for '{e.callee}'")
        for given, p in zip(arg_types, callee.params):
            want = subst(p.type, s)
            if not fits(given, want):
                raise TypeErr("pointer/null mismatch", given, want)
        for tp, trait_path in callee.bounds.items():      # the type-arg must satisfy its bound
            got = s.get(tp)
            if isinstance(got, NameT) and (trait_path, got.path) not in space.impls:
                raise TypeErr(f"{got.path.rsplit('.', 1)[-1]} does not implement "
                              f"{trait_path.rsplit('.', 1)[-1]}")
        return subst(ret_type(target, space), s)
    for a, p in zip(e.args, callee.params):
        given = infer(a, locals_, space, scope, p.type)
        if not fits(given, p.type):
            raise TypeErr("pointer/null mismatch", given, p.type)
    return ret_type(target, space)


_INFERRING = object()      # sentinel parked in fn.ret while its body is being inferred


def ret_type(qual, space):
    """The return type of a function: its annotation, or — when omitted — inferred
    from the body and memoized onto `fn.ret`. The sentinel doubles as the
    recursion guard, so no checking state lives on `Namespace`. Recursion through an
    un-annotated return is an error (annotate it), like every ML-family checker."""
    fn = space.walk(qual).value
    if fn.ret is _INFERRING:
        raise TypeErr(f"recursive function '{qual.rsplit('.', 1)[-1]}' needs a return-type annotation")
    if fn.ret is not None:
        return fn.ret
    fn.ret = _INFERRING
    try:
        fn.ret = infer_block(fn.body, {p.name: p.type for p in fn.params},
                             space, fn.scope, None)
    except BaseException:
        fn.ret = None      # roll back so a later check of this fn re-infers cleanly
        raise
    return fn.ret


def infer_trait_call(e, tm, locals_, space, scope):
    """Type a call to a bound's trait method: check args against the signature
    with Self left abstract (the type var of the bound this method came from)."""
    params = [subst(p, {"Self": TVar(tm.tparam)}) for p in tm.sig.params]
    if len(e.args) != len(params):
        raise TypeErr(f"'{e.callee}' wants {len(params)} args, got {len(e.args)}")
    for a, pt in zip(e.args, params):
        given = infer(a, locals_, space, scope)
        if not fits(given, pt):
            raise TypeErr("trait-method argument", given, pt)
    return subst(tm.sig.ret, {"Self": TVar(tm.tparam)})


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


def infer_match(e, expect, locals_, space, scope):
    """A match types each arm against the expected result, binds a variant's
    payload inside its arm (narrowing), and demands exhaustive coverage."""
    st = infer(e.subject, locals_, space, scope)
    if isinstance(st, PrimT):
        return _infer_match_lit(e, st, expect, locals_, space, scope)
    if not isinstance(st, NameT) or not isinstance(space.walk(st.path).value, EnumDecl):
        raise TypeErr(f"match on a non-enum value ({st.path if isinstance(st, NameT) else st})")
    decl = space.walk(st.path).value
    sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
    variants = {v.name: v for v in decl.variants}

    covered, wildcard, result = set(), False, expect
    for arm in e.arms:
        if wildcard:                                      # a catch-all already matched everything
            raise TypeErr("unreachable match arm after '_'")
        arm_locals = locals_
        if arm.variant is None:
            wildcard = True
        else:
            if arm.variant not in variants:
                raise TypeErr(f"enum {st.path} has no variant '.{arm.variant}'")
            if arm.variant in covered:
                raise TypeErr(f"duplicate match arm '.{arm.variant}'")
            covered.add(arm.variant)
            var = variants[arm.variant]
            if arm.binding is not None:
                if var.payload is None:
                    raise TypeErr(f"variant '.{arm.variant}' has no payload to bind")
                arm_locals = {**locals_, arm.binding: subst(var.payload, sub)}
        bt = infer(arm.body, arm_locals, space, scope, result)
        if result is None:
            result = bt
        elif not fits(bt, result):
            raise TypeErr("match arms differ", bt, result)

    missing = [v for v in variants if v not in covered]
    if not wildcard and missing:
        raise TypeErr(f"non-exhaustive match: missing {', '.join('.' + m for m in missing)}")
    return result


def _infer_match_lit(e, st, expect, locals_, space, scope):
    """Match on an i32/bool subject: literal patterns and a wildcard. Integers
    can't be enumerated, so a `_` is required (bool may instead cover true+false)."""
    wildcard, result, seen = False, expect, set()
    for arm in e.arms:
        if wildcard:
            raise TypeErr("unreachable match arm after '_'")
        if arm.variant is not None:
            raise TypeErr("variant pattern on a non-enum value")
        if arm.lit is None:
            wildcard = True
        else:
            lt = infer(arm.lit, locals_, space, scope)
            if not fits(lt, st):
                raise TypeErr("pattern type", lt, st)
            val = arm.lit.b if isinstance(arm.lit, Bool) else arm.lit.n
            if val in seen:
                raise TypeErr(f"duplicate match arm '{val}'")
            seen.add(val)
        bt = infer(arm.body, locals_, space, scope, result)
        if result is None:
            result = bt
        elif not fits(bt, result):
            raise TypeErr("match arms differ", bt, result)
    if not wildcard and not (st == PrimT(Prim.BOOL) and seen == {True, False}):
        raise TypeErr("non-exhaustive match: add a '_' arm")
    return result


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
