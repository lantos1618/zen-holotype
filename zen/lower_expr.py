"""Expression + statement C lowering: `c_expr`, the intrinsic ops, closure
inlining, match lowering, and the statement/block transcription.

Layered on the type-erasure leaf (lower_type.py) and the checker (types.py). The
declaration entry points (c_struct/c_enum/c_proto/c_def) live in lower.py and call
into `c_block` here — the dependency runs one way (decls -> expr/stmt -> types),
so the split is acyclic.
"""
from __future__ import annotations
from .ast import (Prim, PrimT, NameT, PtrT, SliceT, FnT, Fn,
                  Lit, Bool, Str, Var, Field, Bin, Not, Call, MethodCall, StructLit, SliceLit, Index,
                  Let, Assign, While, EnumCtor, Match, Closure)
from .types import infer, subst, solve_call, match_type, struct_at, TraitMethod
from .resolve import _mentions, resolve_type   # _mentions: arm-body payload use; resolve_type: sizeof(T)
from .lower_type import (_c_str, _uid, _tmp, c_name, c_type, mangle, inst_name,  # noqa: F401
                         impl_cname, is_template)


# ───────────────────────── expression codegen ──────────────────────────────
def c_expr(e, locals_, namespace, scope, expect=None) -> str:
    match e:
        case Lit(n):
            return str(n)
        case Bool(b):
            return "true" if b else "false"
        case Str(s):                                     # a `str` literal -> a C string literal
            return f'"{_c_str(s)}"'                      # re-escape so special chars stay valid C
        case Var(name):
            return name
        case Bin(op, l, r):
            return f"({c_expr(l, locals_, namespace, scope)} {op} {c_expr(r, locals_, namespace, scope)})"
        case Not(operand):
            return f"(!{c_expr(operand, locals_, namespace, scope)})"
        case Field(obj, name):
            sep = "->" if isinstance(infer(obj, locals_, namespace, scope), PtrT) else "."
            return f"{c_expr(obj, locals_, namespace, scope)}{sep}{name}"   # pointer access -> ->
        case StructLit():
            st = infer(e, locals_, namespace, scope)                # NameT(qual, targs)
            decl = namespace.walk(st.path).value
            sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
            ftypes = {fl.name: subst(fl.type, sub) for fl in decl.fields}
            inits = ", ".join(f".{n} = {c_expr(v, locals_, namespace, scope, ftypes[n])}"
                              for n, v in e.fields)
            return f"({c_type(st)}){{ {inits} }}"               # C99 compound literal
        case EnumCtor():
            decl = namespace.walk(expect.path).value                # expect names the enum (+ its args)
            cn = c_type(expect)                                 # mangled instance name if generic
            sub = dict(zip(decl.tparams, expect.args))
            var = next(v for v in decl.variants if v.name == e.name)
            if var.payload is None:
                return f"({cn}){{ .tag = {cn}_{e.name} }}"
            inner = c_expr(e.args[0], locals_, namespace, scope, subst(var.payload, sub))
            return f"({cn}){{ .tag = {cn}_{e.name}, .u.{e.name} = {inner} }}"
        case Match():
            return c_match(e, locals_, namespace, scope, expect)
        case SliceLit(elems):                                # [a,b,c] : a (ptr,len) view
            st = infer(e, locals_, namespace, scope, expect)     # SliceT(elem)
            et = c_type(st.elem)
            arr = (f"({et}[]){{ {', '.join(c_expr(x, locals_, namespace, scope, st.elem) for x in elems)} }}"
                   if elems else f"({et}*)0")
            return f"({c_type(st)}){{ .ptr = {arr}, .len = {len(elems)} }}"
        case Index(seq, idx):                                # xs[i] -> xs.ptr[i]
            st = infer(seq, locals_, namespace, scope)
            sx = c_expr(seq, locals_, namespace, scope)
            ix = c_expr(idx, locals_, namespace, scope)
            if isinstance(st, SliceT):
                return f"{sx}.ptr[{ix}]"
            tp, ty, _ = struct_at(st, namespace)                 # []-overloading: dispatch to `at`
            recv = sx if isinstance(st, PtrT) else f"&({sx})"  # `at` takes Ptr<Self>
            return f"{impl_cname(tp, ty, 'at')}({recv}, {ix})"
        case Call():
            return _c_call(e, locals_, namespace, scope, expect)
        case MethodCall(recv, method, args):
            if method in ("break", "continue"):              # loop handle control
                return method                                # `h.break();` -> `break;`
            call = Call(method, (recv,) + tuple(args), getattr(e, "pos", None))  # UFCS: x.f(a) == f(x, a)
            return _c_call(call, locals_, namespace, scope, expect)
        case Closure():
            raise TypeError("a closure may only be passed to a closure parameter (it is inlined there)")
        case _:
            raise TypeError(f"no C lowering for {e!r} — an unknown expression node reached codegen")


