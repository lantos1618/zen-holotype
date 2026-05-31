"""Zen v2 front end: parse with the tree-sitter-zen2 grammar, build the v2 AST.

`parse(src) -> tuple[Decl]`. The kernel walks Decls; a Record is a bag of Decls;
`:` is a requirement, `=`/`:=` a provision.
"""
from __future__ import annotations
import warnings
import pathlib
from tree_sitter import Language, Parser
from .ast import (Decl, NamedT, PtrT, FnT, Record, Sum, Fn,
                  Lit, Str, Bool, Var, Field, Call, Bin, RecordLit, Match, Ctor)

_ROOT = pathlib.Path(__file__).parent.parent.parent      # repo root
_SO = _ROOT / "build" / "zen2.so"
_GRAMMAR = _ROOT / "tree-sitter-zen2"


def _language():
    so, src = _SO, _GRAMMAR / "src" / "parser.c"
    if not so.exists() or so.stat().st_mtime < src.stat().st_mtime:
        so.parent.mkdir(exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Language.build_library(str(so), [str(_GRAMMAR)])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Language(str(so), "zen2")


_PARSER = Parser()
_PARSER.set_language(_language())


def _t(n):
    return n.text.decode()


def _field(n, name):
    return n.child_by_field_name(name)


def _named(n):
    return [c for c in n.named_children if c.type != "comment"]


# ── decls ────────────────────────────────────────────────────────────────────
def _path(n):                                   # name_path / type_path -> tuple of idents
    return tuple(_t(c) for c in n.named_children if c.type == "ident")


def _tparams(n):
    tp = _field(n, "tparams")
    if tp is None:
        return ()
    out = []
    for c in _named(tp):
        if c.type == "tparam":
            b = _field(c, "bound")
            out.append((_t(_field(c, "name")), _t(b) if b else None))
    return tuple(out)


def _decl(n):
    typ = _field(n, "type")
    val = _field(n, "value")
    bind = _field(n, "bind")
    return Decl(
        name=_path(_field(n, "name")),
        pub=_field(n, "pub") is not None,
        tparams=_tparams(n),
        type=_type(typ) if typ is not None else None,
        bind=_t(bind) if bind is not None else None,
        value=_value(val) if val is not None else None,
    )


# ── types ────────────────────────────────────────────────────────────────────
def _type(n):
    t = n.type
    if t == "record":
        return Record(tuple(_decl(d) for d in _named(n) if d.type == "decl"))
    if t == "named_t":
        args = tuple(_type(a) for a in _named(n) if a.type in _TYPE_NODES)
        return NamedT(_path(_field(n, "name")), args)
    if t == "ptr_t":
        return PtrT(_t(_field(n, "dir")), _type(next(c for c in _named(n) if c.type in _TYPE_NODES)))
    if t == "fn_t":
        kids = [c for c in _named(n) if c.type in _TYPE_NODES]
        return FnT(tuple(_type(k) for k in kids[:-1]), _type(kids[-1]))
    raise ValueError(f"v2: not a type node: {t}")


_TYPE_NODES = {"record", "named_t", "ptr_t", "fn_t"}


# ── values ───────────────────────────────────────────────────────────────────
def _value(n):
    t = n.type
    if t == "fn":
        params = tuple((_t(_field(p, "name")), _type(_field(p, "type")))
                       for p in _named(n) if p.type == "param")
        ret = _field(n, "ret")
        body = _field(n, "body")
        return Fn(params, _type(ret) if ret else None, _block(body))
    if t == "sum":
        variants = []
        for v in _named(n):
            if v.type == "variant":
                pl = _field(v, "payload")
                variants.append((_t(_field(v, "name")), _type(pl) if pl else None))
        return Sum(tuple(variants))
    if t == "record":
        return Record(tuple(_decl(d) for d in _named(n) if d.type == "decl"))
    return _expr(n)                              # a plain expression value


def _block(n):                                   # body of a fn: stmts (Decl for a let, else Expr)
    out = []
    for s in _named(n):
        if s.type == "let_":
            ty = _field(s, "type")
            out.append(Decl(name=(_t(_field(s, "name")),), bind=_t(_field(s, "bind")),
                            type=_type(ty) if ty else None, value=_expr(_field(s, "value"))))
        else:
            out.append(_expr(s))
    return tuple(out)


# ── expressions ──────────────────────────────────────────────────────────────
def _expr(n):
    t = n.type
    if t == "integer":
        return Lit(int(_t(n)))
    if t == "string":
        return Str(_t(n)[1:-1])
    if t == "boolean":
        return Bool(_t(n) == "true")
    if t == "ident":
        return Var(_t(n))
    if t == "paren":
        return _expr(_named(n)[0])
    if t == "field":
        return Field(_expr(_field(n, "obj")), _t(_field(n, "name")))
    if t == "call":
        return Call(_expr(_field(n, "fn")), tuple(_args(n)))
    if t == "record_lit":
        fields = tuple((_t(_field(fi, "name")), _expr(_field(fi, "value")))
                       for fi in _named(n) if fi.type == "field_init")
        return RecordLit(_t(_field(n, "type")), fields)
    if t == "match":
        return Match(_expr(_field(n, "subj")),
                     tuple(_arm(a) for a in _named(n) if a.type == "arm"))
    if t == "binary":
        kids = _named(n)
        op = next(c.type for c in n.children if c.type in _BINOPS)
        return Bin(op, _expr(kids[0]), _expr(kids[1]))
    raise ValueError(f"v2: unhandled expr node: {t}")


_BINOPS = {"+", "-", "*", "==", "<", ">", "<=", ">=", "&&", "||"}


def _args(n):
    a = next((c for c in n.named_children if c.type == "args"), None)
    return [_expr(c) for c in _named(a)] if a else []


def _arm(n):
    body = _expr(_field(n, "body"))
    inner = _named(_field(n, "pat"))             # pattern wraps ctor_pat/int/bool; "_" is anon
    if not inner:
        return (Ctor("_"), body)                 # wildcard
    p = inner[0]
    if p.type == "ctor_pat":
        b = _field(p, "bind")
        return (Ctor(_t(_field(p, "name")), _t(b) if b else None), body)
    if p.type == "integer":
        return (Lit(int(_t(p))), body)
    return (Bool(_t(p) == "true"), body)


def parse(src: str):
    root = _PARSER.parse(bytes(src, "utf8")).root_node
    if root.has_error:
        raise SyntaxError("v2 parse error")
    return tuple(_decl(d) for d in _named(root) if d.type == "decl")
