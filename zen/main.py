"""zen driver.

    python3 -m zen build [dir]   # read build.zen, compile + link + run the exe
    python3 -m zen check [dir]   # type-check report only, emit a C lib

Pipeline: parse -> insert into trie -> resolve refs -> infer/fits -> to_c.
Only well-typed functions are codegen'd.
"""
from __future__ import annotations
import sys, pathlib, subprocess, dataclasses
from .ast import (Struct, EnumDecl, Fn, Param, Prim, PrimT, NameT, PtrT, TVar, SliceT, FnT,
                  Str, StructLit, SliceLit, Index, Bin, Not, Field, Let, Assign, While, Loop,
                  Call, MethodCall, EnumCtor, Match, TraitDecl, Impl, Emit, Lit, Bool, Var, Closure)
from .types import (Namespace, fits, infer, infer_block, subst, solve_call, match_type,
                    ret_type, show, scope_with_bounds, struct_at, TraitMethod, TypeErr,
                    Unresolved, Private, Located)
from .lower import (c_struct, c_struct_fwd, c_enum, c_proto, c_def, c_name, inst_name,
                    impl_cname, mangle, slice_typedefs, _slice_reg, _uid_reg, is_template, _CENV)
from .parser import parse
from .comptime import fold_comptime, evaluate, reify_decl, Host

BUILTIN = {"Option"}
_LIBC = {"malloc", "free", "realloc", "calloc", "putchar", "getchar", "puts",
         "printf", "write", "read", "memcpy", "memset", "memmove", "strlen",
         "strcmp", "strncmp", "abort", "exit"}     # declared by the stdlib headers — don't re-proto


# ───────────────────────── front end ────────────────────────────────────────
_PRELUDE_DIR = pathlib.Path(__file__).parent / "prelude"
_BINDINGS_DIR = pathlib.Path(__file__).parent / "bindings"
_STD_DIR = pathlib.Path(__file__).parent / "std"


def load_uses(cfg, files):
    """Install each build `use` as an importable namespace —
    `c = b.use("libc")` makes `{ malloc, free } = c` work.

    A foreign binding is a Zen module of decls (the libc bindings are bodyless
    functions in bindings/libc.zen — content lives in Zen, never in this kernel).
    `b.use(name)` loads that bundled module under the chosen namespace; the kernel
    knows only how to load-a-module-as-a-namespace, nothing C-specific. A real
    *generating* adapter (translate-c / wasm / python → [Decl]) is a future Zen
    comptime function run through the same `b.use` seam — built when one exists."""
    for u in cfg.get("uses", []):
        path = _BINDINGS_DIR / f"{u['module']}.zen"
        if not path.exists():
            raise SystemExit(f"build.zen: no binding module '{u['module']}' "
                             f"(looked in {_BINDINGS_DIR})")
        files[u["ns"]] = parse(path.read_text(), u["ns"])
    return files


def load_prelude():
    """The compiler's bundled Zen prelude (the self-hosted Ast model + derives),
    always available under the `prelude.*` namespace, importable from any file."""
    return {f"prelude.{p.stem}": parse(p.read_text(), f"prelude.{p.stem}")
            for p in sorted(_PRELUDE_DIR.glob("*.zen"))}


def load_std():
    """The bundled standard library — ordinary runtime Zen under `std.*`, importable
    from any file. Unlike the prelude (comptime-only, never lowered), std IS checked
    and lowered like user code. But its helpers are templates/generics, so nothing is
    emitted unless a program imports AND uses them — the stdlib is zero-cost ambient."""
    if not _STD_DIR.exists():
        return {}
    return {f"std.{p.stem}": parse(p.read_text(), f"std.{p.stem}")
            for p in sorted(_STD_DIR.glob("*.zen"))}


def load(root, skip=()):
    skip = set(skip) | {"build.zen"}        # build.zen is a build script, never a module
    files = dict(load_prelude())
    files.update(load_std())
    for path in sorted(pathlib.Path(root).rglob("*.zen")):
        if path.name in skip:
            continue
        ns = ".".join(path.relative_to(root).with_suffix("").parts)
        files[ns] = parse(path.read_text(), ns)
    return files