# ── closures: an inline template + a per-site closure environment ────────────
# A template (fn with FnT params) is never a C function. Each call lowers to a GNU
# statement-expression `({ … })` splicing the body: value params bound to the arg
# exprs, calls to a closure param inlined as nested `({ … })`. Every binding goes
# through a fresh temp first (`T _v = (arg); T name = _v;`) so an arg that mentions
# `name` reads the OUTER value, never the half-initialised inner one (C self-init).
# Captures stay bare Vars and resolve in the caller scope, where the whole thing
# sits — so they read AND mutate exactly as written. _CENV is the active closure
# params; non-reentrant (v1 forbids a template calling a template).
_CENV: dict = {}
_MISSING = object()


def _c_inline_body(stmts, locals_, namespace, scope, ret) -> str:
    """Lower a body as the inside of a statement-expression: the final expression
    is the produced VALUE (a bare `expr;`, not a `return`)."""
    locals_ = dict(locals_)
    is_void = isinstance(ret, PrimT) and ret.prim is Prim.VOID
    out, last = [], len(stmts) - 1
    for i, s in enumerate(stmts):
        if isinstance(s, (Let, Assign, While)):
            out.append(c_stmt(s, locals_, namespace, scope))
        elif isinstance(s, Match) and not (i == last and not is_void):
            out.append(c_match_stmt(s, locals_, namespace, scope))
        elif i == last and not is_void:
            out.append(f"{c_expr(s, locals_, namespace, scope, ret)};")
        else:
            out.append(f"{c_expr(s, locals_, namespace, scope)};")
    return " ".join(out)


def _bindings(e, names_types_args, locals_, namespace, scope) -> str:
    """`T _v0 = (arg0); T name0 = _v0; …` — temp-first so a self-named arg is safe."""
    pre, binds = [], []
    for i, (name, pt, arg) in enumerate(names_types_args):
        ct, u = c_type(pt), _tmp(e, i)
        pre.append(f"{ct} {u} = ({c_expr(arg, locals_, namespace, scope, pt)});")
        binds.append(f"{ct} {name} = {u};")
    return " ".join(pre + binds)


def _c_inline_template(e, tmpl, locals_, namespace, scope) -> str:
    s: dict = {}
    for a, p in zip(e.args, tmpl.params):                 # solve type-args from the value args
        if not isinstance(p.type, FnT):
            match_type(p.type, infer(a, locals_, namespace, scope), s)
    binds, blocals, frame = [], dict(locals_), {}
    for a, p in zip(e.args, tmpl.params):
        if isinstance(p.type, FnT):                       # closure arg: record for its calls
            fnt = subst(p.type, s)
            frame[p.name] = (a, fnt, locals_, scope)
            blocals[p.name] = fnt                         # so infer() can type `f(…)` in the body
        else:
            pt = subst(p.type, s)
            binds.append((p.name, pt, a))
            blocals[p.name] = pt
    head = _bindings(e, binds, locals_, namespace, scope)
    saved = {k: _CENV.get(k, _MISSING) for k in frame}
    _CENV.update(frame)
    try:
        body = _c_inline_body(tmpl.body, blocals, namespace, tmpl.scope or scope, subst(tmpl.ret, s))
    finally:
        for k, v in saved.items():
            _CENV.pop(k, None) if v is _MISSING else _CENV.__setitem__(k, v)
    return f"({{ {head} {body} }})"


def _c_inline_closure(e, locals_, namespace, scope) -> str:
    clos, fnt, csite_locals, csite_scope = _CENV[e.callee]
    cl = dict(csite_locals)                               # the closure body sees its capture site…
    binds = []
    for a, pname, pt in zip(e.args, clos.params, fnt.params):
        binds.append((pname, pt, a))                      # …args lowered in the CURRENT (template) scope
        cl[pname] = pt
    head = _bindings(e, [(n, t, a) for n, t, a in binds], locals_, namespace, scope)
    body = _c_inline_body(clos.body, cl, namespace, csite_scope, fnt.ret)
    return f"({{ {head} {body} }})"


