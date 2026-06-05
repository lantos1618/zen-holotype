"""Codegen orchestration — monomorphization + C emission.

The reachability scanner walks every type-checked body and collects what codegen
must instantiate: concrete generic-fn instances, trait-impl uses, generic data-type
instances, and (for an executable) the plain fns transitively reached from the entry.
emit_c then assembles the C: forward decls, slice typedefs, dependency-ordered type
definitions, prototypes, and function bodies (delegating the per-node lowering to
lower.py).
"""
from __future__ import annotations
from .ast import (Struct, EnumDecl, Fn, Param, PrimT, NameT, PtrT, FnT, Bin, Not, Field,
                  SliceLit, Index, StructLit, EnumCtor, Match, Call, MethodCall, Closure,
                  While, Let, Assign, TraitDecl, Impl)
from .types import infer, subst, solve_call, match_type, struct_at, TraitMethod
from .lower import (c_struct, c_struct_fwd, c_enum, c_proto, c_def, c_name, inst_name, impl_cname,
                    mangle, slice_typedefs, _slice_reg, _uid_reg, is_template, _CENV)
from .resolve import trait_methods_scope, is_generator, is_prelude_ns

_LIBC = {"malloc", "free", "realloc", "calloc", "putchar", "getchar", "puts",
         "printf", "write", "read", "memcpy", "memset", "memmove", "strlen",
         "strcmp", "strncmp", "abort", "exit"}     # declared by the stdlib headers — don't re-proto


# ───────────────────────── monomorphization ─────────────────────────────────
class _Sink:
    """Collectors the scanner feeds: generic-fn instances, trait-impl uses,
    generic data-type instances (structs + enums), and `reach` — a plain non-generic
    fn that was called (for dead-code elimination from an entry point). `expect`
    threads through exactly like in c_expr, so an enum ctor knows which instance."""
    __slots__ = ("fn", "impl", "data", "reach")

    def __init__(self, fn, impl, data, reach):
        self.fn, self.impl, self.data, self.reach = fn, impl, data, reach


