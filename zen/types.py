"""The type space: ONE trie + the pointer lattice (fits) + expression inference.

The trie is the namespace, import resolver, AND conflict checker.
fits() locks pointer direction and nullability.
infer() type-checks a body and triggers fits() at every call site.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, FnT, Fn, Struct, EnumDecl, MethodSig,
                  Lit, Bool, Str, Var, Field, Bin, Not, Call, MethodCall, StructLit, SliceLit, Index,
                  SliceT, Let, Assign, While, EnumCtor, Match, Closure)


class Conflict(Exception):   ...
class Unresolved(Exception): ...
class Private(Exception):    ...   # imported a name another module didn't export (no `*`)


class Located(str):
    """A diagnostic message that IS its text (so `in`, `startswith`, printing all
    work) but also carries the structured `(ns, row, col)` of the error — so a
    caret can be rendered straight from the location, never by re-parsing the
    formatted string. Format at the edge, carry structure through."""
    ns: "str | None"
    pos: "tuple | None"

    def __new__(cls, text, ns=None, pos=None):
        s = super().__new__(cls, text)
        s.ns, s.pos = ns, pos
        return s


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


# ───────────────────────── expression inference ─────────────────────────────
def _numeric(t) -> bool:
    return isinstance(t, PrimT) and t.prim in (Prim.U8, Prim.I32, Prim.I64)


_TBOUNDS = "\x00tbounds"      # scope key carrying the enclosing fn's tparam bounds


def scope_with_bounds(scope, bounds):
    """Embed an enclosing fn's `{tvar: trait_path}` bounds in its body's scope, so a
    call to a bounded generic can require a forwarded TYPE VARIABLE to be bounded too
    (the key is non-identifier, so it never collides with a real name)."""
    return {**(scope or {}), _TBOUNDS: dict(bounds or {})}


def infer(e, locals_, namespace, scope, expect=None):
    """Type `e`, tagging any TypeErr with the innermost offending expr's position
    (the deepest frame catches first, so the most specific location wins)."""
    if isinstance(expect, TVar):                 # an unsolved type param never constrains a value —
        expect = None                            # it gets solved by match_type, so infer naturally here
    try:
        return _infer(e, locals_, namespace, scope, expect)
    except TypeErr as ex:
        if ex.pos is None:
            ex.pos = getattr(e, "pos", None)
        raise


def _infer(e, locals_, namespace, scope, expect=None):
    """Return the type of expression `e`; raise TypeErr on any call mismatch.

    `expect` is the type the surrounding context wants (return slot, parameter,
    field). It's how a leading-dot enum ctor like `.Some(x)` learns which enum
    it builds — the variant name alone is ambiguous across enums."""
    match e:
        case Lit():                                      # an integer literal adapts to the wanted int type
            if isinstance(expect, PrimT) and expect.prim in (Prim.U8, Prim.I32, Prim.I64):
                return expect
            return PrimT(Prim.I32)
        case Bool():
            return PrimT(Prim.BOOL)
        case Str():                                      # a string literal "…" is a `str`
            return PrimT(Prim.STR)
        case EnumCtor():
            return infer_enum_ctor(e, expect, locals_, namespace, scope)
        case Match():
            return infer_match(e, expect, locals_, namespace, scope)
        case Var(name):
            if name not in locals_:
                raise TypeErr(f"unbound '{name}'")
            return locals_[name]
        case Not(operand):
            if infer(operand, locals_, namespace, scope) != PrimT(Prim.BOOL):
                raise TypeErr("'!' needs a bool operand")
            return PrimT(Prim.BOOL)
        case Bin(op, l, r):
            lt = infer(l, locals_, namespace, scope)
            rt = infer(r, locals_, namespace, scope)
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
            ot = infer(obj, locals_, namespace, scope)
            st = ot.pointee if isinstance(ot, PtrT) else ot     # auto-deref through a pointer
            if isinstance(st, SliceT):                          # a slice exposes .ptr and .len
                if name == "len":
                    return PrimT(Prim.I64)
                if name == "ptr":
                    return PtrT(Dir.RAW, st.elem)
                raise TypeErr(f"a slice has no field '{name}' (only .ptr / .len)")
            if not isinstance(st, NameT):
                raise TypeErr("field access on a non-struct value")
            decl = namespace.walk(st.path).value
            if not isinstance(decl, Struct):                    # an enum payload is reachable
                short = st.path.rsplit(".", 1)[-1]              # ONLY through match, never `.field`
                raise TypeErr(f"cannot read fields of enum {short} — use match")
            for f in decl.fields:
                if f.name == name:
                    # a field of a generic struct carries the instantiation's args
                    return subst(f.type, dict(zip(decl.tparams, st.args))) if decl.tparams else f.type
            raise TypeErr(f"no field '{name}' on {st.path}")
        case StructLit():
            return _infer_struct_lit(e, locals_, namespace, scope)
        case SliceLit(elems):                                  # [a, b, c] : [T]
            et = expect.elem if isinstance(expect, SliceT) else None
            if isinstance(et, TVar):                            # unsolved type param ([T] of a generic
                et = None                                       # struct): infer naturally, solve later
            if et is None:
                if not elems:
                    raise TypeErr("cannot infer the type of an empty slice literal")
                et = infer(elems[0], locals_, namespace, scope)
            for x in elems:                                    # every element must fit the elem type
                xt = infer(x, locals_, namespace, scope, et)
                if fits(xt, et):
                    continue
                if et is not None and fits(et, xt):            # widen toward the larger int
                    et = xt
                else:
                    raise TypeErr("slice element", xt, et)
            return SliceT(et)
        case Index(seq, idx):                                  # xs[i] : T
            st = infer(seq, locals_, namespace, scope)
            if not _numeric(infer(idx, locals_, namespace, scope)):
                raise TypeErr("a slice index must be numeric")
            if isinstance(st, SliceT):
                return st.elem
            at = struct_at(st, namespace)                          # []-overloading: a struct's `at`
            if at is not None:
                return at[2].ret                               # the `at` method's return type
            raise TypeErr("indexing a non-slice value")
        case Closure(params, body):
            if not isinstance(expect, FnT):
                raise TypeErr("a closure needs a known function type here (pass it to a closure parameter)")
            if len(params) != len(expect.params):
                raise TypeErr(f"closure has {len(params)} param(s), expected {len(expect.params)}")
            cl = {**locals_, **dict(zip(params, expect.params))}   # captures + the bound params
            rt = infer_block(body, cl, namespace, scope, expect.ret)
            void = isinstance(expect.ret, PrimT) and expect.ret.prim is Prim.VOID
            if expect.ret is not None and not void and not fits(rt, expect.ret):
                raise TypeErr("closure result", rt, expect.ret)
            return FnT(tuple(expect.params), expect.ret)
        case Call():
            return _infer_call(e, expect, locals_, namespace, scope)
        case MethodCall(recv, method, args):
            if method in ("break", "continue"):                 # the loop handle: h.break()/h.continue()
                if args:
                    raise TypeErr(f"'{method}' takes no arguments")
                return PrimT(Prim.VOID)
            # UFCS: `x.f(a, b)` is sugar for `f(x, a, b)` — the receiver is the first
            # argument. Resolves free functions and trait-bound methods alike.
            call = Call(method, (recv,) + tuple(args), getattr(e, "pos", None))
            return _infer_call(call, expect, locals_, namespace, scope)
        case _:
            raise TypeErr(f"unknown expr {e!r}")


def _infer_mem(e, locals_, namespace, scope):
    """load(p)->T · store(p, v: T)->void · offset(p, i64)->same ptr. T comes from p."""
    pt = infer(e.args[0], locals_, namespace, scope)
    if pt == PrimT(Prim.STR):                            # a str is a const char* — read its bytes raw
        pt = PtrT(Dir.READ, PrimT(Prim.U8))              # (READ: store stays blocked; the text is const)
    if not isinstance(pt, PtrT):
        raise TypeErr(f"'{e.callee}' needs a pointer as its first argument")
    if e.callee == "load":
        return pt.pointee
    if e.callee == "offset":
        idx = infer(e.args[1], locals_, namespace, scope)
        if not _numeric(idx):
            raise TypeErr("offset index must be numeric")
        return pt                                        # offset stays the same pointer type
    # store
    if pt.dir is Dir.READ:
        raise TypeErr("cannot store through a read-only Ptr (use MutPtr/RawPtr)")
    val = infer(e.args[1], locals_, namespace, scope, pt.pointee)
    if not fits(val, pt.pointee):
        raise TypeErr("store value", val, pt.pointee)
    return PrimT(Prim.VOID)


def _infer_struct_lit(e, locals_, namespace, scope):
    qual = scope.get(e.type, e.type)
    decl = namespace.walk(qual).value
    if not isinstance(decl, Struct):                 # `EnumName { … }` / `fn { … }` is not a struct
        raise TypeErr(f"'{qual.rsplit('.', 1)[-1]}' is not a struct")
    ftypes = {f.name: f.type for f in decl.fields}
    givens, s = {}, {}
    for fname, fexpr in e.fields:                # pass 1: infer values, solve type-args
        if fname not in ftypes:
            raise TypeErr(f"no field '{fname}' on {qual}")
        givens[fname] = infer(fexpr, locals_, namespace, scope, ftypes[fname])  # int lits adapt to the field
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


def struct_at(st, namespace):
    """`[]` overloading: if `st` is a struct (or a pointer to one) whose type has an
    impl with an `at` method, return `(trait_path, type_path, at_fn)` — so `s[i]`
    types as `at`'s return and lowers to that call. None if not indexable. This is
    what makes a user struct *loopable*: the element-loop indexes it like a slice."""
    ty = st.pointee if isinstance(st, PtrT) else st
    if not isinstance(ty, NameT):
        return None
    for (trait_path, type_path), methods in namespace.impls.items():
        if type_path == ty.path and "at" in methods:
            return (trait_path, type_path, methods["at"][0])
    return None


def _infer_call(e, expect, locals_, namespace, scope):
    if e.callee == "addr":                                # addr(x): take a mutable pointer
        return PtrT(Dir.MUT, infer(e.args[0], locals_, namespace, scope))
    if e.callee in ("load", "store", "offset"):           # raw memory ops, T inferred from the ptr
        return _infer_mem(e, locals_, namespace, scope)
    if e.callee == "cstr":                                # cstr(p): view a NUL-terminated byte ptr as a str
        pt = infer(e.args[0], locals_, namespace, scope)
        if not (isinstance(pt, PtrT) or pt == PrimT(Prim.STR)):
            raise TypeErr("cstr(p) needs a byte pointer")
        return PrimT(Prim.STR)
    if e.callee == "sizeof":                              # sizeof(T): byte size of a named type, i64
        if len(e.args) != 1 or not isinstance(e.args[0], Var):
            raise TypeErr("sizeof(T) takes a single type name")
        resolved = scope.get(e.args[0].name, e.args[0].name)
        if not isinstance(resolved, TVar):                # a generic tparam is fine — its size is known
            namespace.walk(resolved)                      # once monomorphized; else the type must exist
        return PrimT(Prim.I64)
    if e.callee == "slice":                               # slice(ptr, len): a [T] view of raw memory
        if not isinstance(expect, SliceT):                # element type comes from the wanted slice
            raise TypeErr("slice(ptr, len) needs a known slice type here "
                          "(e.g. a `[T]` return slot or parameter)")
        pt = infer(e.args[0], locals_, namespace, scope)      # a pointer, or a `str` (a C char*)
        if len(e.args) != 2 or not (isinstance(pt, PtrT) or pt == PrimT(Prim.STR)):
            raise TypeErr("slice(ptr, len): a pointer (or str) and a length")
        if not isinstance(infer(e.args[1], locals_, namespace, scope), PrimT):
            raise TypeErr("slice length must be numeric")
        return expect
    if isinstance(locals_.get(e.callee), FnT):            # calling a closure parameter: f(acc, x)
        fnt = locals_[e.callee]
        if len(e.args) != len(fnt.params):
            raise TypeErr(f"closure '{e.callee}' wants {len(fnt.params)} args, got {len(e.args)}")
        for a, pt in zip(e.args, fnt.params):
            given = infer(a, locals_, namespace, scope, pt)
            if not fits(given, pt):
                raise TypeErr("closure argument", given, pt)
        return fnt.ret
    target = scope.get(e.callee)
    if isinstance(target, TraitMethod):                   # a bound's method, e.g. area(x)
        return infer_trait_call(e, target, locals_, namespace, scope)
    if target is None:
        raise TypeErr(f"unbound function '{e.callee}'")
    callee = namespace.walk(target).value
    if not isinstance(callee, Fn):
        raise TypeErr(f"'{e.callee}' is not callable")
    if len(e.args) != len(callee.params):
        raise TypeErr(f"'{e.callee}' wants {len(callee.params)} args, got {len(e.args)}")
    if callee.tparams:                                    # generic: infer type-args, then check
        # Two passes so a closure argument can be checked AFTER the type-args it
        # depends on are solved from the ordinary args (a closure has no standalone
        # type — its param types come from the now-known FnT parameter).
        s, arg_types = {}, [None] * len(e.args)
        for i, (a, p) in enumerate(zip(e.args, callee.params)):
            if isinstance(a, Closure):
                continue
            arg_types[i] = infer(a, locals_, namespace, scope)
            match_type(p.type, arg_types[i], s)
        for i, (a, p) in enumerate(zip(e.args, callee.params)):
            if not isinstance(a, Closure):
                continue
            arg_types[i] = infer(a, locals_, namespace, scope, subst(p.type, s))
            match_type(p.type, arg_types[i], s)
        missing = [n for n in callee.tparams if n not in s]
        if missing:
            raise TypeErr(f"cannot infer type {', '.join(missing)} for '{e.callee}'")
        for given, p in zip(arg_types, callee.params):
            want = subst(p.type, s)
            if not fits(given, want):
                raise TypeErr("pointer/null mismatch", given, want)
        for tp, trait_path in callee.bounds.items():      # the type-arg must satisfy its bound
            got = s.get(tp)
            short = trait_path.rsplit('.', 1)[-1]
            if isinstance(got, NameT):                     # a concrete type — needs an impl
                if (trait_path, got.path) not in namespace.impls:
                    raise TypeErr(f"{got.path.rsplit('.', 1)[-1]} does not implement {short}")
            elif isinstance(got, TVar):                    # a forwarded type var — must be bounded too
                if scope.get(_TBOUNDS, {}).get(got.name) != trait_path:
                    raise TypeErr(f"type {got.name} is unbounded but '{e.callee}' requires "
                                  f"{got.name}: {short} — add the bound")
        return subst(ret_type(target, namespace), s)
    for a, p in zip(e.args, callee.params):
        given = infer(a, locals_, namespace, scope, p.type)
        if not fits(given, p.type):
            raise TypeErr("pointer/null mismatch", given, p.type)
    return ret_type(target, namespace)


_INFERRING = object()      # sentinel parked in fn.ret while its body is being inferred


def ret_type(qual, namespace):
    """The return type of a function: its annotation, or — when omitted — inferred
    from the body and memoized onto `fn.ret`. The sentinel doubles as the
    recursion guard, so no checking state lives on `Namespace`. Recursion through an
    un-annotated return is an error (annotate it), like every ML-family checker."""
    fn = namespace.walk(qual).value
    if fn.ret is _INFERRING:
        raise TypeErr(f"recursive function '{qual.rsplit('.', 1)[-1]}' needs a return-type annotation")
    if fn.ret is not None:
        return fn.ret
    fn.ret = _INFERRING
    try:
        fn.ret = infer_block(fn.body, {p.name: p.type for p in fn.params},
                             namespace, scope_with_bounds(fn.scope, fn.bounds), None)
    except BaseException:
        fn.ret = None      # roll back so a later check of this fn re-infers cleanly
        raise
    return fn.ret


def infer_trait_call(e, tm, locals_, namespace, scope):
    """Type a call to a bound's trait method. Self is solved from the arguments (the
    receiver), so the call checks both in a generic body (Self -> the bound's type var)
    and after instantiation (Self -> the concrete type) — e.g. a let-bound trait call
    inside a generic fn, which the monomorphizer re-infers with a concrete receiver."""
    if len(e.args) != len(tm.sig.params):
        raise TypeErr(f"'{e.callee}' wants {len(tm.sig.params)} args, got {len(e.args)}")
    givens = [infer(a, locals_, namespace, scope) for a in e.args]
    s: dict = {}
    for p, g in zip(tm.sig.params, givens):
        match_type(p, g, s)                          # solve Self (+ any tvars) from the args
    self_t = s.get("Self", TVar(tm.tparam))          # unsolved -> stay abstract (the bound's var)
    for g, p in zip(givens, tm.sig.params):
        if not fits(g, subst(p, {"Self": self_t})):
            raise TypeErr("trait-method argument", g, subst(p, {"Self": self_t}))
    return subst(tm.sig.ret, {"Self": self_t})       # ret with Self resolved from the receiver


def infer_enum_ctor(e, expect, locals_, namespace, scope):
    """`.Variant(payload)` — the expected type names which enum, then the
    variant's declared payload type is checked like any other slot."""
    if not isinstance(expect, NameT):
        raise TypeErr(f"cannot tell which enum '.{e.name}' builds (no expected type here)")
    try:
        decl = namespace.walk(expect.path).value
    except Unresolved:                               # e.g. Option: a builtin coercion target,
        decl = None                                  # not a declared, constructible enum
    if not isinstance(decl, EnumDecl):
        raise TypeErr(f"'.{e.name}' used where {expect.path} (not a constructible enum) is wanted")
    var = next((v for v in decl.variants if v.name == e.name), None)
    if var is None:
        raise TypeErr(f"enum {expect.path} has no variant '.{e.name}'")
    sub = dict(zip(decl.tparams, expect.args))       # generic enum: T -> the instantiation's arg
    if var.payload is None:
        if e.args:
            raise TypeErr(f"variant '.{e.name}' takes no payload")
    else:
        if len(e.args) != 1:
            raise TypeErr(f"variant '.{e.name}' takes one payload value")
        want = subst(var.payload, sub)
        given = infer(e.args[0], locals_, namespace, scope, want)
        if not fits(given, want):
            raise TypeErr("enum payload", given, want)
    return NameT(expect.path, expect.args)           # preserve the type-args (Opt<i32>, not Opt<>)


def infer_match(e, expect, locals_, namespace, scope):
    """A match types each arm against the expected result, binds a variant's
    payload inside its arm (narrowing), and demands exhaustive coverage."""
    st = infer(e.subject, locals_, namespace, scope)
    if isinstance(st, PtrT) and isinstance(st.pointee, NameT):   # match auto-derefs a Ptr<Enum>
        st = st.pointee                                          # (like field access does)
    if isinstance(st, PrimT):
        return _infer_match_lit(e, st, expect, locals_, namespace, scope)
    try:
        decl = namespace.walk(st.path).value if isinstance(st, NameT) else None
    except Unresolved:                               # Option and other non-declared names
        decl = None
    if not isinstance(decl, EnumDecl):
        raise TypeErr(f"match on a non-enum value ({show(st)})")
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
        bt = infer(arm.body, arm_locals, namespace, scope, result)
        if result is None:
            result = bt
        elif not fits(bt, result):
            raise TypeErr("match arms differ", bt, result)

    missing = [v for v in variants if v not in covered]
    if not wildcard and missing:
        raise TypeErr(f"non-exhaustive match: missing {', '.join('.' + m for m in missing)}")
    return result


def _infer_match_lit(e, st, expect, locals_, namespace, scope):
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
            lt = infer(arm.lit, locals_, namespace, scope)
            if not fits(lt, st):
                raise TypeErr("pattern type", lt, st)
            val = arm.lit.b if isinstance(arm.lit, Bool) else arm.lit.n
            if val in seen:
                raise TypeErr(f"duplicate match arm '{val}'")
            seen.add(val)
        bt = infer(arm.body, locals_, namespace, scope, result)
        if result is None:
            result = bt
        elif not fits(bt, result):
            raise TypeErr("match arms differ", bt, result)
    if not wildcard and not (st == PrimT(Prim.BOOL) and seen == {True, False}):
        raise TypeErr("non-exhaustive match: add a '_' arm")
    return result


def infer_block(stmts, locals_, namespace, scope, expect=None):
    """Type a function body: `x := v` bindings extend locals in order; the value
    of the block is the type of its final expression statement (void if none).
    `expect` (the function's return type) reaches the final statement."""
    locals_ = dict(locals_)
    last = PrimT(Prim.VOID)
    for i, s in enumerate(stmts):
        exp = expect if i == len(stmts) - 1 else None
        if isinstance(s, Let):
            locals_[s.name] = infer(s.value, locals_, namespace, scope)
        elif isinstance(s, Assign):
            _check_assign(s, locals_, namespace, scope)
            last = PrimT(Prim.VOID)
        elif isinstance(s, While):                       # @while / desugared loop
            if infer(s.cond, locals_, namespace, scope) != PrimT(Prim.BOOL):
                raise TypeErr("loop/@while condition must be a bool")
            infer_block(s.body, dict(locals_), namespace, scope)   # body in its own scope
            if s.step is not None:                       # the count loop's i = i + 1
                infer_block((s.step,), locals_, namespace, scope)
            last = PrimT(Prim.VOID)
        else:
            last = infer(s, locals_, namespace, scope, exp)
    return last


def _check_assign(s, locals_, namespace, scope):
    target = infer(s.target, locals_, namespace, scope)      # the lvalue's type (also validates it)
    if isinstance(s.target, Field):                      # set a field through a pointer? must be writable
        ot = infer(s.target.obj, locals_, namespace, scope)
        if isinstance(ot, PtrT) and ot.dir is Dir.READ:
            raise TypeErr("cannot assign through a read-only Ptr (use MutPtr)")
    val = infer(s.value, locals_, namespace, scope, target)
    if not fits(val, target):
        raise TypeErr("assignment", val, target)