def _c_call(e, locals_, namespace, scope, expect=None) -> str:
    if e.callee == "addr":
        return f"&({c_expr(e.args[0], locals_, namespace, scope)})"
    if e.callee in ("load", "store", "offset"):           # raw memory ops erase to C
        a = [c_expr(x, locals_, namespace, scope) for x in e.args]
        if e.callee == "load":
            return f"(*({a[0]}))"
        if e.callee == "store":
            return f"(*({a[0]}) = {a[1]})"
        return f"(({a[0]}) + ({a[1]}))"                    # offset
    if e.callee == "cstr":                                # cstr(p) -> reinterpret a byte ptr as const char*
        return f"((const char*)({c_expr(e.args[0], locals_, namespace, scope)}))"
    if e.callee == "sizeof":                              # sizeof(T) -> C sizeof of the named type
        ty = resolve_type(NameT(e.args[0].name), scope, namespace)
        return f"sizeof({c_type(ty)})"
    if e.callee == "slice":                               # slice(ptr, len) -> a [T] view (T = expect)
        styp = c_type(expect)                             # "slice_T" (also registers the typedef)
        ct = c_type(expect.elem)
        p = c_expr(e.args[0], locals_, namespace, scope)
        n = c_expr(e.args[1], locals_, namespace, scope)
        return f"({styp}){{ .ptr = ({ct}*)({p}), .len = ({n}) }}"
    if e.callee in _CENV:                                  # calling a closure param -> inline it
        return _c_inline_closure(e, locals_, namespace, scope)
    target = scope.get(e.callee)
    if isinstance(target, TraitMethod):                 # resolve to the concrete impl fn
        s: dict = {}
        for p, a in zip(target.sig.params, e.args):
            match_type(p, infer(a, locals_, namespace, scope), s)
        cn = impl_cname(target.trait, s["Self"].path, e.callee)
        ptypes = [subst(p, {"Self": s["Self"]}) for p in target.sig.params]
    else:
        callee = namespace.walk(target).value
        assert isinstance(callee, Fn)                   # a callee path always names a function
        if is_template(callee):                         # a closure-taking fn -> inline it here
            return _c_inline_template(e, callee, locals_, namespace, scope)
        if callee.tparams:                              # generic: name the monomorphized instance
            s = solve_call(callee, [infer(a, locals_, namespace, scope) for a in e.args])
            cn = inst_name(target, tuple(s[n] for n in callee.tparams))
            ptypes = [subst(p.type, s) for p in callee.params]
        else:
            cn = callee.name if callee.extern else c_name(target)   # extern → bare C symbol
            ptypes = [p.type for p in callee.params]
    args = ", ".join(c_expr(a, locals_, namespace, scope, pt) for a, pt in zip(e.args, ptypes))
    return f"{cn}({args})"


# ───────────────────────── match codegen ───────────────────────────────────
def _bind_subj(ty, t, subj, chain, expr) -> str:
    """Bind the match subject to a temp once (so a side-effecting subject runs exactly
    once), then the arm tests reference the temp. If NO arm references it — a lone `_`
    wildcard, e.g. `n.match { _ => 42 }` — add `(void)t;` so the still-evaluated subject
    doesn't trip -Werror=unused-variable. The temp is referenced as `t.` (enum tag /
    payload) or `t ==` (literal), and a temp name is never a prefix of another at such a
    boundary, so the substring test is collision-safe across nested matches."""
    used = (f"{t}." in chain) or (f"{t}->" in chain) or (f"{t} ==" in chain)
    guard = "" if used else f"(void){t}; "
    return f"({{ {ty} {t} = {subj}; {guard}{chain}; }})" if expr \
        else f"{{ {ty} {t} = {subj}; {guard}{chain} }}"


