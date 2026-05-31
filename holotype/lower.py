"""Hook-based transcribe to C. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced upstream).
"""
from __future__ import annotations
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, Struct, EnumDecl, Fn,
                  Lit, Bool, Var, Field, Bin, Not, Call, StructLit, Let, EnumCtor, Match)
from .types import infer, subst, solve_call, match_type, TraitMethod

_CMAP = {Prim.I32: "int32_t", Prim.I64: "int64_t", Prim.BOOL: "bool", Prim.VOID: "void"}


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
        return c_name(t.path)
    return "void"


def show(t) -> str:
    """Source-level (pre-erasure) rendering — for diagnostics, not codegen."""
    if isinstance(t, TVar):
        return t.name
    if isinstance(t, PrimT):
        return t.prim.value
    if isinstance(t, PtrT):
        return f"{t.dir.value}<{show(t.pointee)}>"
    if isinstance(t, NameT):
        seg = t.path.rsplit(".", 1)[-1]
        return f"{seg}<{', '.join(show(a) for a in t.args)}>" if t.args else seg
    return "?"


# ───────────────────────── expression codegen ──────────────────────────────
def c_expr(e, locals_, space, scope, expect=None) -> str:
    if isinstance(e, Lit):
        return str(e.n)
    if isinstance(e, Bool):
        return "true" if e.b else "false"
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Bin):
        return f"({c_expr(e.l, locals_, space, scope)} {e.op} {c_expr(e.r, locals_, space, scope)})"
    if isinstance(e, Not):
        return f"(!{c_expr(e.operand, locals_, space, scope)})"
    if isinstance(e, Field):
        ot = infer(e.obj, locals_, space, scope)
        sep = "->" if isinstance(ot, PtrT) else "."     # pointer access lowers to ->
        return f"{c_expr(e.obj, locals_, space, scope)}{sep}{e.name}"
    if isinstance(e, StructLit):
        qual = scope.get(e.type, e.type)
        ftypes = {fl.name: fl.type for fl in space.walk(qual).value.fields}
        inits = ", ".join(f".{n} = {c_expr(v, locals_, space, scope, ftypes[n])}"
                          for n, v in e.fields)
        return f"({c_name(qual)}){{ {inits} }}"                 # C99 compound literal
    if isinstance(e, EnumCtor):
        cn = c_name(expect.path)                        # expect names the enum
        var = next(v for v in space.walk(expect.path).value.variants if v.name == e.name)
        if var.payload is None:
            return f"({cn}){{ .tag = {cn}_{e.name} }}"
        inner = c_expr(e.args[0], locals_, space, scope, var.payload)
        return f"({cn}){{ .tag = {cn}_{e.name}, .u.{e.name} = {inner} }}"
    if isinstance(e, Match):
        return c_match(e, locals_, space, scope, expect)
    if isinstance(e, Call):
        if e.callee == "addr":
            return f"&({c_expr(e.args[0], locals_, space, scope)})"
        target = scope.get(e.callee)
        if isinstance(target, TraitMethod):             # resolve to the concrete impl fn
            s = {}
            for p, a in zip(target.sig.params, e.args):
                match_type(p, infer(a, locals_, space, scope), s)
            cn = impl_cname(target.trait, s["Self"].path, e.callee)
            ptypes = [subst(p, {"Self": s["Self"]}) for p in target.sig.params]
            args = ", ".join(c_expr(a, locals_, space, scope, pt)
                             for a, pt in zip(e.args, ptypes))
            return f"{cn}({args})"
        callee = space.walk(target).value
        if callee.tparams:                              # generic: name the monomorphized instance
            s = solve_call(callee, [infer(a, locals_, space, scope) for a in e.args])
            targs = tuple(s[n] for n in callee.tparams)
            cn = inst_name(scope[e.callee], targs)
            ptypes = [subst(p.type, s) for p in callee.params]
        else:
            cn = c_name(scope[e.callee])
            ptypes = [p.type for p in callee.params]
        args = ", ".join(c_expr(a, locals_, space, scope, pt)
                         for a, pt in zip(e.args, ptypes))
        return f"{cn}({args})"
    return "0"


def c_match(e, locals_, space, scope, expect) -> str:
    """Lower a match to a tag-tested ternary chain. A variant with a payload
    binding uses a statement-expression `({ T b = subj.u.V; body; })` so the
    binding is a real typed local (this narrows the payload inside the arm)."""
    subj = c_expr(e.subject, locals_, space, scope)
    st = infer(e.subject, locals_, space, scope)

    if isinstance(st, PrimT):                           # literal match: subj == lit ? … : …
        body = lambda arm: f"({c_expr(arm.body, locals_, space, scope, expect)})"
        default = next((a for a in e.arms if a.lit is None), None) or e.arms[-1]
        chain = body(default)
        for arm in reversed([a for a in e.arms if a is not default]):
            litc = c_expr(arm.lit, locals_, space, scope)
            chain = f"(({subj}) == {litc} ? {body(arm)} : {chain})"
        return chain

    decl = space.walk(st.path).value
    sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
    cn = c_name(st.path)
    variants = {v.name: v for v in decl.variants}

    def clause(arm):
        if arm.variant is not None and arm.binding is not None:
            pt = c_type(subst(variants[arm.variant].payload, sub))
            al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            return (f"({{ {pt} {arm.binding} = ({subj}).u.{arm.variant}; "
                    f"{c_expr(arm.body, al, space, scope, expect)}; }})")
        return f"({c_expr(arm.body, locals_, space, scope, expect)})"

    # the wildcard arm (or, for an exhaustive match, the last arm) is the else
    default = next((a for a in e.arms if a.variant is None), None) or e.arms[-1]
    chain = clause(default)
    for arm in reversed([a for a in e.arms if a is not default]):
        chain = f"(({subj}).tag == {cn}_{arm.variant} ? {clause(arm)} : {chain})"
    return chain


# ───────────────────────── declaration codegen ─────────────────────────────
def _params(d: Fn) -> str:
    return ", ".join(f"{c_type(p.type)} {p.name}" for p in d.params) or "void"


def c_struct(qual, d: Struct) -> str:
    body = " ".join(f"{c_type(f.type)} {f.name};" for f in d.fields)
    return f"typedef struct {{ {body} }} {c_name(qual)};"


def c_enum(qual, d: EnumDecl) -> str:
    """A tagged union: an int tag plus a union of the payload-carrying variants.
    Tag constants <Enum>_<Variant> take their declaration order (0, 1, 2, …)."""
    cn = c_name(qual)
    members = " ".join(f"{c_type(v.payload)} {v.name};"
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
    lines, ret = [], "0"
    for i, s in enumerate(stmts):
        exp = expect if i == len(stmts) - 1 else None
        if isinstance(s, Let):
            t = infer(s.value, locals_, space, scope)
            locals_[s.name] = t
            lines.append(f"{c_type(t)} {s.name} = {c_expr(s.value, locals_, space, scope)};")
        else:
            ret = c_expr(s, locals_, space, scope, exp)
    return " ".join(lines + [f"return {ret};"])


def c_def(qual, d: Fn, space, scope, cname=None) -> str:
    locals_ = {p.name: p.type for p in d.params}
    body = c_block(d.body, locals_, space, scope, d.ret) if d.body else "return 0;"
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)}) {{ {body} }}"
