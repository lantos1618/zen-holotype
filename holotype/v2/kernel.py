"""v2 kernel — step 1: fold the whole program into the one trie.

Every decl becomes a node at its path; a Record's members and a Sum's variants
nest underneath. So a type, its fields, its impls, and their methods all live as
paths under the type — `Circle`, `Circle.r`, `Circle.Area`, `Circle.Area.area`.
The structure *is* the symbol table; nothing lives outside it.
"""
from __future__ import annotations
from holotype.types import Namespace
from .ast import Record, Sum


def into_trie(decls, ns: Namespace | None = None, prefix: str = "") -> Namespace:
    ns = ns or Namespace()
    for d in decls:
        path = f"{prefix}." if prefix else ""
        path += ".".join(d.name)
        ns.insert(path, d)
        if isinstance(d.value, Record):                 # a product → its fields nest under it
            into_trie(d.value.decls, ns, path)
        elif isinstance(d.value, Sum):                  # a sum → its variants nest under it
            for vname, payload in d.value.variants:
                ns.insert(f"{path}.{vname}", payload)
    return ns