def c_match(e, locals_, namespace, scope, expect) -> str:
    """Lower a match to a tag-tested ternary chain. A variant with a payload
    binding uses a statement-expression `({ T b = subj.u.V; body; })` so the
    binding is a real typed local (this narrows the payload inside the arm)."""
    # The subject is bound to a temp ONCE, then the arm tests reference the temp —
    # so a subject with side effects (e.g. a call) is evaluated exactly once, not
    # per arm. A catch-all is guaranteed last (the checker rejects unreachable
    # arms), so the final arm is the ternary's else.
    subj = c_expr(e.subject, locals_, namespace, scope)
    st = infer(e.subject, locals_, namespace, scope)
    t = f"_subj{_uid(e)}"                                # unique per match node (nesting-safe)
    ptr = isinstance(st, PtrT) and isinstance(st.pointee, NameT)   # match auto-derefs Ptr<Enum>
    mt = st.pointee if ptr else st                      # the matched type; `sep` reaches members
    sep = "->" if ptr else "."

    if isinstance(mt, PrimT):                           # literal match: t == lit ? … : …
        body = lambda arm: f"({c_expr(arm.body, locals_, namespace, scope, expect)})"
        default = next((a for a in e.arms if a.lit is None), None) or e.arms[-1]
        chain = body(default)
        for arm in reversed([a for a in e.arms if a is not default]):
            litc = c_expr(arm.lit, locals_, namespace, scope)
            chain = f"({t} == {litc} ? {body(arm)} : {chain})"
        return _bind_subj(c_type(st), t, subj, chain, expr=True)

    decl = namespace.walk(mt.path).value
    sub = dict(zip(decl.tparams, mt.args)) if decl.tparams else {}
    cn = c_type(mt)                                     # mangled instance name if a generic enum
    variants = {v.name: v for v in decl.variants}

    def clause(arm):
        if arm.variant is not None and arm.binding is not None and _mentions(arm.body, arm.binding):
            pt = c_type(subst(variants[arm.variant].payload, sub))
            al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            return (f"({{ {pt} {arm.binding} = {t}{sep}u.{arm.variant}; "
                    f"{c_expr(arm.body, al, namespace, scope, expect)}; }})")
        return f"({c_expr(arm.body, locals_, namespace, scope, expect)})"  # no binding / unused payload

    default = next((a for a in e.arms if a.variant is None), None) or e.arms[-1]
    chain = clause(default)
    for arm in reversed([a for a in e.arms if a is not default]):
        chain = f"({t}{sep}tag == {cn}_{arm.variant} ? {clause(arm)} : {chain})"
    return _bind_subj(c_type(st), t, subj, chain, expr=True)


def c_match_stmt(e, locals_, namespace, scope) -> str:
    """Lower a match used as a STATEMENT (for effect, not value) to an if/else
    chain, so arm bodies may be statements — `h.break()`, `h.continue()`, an
    assignment — which a ternary can't hold."""
    subj = c_expr(e.subject, locals_, namespace, scope)
    st = infer(e.subject, locals_, namespace, scope)
    t = f"_subj{_uid(e)}"
    ptr = isinstance(st, PtrT) and isinstance(st.pointee, NameT)   # match auto-derefs Ptr<Enum>
    mt = st.pointee if ptr else st
    sep = "->" if ptr else "."
    arm_stmt = lambda a, al: (c_match_stmt(a.body, al, namespace, scope) if isinstance(a.body, Match)
                              else f"{c_expr(a.body, al, namespace, scope)};")

    if isinstance(mt, PrimT):                            # literal match
        default = next((a for a in e.arms if a.lit is None), None)
        clauses = [f"if ({t} == {c_expr(a.lit, locals_, namespace, scope)}) {{ {arm_stmt(a, locals_)} }}"
                   for a in e.arms if a is not default]
        chain = " else ".join(clauses)
        if default is not None:
            chain += (f" else {{ {arm_stmt(default, locals_)} }}" if clauses
                      else f"{{ {arm_stmt(default, locals_)} }}")
        return _bind_subj(c_type(st), t, subj, chain, expr=False)

    decl = namespace.walk(mt.path).value
    sub = dict(zip(decl.tparams, mt.args)) if decl.tparams else {}
    cn = c_type(mt)
    variants = {v.name: v for v in decl.variants}
    default = next((a for a in e.arms if a.variant is None), None)
    clauses = []
    for a in e.arms:
        if a is default:
            continue
        al, bind = locals_, ""
        if a.binding is not None and _mentions(a.body, a.binding):   # skip an unused payload binding
            pt = c_type(subst(variants[a.variant].payload, sub))
            al = {**locals_, a.binding: subst(variants[a.variant].payload, sub)}
            bind = f"{pt} {a.binding} = {t}{sep}u.{a.variant}; "
        clauses.append(f"if ({t}{sep}tag == {cn}_{a.variant}) {{ {bind}{arm_stmt(a, al)} }}")
    chain = " else ".join(clauses)
    if default is not None:
        chain += (f" else {{ {arm_stmt(default, locals_)} }}" if clauses
                  else f"{{ {arm_stmt(default, locals_)} }}")
    return _bind_subj(c_type(st), t, subj, chain, expr=False)


