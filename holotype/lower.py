"""Hook-based transcribe to C. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced upstream).
"""
from __future__ import annotations
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, Struct, EnumDecl, Fn,
                  Lit, Bool, Var, Field, Bin, Not, Call, StructLit, Let, Assign, While,
                  EnumCtor, Match)
from .types import infer, subst, solve_call, match_type, TraitMethod
from .comptime import evaluate

_CMAP = {Prim.I32: "int32_t", Prim.I64: "int64_t", Prim.U8: "uint8_t",
         Prim.BOOL: "bool", Prim.VOID: "void"}


def c_name(path: str) -> str:
    return path.replace(".", "_")


_DIRTAG = {Dir.READ: "p", Dir.MUT: "mp", Dir.RAW: "rp"}


def mangle(t) -> str:
    """A C-identifier fragment for a concrete type — used to name monomorphized
    instances so two type-args never collide (id<Vec> -> ..._core_vec_Vec)."""
    if isinstance(t, PrimT):
        return t.prim.value
    if isinstance(t, NameT):
        tail = ("_" + "_".join(mangle(a) for a in t.args)) if t.args else ""
        return c_name(t.path) + tail
    if isinstance(t, PtrT):
        return _DIRTAG[t.dir] + "_" + mangle(t.pointee)
    return "x"


def inst_name(qual, targs) -> str:
    """The mangled C name of a generic instance: <fn>_<arg1>_<arg2>…"""
    return c_name(qual) + "_" + "_".join(mangle(t) for t in targs)


def impl_cname(trait_path, type_path, method) -> str:
    """The mangled C name of a trait method's concrete impl: impl_<Trait>_<Type>_<m>."""
    return f"impl_{c_name(trait_path)}_{c_name(type_path)}_{method}"


def c_type(t) -> str:
    if isinstance(t, TVar):
        raise TypeError(f"un-monomorphized type variable {t.name} reached codegen")
    if isinstance(t, PrimT):
        return _CMAP[t.prim]
    if isinstance(t, PtrT):
        return c_type(t.pointee) + (" const *" if t.dir is Dir.READ else " *")
    if isinstance(t, NameT):
        if t.path == "Option":
            inner = t.args[0]
            if isinstance(inner, PtrT) or (isinstance(inner, NameT) and inner.path == "Option"):
                return c_type(inner)        # niche: nullable pointer IS the pointer (NULL = none)
            return c_type(inner) + " *"
        if t.args:                          # a generic struct/enum instance -> monomorphized name
            return mangle(t)
        return c_name(t.path)
    return "void"


# ───────────────────────── expression codegen ──────────────────────────────
def c_expr(e, locals_, space, scope, expect=None) -> str:
    match e:
        case Lit(n):
            return str(n)
        case Bool(b):
            return "true" if b else "false"
        case Var(name):
            return name
        case Bin(op, l, r):
            return f"({c_expr(l, locals_, space, scope)} {op} {c_expr(r, locals_, space, scope)})"
        case Not(operand):
            return f"(!{c_expr(operand, locals_, space, scope)})"
        case Field(obj, name):
            sep = "->" if isinstance(infer(obj, locals_, space, scope), PtrT) else "."
            return f"{c_expr(obj, locals_, space, scope)}{sep}{name}"   # pointer access -> ->
        case StructLit():
            st = infer(e, locals_, space, scope)                # NameT(qual, targs)
            decl = space.walk(st.path).value
            sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
            ftypes = {fl.name: subst(fl.type, sub) for fl in decl.fields}
            inits = ", ".join(f".{n} = {c_expr(v, locals_, space, scope, ftypes[n])}"
                              for n, v in e.fields)
            return f"({c_type(st)}){{ {inits} }}"               # C99 compound literal
        case EnumCtor():
            decl = space.walk(expect.path).value                # expect names the enum (+ its args)
            cn = c_type(expect)                                 # mangled instance name if generic
            sub = dict(zip(decl.tparams, expect.args))
            var = next(v for v in decl.variants if v.name == e.name)
            if var.payload is None:
                return f"({cn}){{ .tag = {cn}_{e.name} }}"
            inner = c_expr(e.args[0], locals_, space, scope, subst(var.payload, sub))
            return f"({cn}){{ .tag = {cn}_{e.name}, .u.{e.name} = {inner} }}"
        case Match():
            return c_match(e, locals_, space, scope, expect)
        case Call():
            return _c_call(e, locals_, space, scope)
        case _:
            return "0"