def build_namespace(files):
    namespace = Namespace()                       # trie + impls registry; impls filled in resolve()
    for f in files.values():
        for d in f.decls:
            if isinstance(d, (Impl, Emit)):   # no name: impls registered in resolve, emits splice later
                continue
            namespace.insert(f"{f.ns}.{d.name}", d)
    return namespace


def build_scopes(files):
    for f in files.values():
        sc = {}
        for imp in f.imports:
            for n in imp.names:
                sc[n] = f"{imp.module}.{n}"
        for d in f.decls:
            if not isinstance(d, (Impl, Emit)):
                sc[d.name] = f"{f.ns}.{d.name}"
        f.scope = sc


def trait_methods_scope(fn, base, namespace):
    """`base` scope plus, for every bound `T: Trait`, the trait's methods bound
    as TraitMethod entries — so a bounded body can call them by name."""
    sc = dict(base)
    for tp, trait_path in fn.bounds.items():
        trait = namespace.walk(trait_path).value
        for sig in trait.methods:
            sc[sig.name] = TraitMethod(tp, sig, trait_path)
    return sc


def resolve_type(t, scope, namespace, tparams=()):
    if isinstance(t, (PrimT, TVar)):
        return t
    if isinstance(t, SliceT):
        return SliceT(resolve_type(t.elem, scope, namespace, tparams))
    if isinstance(t, FnT):                        # (A, T) Ret — resolve params + ret
        return FnT(tuple(resolve_type(p, scope, namespace, tparams) for p in t.params),
                   resolve_type(t.ret, scope, namespace, tparams))
    if isinstance(t, PtrT):
        return PtrT(t.dir, resolve_type(t.pointee, scope, namespace, tparams))
    if isinstance(t, NameT):
        if t.path in tparams:                    # a bare name in scope as a type param
            return TVar(t.path)
        args = tuple(resolve_type(a, scope, namespace, tparams) for a in t.args)
        if t.path in BUILTIN:
            return NameT(t.path, args)
        qual = scope.get(t.path, t.path)
        namespace.walk(qual)
        return NameT(qual, args)
    raise TypeErr(f"unknown type node {t!r}")


def check_visibility(files, namespace):
    """A module may only import another module's *public* names — a decl is public
    when its name carries the glued `*` (`Vec*`, `area*`). A bare name is private to
    its file. Same-file references never go through an import, so they're unaffected."""
    for f in files.values():
        for imp in f.imports:
            if imp.module == f.ns:                       # (a file never imports itself, but be safe)
                continue
            for name in imp.names:
                try:
                    decl = namespace.walk(f"{imp.module}.{name}").value
                except Unresolved:
                    continue                              # resolve() reports the missing name
                if not getattr(decl, "pub", False):
                    raise Private(f"{f.ns}: '{name}' is private to {imp.module} "
                                  f"(mark it '{name}*' there to export it)")


def resolve(files, namespace):
    check_visibility(files, namespace)
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Struct):
                tp = set(d.tparams)
                for fld in d.fields:
                    fld.type = resolve_type(fld.type, f.scope, namespace, tp)
            elif isinstance(d, EnumDecl):
                tp = set(d.tparams)
                for v in d.variants:
                    if v.payload is not None:
                        v.payload = resolve_type(v.payload, f.scope, namespace, tp)
            elif isinstance(d, Fn):
                _resolve_fn(d, f.scope, namespace)
            elif isinstance(d, TraitDecl):
                for sig in d.methods:                       # Self is the implementor's type var
                    sig.params = tuple(resolve_type(p, f.scope, namespace, {"Self"}) for p in sig.params)
                    sig.ret = resolve_type(sig.ret, f.scope, namespace, {"Self"})
            elif isinstance(d, Impl):
                trait_path = f.scope.get(d.trait, d.trait)
                type_path = f.scope.get(d.type, d.type)
                namespace.walk(trait_path); namespace.walk(type_path)   # both must exist
                for m in d.methods:
                    _resolve_fn(m, f.scope, namespace)
                namespace.impls[(trait_path, type_path)] = {m.name: (m, f.scope) for m in d.methods}
    desugar_loops(files)                                # loop → @while, before check + lower


