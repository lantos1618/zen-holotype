"""Resolution + desugaring — the middle-end between parse and check.

Builds the global name trie, per-file scopes and the trait-impl registry; resolves
every type node to a fully-qualified form; enforces import visibility; and lowers
the `loop` sugar onto the `@while` primitive. After this pass, check and lower only
ever meet resolved types and structured `@while`.
"""
from __future__ import annotations
import dataclasses
from .ast import (Struct, EnumDecl, Fn, PrimT, NameT, PtrT, TVar, SliceT, FnT,
                  Index, Bin, Field, Let, Assign, While, Loop, TraitDecl, Impl, Emit, Lit, Bool, Var)
from .types import Namespace, TraitMethod, TypeErr, Unresolved, Private, Conflict

BUILTIN = {"Option"}


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
        sc: dict = {}

        def bind(name, path):
            # A local name resolves to ONE path. Two imports of different things under the
            # same name, or an import colliding with a local decl, is ambiguous — reject it
            # rather than silently take the last (re-binding the SAME path is a harmless dup).
            if sc.get(name, path) != path:
                raise Conflict(f"{f.ns}: '{name}' is bound to both '{sc[name]}' and '{path}'")
            sc[name] = path

        for imp in f.imports:
            for n in imp.names:
                bind(n, f"{imp.module}.{n}")
        for d in f.decls:
            if not isinstance(d, (Impl, Emit)):
                bind(d.name, f"{f.ns}.{d.name}")
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
        bound = scope.get(t.path)                # a tparam bound to a concrete type at instantiation
        if isinstance(bound, (PrimT, NameT, PtrT, SliceT, FnT, TVar)):   # (e.g. `sizeof(T)` in an instance)
            return bound
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