def _c_call(e, locals_, space, scope) -> str:
    if e.callee == "addr":
        return f"&({c_expr(e.args[0], locals_, space, scope)})"
    if e.callee in ("load", "store", "offset"):           # raw memory ops erase to C
        a = [c_expr(x, locals_, space, scope) for x in e.args]
        if e.callee == "load":
            return f"(*({a[0]}))"
        if e.callee == "store":
            return f"(*({a[0]}) = {a[1]})"
        return f"(({a[0]}) + ({a[1]}))"                    # offset
    if e.callee == "comptime":                            # evaluate now, emit the constant
        v = evaluate(e.args[0], space, scope)
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        raise NotImplementedError(f"comptime value {v!r} is not yet lowerable")
    target = scope.get(e.callee)
    if isinstance(target, TraitMethod):                 # resolve to the concrete impl fn
        s: dict = {}
        for p, a in zip(target.sig.params, e.args):
            match_type(p, infer(a, locals_, space, scope), s)
        cn = impl_cname(target.trait, s["Self"].path, e.callee)
        ptypes = [subst(p, {"Self": s["Self"]}) for p in target.sig.params]
    else:
        callee = space.walk(target).value
        assert isinstance(callee, Fn)                   # a callee path always names a function
        if callee.tparams:                              # generic: name the monomorphized instance
            s = solve_call(callee, [infer(a, locals_, space, scope) for a in e.args])
            cn = inst_name(target, tuple(s[n] for n in callee.tparams))
            ptypes = [subst(p.type, s) for p in callee.params]
        else:
            cn = callee.name if callee.extern else c_name(target)   # extern → bare C symbol
            ptypes = [p.type for p in callee.params]
    args = ", ".join(c_expr(a, locals_, space, scope, pt) for a, pt in zip(e.args, ptypes))
    return f"{cn}({args})"


def c_match(e, locals_, space, scope, expect) -> str:
    """Lower a match to a tag-tested ternary chain. A variant with a payload
    binding uses a statement-expression `({ T b = subj.u.V; body; })` so the
    binding is a real typed local (this narrows the payload inside the arm)."""
    # The subject is bound to a temp ONCE, then the arm tests reference the temp —
    # so a subject with side effects (e.g. a call) is evaluated exactly once, not
    # per arm. A catch-all is guaranteed last (the checker rejects unreachable
    # arms), so the final arm is the ternary's else.
    subj = c_expr(e.subject, locals_, space, scope)
    st = infer(e.subject, locals_, space, scope)
    t = f"_subj{id(e)}"                                  # unique per match node (nesting-safe)

    if isinstance(st, PrimT):                           # literal match: t == lit ? … : …
        body = lambda arm: f"({c_expr(arm.body, locals_, space, scope, expect)})"
        default = next((a for a in e.arms if a.lit is None), None) or e.arms[-1]
        chain = body(default)
        for arm in reversed([a for a in e.arms if a is not default]):
            litc = c_expr(arm.lit, locals_, space, scope)
            chain = f"({t} == {litc} ? {body(arm)} : {chain})"
        return f"({{ {c_type(st)} {t} = {subj}; {chain}; }})"

    decl = space.walk(st.path).value
    sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
    cn = c_type(st)                                     # mangled instance name if a generic enum
    variants = {v.name: v for v in decl.variants}

    def clause(arm):
        if arm.variant is not None and arm.binding is not None:
            pt = c_type(subst(variants[arm.variant].payload, sub))
            al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            return (f"({{ {pt} {arm.binding} = {t}.u.{arm.variant}; "
                    f"{c_expr(arm.body, al, space, scope, expect)}; }})")
        return f"({c_expr(arm.body, locals_, space, scope, expect)})"

    default = next((a for a in e.arms if a.variant is None), None) or e.arms[-1]
    chain = clause(default)
    for arm in reversed([a for a in e.arms if a is not default]):
        chain = f"({t}.tag == {cn}_{arm.variant} ? {clause(arm)} : {chain})"
    return f"({{ {c_type(st)} {t} = {subj}; {chain}; }})"


