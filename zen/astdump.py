"""A canonical, deterministic serialization of the parsed AST (ast.py).

This is the *reference* for parity work: the Python front end's AST, rendered as a stable
s-expression that a future Zen-written parser can be diffed against. It is structural only
— source positions (`pos`) and resolve/check-populated state (`scope`) are excluded, so
the dump depends on the program's STRUCTURE, not on formatting or on which pipeline stage
produced the node. `ast_hash` reduces a dump to a short stable fingerprint for golden
tests and the eventual fixpoint check.

    from zen.parser import parse
    from zen.astdump import dump, ast_hash
    dump(parse("main* = () i32 { 42 }", "m"))
    # (File ns='m' imports=[] decls=[(Fn name='main' params=[] ret=(PrimT prim=I32) …)])
"""
from __future__ import annotations

import hashlib
from dataclasses import fields, is_dataclass
from enum import Enum

# Fields that are NOT part of a program's structure: source location, and the local-name
# scope maps that resolve() fills in later. Excluding them makes the dump stage-stable.
_SKIP = {"pos", "scope"}


def dump(node) -> str:
    """Render `node` (an AST dataclass, list, enum, or scalar) as a canonical s-expr."""
    if isinstance(node, (list, tuple)):
        return "[" + " ".join(dump(x) for x in node) + "]"
    if isinstance(node, dict):                       # e.g. a Fn's `bounds` — sorted for determinism
        return "{" + " ".join(f"{k}:{dump(v)}" for k, v in sorted(node.items())) + "}"
    if is_dataclass(node) and not isinstance(node, type):
        inner = " ".join(f"{f.name}={dump(getattr(node, f.name))}"
                         for f in fields(node) if f.name not in _SKIP)
        return f"({type(node).__name__} {inner})" if inner else f"({type(node).__name__})"
    if isinstance(node, Enum):                       # Dir / Prim -> their member name (I32, READ, …)
        return node.name
    return repr(node)                                # str / int / bool / None


def ast_hash(node) -> str:
    """A short, stable fingerprint of `node`'s structure (sha256 of its canonical dump)."""
    return hashlib.sha256(dump(node).encode()).hexdigest()[:16]
