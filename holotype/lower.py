"""Hook-based transcribe to C. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced upstream).
"""
from __future__ import annotations
from .ast import (Dir, Prim, PrimT, NameT, PtrT, Struct, Fn,
                  Lit, Bool, Var, Field, Bin, Call, StructLit, Let)
from .types import infer

_CMAP = {Prim.I32: "int32_t", Prim.I64: "int64_t", Prim.BOOL: "bool", Prim.VOID: "void"}


def c_name(path: str) -> str:
    return path.replace(".", "_")


def c_type(t) -> str:
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
    if isinstance(t, PrimT):
        return t.prim.value
    if isinstance(t, PtrT):
        return f"{t.dir.value}<{show(t.pointee)}>"
    if isinstance(t, NameT):
        seg = t.path.rsplit(".", 1)[-1]
        return f"{seg}<{', '.join(show(a) for a in t.args)}>" if t.args else seg
    return "?"


# ───────────────────────── expression codegen ──────────────────────────────
def c_expr(e, locals_, space, scope) -> str:
    if isinstance(e, Lit):
        return str(e.n)
    if isinstance(e, Bool):
        return "true" if e.b else "false"
    if isinstance(e, Var):
        return e.name
    if isinstance(e, Bin):
        return f"({c_expr(e.l, locals_, space, scope)} {e.op} {c_expr(e.r, locals_, space, scope)})"
    if isinstance(e, Field):
        ot = infer(e.obj, locals_, space, scope)
        sep = "->" if isinstance(ot, PtrT) else "."     # pointer access lowers to ->
        return f"{c_expr(e.obj, locals_, space, scope)}{sep}{e.name}"
    if isinstance(e, StructLit):
        qual = scope.get(e.type, e.type)
        inits = ", ".join(f".{n} = {c_expr(v, locals_, space, scope)}" for n, v in e.fields)
        return f"({c_name(qual)}){{ {inits} }}"                 # C99 compound literal
    if isinstance(e, Call):
        if e.callee == "addr":
            return f"&({c_expr(e.args[0], locals_, space, scope)})"
        cn = c_name(scope[e.callee])
        args = ", ".join(c_expr(a, locals_, space, scope) for a in e.args)
        return f"{cn}({args})"
    return "0"


# ───────────────────────── declaration codegen ─────────────────────────────
def _params(d: Fn) -> str:
    return ", ".join(f"{c_type(p.type)} {p.name}" for p in d.params) or "void"


def c_struct(qual, d: Struct) -> str:
    body = " ".join(f"{c_type(f.type)} {f.name};" for f in d.fields)
    return f"typedef struct {{ {body} }} {c_name(qual)};"


def c_proto(qual, d: Fn) -> str:
    return f"{c_type(d.ret)} {c_name(qual)}({_params(d)});"


def c_block(stmts, locals_, space, scope) -> str:
    """Lower a statement list: each `x := v` becomes a typed C local; the final
    expression statement becomes the `return`."""
    locals_ = dict(locals_)
    lines, ret = [], "0"
    for s in stmts:
        if isinstance(s, Let):
            t = infer(s.value, locals_, space, scope)
            locals_[s.name] = t
            lines.append(f"{c_type(t)} {s.name} = {c_expr(s.value, locals_, space, scope)};")
        else:
            ret = c_expr(s, locals_, space, scope)
    return " ".join(lines + [f"return {ret};"])


def c_def(qual, d: Fn, space, scope) -> str:
    locals_ = {p.name: p.type for p in d.params}
    body = c_block(d.body, locals_, space, scope) if d.body else "return 0;"
    return f"{c_type(d.ret)} {c_name(qual)}({_params(d)}) {{ {body} }}"
