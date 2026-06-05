"""The type-erasure leaf of C lowering: C type names, mangling, and the
reproducible node-id / slice-typedef registries.

This is a leaf layer — it depends only on the AST node classes, never on the
expression/declaration lowering that builds on it. The type system ERASES here:
direction -> const, Option -> a plain pointer (nullability already enforced
upstream).
"""
from __future__ import annotations
from .ast import Dir, Prim, PrimT, NameT, PtrT, TVar, SliceT, FnT, Fn

_CMAP = {Prim.I32: "int32_t", Prim.I64: "int64_t", Prim.U8: "uint8_t",
         Prim.BOOL: "bool", Prim.VOID: "void", Prim.STR: "const char*"}


def _c_str(s: str) -> str:
    """Escape a string's bytes for a C string literal (backslash first, so it doesn't
    double-escape the others)."""
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))

_slice_reg: dict = {}             # mangle(elem) -> elem type, for emitting slice typedefs
_uid_reg: dict = {}               # id(node) -> stable small int (see _uid)


def _uid(e) -> int:
    """A reproducible, address-free integer name for a node. `id(e)` is a memory
    address — using it for temp/subject names made the emitted C differ run-to-run
    (breaking ccache, reproducible builds, and C diffs). Here we hand out small ints
    in first-encounter order instead: same AST → same traversal → same names. Reset
    per emit_c. AST nodes live for the whole emit, so `id` is never reused under us."""
    return _uid_reg.setdefault(id(e), len(_uid_reg))


def _tmp(e, i) -> str:
    return f"_v{_uid(e)}_{i}"


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
    raise TypeError(f"no C type for {t!r} — an unresolved/unknown type reached codegen")
