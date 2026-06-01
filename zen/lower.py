"""Hook-based transcribe to C. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced upstream).
"""
from __future__ import annotations
from .ast import (Dir, Prim, PrimT, NameT, PtrT, TVar, SliceT, FnT, Struct, EnumDecl, Fn,
                  Lit, Bool, Str, Var, Field, Bin, Not, Call, MethodCall, StructLit, SliceLit, Index,
                  Let, Assign, While, EnumCtor, Match, Closure)
from .types import infer, subst, solve_call, match_type, struct_at, TraitMethod

_CMAP = {Prim.I32: "int32_t", Prim.I64: "int64_t", Prim.U8: "uint8_t",
         Prim.BOOL: "bool", Prim.VOID: "void", Prim.STR: "const char*"}

_slice_reg: dict = {}             # mangle(elem) -> elem type, for emitting slice typedefs
_uid_reg: dict = {}               # id(node) -> stable small int (see _uid)


def _uid(e) -> int:
    """A reproducible, address-free integer name for a node. `id(e)` is a memory
    address — using it for temp/subject names made the emitted C differ run-to-run
    (breaking ccache, reproducible builds, and C diffs). Here we hand out small ints
    in first-encounter order instead: same AST → same traversal → same names. Reset
    per emit_c. AST nodes live for the whole emit, so `id` is never reused under us."""
    return _uid_reg.setdefault(id(e), len(_uid_reg))


def slice_typedefs() -> list:
    """`typedef struct { T* ptr; int64_t len; } slice_<T>;` for each slice used.
    Nested elem types register first (c_type recurses), so this is dependency-ordered."""
    return [f"typedef struct {{ {c_type(elem)} * ptr; int64_t len; }} slice_{nm};"
            for nm, elem in list(_slice_reg.items())]


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
    if isinstance(t, SliceT):
        return "slice_" + mangle(t.elem)
    return "x"


def inst_name(qual, targs) -> str:
    """The mangled C name of a generic instance: <fn>_<arg1>_<arg2>…"""
    return c_name(qual) + "_" + "_".join(mangle(t) for t in targs)


def impl_cname(trait_path, type_path, method) -> str:
    """The mangled C name of a trait method's concrete impl: impl_<Trait>_<Type>_<m>."""
    return f"impl_{c_name(trait_path)}_{c_name(type_path)}_{method}"


def is_template(d) -> bool:
    """A function with a closure (FnT) parameter — never a standalone C function;
    inlined at each call site (see _c_inline_template)."""
    return isinstance(d, Fn) and any(isinstance(p.type, FnT) for p in d.params)


def c_type(t) -> str:
    if isinstance(t, FnT):
        raise TypeError("a closure type has no C representation — it is always inlined")
    if isinstance(t, TVar):
        raise TypeError(f"un-monomorphized type variable {t.name} reached codegen")
    if isinstance(t, PrimT):
        return _CMAP[t.prim]
    if isinstance(t, SliceT):
        c_type(t.elem)                          # recurse first: registers nested slices
        _slice_reg[mangle(t.elem)] = t.elem     # key = mangle(elem); typedef = slice_<key>
        return "slice_" + mangle(t.elem)
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
        case Str(s):                                     # a `str` literal -> a C string literal
            return f'"{s}"'
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
        case SliceLit(elems):                                # [a,b,c] : a (ptr,len) view
            st = infer(e, locals_, space, scope, expect)     # SliceT(elem)
            et = c_type(st.elem)
            arr = (f"({et}[]){{ {', '.join(c_expr(x, locals_, space, scope, st.elem) for x in elems)} }}"
                   if elems else f"({et}*)0")
            return f"({c_type(st)}){{ .ptr = {arr}, .len = {len(elems)} }}"
        case Index(seq, idx):                                # xs[i] -> xs.ptr[i]
            st = infer(seq, locals_, space, scope)
            sx = c_expr(seq, locals_, space, scope)
            ix = c_expr(idx, locals_, space, scope)
            if isinstance(st, SliceT):
                return f"{sx}.ptr[{ix}]"
            tp, ty, _ = struct_at(st, space)                 # []-overloading: dispatch to `at`
            recv = sx if isinstance(st, PtrT) else f"&({sx})"  # `at` takes Ptr<Self>
            return f"{impl_cname(tp, ty, 'at')}({recv}, {ix})"
        case Call():
            return _c_call(e, locals_, space, scope, expect)
        case MethodCall(recv, method, args):                 # loop handle control
            if method in ("break", "continue"):
                return method                                # `h.break();` -> `break;`
            return "0"
        case Closure():
            raise TypeError("a closure may only be passed to a closure parameter (it is inlined there)")
        case _:
            return "0"


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


