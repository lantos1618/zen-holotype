"""Compile-time evaluation (comptime) — a small interpreter over the AST.

The hinge: run pure functions at *compile time* and fold the result into the
program. `comptime(expr)` evaluates `expr` now and emits its constant — no
runtime call survives. This is the engine; the reified-AST self-hosting
(impl/derive as `(Ast) Ast`) will be built on top of it.

Values: int, bool, dict (a struct), or ("@enum", variant, payload).
"""
from __future__ import annotations
from dataclasses import replace
from .ast import (Lit, Bool, Var, Not, Bin, Field, Call, Match, StructLit, EnumCtor,
                  MethodCall, Let, Assign, While, Arm, Str, Fn, Param, Impl, Struct, EnumDecl,
                  TraitDecl, Prim, PrimT, NameT, PtrT, Dir)

_FUEL = 200_000               # recursion/step budget — turns a comptime ∞-loop into an error
_RUNTIME = {"addr", "load", "store", "offset", "comptime"}


class ComptimeErr(Exception):
    ...


# ───────────────────────── the dedicated comptime pass ──────────────────────
# A first-class run, after resolve and before check: walk every function body
# and rewrite each `comptime(e)` node into the constant it evaluates to. The
# checker and the lowerer therefore never see a comptime node — they only ever
# meet plain literals. This is the hinge P4 builds on: once comptime is a pass
# that *rewrites the AST*, it can grow to evaluate functions that return AST
# (derive/impl as `(Ast) Ast`), and the new nodes flow into check unchanged.
def fold_comptime(files, space):
    """Rewrite every comptime(...) in every body to its constant, in place."""
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and d.body is not None and not d.extern:
                d.body = [_fold(s, space, d.scope) for s in d.body]
            elif isinstance(d, Impl):
                for m in d.methods:
                    if m.body is not None:
                        m.body = [_fold(s, space, m.scope) for s in m.body]


def _to_node(v, pos):
    """Turn a comptime value back into a literal expression node."""
    if isinstance(v, bool):
        return Bool(v, pos)
    if isinstance(v, int):
        return Lit(v, pos)
    raise ComptimeErr(f"comptime value {v!r} cannot be folded into a literal yet")


def _fold(e, space, scope):
    """Recurse an expr/stmt, replacing comptime(x) with its folded constant."""
    if isinstance(e, Call) and e.callee == "comptime":
        return _to_node(evaluate(e.args[0], space, scope), e.pos)
    if isinstance(e, Call):
        return replace(e, args=tuple(_fold(a, space, scope) for a in e.args))
    if isinstance(e, Bin):
        return replace(e, l=_fold(e.l, space, scope), r=_fold(e.r, space, scope))
    if isinstance(e, Not):
        return replace(e, operand=_fold(e.operand, space, scope))
    if isinstance(e, Field):
        return replace(e, obj=_fold(e.obj, space, scope))
    if isinstance(e, StructLit):
        return replace(e, fields=tuple((n, _fold(v, space, scope)) for n, v in e.fields))
    if isinstance(e, EnumCtor):
        return replace(e, args=tuple(_fold(a, space, scope) for a in e.args))
    if isinstance(e, MethodCall):
        return replace(e, recv=_fold(e.recv, space, scope),
                       args=tuple(_fold(a, space, scope) for a in e.args))
    if isinstance(e, Match):
        arms = tuple(replace(a, body=_fold(a.body, space, scope)) for a in e.arms)
        return replace(e, subject=_fold(e.subject, space, scope), arms=arms)
    if isinstance(e, Let):
        return replace(e, value=_fold(e.value, space, scope))
    if isinstance(e, Assign):
        return replace(e, target=_fold(e.target, space, scope),
                       value=_fold(e.value, space, scope))
    if isinstance(e, While):
        return replace(e, cond=_fold(e.cond, space, scope),
                       body=tuple(_fold(s, space, scope) for s in e.body))
    return e                                  # Lit / Bool / Var / Str — nothing to fold


def evaluate(e, space, scope):
    """Evaluate `e` to a compile-time value (int/bool/struct/enum)."""
    try:
        return _eval(e, {}, space, scope, [_FUEL])
    except RecursionError:                   # deep comptime recursion → a clean error, not a crash
        raise ComptimeErr("comptime recursion too deep (infinite recursion?)")