# ───────────────────────── desugar: loop → @while ───────────────────────────
# The everyday `loop` sugar collapses onto the one structured primitive (While)
# BEFORE checking, so check + lower only ever meet @while. Nothing is unravelled
# to gotos — While stays structured (→ a C `for`) so it can auto-vectorize.
_seq_ctr = [0]                                          # element-loop `_seq` names: a deterministic
                                                        # counter (not id()) so desugaring is reproducible


def desugar_loops(files):
    _seq_ctr[0] = 0
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and d.body is not None and not d.extern:
                d.body = _desugar_block(d.body)
            elif isinstance(d, Impl):
                for m in d.methods:
                    if m.body is not None:
                        m.body = _desugar_block(m.body)


def _desugar_block(stmts):
    out = []
    for s in stmts:
        out.extend(_desugar_stmt(s))
    return out


def _mentions(node, name) -> bool:
    """Does `name` appear as a Var anywhere in this AST node? (Used so the element
    binding `x := xs[i]` is only emitted when the body actually reads it — an
    unused one would trip -Werror=unused-variable.)"""
    if isinstance(node, Var):
        return node.name == name
    if dataclasses.is_dataclass(node):
        return any(_mentions(getattr(node, f.name), name) for f in dataclasses.fields(node))
    if isinstance(node, (tuple, list)):
        return any(_mentions(x, name) for x in node)
    return False


def _desugar_stmt(s):
    if isinstance(s, Loop):
        body = tuple(_desugar_block(s.body))
        if s.count is None:                          # loop((h){B}) -> @while(true){B}
            return [While(Bool(True), body, None)]
        if len(s.params) >= 3:                        # element form: loop(xs, (h, i, x) { B })
            _seq_ctr[0] += 1
            seq, idx, elem = f"_seq{_seq_ctr[0]}", s.params[1], s.params[2]
            cond = Bin("<", Var(idx), Field(Var(seq), "len"))      # i < xs.len
            step = Assign(Var(idx), Bin("+", Var(idx), Lit(1)))
            pre = (Let(elem, Index(Var(seq), Var(idx))),) if _mentions(body, elem) else ()  # x := xs[i]
            return [Let(seq, s.count), Let(idx, Lit(0)),
                    While(cond, pre + body, step)]
        idx = s.params[1] if len(s.params) > 1 else "_i"   # count form: loop(n,(h,i){B})
        cond = Bin("<", Var(idx), s.count)
        step = Assign(Var(idx), Bin("+", Var(idx), Lit(1)))
        return [Let(idx, Lit(0)), While(cond, body, step)]   #  i:=0; @while(i<n){B; step i++}
    if isinstance(s, While):                         # @while primitive — desugar its nested body
        return [While(s.cond, tuple(_desugar_block(s.body)), s.step)]
    return [s]


def _resolve_fn(d, scope, namespace):
    tp = set(d.tparams)
    for p in d.params:
        p.type = resolve_type(p.type, scope, namespace, tp)
    if d.ret is not None:                                   # None -> inferred from the body later
        d.ret = resolve_type(d.ret, scope, namespace, tp)
    d.bounds = {k: (scope.get(v, v)) for k, v in d.bounds.items()}
    for trait_path in d.bounds.values():
        namespace.walk(trait_path)                              # the bound trait must exist
    d.scope = trait_methods_scope(d, scope, namespace) if d.bounds else scope   # for ret inference


def is_prelude_ns(ns):
    """Prelude files (the self-hosted Ast model + derives) are loaded, resolved,
    and available at comptime, but the kernel never checks or lowers them."""
    return ns == "prelude" or ns.startswith("prelude.")


def is_generator(d):
    """A comptime generator: a fn whose result is a prelude (Ast-model) type — e.g.
    `(spec) Decl`. It IS type-checked (so its Ast construction is validated against
    the model), but it's consumed by @emit at comptime and never lowered (those
    types have no runtime C form)."""
    return isinstance(d, Fn) and isinstance(d.ret, NameT) and is_prelude_ns(d.ret.path)


