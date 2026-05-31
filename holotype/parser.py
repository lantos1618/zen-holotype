"""Front end: parse Zen with the tree-sitter grammar, convert the CST into
holotype's ast.py dataclasses. Exposes `parse(src, ns) -> File`.

The grammar lives in tree-sitter-zen/; its C parser is compiled to build/zen.so.
"""
from __future__ import annotations
import warnings, pathlib
from tree_sitter import Language, Parser
from .ast import (Dir, Prim, PrimT, NameT, PtrT, Field_, Struct, Variant,
                  EnumDecl, Param, Fn, Import, File,
                  Lit, Var, Field, Bin, Call, Str, StructLit, MethodCall, EnumCtor)

_ROOT = pathlib.Path(__file__).parent.parent          # repo root (package lives in holotype/)
_SO   = _ROOT / "build" / "zen.so"
_GRAMMAR = _ROOT / "tree-sitter-zen"

_PRIM = {p.value: p for p in Prim}
_DIR  = {d.value: d for d in Dir}
_TYPES = {"primitive", "pointer", "named_type"}


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
    if n.type == "named_type":
        args = tuple(_type(c) for c in _named(n) if c.type in _TYPES)
        return NameT(_t(_field(n, "name")), args)
    raise ValueError(f"not a type node: {n.type}")


def _expr(n):
    t = n.type
    if t == "integer":
        return Lit(int(_t(n)))
    if t == "string":
        return Str(_t(n)[1:-1])
    if t == "identifier":
        return Var(_t(n))
    if t == "parenthesized":
        return _expr(_named(n)[0])
    if t == "binary":
        kids = _named(n)
        op = next(c.type for c in n.children if c.type in ("+", "-", "*"))
        return Bin(op, _expr(kids[0]), _expr(kids[1]))
    if t == "call":
        fn = _field(n, "fn")
        if fn.type == "field_access":          # b.add(x)  ->  a method call
            return MethodCall(_expr(_field(fn, "obj")), _t(_field(fn, "name")), tuple(_args(n)))
        return Call(_t(fn), tuple(_args(n)))    # len(v) / addr(x)
    if t == "field_access":
        return Field(_expr(_field(n, "obj")), _t(_field(n, "name")))
    if t == "struct_literal":
        fields = tuple((_t(_field(fi, "name")), _expr(_field(fi, "value")))
                       for fi in _named(n) if fi.type == "field_init")
        return StructLit(_t(_field(n, "type")), fields)
    if t == "enum_ctor":
        return EnumCtor(_t(_field(n, "name")), tuple(_args(n)))
    raise ValueError(f"unhandled expr node: {t}")


def _args(n):
    arg = next((c for c in n.named_children if c.type == "arguments"), None)
    return [_expr(c) for c in _named(arg)] if arg else []


def _decl(n):
    pub = any(c.type == "pub" for c in n.children)
    if n.type == "struct":
        fields = [Field_(_t(_field(f, "name")), _type(_field(f, "type")))
                  for f in _named(n) if f.type == "field"]
        return Struct(_t(_field(n, "name")), fields, pub)
    if n.type == "enum":
        variants = [Variant(_t(_field(v, "name")),
                            _type(_field(v, "payload")) if _field(v, "payload") else None)
                    for v in _named(n) if v.type == "variant"]
        return EnumDecl(_t(_field(n, "name")), variants, pub)
    if n.type == "function":
        params = [Param(_t(_field(p, "name")), _type(_field(p, "type")))
                  for p in _named(n) if p.type == "param"]
        body = [_expr(s) for s in _named(_field(n, "body"))]
        return Fn(_t(_field(n, "name")), params, _type(_field(n, "ret")), body, pub)
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
