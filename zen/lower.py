"""Hook-based transcribe to C. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced upstream).

This module is the declaration layer (struct/enum/proto/def). The two leaves it
builds on were split out to keep each file cohesive:
  • lower_type.py — C type names, mangling, the slice/uid registries (a pure leaf).
  • lower_expr.py — c_expr, the intrinsics, closures, match + statement lowering.
The public names other modules import (c_name, mangle, inst_name, impl_cname,
is_template, c_type, slice_typedefs, the _slice_reg/_uid_reg/_CENV registries) are
re-exported here so `from .lower import …` is unchanged.
"""
from __future__ import annotations
from .ast import Struct, EnumDecl, Fn
from .lower_type import (  # noqa: F401  (re-exported public surface)
    c_name, mangle, inst_name, impl_cname, is_template, c_type, slice_typedefs,
    _c_str, _uid, _tmp, _slice_reg, _uid_reg, _CMAP, _DIRTAG)
from .lower_expr import (  # noqa: F401  (re-exported public surface)
    c_expr, c_stmt, c_block, c_match, c_match_stmt, _CENV)
from .types import subst
from .resolve import _mentions   # a body-use predicate: does this body read this name?


# ───────────────────────── declaration codegen ─────────────────────────────
def _params(d: Fn) -> str:
    return ", ".join(f"{c_type(p.type)} {p.name}" for p in d.params) or "void"


def c_struct_fwd(cn) -> str:
    """A forward declaration `typedef struct <cn> <cn>;`. Emitted for every struct/enum
    tag before any slice typedef, so a `slice_<cn>` (which uses only `<cn>*`) compiles
    regardless of whether the struct's full definition comes before or after it."""
    return f"typedef struct {cn} {cn};"


def c_struct(qual, d: Struct, sub=None, cname=None) -> str:
    sub = sub or {}
    body = " ".join(f"{c_type(subst(f.type, sub))} {f.name};" for f in d.fields)
    return f"struct {cname or c_name(qual)} {{ {body} }};"      # definition (tag forward-declared)


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
    return f"struct {cn} {{ int32_t tag;{union} }};\nenum {{ {tags} }};"


def c_proto(qual, d: Fn, cname=None) -> str:
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)});"


def c_def(qual, d: Fn, namespace, scope, cname=None) -> str:
    locals_ = {p.name: p.type for p in d.params}
    # an EMPTY body [] still lowers through c_block, which emits "" for a void return and
    # "return 0;" for a value return — so `() void {}` doesn't get a bogus `return 0;`.
    body = c_block(d.body, locals_, namespace, scope, d.ret) if d.body is not None else "return 0;"
    # a param the body never reads is fine in zen (e.g. a stateless trait impl's self);
    # `(void)p;` silences -Werror=unused-parameter without changing behaviour.
    voids = "".join(f"(void){p.name}; " for p in d.params if d.body and not _mentions(d.body, p.name))
    return f"{c_type(d.ret)} {cname or c_name(qual)}({_params(d)}) {{ {voids}{body} }}"