def _eval(e, env, space, scope, fuel):
    fuel[0] -= 1
    if fuel[0] <= 0:
        raise ComptimeErr("comptime ran too long (infinite recursion?)")
    if isinstance(e, Lit):
        return e.n
    if isinstance(e, Bool):
        return e.b
    if isinstance(e, Str):
        return e.s
    if isinstance(e, Var):
        if e.name not in env:
            raise ComptimeErr(f"comptime: unbound '{e.name}'")
        return env[e.name]
    if isinstance(e, Not):
        return not _eval(e.operand, env, space, scope, fuel)
    if isinstance(e, Bin):
        return _binop(e.op, _eval(e.l, env, space, scope, fuel),
                      _eval(e.r, env, space, scope, fuel))
    if isinstance(e, Field):
        obj = _eval(e.obj, env, space, scope, fuel)
        if not isinstance(obj, dict):
            raise ComptimeErr("comptime: field access on a non-struct")
        return obj[e.name]
    if isinstance(e, StructLit):
        return {n: _eval(v, env, space, scope, fuel) for n, v in e.fields}
    if isinstance(e, EnumCtor):
        pay = _eval(e.args[0], env, space, scope, fuel) if e.args else None
        return ("@enum", e.name, pay)
    if isinstance(e, Match):
        return _match(e, env, space, scope, fuel)
    if isinstance(e, Call):
        return _call(e, env, space, scope, fuel)
    raise ComptimeErr(f"comptime: can't evaluate {type(e).__name__}")


def _binop(op, l, r):
    import operator as o
    return {"+": o.add, "-": o.sub, "*": o.mul, "==": o.eq, "<": o.lt, ">": o.gt,
            "<=": o.le, ">=": o.ge, "&&": lambda a, b: a and b,
            "||": lambda a, b: a or b}[op](l, r)


# ───────────────────────── the host reflection kernel ───────────────────────
# All the host gives a derive is the ability to *read* a type's structure. The
# Ast it *builds* is defined in Zen (prelude/derive.zen); the host only reifies
# that value back into a real declaration (see reify_decl below). (VISION 4.)
def _resolve_named(arg, scope, space, what):
    """A bare-name argument (reflect(Point) / reflect_trait(Show)) -> its decl."""
    if not isinstance(arg, Var):
        raise ComptimeErr(f"{what} expects a bare name, e.g. {what}(Foo)")
    try:
        return space.walk(scope.get(arg.name, arg.name)).value
    except Exception:
        raise ComptimeErr(f"{what}: no such name '{arg.name}'")


def _bi_reflect(e, env, space, scope, fuel):
    node = _resolve_named(e.args[0], scope, space, "reflect")
    if not isinstance(node, (Struct, EnumDecl)):
        raise ComptimeErr(f"reflect: '{e.args[0].name}' is not a type")
    return node


def _bi_reflect_trait(e, env, space, scope, fuel):
    node = _resolve_named(e.args[0], scope, space, "reflect_trait")
    if not isinstance(node, TraitDecl):
        raise ComptimeErr(f"reflect_trait: '{e.args[0].name}' is not a trait")
    return node