# ───────────────────────── declaration codegen ─────────────────────────────
def _params(d: Fn) -> str:
    return ", ".join(f"{c_type(p.type)} {p.name}" for p in d.params) or "void"


def c_struct(qual, d: Struct, sub=None, cname=None) -> str:
    sub = sub or {}
    body = " ".join(f"{c_type(subst(f.type, sub))} {f.name};" for f in d.fields)
    return f"typedef struct {{ {body} }} {cname or c_name(qual)};"


def c_enum(qual, d: EnumDecl, sub=None, cname=None) -> str:
    """A tagged union: an int tag plus a union of the payload-carrying variants.
    Tag constants <Enum>_<Variant> take their declaration order (0, 1, 2, …).
    `sub`/`cname` monomorphize a generic enum instance (Opt<i32> -> Opt_i32)."""
    sub = sub or {}
    cn = cname or c_name(qual)
    members = " ".join(f"{c_type(subst(v.payload, sub))} {v.name};"
                       for v in d.variants if v.payload is not None)
    union = f" union {{ {members} }} u;" if members else ""
    tags = ", ".join(f"{cn}_{v.name}" for v in d.variants)
    return f"typedef struct {{ int32_t tag;{union} }} {cn};\nenum {{ {tags} }};"


def c_proto(qual, d: Fn, cname=None) -> str:
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)});"


def c_block(stmts, locals_, space, scope, expect=None) -> str:
    """Lower a statement list: each `x := v` becomes a typed C local; the final
    expression statement becomes the `return` (and gets the expected type)."""
    locals_ = dict(locals_)
    is_void = isinstance(expect, PrimT) and expect.prim is Prim.VOID
    lines, last = [], len(stmts) - 1
    for i, s in enumerate(stmts):
        if isinstance(s, (Let, Assign, While)):
            lines.append(c_stmt(s, locals_, space, scope))
        elif i == last and not is_void:
            lines.append(f"return {c_expr(s, locals_, space, scope, expect)};")
        else:                                            # statement — keep its effect, discard value
            lines.append(f"{c_expr(s, locals_, space, scope)};")
    if not is_void and (not stmts or isinstance(stmts[-1], (Let, Assign, While))):
        lines.append("return 0;")                        # non-void body ending without a value expr
    return " ".join(lines)


def c_stmt(s, locals_, space, scope) -> str:
    """One statement (mutates `locals_` for a let)."""
    if isinstance(s, Let):
        t = infer(s.value, locals_, space, scope)
        locals_[s.name] = t
        return f"{c_type(t)} {s.name} = {c_expr(s.value, locals_, space, scope)};"
    if isinstance(s, Assign):
        return f"{c_expr(s.target, locals_, space, scope)} = {c_expr(s.value, locals_, space, scope)};"
    if isinstance(s, While):
        bl = dict(locals_)                               # loop body has its own scope
        body = " ".join(c_stmt(x, bl, space, scope) if isinstance(x, (Let, Assign, While))
                        else f"{c_expr(x, bl, space, scope)};" for x in s.body)
        return f"while ({c_expr(s.cond, locals_, space, scope)}) {{ {body} }}"
    return f"{c_expr(s, locals_, space, scope)};"


def c_def(qual, d: Fn, space, scope, cname=None) -> str:
    locals_ = {p.name: p.type for p in d.params}
    body = c_block(d.body, locals_, space, scope, d.ret) if d.body else "return 0;"
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)}) {{ {body} }}"