def _graft_impl(d, f, namespace):
    """Register a generated trait impl exactly like resolve() does for a written
    one: resolve its methods and record it in the impls registry."""
    trait_path = f.scope.get(d.trait, d.trait)
    type_path = f.scope.get(d.type, d.type)
    namespace.walk(trait_path); namespace.walk(type_path)        # both must exist
    for m in d.methods:
        _resolve_fn(m, f.scope, namespace)
    namespace.impls[(trait_path, type_path)] = {m.name: (m, f.scope) for m in d.methods}


def run_emits(files, namespace):
    """The splice pass: evaluate each `emit` generator at comptime, reify the
    Zen `Ast` value it returns into a real declaration (a free fn or a trait
    impl), and graft it into the module — so check + lower meet it as ordinary
    code. Runs after resolve, before check (VISION step 4: prelude `Ast → Ast`)."""
    for f in files.values():
        grafted = []
        for d in f.decls:
            if not isinstance(d, Emit):
                continue
            out = evaluate(d.value, namespace, f.scope)
            for g in (out if isinstance(out, list) else [out]):
                g = reify_decl(g)                        # Zen Ast value -> host Fn / Impl
                if isinstance(g, Impl):
                    _graft_impl(g, f, namespace)
                else:
                    f.scope[g.name] = f"{f.ns}.{g.name}"     # same dict the siblings see
                    namespace.insert(f"{f.ns}.{g.name}", g)
                    _resolve_fn(g, f.scope, namespace)
                grafted.append(g)
        if grafted:
            f.decls = [d for d in f.decls if not isinstance(d, Emit)] + grafted


def _check_fn(qual, ns, d, namespace, results, passing):
    if not d.body:
        return
    locals_ = {p.name: p.type for p in d.params}
    try:
        want = d.ret if d.ret is not None else ret_type(qual, namespace)   # declared or inferred
        bt = infer_block(d.body, locals_, namespace, scope_with_bounds(d.scope, d.bounds), want)
        void = isinstance(want, PrimT) and want.prim is Prim.VOID
        if want is not None and not void and not fits(bt, want):        # void discards the body value
            raise TypeErr("return type", bt, want)
        results.append((qual, True, "ok")); passing.add(qual)
    except TypeErr as ex:
        core = (f"{show(ex.given)}  ⊀  {show(ex.want)}"
                if ex.given is not None else str(ex))
        loc = f"{ns}:{ex.pos[0] + 1}:{ex.pos[1] + 1}: " if ex.pos else ""
        results.append((qual, False, Located(loc + core, ns, ex.pos)))


def check(files, namespace):
    results, passing = [], set()
    for f in files.values():
        if is_prelude_ns(f.ns):                            # the prelude runs at comptime; never checked
            continue
        for d in f.decls:
            if isinstance(d, Fn):
                _check_fn(f"{f.ns}.{d.name}", f.ns, d, namespace, results, passing)
            elif isinstance(d, Impl):
                _check_impl(d, f, namespace, results, passing)
    return results, passing