def _scan_expr(e, locals_, namespace, scope, sink, expect=None, cenv=None):
    """Walk an expression, feeding every monomorphization site to `sink`. `cenv`
    carries the active closure params while scanning an inlined template body."""
    if isinstance(e, Bin):
        _scan_expr(e.l, locals_, namespace, scope, sink, None, cenv)
        _scan_expr(e.r, locals_, namespace, scope, sink, None, cenv)
    elif isinstance(e, Not):
        _scan_expr(e.operand, locals_, namespace, scope, sink, None, cenv)
    elif isinstance(e, Field):
        _scan_expr(e.obj, locals_, namespace, scope, sink, None, cenv)
    elif isinstance(e, SliceLit):
        et = infer(e, locals_, namespace, scope).elem if e.elems else None
        for x in e.elems:
            _scan_expr(x, locals_, namespace, scope, sink, et, cenv)
    elif isinstance(e, Index):
        _scan_expr(e.seq, locals_, namespace, scope, sink, None, cenv)
        _scan_expr(e.idx, locals_, namespace, scope, sink, None, cenv)
        at = struct_at(infer(e.seq, locals_, namespace, scope), namespace)   # []-overloading: the `at` impl
        if at is not None:
            sink.impl(at[0], at[1])
    elif isinstance(e, StructLit):
        st = infer(e, locals_, namespace, scope)
        decl = namespace.walk(st.path).value
        sub = dict(zip(decl.tparams, st.args))
        ftypes = {fl.name: subst(fl.type, sub) for fl in decl.fields}
        for n, v in e.fields:                            # children first (inner-first emit order)
            _scan_expr(v, locals_, namespace, scope, sink, ftypes[n], cenv)
        if decl.tparams:
            sink.data(st.path, st.args)
    elif isinstance(e, EnumCtor):
        decl = namespace.walk(expect.path).value             # expect names the enum (generic or not)
        sub = dict(zip(decl.tparams, expect.args))
        var = next(v for v in decl.variants if v.name == e.name)
        for a in e.args:
            _scan_expr(a, locals_, namespace, scope, sink, subst(var.payload, sub), cenv)
        if decl.tparams:
            sink.data(expect.path, expect.args)
    elif isinstance(e, Match):
        _scan_expr(e.subject, locals_, namespace, scope, sink, None, cenv)
        st = infer(e.subject, locals_, namespace, scope)
        if isinstance(st, PtrT) and isinstance(st.pointee, NameT):   # match auto-derefs Ptr<Enum>
            st = st.pointee
        if isinstance(st, PrimT):                         # literal match: arms bind nothing
            for arm in e.arms:
                _scan_expr(arm.body, locals_, namespace, scope, sink, expect, cenv)
            return
        decl = namespace.walk(st.path).value
        sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
        variants = {v.name: v for v in decl.variants}
        for arm in e.arms:
            al = locals_
            if arm.variant is not None and arm.binding is not None:
                al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            _scan_expr(arm.body, al, namespace, scope, sink, expect, cenv)
    elif isinstance(e, Closure):                          # a closure literal that wasn't a call arg
        pass                                              # (only reachable via a template call, handled there)
    elif isinstance(e, MethodCall):                       # UFCS: x.f(a) == f(x, a)
        if e.method in ("break", "continue"):
            return
        call = Call(e.method, (e.recv,) + tuple(e.args), getattr(e, "pos", None))
        _scan_expr(call, locals_, namespace, scope, sink, expect, cenv)
    elif isinstance(e, Call):
        if e.callee == "sizeof":                          # sizeof(T): the arg is a TYPE, not a value
            return
        if e.callee in ("addr", "load", "store", "offset", "slice", "cstr"):   # intrinsics: just scan args
            for a in e.args:
                _scan_expr(a, locals_, namespace, scope, sink, None, cenv)
            return
        if cenv and e.callee in cenv:                     # calling a closure param: scan its inlined body
            clos, fnt, csite_locals, csite_scope = cenv[e.callee]
            for a, pt in zip(e.args, fnt.params):
                _scan_expr(a, locals_, namespace, scope, sink, pt, cenv)
            cl = {**csite_locals, **dict(zip(clos.params, fnt.params))}
            _scan_block(clos.body, cl, namespace, csite_scope, sink, fnt.ret)
            return
        target = scope.get(e.callee)
        if isinstance(target, TraitMethod):              # resolve concrete Self -> impl used
            s = {}
            for p, a in zip(target.sig.params, e.args):
                match_type(p, infer(a, locals_, namespace, scope), s)
            ptypes = [subst(p, {"Self": s["Self"]}) for p in target.sig.params]
            for a, pt in zip(e.args, ptypes):
                _scan_expr(a, locals_, namespace, scope, sink, pt, cenv)
            if isinstance(s.get("Self"), NameT):
                sink.impl(target.trait, s["Self"].path)
            return
        callee = namespace.walk(target).value
        if is_template(callee):                           # a closure-taking fn: scan the inlined body
            _scan_template_call(e, callee, locals_, namespace, scope, sink, cenv)
            return
        if isinstance(callee, Fn) and callee.tparams:
            s = solve_call(callee, [infer(a, locals_, namespace, scope) for a in e.args])
            ptypes = [subst(p.type, s) for p in callee.params]
            sink.fn(target, tuple(s[n] for n in callee.tparams))
        else:
            sink.reach(target)                            # a plain fn call — mark it live
            ptypes = [p.type for p in callee.params]
        for a, pt in zip(e.args, ptypes):
            _scan_expr(a, locals_, namespace, scope, sink, pt, cenv)