def _bi_trait_method_name(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    if not isinstance(t, TraitDecl):
        raise ComptimeErr("trait_method_name: argument is not a trait")
    return t.methods[0].name                     # single-method traits, for now


def _bi_name_of(e, env, space, scope, fuel):
    return _eval(e.args[0], env, space, scope, fuel).name


def _bi_field_count(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    if isinstance(t, Struct):
        return len(t.fields)
    if isinstance(t, EnumDecl):
        return len(t.variants)
    raise ComptimeErr("field_count: argument is not a type")


def _bi_field_name_at(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    i = _eval(e.args[1], env, space, scope, fuel)
    if not isinstance(t, Struct):
        raise ComptimeErr("field_name_at: argument is not a struct")
    return t.fields[i].name


def _bi_variant_count(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    if not isinstance(t, EnumDecl):
        raise ComptimeErr("variant_count: argument is not an enum")
    return len(t.variants)


def _bi_variant_name_at(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    i = _eval(e.args[1], env, space, scope, fuel)
    if not isinstance(t, EnumDecl):
        raise ComptimeErr("variant_name_at: argument is not an enum")
    return t.variants[i].name


def _bi_variant_has_payload(e, env, space, scope, fuel):
    t = _eval(e.args[0], env, space, scope, fuel)
    i = _eval(e.args[1], env, space, scope, fuel)
    if not isinstance(t, EnumDecl):
        raise ComptimeErr("variant_has_payload: argument is not an enum")
    return t.variants[i].payload is not None


def _bi_concat(e, env, space, scope, fuel):
    return str(_eval(e.args[0], env, space, scope, fuel)) + \
           str(_eval(e.args[1], env, space, scope, fuel))


_BUILTINS = {"reflect": _bi_reflect, "reflect_trait": _bi_reflect_trait,
             "name_of": _bi_name_of, "trait_method_name": _bi_trait_method_name,
             "field_count": _bi_field_count, "field_name_at": _bi_field_name_at,
             "variant_count": _bi_variant_count, "variant_name_at": _bi_variant_name_at,
             "variant_has_payload": _bi_variant_has_payload, "concat": _bi_concat}


# ───────────────────────── reify: Zen Ast value → host AST node ──────────────
# A derive returns a comptime value shaped by prelude/derive.zen: an enum is
# ("@enum", Variant, payload); a struct is a dict. reify_decl walks it back into
# a real ast.py declaration, which then flows through check + lower unchanged.
_PRIMS = {p.value: p for p in Prim}


def _enum(v):
    if not (isinstance(v, tuple) and len(v) == 3 and v[0] == "@enum"):
        raise ComptimeErr(f"reify: expected an Ast value, got {v!r}")
    return v[1], v[2]                            # (variant, payload)


def _flist(v, head_key):
    """Walk a prelude cons-list (?Nil / ?Cons(cell)) into the cells' dicts."""
    out = []
    while True:
        tag, payload = _enum(v)
        if tag.endswith("Nil"):
            return out
        out.append(payload)                      # the cell dict
        v = payload[head_key]                    # its tail


def _reify_type(name):
    return PrimT(_PRIMS[name]) if name in _PRIMS else NameT(name, ())


def reify_expr(v):
    tag, p = _enum(v)
    if tag == "Int":
        return Lit(p)
    if tag == "Boolean":
        return Bool(p)
    if tag == "Var":
        return Var(p)
    if tag == "Field":
        return Field(reify_expr(p["obj"]), p["fld"])
    if tag == "Bin":
        return Bin(p["op"], reify_expr(p["lhs"]), reify_expr(p["rhs"]))
    if tag == "Struct":
        inits = tuple((c["key"], reify_expr(c["val"])) for c in _flist(p["inits"], "tail"))
        return StructLit(p["ty"], inits)
    if tag == "Match":
        arms = tuple(Arm(None if c["tag"] == "_" else c["tag"],   # variant (None = wildcard)
                         c.get("bind") or None,                    # payload binding ("" = none)
                         reify_expr(c["body"]), None)
                     for c in _flist(p["arms"], "tail"))
        return Match(reify_expr(p["subj"]), arms)
    raise ComptimeErr(f"reify: unknown Ast node '{tag}'")


def _reify_func(p):
    params = [Param(c["pnm"], PtrT(Dir.READ, _reify_type(c["pty"])) if c["ptr"]
                    else _reify_type(c["pty"]))
              for c in _flist(p["ps"], "tail")]
    return Fn(p["nm"], params, _reify_type(p["ret"]), body=[reify_expr(p["body"])])


def reify_decl(v):
    tag, p = _enum(v)
    if tag == "Func":                            # a free function
        return _reify_func(p)
    if tag == "Impl":                            # impl Trait for Ty { method }
        return Impl(p["trait"], p["ty"], [_reify_func(p["method"])])
    raise ComptimeErr(f"reify: a derive must return a Decl, got '{tag}'")


def _call(e, env, space, scope, fuel):
    if e.callee in _BUILTINS:                     # reified-AST surface, before everything else
        return _BUILTINS[e.callee](e, env, space, scope, fuel)
    if e.callee in _RUNTIME:
        raise ComptimeErr(f"comptime: '{e.callee}' is a runtime op, not evaluatable")
    target = scope.get(e.callee)
    if target is None:
        raise ComptimeErr(f"comptime: unknown function '{e.callee}'")
    fn = space.walk(target).value
    if not isinstance(fn, Fn) or fn.extern or fn.body is None:
        raise ComptimeErr(f"comptime: '{e.callee}' has no evaluatable body")
    args = [_eval(a, env, space, scope, fuel) for a in e.args]
    fenv = {p.name: v for p, v in zip(fn.params, args)}
    return _block(fn.body, fenv, space, fn.scope, fuel)


def _block(stmts, env, space, scope, fuel):
    env, val = dict(env), None
    for s in stmts:
        if isinstance(s, Let):
            env[s.name] = _eval(s.value, env, space, scope, fuel)
        else:
            val = _eval(s, env, space, scope, fuel)
    return val


def _match(e, env, space, scope, fuel):
    subj = _eval(e.subject, env, space, scope, fuel)
    is_enum = isinstance(subj, tuple) and len(subj) == 3 and subj[0] == "@enum"
    for arm in e.arms:
        if arm.variant is not None:                  # variant pattern
            if is_enum and subj[1] == arm.variant:
                aenv = {**env, arm.binding: subj[2]} if arm.binding else env
                return _eval(arm.body, aenv, space, scope, fuel)
        elif arm.lit is not None:                    # literal pattern
            litv = arm.lit.n if isinstance(arm.lit, Lit) else arm.lit.b
            if subj == litv:
                return _eval(arm.body, env, space, scope, fuel)
        else:                                        # wildcard
            return _eval(arm.body, env, space, scope, fuel)
    raise ComptimeErr("comptime: non-exhaustive match")
