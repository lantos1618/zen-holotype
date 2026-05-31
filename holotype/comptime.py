"""Compile-time evaluation (comptime) — a small interpreter over the AST.

The hinge: run pure functions at *compile time* and fold the result into the
program. `comptime(expr)` evaluates `expr` now and emits its constant — no
runtime call survives. This is the engine; the reified-AST self-hosting
(impl/derive as `(Ast) Ast`) will be built on top of it.

Values: int, bool, dict (a struct), or ("@enum", variant, payload).
"""
from __future__ import annotations
from .ast import Lit, Bool, Var, Not, Bin, Field, Call, Match, StructLit, EnumCtor, Let, Fn

_FUEL = 200_000               # recursion/step budget — turns a comptime ∞-loop into an error
_RUNTIME = {"addr", "load", "store", "offset", "comptime"}


class ComptimeErr(Exception):
    ...


def evaluate(e, space, scope):
    """Evaluate `e` to a compile-time value. Used by codegen for comptime(...)."""
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


def _call(e, env, space, scope, fuel):
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