def _scan_template_call(e, tmpl, locals_, namespace, scope, sink, cenv):
    """A template is inlined, not instanced — so don't sink.fn it. Mirror the
    inlining: solve type-args from the value args, scan them, then scan the body
    with the closure params bound (so any monomorph sites inside are collected)."""
    s: dict = {}
    for a, p in zip(e.args, tmpl.params):
        if not isinstance(p.type, FnT):
            match_type(p.type, infer(a, locals_, namespace, scope), s)
    blocals, frame = dict(locals_), {}
    for a, p in zip(e.args, tmpl.params):
        if isinstance(p.type, FnT):
            fnt = subst(p.type, s)
            frame[p.name] = (a, fnt, locals_, scope)
            blocals[p.name] = fnt
        else:
            pt = subst(p.type, s)
            _scan_expr(a, locals_, namespace, scope, sink, pt, cenv)
            blocals[p.name] = pt
    _scan_block(tmpl.body, blocals, namespace, tmpl.scope or scope, sink, subst(tmpl.ret, s),
                {**(cenv or {}), **frame})


def _scan_block(stmts, locals_, namespace, scope, sink, expect=None, cenv=None):
    locals_ = dict(locals_)
    last = len(stmts) - 1
    for i, s in enumerate(stmts):
        if isinstance(s, Let):
            _scan_expr(s.value, locals_, namespace, scope, sink, None, cenv)
            locals_[s.name] = infer(s.value, locals_, namespace, scope)
        elif isinstance(s, Assign):
            _scan_expr(s.target, locals_, namespace, scope, sink, None, cenv)
            _scan_expr(s.value, locals_, namespace, scope, sink, None, cenv)
        elif isinstance(s, While):
            _scan_expr(s.cond, locals_, namespace, scope, sink, None, cenv)
            _scan_block(s.body, locals_, namespace, scope, sink, None, cenv)
            if s.step is not None:
                _scan_block((s.step,), locals_, namespace, scope, sink, None, cenv)
        else:
            _scan_expr(s, locals_, namespace, scope, sink, expect if i == last else None, cenv)


def specialize(fn, s):
    """A concrete copy of a generic fn with its type-args substituted in (bounds
    kept so its body's trait-method calls still resolve)."""
    return Fn(fn.name, [Param(p.name, subst(p.type, s)) for p in fn.params],
              subst(fn.ret, s), fn.body, fn.pub, (), fn.bounds)


def collect_instances(files, passing, namespace, roots=None):
    """Reachable, transitively, from the seed functions: every concrete generic-fn
    instance, trait impl, generic data-type instance, and (for dead-code
    elimination) every plain fn actually called.

    `roots` None  → seed from ALL passing non-generic fns (a library: emit
                    everything that type-checks); `reached` is returned as None.
    `roots` a set → seed from just those quals (an executable's entry); `reached`
                    is the set of plain fns transitively called, so emit_c can drop
                    the rest. -> (fn_insts, impls_used, data_insts, reached)"""
    decl_scope = {f"{f.ns}.{d.name}": f.scope
                  for f in files.values() for d in f.decls if not isinstance(d, Impl)}
    # impls_used is an *ordered* set (a dict): emit_c iterates it to order trait-impl
    # output, and a plain set's iteration order varies with PYTHONHASHSEED — which
    # would make codegen non-reproducible. Discovery order is deterministic; keep it.
    insts, impls_used, data_insts, work = {}, {}, {}, []

    def add(qual, targs):
        if (qual, targs) in insts:
            return
        fn = namespace.walk(qual).value
        sub = dict(zip(fn.tparams, targs))
        sc = {**trait_methods_scope(fn, decl_scope[qual], namespace), **sub}   # bind tparams so `sizeof(T)` lowers
        spec = specialize(fn, sub)
        insts[(qual, targs)] = (spec, sc)
        work.append((spec, sc))

    def add_impl(trait_path, type_path):
        if (trait_path, type_path) in impls_used:
            return
        impls_used[(trait_path, type_path)] = None
        for mfn, msc in namespace.impls[(trait_path, type_path)].values():
            work.append((mfn, msc))

    def add_data(qual, targs):                # struct OR enum; inner-first insertion = emit order
        data_insts.setdefault((qual, targs), dict(zip(namespace.walk(qual).value.tparams, targs)))

    reached = None if roots is None else set()

    def add_reach(qual):                      # a plain fn became live — scan it once (DCE)
        if reached is None or qual in reached or qual not in passing:
            return
        fn = namespace.walk(qual).value
        if not isinstance(fn, Fn) or fn.tparams or is_template(fn) or fn.body is None:
            return                            # generics/templates/externs handled elsewhere
        reached.add(qual)
        sc = trait_methods_scope(fn, decl_scope[qual], namespace) if fn.bounds else decl_scope[qual]
        work.append((fn, sc))

    sink = _Sink(add, add_impl, add_data, add_reach)
    if roots is None:                         # library: every passing non-generic fn is a seed
        for f in files.values():
            for d in f.decls:
                if (isinstance(d, Fn) and not d.tparams and not is_template(d)
                        and not is_generator(d) and f"{f.ns}.{d.name}" in passing):
                    sc = trait_methods_scope(d, f.scope, namespace) if d.bounds else f.scope
                    _scan_block(d.body, {p.name: p.type for p in d.params}, namespace, sc, sink, d.ret)
    else:                                     # executable: seed from the entry, prune the rest
        for r in roots:
            add_reach(r)
    while work:
        fn, sc = work.pop()
        _scan_block(fn.body, {p.name: p.type for p in fn.params}, namespace, sc, sink, fn.ret)
    return insts, impls_used, data_insts, reached