def _check_impl(d, f, namespace, results, passing):
    trait_path = f.scope.get(d.trait, d.trait)
    type_path = f.scope.get(d.type, d.type)
    trait = namespace.walk(trait_path).value
    sigs = {s.name: s for s in trait.methods}
    self_sub = {"Self": NameT(type_path, ())}
    for m in d.methods:
        tag = f"{d.trait} for {d.type}::{m.name}"
        # conformance: the method must match the trait signature with Self = the type
        sig = sigs.get(m.name)
        if sig is None:
            results.append((tag, False, f"{d.trait} has no method '{m.name}'")); continue
        want_params = [subst(p, self_sub) for p in sig.params]
        got_params = [p.type for p in m.params]
        if got_params != want_params or m.ret != subst(sig.ret, self_sub):
            results.append((tag, False, "signature does not match the trait")); continue
        _check_fn(tag, f.ns, m, namespace, results, passing)
        if tag in passing:                          # record the codegen key in `passing` too
            passing.add((trait_path, type_path, m.name))
    missing = [name for name in sigs if name not in {m.name for m in d.methods}]
    if missing:
        results.append((f"{d.trait} for {d.type}", False,
                        f"missing method(s): {', '.join(missing)}"))


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
        if e.callee in ("addr", "load", "store", "offset", "slice"):   # intrinsics: just scan args
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
        sc = trait_methods_scope(fn, decl_scope[qual], namespace)
        spec = specialize(fn, dict(zip(fn.tparams, targs)))
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
    # full definitions. A slice typedef uses only `T*`, so a forward decl satisfies it —
    # that lets a slice-of-struct and a struct-with-a-slice-field coexist (each would
    # otherwise demand the other come first). Definitions stay in decl order.
    fwd, defs = [], []
    for f in files.values():                             # types (generic templates emit nothing)
        if is_prelude_ns(f.ns):                          # prelude Ast model is never lowered
            continue
        for d in f.decls:
            if isinstance(d, Struct) and not d.tparams:
                fwd.append(c_struct_fwd(c_name(f"{f.ns}.{d.name}")))
                defs.append(c_struct(f"{f.ns}.{d.name}", d))
            elif isinstance(d, EnumDecl) and not d.tparams:
                fwd.append(c_struct_fwd(c_name(f"{f.ns}.{d.name}")))
                defs.append(c_enum(f"{f.ns}.{d.name}", d))
    for (qual, targs), sub in data_insts.items():        # monomorphized generic structs + enums
        decl = namespace.walk(qual).value
        cn = mangle(NameT(qual, targs))
        fwd.append(c_struct_fwd(cn))
        defs.append((c_struct if isinstance(decl, Struct) else c_enum)(qual, decl, sub, cn))
    lines += fwd
    slice_at = len(lines)                                # slice typedefs go here: after fwd-decls,
    lines += defs                                        # before the full definitions
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


# ───────────────────────── build.zen interpreter ────────────────────────────
# build.zen is a real Zen program: we *run* its build() function through the
# comptime engine, with `b` a live host Builder. b.add / b.use / b.config execute
# as the script does, so conditionals, helper functions and computed values are
# all honoured — nothing is scraped out of the AST.
class _UseToken:
    """The value of `b.use(mod)`. The name it's assigned to becomes the namespace
    the module installs under — `c = b.use("libc")` → namespace `c`, so a program
    then does `{ malloc, free } = c`."""
    def __init__(self, module):
        self.module = module


class _Builder(Host):
    """The build `Builder`. `b.add(Executable/Test)` registers a graph node,
    `b.use(mod)` a foreign-binding module, `b.config()` finalizes to a Result."""
    def __init__(self):
        self.execs, self.tests = [], []

    def invoke(self, method, args):
        if method == "add":
            comp = args[0] if args else None
            ty = getattr(comp, "type_name", None)
            if ty == "Executable":
                self.execs.append(comp)
            elif ty == "Test":
                self.tests.append(comp)
            else:
                raise SystemExit(f"build.zen: b.add expects an Executable or Test, got {ty!r}")
            return self                                    # chainable: b.add(...).add(...)
        if method == "use":
            if not (args and isinstance(args[0], str)):
                raise SystemExit("build.zen: b.use(<module>) needs a string module name")
            return _UseToken(args[0])
        if method == "config":
            return ("@enum", "Ok", None)                   # Result<BuildConfig, BuildError>.Ok
        raise SystemExit(f"build.zen: a Builder has no method '{method}'")


def _build_cfg(b, uses):
    """Read the executed Builder's accumulated graph into the config dict the rest
    of the build pipeline consumes."""
    cfg = {"name": "a.out", "main": "main.zen", "out_dir": ".", "tests": [], "uses": uses,
           "cflags": [], "links": [], "target": "native"}
    if b.execs:
        e = b.execs[0]                                     # one executable per build, today
        cfg["name"] = e.get("name", cfg["name"])
        cfg["main"] = e.get("main", cfg["main"])
        cfg["out_dir"] = e.get("out_dir", cfg["out_dir"])
        cfg["cflags"] = e.get("cflags", []) or []          # ["-O2", "-g"]
        cfg["links"] = e.get("links", []) or []            # ["m"] -> -lm
        cfg["target"] = e.get("target", "native")
    cfg["tests"] = [r for t in b.tests if (r := t.get("root"))]
    return cfg