# ───────────────────────── statement / block codegen ───────────────────────
def _loop_index(s, nxt):
    """If `s` is `idx := 0` and `nxt` is the While that steps idx (a desugared counting
    loop), return idx — so the index can be scoped to the C `for`, not the block (two
    loops in one block must not collide on the index variable)."""
    if (isinstance(s, Let) and isinstance(s.value, Lit) and s.value.n == 0
            and isinstance(nxt, While) and isinstance(nxt.step, Assign)
            and isinstance(nxt.step.target, Var) and nxt.step.target.name == s.name):
        return s.name
    return None


def c_block(stmts, locals_, namespace, scope, expect=None) -> str:
    """Lower a statement list: each `x := v` becomes a typed C local; the final
    expression statement becomes the `return` (and gets the expected type)."""
    locals_ = dict(locals_)
    is_void = isinstance(expect, PrimT) and expect.prim is Prim.VOID
    lines, last, i = [], len(stmts) - 1, 0
    while i < len(stmts):
        s = stmts[i]
        idx = _loop_index(s, stmts[i + 1]) if i < last else None
        if idx is not None:                              # fuse `idx:=0` + While -> for(idx scoped)
            locals_[idx] = infer(s.value, locals_, namespace, scope)
            lines.append(_c_for(stmts[i + 1], idx, locals_, namespace, scope))
            i += 2; continue
        if isinstance(s, (Let, Assign, While)):
            lines.append(c_stmt(s, locals_, namespace, scope))
        elif i == last and not is_void:
            lines.append(f"return {c_expr(s, locals_, namespace, scope, expect)};")
        elif isinstance(s, Match):                       # match for effect -> if/else statement
            lines.append(c_match_stmt(s, locals_, namespace, scope))
        else:                                            # statement — keep its effect, discard value
            lines.append(f"{c_expr(s, locals_, namespace, scope)};")
        i += 1
    if not is_void and (not stmts or isinstance(stmts[-1], (Let, Assign, While))):
        lines.append("return 0;")                        # non-void body ending without a value expr
    return " ".join(lines)


def _c_for(w, idx, locals_, namespace, scope) -> str:
    """A desugared counting loop -> a C `for` with its index scoped to the loop:
    `for (int32_t idx = 0; cond; step) { body }`."""
    bl = dict(locals_)
    body = " ".join(c_stmt(x, bl, namespace, scope) if isinstance(x, (Let, Assign, While, Match))
                    else f"{c_expr(x, bl, namespace, scope)};" for x in w.body)
    cond = c_expr(w.cond, locals_, namespace, scope)
    step = c_stmt(w.step, locals_, namespace, scope).rstrip(";")
    return f"for ({c_type(locals_[idx])} {idx} = 0; {cond}; {step}) {{ {body} }}"


def c_stmt(s, locals_, namespace, scope) -> str:
    """One statement (mutates `locals_` for a let)."""
    if isinstance(s, Let):
        t = infer(s.value, locals_, namespace, scope)
        locals_[s.name] = t
        return f"{c_type(t)} {s.name} = {c_expr(s.value, locals_, namespace, scope)};"
    if isinstance(s, Assign):
        return f"{c_expr(s.target, locals_, namespace, scope)} = {c_expr(s.value, locals_, namespace, scope)};"
    if isinstance(s, Match):                             # a match used as a statement
        return c_match_stmt(s, locals_, namespace, scope)
    if isinstance(s, While):
        bl = dict(locals_)                               # loop body has its own scope
        body = " ".join(c_stmt(x, bl, namespace, scope) if isinstance(x, (Let, Assign, While, Match))
                        else f"{c_expr(x, bl, namespace, scope)};" for x in s.body)
        cond = c_expr(s.cond, locals_, namespace, scope)
        # the structured loop primitive → a C `for` (the step slot makes `continue`
        # correct and keeps it a counted loop the C compiler can auto-vectorize).
        step = c_stmt(s.step, locals_, namespace, scope).rstrip(";") if s.step is not None else ""
        return f"for (; {cond}; {step}) {{ {body} }}"
    return f"{c_expr(s, locals_, namespace, scope)};"