def _by_value_dep(t):
    """The C type-name a field/payload embeds BY VALUE — so it must be defined before
    the embedding type — or None. A `Ptr<T>` or `[T]` needs only a forward decl, and
    `Option<…>` lowers to a pointer, so none of those create a definition dependency."""
    return mangle(t) if isinstance(t, NameT) and t.path != "Option" else None


def emit_c(files, passing, namespace, extra="", roots=None):
    # `roots` (a set of entry quals) prunes plain fns to those reachable from it —
    # dead-code elimination for an executable. None emits every passing fn (a lib).
    # Integrity: codegen lowers struct/enum/fn directly and trait impls on demand.
    # A trait declaration emits nothing; anything else fails loudly.
    for f in files.values():
        if is_prelude_ns(f.ns):                          # prelude types/fns are comptime-only
            continue
        for d in f.decls:
            if not isinstance(d, (Struct, EnumDecl, Fn, TraitDecl, Impl)):
                raise NotImplementedError(
                    f"cannot lower {type(d).__name__} '{getattr(d, 'name', '?')}' to C yet "
                    f"(codegen supports struct + enum + fn + trait/impl)")
    insts, impls_used, data_insts, reached = collect_instances(files, passing, namespace, roots)
    live = lambda qual: reached is None or qual in reached   # DCE: plain fn reachable?
    impl_fns = []                                         # the trait methods actually used
    for (tp, ty) in impls_used:
        for m, (mfn, msc) in namespace.impls[(tp, ty)].items():
            if (tp, ty, m) not in passing:                # used but ill-typed -> refuse loudly
                raise NotImplementedError(
                    f"trait impl {ty.rsplit('.', 1)[-1]}::{m} is used but did not type-check")
            impl_fns.append((impl_cname(tp, ty, m), mfn, msc))

    _slice_reg.clear()                                   # slice typedefs collected during lowering
    _uid_reg.clear()                                     # node→name ids: reset so output is reproducible
    _CENV.clear()                                        # closure-inlining env (always empties itself)
    lines = ["#include <stdint.h>", "#include <stdbool.h>"]
    externs = [d for f in files.values() for d in f.decls if isinstance(d, Fn) and d.extern]
    if externs:                                          # libc headers declare the common ones
        lines += ["#include <stdlib.h>", "#include <stdio.h>",
                  "#include <string.h>", "#include <unistd.h>"]
    lines.append("")
    # Forward-declare every struct/enum tag first, then the slice typedefs, then the
    # full definitions TOPOSORTED by by-value containment: a struct/tagged-union embeds
    # its payload, so the inner type must be defined before it; a Ptr<T> or [T] field
    # needs only the forward decl (a slice typedef is just `T*`). So a recursive type
    # (`Tree` holding `Ptr<Tree>`) or any nesting works regardless of declaration order.
    entries = []                                         # (cname, by-value deps, emitted def)
    for f in files.values():                             # types (generic templates emit nothing)
        if is_prelude_ns(f.ns):                          # prelude Ast model is never lowered
            continue
        for d in f.decls:
            if isinstance(d, Struct) and not d.tparams:
                deps = {dp for fld in d.fields if (dp := _by_value_dep(fld.type))}
                entries.append((c_name(f"{f.ns}.{d.name}"), deps, c_struct(f"{f.ns}.{d.name}", d)))
            elif isinstance(d, EnumDecl) and not d.tparams:
                deps = {dp for v in d.variants if v.payload is not None and (dp := _by_value_dep(v.payload))}
                entries.append((c_name(f"{f.ns}.{d.name}"), deps, c_enum(f"{f.ns}.{d.name}", d)))
    for (qual, targs), sub in data_insts.items():        # monomorphized generic structs + enums
        decl = namespace.walk(qual).value
        cn = mangle(NameT(qual, targs))
        if isinstance(decl, Struct):
            deps = {dp for fld in decl.fields if (dp := _by_value_dep(subst(fld.type, sub)))}
            entries.append((cn, deps, c_struct(qual, decl, sub, cn)))
        else:
            deps = {dp for v in decl.variants if v.payload is not None and (dp := _by_value_dep(subst(v.payload, sub)))}
            entries.append((cn, deps, c_enum(qual, decl, sub, cn)))
    emitted = {cn: s for cn, _, s in entries}
    deps_of = {cn: d for cn, d, _ in entries}
    order, placed = [], set()
    def _emit_type(cn):                                  # DFS: a type's by-value deps precede it
        if cn in placed or cn not in deps_of:
            return
        placed.add(cn)
        for dep in sorted(deps_of[cn]):                  # sorted: a deterministic order (deps is a set)
            _emit_type(dep)
        order.append(cn)
    for cn, _, _ in entries:
        _emit_type(cn)
    lines += [c_struct_fwd(cn) for cn, _, _ in entries]  # forward decls (any order)
    slice_at = len(lines)                                # slice typedefs go here: after fwd-decls,
    lines += [emitted[cn] for cn in order]               # definitions, dependency-ordered
    lines.append("")
    for d in externs:                                    # protos only for non-libc externs
        if d.name not in _LIBC:                           # (the headers above declare libc)
            lines.append("extern " + c_proto(d.name, d, d.name))
    for f in files.values():                             # prototypes: concrete fns…
        for d in f.decls:
            if (isinstance(d, Fn) and not d.tparams and not d.extern and not is_template(d)
                    and not is_generator(d)
                    and f"{f.ns}.{d.name}" in passing and live(f"{f.ns}.{d.name}")):
                lines.append(c_proto(f"{f.ns}.{d.name}", d))
    for (qual, targs), (spec, _) in insts.items():       # …monomorphized instances…
        lines.append(c_proto(qual, spec, inst_name(qual, targs)))
    for cn, mfn, _ in impl_fns:                          # …and trait-impl methods
        lines.append(c_proto(cn, mfn, cn))
    lines.append("")
    for f in files.values():                             # definitions
        for d in f.decls:
            if (isinstance(d, Fn) and not d.tparams and not is_template(d)
                    and not is_generator(d)
                    and f"{f.ns}.{d.name}" in passing and live(f"{f.ns}.{d.name}")):
                lines.append(c_def(f"{f.ns}.{d.name}", d, namespace, f.scope))
    for (qual, targs), (spec, sc) in insts.items():
        lines.append(c_def(qual, spec, namespace, sc, inst_name(qual, targs)))
    for cn, mfn, msc in impl_fns:
        lines.append(c_def(cn, mfn, namespace, msc, cn))
    lines[slice_at:slice_at] = slice_typedefs()          # now _slice_reg is fully populated
    return "\n".join(lines) + "\n" + extra