def interpret_build(bf):
    """Run build() for real and return its config dict. `b` is a host Builder threaded
    through the comptime evaluator; the graph it accumulates *is* the executed result."""
    files = {"build": bf}
    namespace = build_namespace(files)
    build_scopes(files)
    for d in bf.decls:
        if isinstance(d, Fn):
            d.scope = bf.scope                             # comptime _call reads fn.scope
    fn = next((d for d in bf.decls if isinstance(d, Fn) and d.name == "build"), None)
    if fn is None:
        raise SystemExit("build.zen: no build() function")

    b = _Builder()
    env = {fn.params[0].name: b} if fn.params else {}      # bind the `b: Builder` parameter
    uses, final = [], None
    for stmt in fn.body:
        if isinstance(stmt, Let):
            env[stmt.name] = v = evaluate(stmt.value, namespace, fn.scope, env)
            if isinstance(v, _UseToken):                   # c := b.use(...)
                uses.append({"module": v.module, "ns": stmt.name})
        elif isinstance(stmt, Assign) and isinstance(stmt.target, Var):
            env[stmt.target.name] = v = evaluate(stmt.value, namespace, fn.scope, env)
            if isinstance(v, _UseToken):                   # c = b.use(...)
                uses.append({"module": v.module, "ns": stmt.target.name})
        else:
            final = evaluate(stmt, namespace, fn.scope, env)
    if isinstance(final, tuple) and len(final) == 3 and final[:2] == ("@enum", "Err"):
        raise SystemExit(f"build.zen: build() returned an error: {final[2]!r}")
    return _build_cfg(b, uses)


def is_test_fn(d) -> bool:
    """A test is a no-arg function returning bool — true means the test passed."""
    return (isinstance(d, Fn) and not d.params
            and isinstance(d.ret, PrimT) and d.ret.prim is Prim.BOOL)


def run_test_root(root, test_rel, cc_extra=()):
    """Compile the test root together with the project modules and run each
    bool-returning no-arg test, reporting PASS/FAIL from its return value.
    `cc_extra` are extra cc args (the Executable's cflags + `-l` links)."""
    test_ns = pathlib.Path(test_rel).with_suffix("").as_posix().replace("/", ".")
    files = load(root)                       # includes the test root (skips only build.zen)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)

    tf = files.get(test_ns)
    tests = [d for d in (tf.decls if tf else []) if is_test_fn(d)]
    runnable = [d for d in tests if f"{test_ns}.{d.name}" in passing]

    calls = "\n".join(
        f'    printf("   %s  {test_ns}.{d.name}\\n", '
        f'{c_name(f"{test_ns}.{d.name}")}() ? "PASS \\u2713" : "FAIL \\u2717");'
        for d in runnable)
    harness = f'\n#include <stdio.h>\nint main(void) {{\n{calls}\n    return 0;\n}}\n'

    out_dir = pathlib.Path(root) / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{test_ns}_test.c", out_dir / f"{test_ns}_test"
    compile_if_changed(cpath, bpath, emit_c(files, passing, namespace, harness), cc_extra)
    print(f"\n── tests: {test_rel} ──")
    skipped = [d.name for d in tests if d not in runnable]
    print(subprocess.run([str(bpath)], capture_output=True, text=True).stdout, end="")
    for name in skipped:
        print(f"   SKIP    {test_ns}.{name}  (did not type-check)")


# ───────────────────────── commands ─────────────────────────────────────────
def caret(root, why):
    """The offending source line + a caret under the column, built straight from a
    Located diagnostic's structured `(ns, pos)` — no message re-parsing. '' if the
    location is absent or the source can't be read."""
    ns, pos = getattr(why, "ns", None), getattr(why, "pos", None)
    if not ns or not pos:
        return ""
    try:
        line = (pathlib.Path(root) / (ns.replace(".", "/") + ".zen")).read_text().splitlines()[pos[0]]
    except (OSError, IndexError):
        return ""
    return f"\n        {line}\n        {' ' * pos[1]}^"


def report(results, root):
    """Print the PASS/FAIL table; under each failure, show its source line + caret."""
    for qual, ok, why in results:
        print(f"   {'PASS ✓' if ok else 'FAIL ✗'}  {qual:<14} {'' if ok else why}"
              + ("" if ok else caret(root, why)))


