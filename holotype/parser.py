"""Front end: parse Zen with the tree-sitter grammar, convert the CST into
holotype's ast.py dataclasses. Exposes `parse(src, ns) -> File`.

The grammar lives in tree-sitter-zen/; its C parser is compiled to build/zen.so.
"""
from __future__ import annotations
import warnings, pathlib
from tree_sitter import Language, Parser
from .ast import (Dir, Prim, PrimT, NameT, PtrT, SliceT, FnT, Field_, Struct, Variant,
                  EnumDecl, Param, Fn, Import, File, MethodSig, TraitDecl, Impl,
                  Emit, Lit, Bool, Var, Field, Bin, Not, Call, Str, StructLit, SliceLit,
                  Index, MethodCall, EnumCtor, Let, Assign, While, Loop, Arm, Match, Closure)

_ROOT = pathlib.Path(__file__).parent.parent          # repo root (package lives in holotype/)
_SO   = _ROOT / "build" / "zen.so"
_GRAMMAR = _ROOT / "tree-sitter-zen"

_PRIM = {p.value: p for p in Prim}
_DIR  = {d.value: d for d in Dir}
_TYPES = {"primitive", "pointer", "slice_type", "fn_type", "named_type"}


def _language():
    so, src = _SO, _GRAMMAR / "src" / "parser.c"
    if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
        so.parent.mkdir(exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Language.build_library(str(so), [str(_GRAMMAR)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Language(str(so), "zen")


_PARSER = Parser()
_PARSER.set_language(_language())


def _t(n):                       # node text
    return n.text.decode()


def _named(n):                   # named children minus comments
    return [c for c in n.named_children if c.type != "comment"]


def _field(n, name):
    return n.child_by_field_name(name)


# ───────────────────────── CST -> AST ───────────────────────────────────────
def _type(n):
    if n.type == "primitive":
        return PrimT(_PRIM[_t(n)])
    if n.type == "pointer":
        return PtrT(_DIR[_t(_field(n, "dir"))], _type(_field(n, "pointee")))
    if n.type == "slice_type":
        return SliceT(_type(_field(n, "elem")))
    if n.type == "fn_type":                              # (A, T) Ret — a closure type
        ret = _field(n, "ret")
        params = tuple(_type(c) for c in _named(n) if c.type in _TYPES and c != ret)
        return FnT(params, _type(ret))
    if n.type == "named_type":
        args = tuple(_type(c) for c in _named(n) if c.type in _TYPES)
        return NameT(_t(_field(n, "name")), args)
    raise ValueError(f"not a type node: {n.type}")


def _expr(n):
    e = _expr_inner(n)
    object.__setattr__(e, "pos", n.start_point)     # (row, col) for diagnostics
    return e


def _expr_inner(n):
    t = n.type
    if t == "integer":
        return Lit(int(_t(n)))
    if t == "boolean":
        return Bool(_t(n) == "true")
    if t == "string":
        return Str(_t(n)[1:-1])
    if t == "identifier":
        return Var(_t(n))
    if t == "parenthesized":
        return _expr(_named(n)[0])
    if t == "binary":
        kids = _named(n)
        op = next(c.type for c in n.children
                  if c.type in ("+", "-", "*", "==", "<", ">", "<=", ">=", "&&", "||"))
        return Bin(op, _expr(kids[0]), _expr(kids[1]))
    if t == "unary_op":
        return Not(_expr(_named(n)[0]))
    if t == "call":
        fn = _field(n, "fn")
        if fn.type == "field_access":          # b.add(x)  ->  a method call
            return MethodCall(_expr(_field(fn, "obj")), _t(_field(fn, "name")), tuple(_args(n)))
        return Call(_t(fn), tuple(_args(n)))    # len(v) / addr(x)
    if t == "field_access":
        return Field(_expr(_field(n, "obj")), _t(_field(n, "name")))
    if t == "index":                            # xs[i]
        return Index(_expr(_field(n, "seq")), _expr(_field(n, "idx")))
    if t == "slice_literal":                    # [a, b, c]
        return SliceLit(tuple(_expr(c) for c in _named(n)))
    if t == "struct_literal":
        fields = tuple((_t(_field(fi, "name")), _expr(_field(fi, "value")))
                       for fi in _named(n) if fi.type == "field_init")
        return StructLit(_t(_field(n, "type")), fields)
    if t == "enum_ctor":
        return EnumCtor(_t(_field(n, "name")), tuple(_args(n)))
    if t == "match":
        return Match(_expr(_field(n, "subject")), tuple(_arm(a) for a in _named(n)
                                                        if a.type == "match_arm"))
    if t == "closure":                          # (a, x) { a + x } — an inlined function value
        params = tuple(_t(p) for p in n.children_by_field_name("params") if p.type == "identifier")
        body = tuple(_stmt(s) for s in _named(_field(n, "body")))
        return Closure(params, body)
    raise ValueError(f"unhandled expr node: {t}")


def _arm(n):
    pat = _named(_field(n, "pat"))[0]               # ctor_pattern | literal_pattern | wildcard
    body = _expr(_field(n, "body"))
    if pat.type == "wildcard":
        return Arm(None, None, body)
    if pat.type == "literal_pattern":
        return Arm(None, None, body, _expr(_named(pat)[0]))
    binding = _field(pat, "binding")
    return Arm(_t(_field(pat, "name")), _t(binding) if binding else None, body)


def _args(n):
    arg = next((c for c in n.named_children if c.type == "arguments"), None)
    return [_expr(c) for c in _named(arg)] if arg else []


def _stmt(n):
    if n.type == "let_binding":                     # x := value
        return Let(_t(_field(n, "name")), _expr(_field(n, "value")))
    if n.type == "assign":                          # lvalue = value
        return Assign(_expr(_field(n, "target")), _expr(_field(n, "value")))
    if n.type == "while_prim":                      # @while(cond) { body } — the primitive
        body = tuple(_stmt(s) for s in _named(_field(n, "body")))
        return While(_expr(_field(n, "cond")), body)
    if n.type == "loop_":                           # loop(n, (h, i) { body }) / loop((h) { body })
        cnt = _field(n, "count")
        params = tuple(_t(p) for p in n.children_by_field_name("params") if p.type == "identifier")
        body = tuple(_stmt(s) for s in _named(_field(n, "body")))
        return Loop(_expr(cnt) if cnt is not None else None, params, body)
    if n.type == "loop_method":                     # xs.loop((h, i, x) { body }) == loop(xs, …)
        params = tuple(_t(p) for p in n.children_by_field_name("params") if p.type == "identifier")
        body = tuple(_stmt(s) for s in _named(_field(n, "body")))
        return Loop(_expr(_field(n, "recv")), params, body)
    return _expr(n)


def _tparams(n):
    """(names, bounds) — bounds maps a param name to its trait bound, e.g. T: Area."""
    tp = _field(n, "tparams")
    if not tp:
        return (), {}
    names, bounds = [], {}
    for c in tp.named_children:
        if c.type != "tparam":
            continue
        nm = _t(_field(c, "name"))
        names.append(nm)
        b = _field(c, "bound")
        if b is not None:
            bounds[nm] = _t(b)
    return tuple(names), bounds


def _fn(n):
    pub = _field(n, "vis") is not None          # a glued `*` after the name = public
    params = [Param(_t(_field(p, "name")), _type(_field(p, "type")))
              for p in _named(n) if p.type == "param"]
    body = [_stmt(s) for s in _named(_field(n, "body"))]
    names, bounds = _tparams(n)
    rn = _field(n, "ret")
    ret = _type(rn) if rn is not None else None          # None -> infer from the body
    return Fn(_t(_field(n, "name")), params, ret, body, pub, names, bounds)


def _decl(n):
    pub = _field(n, "vis") is not None          # a glued `*` after the name = public
    if n.type == "struct":
        fields = [Field_(_t(_field(f, "name")), _type(_field(f, "type")))
                  for f in _named(n) if f.type == "field"]
        return Struct(_t(_field(n, "name")), fields, pub, _tparams(n)[0])
    if n.type == "enum":
        variants = [Variant(_t(_field(v, "name")),
                            _type(_field(v, "payload")) if _field(v, "payload") else None)
                    for v in _named(n) if v.type == "variant"]
        return EnumDecl(_t(_field(n, "name")), variants, pub, _tparams(n)[0])
    if n.type == "function":
        return _fn(n)
    if n.type == "trait":
        sigs = []
        for m in _named(n):
            if m.type != "method_sig":
                continue
            tks = [c for c in _named(m) if c.type in _TYPES]   # param types … then ret (last)
            sigs.append(MethodSig(_t(_field(m, "name")),
                                  tuple(_type(t) for t in tks[:-1]), _type(tks[-1])))
        return TraitDecl(_t(_field(n, "name")), sigs, pub)
    if n.type == "impl":
        methods = [_fn(f) for f in _named(n) if f.type == "function"]
        return Impl(_t(_field(n, "trait")), _t(_field(n, "type")), methods)
    if n.type == "extern":
        params = [Param(_t(_field(p, "name")), _type(_field(p, "type")))
                  for p in _named(n) if p.type == "param"]
        return Fn(_t(_field(n, "name")), params, _type(_field(n, "ret")),
                  body=None, extern=True)
    if n.type == "emit":
        return Emit(_expr(_field(n, "value")))
    raise ValueError(f"unhandled decl: {n.type}")


def _import(n):
    names = [_t(c) for c in n.named_children if c.type == "identifier"]
    mp = next(c for c in n.named_children if c.type == "module_path")
    return Import(names, ".".join(_t(g) for g in mp.named_children))


def _first_error(n):
    """Depth-first hunt for the first ERROR / MISSING node, for a located message."""
    if n.type == "ERROR" or n.is_missing:
        return n
    for c in n.children:
        hit = _first_error(c)
        if hit is not None:
            return hit
    return None


def parse(src: str, ns: str) -> File:
    root = _PARSER.parse(bytes(src, "utf8")).root_node
    if root.has_error:
        bad = _first_error(root) or root
        r, c = bad.start_point                 # 0-based row, col from tree-sitter
        what = "missing" if bad.is_missing else f"unexpected {_t(bad)!r}"
        raise SyntaxError(f"{ns}:{r + 1}:{c + 1}: parse error ({what})")
    imports, decls = [], []
    for n in _named(root):
        if n.type == "import":
            imports.append(_import(n))
        else:
            decls.append(_decl(n))
    return File(ns, imports, decls)