def _tmp(e, i) -> str:
    return f"_v{_uid(e)}_{i}"


def _c_inline_body(stmts, locals_, space, scope, ret) -> str:
    """Lower a body as the inside of a statement-expression: the final expression
    is the produced VALUE (a bare `expr;`, not a `return`)."""
    locals_ = dict(locals_)
    is_void = isinstance(ret, PrimT) and ret.prim is Prim.VOID
    out, last = [], len(stmts) - 1
    for i, s in enumerate(stmts):
        if isinstance(s, (Let, Assign, While)):
            out.append(c_stmt(s, locals_, space, scope))
        elif isinstance(s, Match) and not (i == last and not is_void):
            out.append(c_match_stmt(s, locals_, space, scope))
        elif i == last and not is_void:
            out.append(f"{c_expr(s, locals_, space, scope, ret)};")
        else:
            out.append(f"{c_expr(s, locals_, space, scope)};")
    return " ".join(out)


def _bindings(e, names_types_args, locals_, space, scope) -> str:
    """`T _v0 = (arg0); T name0 = _v0; …` — temp-first so a self-named arg is safe."""
    pre, binds = [], []
    for i, (name, pt, arg) in enumerate(names_types_args):
        ct, u = c_type(pt), _tmp(e, i)
        pre.append(f"{ct} {u} = ({c_expr(arg, locals_, space, scope, pt)});")
        binds.append(f"{ct} {name} = {u};")
    return " ".join(pre + binds)


def _c_inline_template(e, tmpl, locals_, space, scope) -> str:
    s: dict = {}
    for a, p in zip(e.args, tmpl.params):                 # solve type-args from the value args
        if not isinstance(p.type, FnT):
            match_type(p.type, infer(a, locals_, space, scope), s)
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
    head = _bindings(e, binds, locals_, space, scope)
    saved = {k: _CENV.get(k, _MISSING) for k in frame}
    _CENV.update(frame)
    try:
        body = _c_inline_body(tmpl.body, blocals, space, tmpl.scope or scope, subst(tmpl.ret, s))
    finally:
        for k, v in saved.items():
            _CENV.pop(k, None) if v is _MISSING else _CENV.__setitem__(k, v)
    return f"({{ {head} {body} }})"


def _c_inline_closure(e, locals_, space, scope) -> str:
    clos, fnt, csite_locals, csite_scope = _CENV[e.callee]
    cl = dict(csite_locals)                               # the closure body sees its capture site…
    binds = []
    for a, pname, pt in zip(e.args, clos.params, fnt.params):
        binds.append((pname, pt, a))                      # …args lowered in the CURRENT (template) scope
        cl[pname] = pt
    head = _bindings(e, [(n, t, a) for n, t, a in binds], locals_, space, scope)
    body = _c_inline_body(clos.body, cl, space, csite_scope, fnt.ret)
    return f"({{ {head} {body} }})"