def cmd_check(root):
    files = load(root)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    print(f"── check {root} ──")
    report(results, root)
    pathlib.Path("out.c").write_text(emit_c(files, passing, namespace))
    print("   -> wrote out.c")


def compile_if_changed(cpath, bpath, c_text, cc_extra=()):
    """Write `c_text` and compile it to `bpath` with cc, but skip the compile when
    the source we'd write is byte-identical to last time and the binary still
    exists. Sound because codegen is deterministic — same program → same C → same
    binary. A header comment records the exact cc command, so changing cflags or
    links changes the file and busts the cache too. Returns True if it compiled."""
    cc = ["cc", "-Wall", "-Wextra", *cc_extra]
    stamped = f"// built with: {' '.join(cc)} {cpath.name} -o {bpath.name}\n{c_text}"
    if bpath.exists() and cpath.exists() and cpath.read_text() == stamped:
        return False
    cpath.write_text(stamped)
    subprocess.run([*cc, str(cpath), "-o", str(bpath)], check=True)
    return True


# Build targets. Only "native" (compile C with cc) is implemented; the dict is the
# extension point — a wasm backend slots in here as `"wasm": <emitter>` once it exists.
_TARGETS = {"native"}


def cmd_build(root):
    bf = parse((pathlib.Path(root) / "build.zen").read_text(), "build")
    cfg = interpret_build(bf)
    if cfg["target"] not in _TARGETS:
        raise SystemExit(f"build.zen: target {cfg['target']!r} is not supported yet "
                         f"(have: {', '.join(sorted(_TARGETS))}; wasm is the next backend)")
    print(f"── build.zen graph ──\n   Executable {cfg['name']}  "
          f"(main={cfg['main']}, out={cfg['out_dir']}, target={cfg['target']})")
    if cfg["cflags"] or cfg["links"]:
        print(f"   cc flags {cfg['cflags']}  links {cfg['links']}")
    for u in cfg["uses"]:
        print(f"   use \"{u['module']}\"  -> namespace `{u['ns']}`")
    for t in cfg["tests"]:
        print(f"   Test {t}  (declared)")

    files = load(root, skip={"build.zen"} | set(cfg["tests"]))
    load_uses(cfg, files)                          # install foreign-binding namespaces (b.use)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    print("\n── type checks ──")
    report(results, root)

    entry_ns = pathlib.Path(cfg["main"]).with_suffix("").as_posix().replace("/", ".")
    entry = f"{entry_ns}.main"
    if entry not in passing:
        raise SystemExit(f"\nentry '{entry}' did not type-check — nothing to run")

    # The entry must return i32 (printed) or void (run for effect) — anything else
    # has no sensible harness, so reject it rather than misformat (e.g. %d on a ptr).
    entry_ret = namespace.walk(entry).value.ret
    if entry_ret == PrimT(Prim.VOID):
        harness = (f'\nint main(void) {{\n    {c_name(entry)}();\n'
                   f'    return 0;\n}}\n')
    elif entry_ret == PrimT(Prim.I32):
        harness = (f'\n#include <stdio.h>\nint main(void) {{\n'
                   f'    printf("{cfg["name"]} -> %d\\n", {c_name(entry)}());\n'
                   f'    return 0;\n}}\n')
    else:
        raise SystemExit(f"\nentry '{entry}' must return i32 or void, not {show(entry_ret)}")
    out_dir = pathlib.Path(root) / cfg["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{cfg['name']}.c", out_dir / cfg["name"]
    cc_extra = [*cfg["cflags"], *(f"-l{lib}" for lib in cfg["links"])]   # build.zen flags
    exe_c = emit_c(files, passing, namespace, harness, roots={entry})        # DCE from the entry
    if compile_if_changed(cpath, bpath, exe_c, cc_extra):
        print(f"\n── compiled {cpath} ──")
    else:
        print(f"\n── {bpath} up to date (cached) ──")
    print(f"── running {bpath} ──")
    print(subprocess.run([str(bpath)], capture_output=True, text=True).stdout, end="")

    for t in cfg["tests"]:
        run_test_root(root, t, cc_extra)


def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "build"
    arg = argv[1] if len(argv) > 1 else "examples"
    (cmd_build if cmd == "build" else cmd_check)(arg)


if __name__ == "__main__":
    cli()