def _c_call(e, locals_, space, scope, expect=None) -> str:
    if e.callee == "addr":
        return f"&({c_expr(e.args[0], locals_, space, scope)})"
    if e.callee in ("load", "store", "offset"):           # raw memory ops erase to C
        a = [c_expr(x, locals_, space, scope) for x in e.args]
        if e.callee == "load":
            return f"(*({a[0]}))"
        if e.callee == "store":
            return f"(*({a[0]}) = {a[1]})"
        return f"(({a[0]}) + ({a[1]}))"                    # offset
    if e.callee == "slice":                               # slice(ptr, len) -> a [T] view (T = expect)
        styp = c_type(expect)                             # "slice_T" (also registers the typedef)
        ct = c_type(expect.elem)
        p = c_expr(e.args[0], locals_, space, scope)
        n = c_expr(e.args[1], locals_, space, scope)
        return f"({styp}){{ .ptr = ({ct}*)({p}), .len = ({n}) }}"
    if e.callee in _CENV:                                  # calling a closure param -> inline it
        return _c_inline_closure(e, locals_, space, scope)
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
        if is_template(callee):                         # a closure-taking fn -> inline it here
            return _c_inline_template(e, callee, locals_, space, scope)
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
    t = f"_subj{_uid(e)}"                                # unique per match node (nesting-safe)

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


def c_match_stmt(e, locals_, space, scope) -> str:
    """Lower a match used as a STATEMENT (for effect, not value) to an if/else
    chain, so arm bodies may be statements — `h.break()`, `h.continue()`, an
    assignment — which a ternary can't hold."""
    subj = c_expr(e.subject, locals_, space, scope)
    st = infer(e.subject, locals_, space, scope)
    t = f"_subj{_uid(e)}"
    arm_stmt = lambda a, al: (c_match_stmt(a.body, al, space, scope) if isinstance(a.body, Match)
                              else f"{c_expr(a.body, al, space, scope)};")

    if isinstance(st, PrimT):                            # literal match
        default = next((a for a in e.arms if a.lit is None), None)
        clauses = [f"if ({t} == {c_expr(a.lit, locals_, space, scope)}) {{ {arm_stmt(a, locals_)} }}"
                   for a in e.arms if a is not default]
        chain = " else ".join(clauses)
        if default is not None:
            chain += (f" else {{ {arm_stmt(default, locals_)} }}" if clauses
                      else f"{{ {arm_stmt(default, locals_)} }}")
        return f"{{ {c_type(st)} {t} = {subj}; {chain} }}"

    decl = space.walk(st.path).value
    sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
    cn = c_type(st)
    variants = {v.name: v for v in decl.variants}
    default = next((a for a in e.arms if a.variant is None), None)
    clauses = []
    for a in e.arms:
        if a is default:
            continue
        al, bind = locals_, ""
        if a.binding is not None:
            pt = c_type(subst(variants[a.variant].payload, sub))
            al = {**locals_, a.binding: subst(variants[a.variant].payload, sub)}
            bind = f"{pt} {a.binding} = {t}.u.{a.variant}; "
        clauses.append(f"if ({t}.tag == {cn}_{a.variant}) {{ {bind}{arm_stmt(a, al)} }}")
    chain = " else ".join(clauses)
    if default is not None:
        chain += (f" else {{ {arm_stmt(default, locals_)} }}" if clauses
                  else f"{{ {arm_stmt(default, locals_)} }}")
    return f"{{ {c_type(st)} {t} = {subj}; {chain} }}"


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
        elif isinstance(s, Match):                       # match for effect -> if/else statement
            lines.append(c_match_stmt(s, locals_, space, scope))
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
    if isinstance(s, Match):                             # a match used as a statement
        return c_match_stmt(s, locals_, space, scope)
    if isinstance(s, While):
        bl = dict(locals_)                               # loop body has its own scope
        body = " ".join(c_stmt(x, bl, space, scope) if isinstance(x, (Let, Assign, While, Match))
                        else f"{c_expr(x, bl, space, scope)};" for x in s.body)
        cond = c_expr(s.cond, locals_, space, scope)
        # the structured loop primitive → a C `for` (the step slot makes `continue`
        # correct and keeps it a counted loop the C compiler can auto-vectorize).
        step = c_stmt(s.step, locals_, space, scope).rstrip(";") if s.step is not None else ""
        return f"for (; {cond}; {step}) {{ {body} }}"
    return f"{c_expr(s, locals_, space, scope)};"


def c_def(qual, d: Fn, space, scope, cname=None) -> str:
    locals_ = {p.name: p.type for p in d.params}
    body = c_block(d.body, locals_, space, scope, d.ret) if d.body else "return 0;"
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)}) {{ {body} }}"
