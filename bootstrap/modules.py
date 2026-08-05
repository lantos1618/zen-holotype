"""bootstrap/modules.py — the file tree becomes one module graph.

`PLAN.md` 0.2: `<folder>/<folder>.zen` resolution, per-module namespaces, `*`
as the export gate, re-export as starred import bindings.

A name in scope is a *set* of bindings, never one: overloads resolve on
parameter types later (`same_name_overload`), and one declaration may arrive by
two paths (`diamond_reexport`). The `*` gate is checked twice — at the import
site and at the member-access site, because nothing is imported when `v.grow()`
leaks — and it is closed by construction: a name is visible only if something
in the program says it is, never by default.

Whole-program: one merged graph, which is what makes `Vec<Circle>` work when
`Vec` and `Circle` come from different modules.

This file imports `bootstrap/ast.py` and nothing else in `bootstrap/`. The
parser is *injected* (`build(root, parse=...)`), so this module never reaches
down into `cst.py`, and AST nodes are duck typed — class name plus dataclass
fields — so a rename in `ast.py` cannot silently change what is gated.

Determinism (`CONTRACT.md`): every dict is built in sorted key order, no set is
iterated, filesystem enumeration is sorted, and diagnostics are sorted by
position before they are handed back.
"""

from __future__ import annotations

import bisect
import os
from dataclasses import dataclass, is_dataclass
from dataclasses import fields as _dc_fields
from typing import Any, Callable, Iterable, Iterator, Optional


# --------------------------------------------------------------------------
# ast.py, and only ast.py
# --------------------------------------------------------------------------

def _load_ast() -> Any:
    """Import the sibling `ast.py` without ever picking up the stdlib `ast`."""
    try:  # package context: `from bootstrap import modules`
        from . import ast as mod  # type: ignore[attr-defined]
        return mod
    except ImportError:
        pass

    import sys

    cand = sys.modules.get("ast")
    if cand is not None and hasattr(cand, "Diag") and hasattr(cand, "Span"):
        return cand  # already imported as a top-level module by bootstrap.py

    try:
        import ast as mod  # type: ignore[no-redef]
        if hasattr(mod, "Diag") and hasattr(mod, "Span"):
            return mod
    except ImportError:
        pass

    import importlib.util

    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "bootstrap_ast", os.path.join(here, "ast.py")
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError("cannot locate bootstrap/ast.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ast = _load_ast()
Span = _ast.Span
Diag = _ast.Diag


# --------------------------------------------------------------------------
# source text — spans smaller than a node
# --------------------------------------------------------------------------
#
# `CONTRACT.md` freezes the AST, and no node carries a span for *one imported
# name*: `Import` holds `names` and one span for the whole binding. But
# `TESTING.md` wants the position of the first byte of the smallest offending
# node, and every module diagnostic in `tests/must-fail/modules/` points at a
# name or at a path inside a larger node. So sub-spans are recovered from the
# source text, which discovery has already read.

_IDENT_EXTRA = b"_"


def _is_ident_byte(b: int) -> bool:
    ch = bytes((b,))
    return ch.isalnum() or ch in _IDENT_EXTRA


class Source:
    """One file's bytes, with 1-based line / 1-based **byte** column mapping."""

    __slots__ = ("path", "text", "data", "_line_starts")

    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.text = text
        self.data = text.encode("utf-8")
        starts = [0]
        i = self.data.find(b"\n")
        while i != -1:
            starts.append(i + 1)
            i = self.data.find(b"\n", i + 1)
        self._line_starts = starts

    # -- offsets ----------------------------------------------------------

    def offset(self, pos: Any) -> int:
        line, col = int(pos[0]), int(pos[1])
        if line < 1:
            return 0
        if line > len(self._line_starts):
            return len(self.data)
        return min(self._line_starts[line - 1] + (col - 1), len(self.data))

    def position(self, off: int) -> tuple:
        off = max(0, min(off, len(self.data)))
        line = bisect.bisect_right(self._line_starts, off)
        return (line, off - self._line_starts[line - 1] + 1)

    def span(self, start_off: int, end_off: int) -> Any:
        return Span(
            file=self.path,
            start=self.position(start_off),
            end=self.position(end_off),
        )

    # -- searching --------------------------------------------------------

    def find_word(self, name: str, lo: int, hi: int) -> int:
        """Offset of the first whole-identifier `name` in `[lo, hi)`, or -1."""
        needle = name.encode("utf-8")
        if not needle:
            return -1
        lo = max(0, lo)
        hi = min(hi, len(self.data))
        i = self.data.find(needle, lo, hi)
        while i != -1:
            before_ok = i == 0 or not _is_ident_byte(self.data[i - 1])
            j = i + len(needle)
            after_ok = j >= len(self.data) or not _is_ident_byte(self.data[j])
            if before_ok and after_ok:
                return i
            i = self.data.find(needle, i + 1, hi)
        return -1

    def word_span(self, name: str, lo: int, hi: int) -> Optional[Any]:
        off = self.find_word(name, lo, hi)
        if off < 0:
            return None
        return self.span(off, off + len(name.encode("utf-8")))


def _span_bounds(source: Optional[Source], span: Any) -> tuple:
    """`(start_off, end_off)` for a node span, clamped to the file."""
    if source is None or span is None:
        return (0, 0)
    try:
        start = source.offset(span.start)
        end = source.offset(span.end)
    except Exception:
        return (0, len(source.data))
    if end < start:
        end = len(source.data)
    return (start, end)


# --------------------------------------------------------------------------
# generic AST walking — duck typed, so ast.py can move without breaking the gate
# --------------------------------------------------------------------------

_NON_NODE = frozenset({"Span", "Trivia", "Diag"})
_SKIP_FIELDS = frozenset({"span", "leading", "trailing"})


def _is_node(x: Any) -> bool:
    return (
        is_dataclass(x)
        and not isinstance(x, type)
        and type(x).__name__ not in _NON_NODE
        and hasattr(x, "span")
    )


def _kind(x: Any) -> str:
    return type(x).__name__


def _field_names(x: Any) -> tuple:
    return tuple(f.name for f in _dc_fields(x) if f.name not in _SKIP_FIELDS)


def _children(node: Any) -> Iterator[Any]:
    """Direct child nodes, in declaration order (deterministic)."""
    for name in _field_names(node):
        value = getattr(node, name, None)
        for item in _flatten(value):
            yield item


def _flatten(value: Any) -> Iterator[Any]:
    if _is_node(value):
        yield value
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _flatten(item)


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in _children(node):
        yield from _walk(child)


def _node_tuples(node: Any, *names: str) -> tuple:
    """Concatenate the named tuple-valued attributes that exist on `node`."""
    out = []
    for name in names:
        value = getattr(node, name, None)
        if isinstance(value, (tuple, list)):
            out.extend(x for x in value if _is_node(x))
    return tuple(out)


# --------------------------------------------------------------------------
# the graph's own vocabulary
# --------------------------------------------------------------------------

# what a declaration is, for the purpose of visibility
TYPE = "type"       # Struct / Enum / Alias
FN = "fn"           # top-level Function
CONST = "const"     # top-level Const
VARIANT = "variant"  # an enum's variant: exported with its enum
FIELD = "field"     # struct field:   storage per value
MEMBER = "member"   # struct const / method: one value per type


@dataclass(frozen=True)
class Entity:
    """One declared name, at the place it was declared."""

    kind: str
    name: str
    exported: bool
    module: str              # dotted module path that declares it
    owner: Optional[str]     # enclosing type, for variants and members
    node: Any
    span: Any

    @property
    def qualified(self) -> str:
        if self.owner:
            return "%s::%s.%s" % (self.module, self.owner, self.name)
        return "%s::%s" % (self.module, self.name)

    @property
    def identity(self) -> tuple:
        """*Which declaration* this is — not which name it declares.

        A name does not identify a declaration: `std.core.loop` declares seven
        `loop`s and `std.core.result` declares `Res<T>` and `Res<T, E>`, and
        overloading resolves those on parameter types and arity, later. The
        place it is written does identify it, so the span is the identity —
        and two paths to the *same* declaration (`diamond_reexport`) still
        collapse to one, which is the only collapsing anything here may do.
        """
        span = self.span
        where = ()
        if span is not None:
            where = (getattr(span, "file", ""), getattr(span, "start", ()),
                     getattr(span, "end", ()))
        return (self.module, self.owner or "", self.kind, self.name, where)

    @property
    def sort_key(self) -> tuple:
        return self.identity


@dataclass(frozen=True)
class Binding:
    """A name as seen from inside one module, bound to ONE declaration.

    An overload set is a *tuple of bindings* under one name: `lookup` and
    `scope` hand back every candidate, and picking among them is overload
    resolution's job, never the graph's.
    """

    name: str
    entity: Entity
    origin: str        # dotted path of the module the name was taken from
    exported: bool     # re-exported from the module that holds this binding
    span: Any          # where the binding is written
    source: str        # "local" | "import" | "prelude"

    @property
    def key(self) -> tuple:
        return self.entity.identity


@dataclass(frozen=True)
class ImportedName:
    name: str
    exported: bool
    span: Any


@dataclass
class ImportEdge:
    """`Token*, token_id* = token.token` — one binding line."""

    module: str                 # the importing module, dotted
    path: str                   # the written path, dotted
    target: Optional[str]       # the resolved module, dotted, or None
    names: tuple                # ImportedName
    span: Any                   # the whole line
    path_span: Any              # just the right-hand side


@dataclass
class ModuleInfo:
    name: str                   # the display name: the file stem
    dotted: str                 # identity: the path relative to the root
    path: str                   # the file, relative to the compilation root
    node: Any                   # the ast Module, or None if it did not parse
    source: Optional[Source]
    decls: dict                 # name -> tuple[Entity]   (declared here)
    types: dict                 # type name -> dict member name -> tuple[Entity]
    imports: tuple              # ImportEdge
    exports: dict               # name -> tuple[Binding]  (crosses the boundary)
    scope: dict                 # name -> tuple[Binding]  (visible inside)

    @property
    def deps(self) -> tuple:
        seen = []
        for edge in self.imports:
            if edge.target and edge.target != self.dotted and edge.target not in seen:
                seen.append(edge.target)
        return tuple(seen)


class Graph:
    """The whole program: every module, merged, plus every diagnostic."""

    def __init__(self, root: str, prelude: Optional[str]) -> None:
        self.root = root
        self.prelude = prelude
        self.modules: dict = {}
        self.order: tuple = ()
        self.diags: tuple = ()
        self.entities: dict = {}     # qualified name -> Entity
        self.members: dict = {}      # member name -> tuple[Entity]
        self.functions: dict = {}    # top-level fn name -> tuple[Entity]

    # -- queries, for sema.py --------------------------------------------

    def module(self, dotted: str) -> Optional[ModuleInfo]:
        return self.modules.get(dotted)

    def lookup(self, module: str, name: str) -> tuple:
        info = self.modules.get(module)
        return info.scope.get(name, ()) if info else ()

    def exports_of(self, module: str) -> dict:
        info = self.modules.get(module)
        return dict(info.exports) if info else {}

    def type_members(self, module: str, type_name: str) -> dict:
        info = self.modules.get(module)
        return dict(info.types.get(type_name, {})) if info else {}

    def members_named(self, name: str) -> tuple:
        return self.members.get(name, ())

    def visible(self, entity: Entity, from_module: str) -> bool:
        """The gate, in one line: your own module, or a `*`."""
        return entity.module == from_module or entity.exported

    def __iter__(self) -> Iterator[ModuleInfo]:
        for dotted in self.order:
            yield self.modules[dotted]


# --------------------------------------------------------------------------
# discovery
# --------------------------------------------------------------------------

ZEN = ".zen"


@dataclass(frozen=True)
class SourceFile:
    dotted: str      # identity: the path relative to the compilation root
    name: str        # display: the file stem
    path: str        # relative to the compilation root
    abspath: str
    aliases: tuple   # every dotted spelling that names this file


def _dotted_of(relpath: str) -> str:
    stem = relpath[: -len(ZEN)] if relpath.endswith(ZEN) else relpath
    return stem.replace(os.sep, ".").replace("/", ".")


def _search_roots(root: str, extra_roots: Iterable[str]) -> list:
    """The compilation root first, then `<root>/src`, then whatever was passed.

    `DESIGN.md` writes `std.core.result` and `STYLE.md` writes
    `src.parse.parse_expr` for a tree whose files are `src/std/core/result.zen`
    and `src/parse/parse_expr.zen`. Both spellings are real, so `src` is a
    search root as well as a directory, and one file answers to both names.
    """
    roots = [os.path.abspath(root)]
    src = os.path.join(roots[0], "src")
    if os.path.isdir(src):
        roots.append(src)
    for extra in extra_roots:
        extra = os.path.abspath(extra)
        if extra not in roots:
            roots.append(extra)
    return roots


def discover(root: str, extra_roots: Iterable[str] = ()) -> tuple:
    """Every `.zen` under the search roots, once each, sorted by path.

    A file reachable from two search roots is **one** module with two names,
    never two modules — otherwise every declaration in `src/` would exist twice
    in a whole-program graph.
    """
    roots = _search_roots(root, extra_roots)

    order: list = []           # abspath, in discovery order
    found: dict = {}           # abspath -> (name, path, [aliases])
    for base in roots:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for filename in sorted(filenames):
                if not filename.endswith(ZEN):
                    continue
                abspath = os.path.join(dirpath, filename)
                dotted = _dotted_of(os.path.relpath(abspath, base))
                entry = found.get(abspath)
                if entry is None:
                    display = os.path.relpath(abspath, roots[0]).replace(os.sep, "/")
                    found[abspath] = (filename[: -len(ZEN)], display, [dotted])
                    order.append(abspath)
                elif dotted not in entry[2]:
                    entry[2].append(dotted)

    files = []
    for abspath in order:
        name, path, aliases = found[abspath]
        files.append(SourceFile(
            dotted=aliases[0],
            name=name,
            path=path,
            abspath=abspath,
            aliases=tuple(aliases),
        ))
    return tuple(sorted(files, key=lambda f: f.dotted))


def _module_index(files: Iterable[SourceFile]) -> dict:
    """Dotted path -> module identity, including every shorthand.

    `gen/gen.zen` answers to `gen.gen` and to `gen`. That shorthand is not a
    convenience: `std.core` naming `std/core/core.zen` is what lets the prelude
    span several files instead of being one enormous one.
    """
    index: dict = {}
    ordered = sorted(files, key=lambda f: f.dotted)
    for f in ordered:
        for alias in f.aliases:
            index.setdefault(alias, f.dotted)
    for f in ordered:
        for alias in f.aliases:
            parts = alias.split(".")
            if len(parts) >= 2 and parts[-1] == parts[-2]:
                index.setdefault(".".join(parts[:-1]), f.dotted)
    return index


# --------------------------------------------------------------------------
# declarations: what a module declares, and how much of it is starred
# --------------------------------------------------------------------------

def _decl_span(node: Any, source: Optional[Source]) -> Any:
    """The span of a declaration's own name, not of its whole body."""
    span = getattr(node, "span", None)
    name = getattr(node, "name", None)
    if source is None or span is None or not isinstance(name, str):
        return span
    lo, hi = _span_bounds(source, span)
    found = source.word_span(name, lo, hi)
    return found or span


def _struct_members(node: Any) -> tuple:
    """Everything a struct body declares.

    `CONTRACT.md` gives `Struct(name, exported, tparams, fields, consts)`, and
    the grammar has *one* rule for fields and methods — so a method may land in
    either tuple depending on how `cst.py` reads `name* = sig {..}`. Both are
    read, plus anything else tuple-shaped that carries a name and a `*`, and
    `tparams` is excluded because a `TParam` has a name but no export marker.
    """
    out = []
    seen = []
    for attr in _field_names(node):
        if attr in ("tparams", "name", "variants"):
            continue
        value = getattr(node, attr, None)
        if not isinstance(value, (tuple, list)):
            continue
        for item in value:
            if not _is_node(item):
                continue
            if not isinstance(getattr(item, "name", None), str):
                continue
            if not isinstance(getattr(item, "exported", None), bool):
                continue
            if id(item) in seen:
                continue
            seen.append(id(item))
            out.append((attr, item))
    return tuple(out)


def _member_kind(attr: str, node: Any) -> str:
    """A field is storage per value; anything else is one value per type."""
    if attr == "fields" and _kind(node) not in ("Function",):
        return FIELD
    if _kind(node) == "Function":
        return MEMBER
    if getattr(node, "ty", None) is not None and getattr(node, "value", None) is None:
        return FIELD
    return MEMBER


def _collect_decls(info: ModuleInfo) -> None:
    """Fill `info.decls` and `info.types` from the module's own declarations."""
    node, source = info.node, info.source
    if node is None:
        return

    decls: dict = {}
    types: dict = {}

    def add(entity: Entity) -> None:
        decls.setdefault(entity.name, []).append(entity)

    for decl in _node_tuples(node, "decls"):
        kind = _kind(decl)
        name = getattr(decl, "name", None)
        exported = bool(getattr(decl, "exported", False))

        if kind == "Import":
            continue  # imports are edges, not declarations

        if not isinstance(name, str):
            continue

        if kind in ("Struct", "Enum", "Alias"):
            entity_kind = TYPE
        elif kind == "Function":
            entity_kind = FN
        else:
            entity_kind = CONST

        entity = Entity(
            kind=entity_kind,
            name=name,
            exported=exported,
            module=info.dotted,
            owner=None,
            node=decl,
            span=_decl_span(decl, source),
        )
        add(entity)

        if kind == "Enum":
            # A variant is exported with its enum: `CONTRACT.md` gives
            # `Variant(name, payload)` and no export marker of its own, so
            # `Mode` without a `*` keeps `Fast` and `Slow` inside the module.
            members = types.setdefault(name, {})
            for variant in _node_tuples(decl, "variants"):
                vname = getattr(variant, "name", None)
                if not isinstance(vname, str):
                    continue
                ventity = Entity(
                    kind=VARIANT,
                    name=vname,
                    exported=exported,
                    module=info.dotted,
                    owner=name,
                    node=variant,
                    span=_decl_span(variant, source) or entity.span,
                )
                add(ventity)
                members.setdefault(vname, []).append(ventity)

        if kind == "Struct":
            members = types.setdefault(name, {})
            for attr, member in _struct_members(decl):
                mentity = Entity(
                    kind=_member_kind(attr, member),
                    name=member.name,
                    exported=bool(getattr(member, "exported", False)),
                    module=info.dotted,
                    owner=name,
                    node=member,
                    span=_decl_span(member, source) or entity.span,
                )
                members.setdefault(member.name, []).append(mentity)

    # `A.impl(B, {..})` supplies values for a target's fields; they are members
    # of the target, and they are visible exactly as the target's own are.
    for decl in _node_tuples(node, "decls"):
        if _kind(decl) != "Impl":
            continue
        target = getattr(decl, "target", None)
        if not isinstance(target, str):
            continue
        members = types.setdefault(target, {})
        for entry in _node_tuples(decl, "entries"):
            ename = getattr(entry, "name", None)
            if not isinstance(ename, str):
                continue
            members.setdefault(ename, []).append(
                Entity(
                    kind=MEMBER,
                    name=ename,
                    exported=bool(getattr(entry, "exported", False)),
                    module=info.dotted,
                    owner=target,
                    node=entry,
                    span=_decl_span(entry, source),
                )
            )

    info.decls = {k: tuple(v) for k, v in sorted(decls.items())}
    info.types = {
        t: {m: tuple(e) for m, e in sorted(ms.items())}
        for t, ms in sorted(types.items())
    }


# --------------------------------------------------------------------------
# imports: the written line, and the spans inside it
# --------------------------------------------------------------------------

def _import_nodes(node: Any) -> tuple:
    """`Module.imports`, plus any `Import` that landed in `decls`."""
    out = list(_node_tuples(node, "imports"))
    ids = [id(x) for x in out]
    for decl in _node_tuples(node, "decls"):
        if _kind(decl) == "Import" and id(decl) not in ids:
            out.append(decl)
    return tuple(out)


def _import_edge(info: ModuleInfo, node: Any, index: dict) -> ImportEdge:
    source = info.source
    span = getattr(node, "span", None)
    lo, hi = _span_bounds(source, span)

    # the binding list ends at the operator, so names are searched only to its
    # left — `sum = sum.sum` must bind the `sum` on the left, not either right.
    lhs_end = hi
    if source is not None:
        eq = source.data.find(b"=", lo, hi)
        if eq != -1:
            lhs_end = eq

    names = []
    cursor = lo
    for entry in getattr(node, "names", ()) or ():
        if isinstance(entry, (tuple, list)) and len(entry) >= 2:
            name, exported = str(entry[0]), bool(entry[1])
        elif isinstance(entry, str):
            name, exported = entry, False
        else:
            name = str(getattr(entry, "name", ""))
            exported = bool(getattr(entry, "exported", False))
        nspan = span
        if source is not None and name:
            off = source.find_word(name, cursor, lhs_end)
            if off < 0:
                off = source.find_word(name, lo, lhs_end)
            if off >= 0:
                width = len(name.encode("utf-8"))
                nspan = source.span(off, off + width)
                cursor = off + width
        names.append(ImportedName(name=name, exported=exported, span=nspan))

    # the path is the first thing after the operator
    path_span = span
    if source is not None and lhs_end < hi:
        j = lhs_end
        while j < hi and source.data[j : j + 1] in (b"=", b":", b" ", b"\t"):
            j += 1
        if j < hi:
            end = j
            while end < hi and (
                _is_ident_byte(source.data[end]) or source.data[end : end + 1] == b"."
            ):
                end += 1
            path_span = source.span(j, max(end, j + 1))

    path = str(getattr(node, "path", "") or "")
    return ImportEdge(
        module=info.dotted,
        path=path,
        target=index.get(path),
        names=tuple(names),
        span=span,
        path_span=path_span,
    )


# --------------------------------------------------------------------------
# resolution: exports, re-export chains, and scopes
# --------------------------------------------------------------------------

class _Resolver:
    """Export tables, solved to a fixpoint rather than by recursion.

    A re-export chain is usually a DAG and one pass down it would do. But
    `std.core.display` needs `String` from `std.text`, and `std.text` wants
    `Display` for `str` — a real cycle in the standard library, and recursion
    through it can only guess an answer and then cache the guess. Re-export
    only ever *adds* names, so iterating to a fixpoint is monotone, terminates
    in the length of the longest chain, and needs no guess.
    """

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._exports: dict = {d: {} for d in graph.order}

    def solve(self) -> None:
        while True:
            changed = False
            for dotted in self.graph.order:
                table = self._compute(dotted)
                if _signature(table) != _signature(self._exports[dotted]):
                    self._exports[dotted] = table
                    changed = True
            if not changed:
                return

    def exports(self, dotted: str) -> dict:
        """`name -> tuple[Binding]` that cross this module's boundary."""
        return self._exports.get(dotted, {})

    def _compute(self, dotted: str) -> dict:
        info = self.graph.modules.get(dotted)
        if info is None:
            return {}
        table: dict = {}

        for name in sorted(info.decls):
            for entity in info.decls[name]:
                if not entity.exported:
                    continue
                self._bind(table, Binding(
                    name=name,
                    entity=entity,
                    origin=dotted,
                    exported=True,
                    span=entity.span,
                    source="local",
                ))

        for edge in info.imports:
            if edge.target is None or edge.target == dotted:
                continue
            upstream = self._exports.get(edge.target, {})
            for imported in edge.names:
                if not imported.exported:
                    continue  # no star: local to this module, never re-exported
                for binding in upstream.get(imported.name, ()):
                    self._bind(table, Binding(
                        name=imported.name,
                        entity=binding.entity,
                        origin=edge.target,
                        exported=True,
                        span=imported.span,
                        source="import",
                    ))

        return {k: tuple(v) for k, v in sorted(table.items())}

    @staticmethod
    def _bind(table: dict, binding: Binding) -> None:
        """Add a binding, collapsing the diamond and nothing else.

        `alpha` and `beta` both re-export `token`'s `Token`: one declaration
        arrived twice and must stay one name. Two *different* declarations with
        the same name are an overload set and both survive — every hop merges,
        none of them picks.
        """
        bucket = table.setdefault(binding.name, [])
        for existing in bucket:
            if existing.key == binding.key:
                return
        bucket.append(binding)


def _signature(table: dict) -> tuple:
    """Which declarations a table holds — cheap to compare, no AST equality."""
    return tuple((name, tuple(b.key for b in table[name])) for name in sorted(table))


def _module_scope(graph: Graph, resolver: _Resolver, info: ModuleInfo,
                  diags: list) -> None:
    """Everything nameable inside one module, and the import-site `*` gate."""
    table: dict = {}

    for name in sorted(info.decls):
        for entity in info.decls[name]:
            _Resolver._bind(table, Binding(
                name=name,
                entity=entity,
                origin=info.dotted,
                exported=entity.exported,
                span=entity.span,
                source="local",
            ))

    for edge in info.imports:
        if edge.target is None:
            diags.append(Diag(
                span=edge.path_span or edge.span,
                message="module %s not found" % (edge.path or "?"),
            ))
            continue
        if edge.target == info.dotted:
            # `self_import`: a module importing itself is not a cycle to
            # untangle, it is a typo, and it gets its own words.
            diags.append(Diag(
                span=edge.path_span or edge.span,
                message="module %s imports itself" % info.name,
            ))
            continue

        upstream = resolver.exports(edge.target)
        target = graph.modules[edge.target]
        for imported in edge.names:
            bindings = upstream.get(imported.name, ())
            if not bindings:
                diags.append(_not_exported(imported, target))
                continue
            for binding in bindings:
                _Resolver._bind(table, Binding(
                    name=imported.name,
                    entity=binding.entity,
                    origin=edge.target,
                    exported=imported.exported,
                    span=imported.span,
                    source="import",
                ))

    # The prelude is auto-imported into every module, and it loses every tie:
    # a name the module declares or imports explicitly keeps its meaning.
    prelude = graph.prelude
    if prelude and prelude != info.dotted:
        for name, bindings in sorted(resolver.exports(prelude).items()):
            if name in table:
                continue
            for binding in bindings:
                _Resolver._bind(table, Binding(
                    name=name,
                    entity=binding.entity,
                    origin=prelude,
                    exported=False,
                    span=binding.span,
                    source="prelude",
                ))

    info.scope = {k: tuple(v) for k, v in sorted(table.items())}


def _not_exported(imported: ImportedName, target: ModuleInfo) -> Any:
    """The gate's message.

    A name that exists but has no `*` and a name that does not exist are both
    errors — the gate never fails open — but they are different mistakes and
    they say so.
    """
    known = imported.name in target.decls or any(
        imported.name in (n.name for n in edge.names) for edge in target.imports
    )
    if known:
        message = "%s is not exported by module %s" % (imported.name, target.name)
    else:
        message = "module %s does not define %s" % (target.name, imported.name)
    return Diag(span=imported.span, message=message)


# --------------------------------------------------------------------------
# import cycles
# --------------------------------------------------------------------------

def _init_edges(graph: Graph) -> dict:
    """`module -> modules whose top-level constants it needs, to initialise`.

    An *import* cycle is not a problem a whole-program compiler has: one merged
    graph, and a type or a function has no initialisation order to get wrong.
    `std.core.display` needing `String` from `std.text` while `std.text` wants
    `Display` for `str` is a real cycle in the standard library and a legal
    one.

    A cycle in top-level *constants* is a different thing and stays an error:
    `seed_even = seed_odd + 1` beside `seed_odd = seed_even + 1` has no order
    that computes both, whatever the compiler does with the modules.
    """
    edges: dict = {}
    for dotted in graph.order:
        info = graph.modules[dotted]
        out: list = []
        for name in sorted(info.decls):
            for entity in info.decls[name]:
                if entity.kind != CONST:
                    continue
                value = getattr(entity.node, "value", None)
                if not _is_node(value):
                    continue
                for ref in _walk(value):
                    if _kind(ref) != "Path":
                        continue
                    rname = getattr(ref, "name", None)
                    if not isinstance(rname, str):
                        continue
                    for binding in info.scope.get(rname, ()):
                        other = binding.entity
                        if other.kind != CONST or other.module == dotted:
                            continue
                        if other.module not in out:
                            out.append(other.module)
        edges[dotted] = tuple(sorted(out))
    return edges


def _cycles(graph: Graph, diags: list) -> None:
    """Report each cyclic component once, from its smallest member.

    Canonicalising on the smallest member is what makes the message stable:
    the same cycle reads `even -> odd -> even` whichever module the walk
    happened to enter it from.
    """
    adjacency = _init_edges(graph)

    index: dict = {}
    low: dict = {}
    on_stack: dict = {}
    stack: list = []
    components: list = []
    counter = [0]

    def strongconnect(v: str) -> None:
        # iterative Tarjan: the compiler's own tree is deep enough to matter
        work = [(v, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = low[node] = counter[0]
                counter[0] += 1
                stack.append(node)
                on_stack[node] = True
            recursed = False
            neighbours = adjacency.get(node, ())
            for i in range(pi, len(neighbours)):
                w = neighbours[i]
                if w not in index:
                    work[-1] = (node, i + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if on_stack.get(w):
                    low[node] = min(low[node], index[w])
            if recursed:
                continue
            if low[node] == index[node]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == node:
                        break
                components.append(sorted(component))
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])

    for dotted in graph.order:
        if dotted not in index:
            strongconnect(dotted)

    for component in sorted(components):
        if len(component) < 2:
            continue
        start = component[0]
        members = list(component)
        path = _shortest_cycle(adjacency, start, members)
        if path is None:
            path = members + [start]
        names = [graph.modules[d].name for d in path]
        span, notes = _cycle_positions(graph, path)
        diags.append(Diag(
            span=span,
            message="import cycle: %s" % " -> ".join(names),
            notes=tuple(notes),
        ))


def _shortest_cycle(adjacency: dict, start: str, members: list) -> Optional[list]:
    """The shortest walk from `start` back to `start` inside the component."""
    inside = list(members)
    best: Optional[list] = None
    for first in sorted(adjacency.get(start, ())):
        if first not in inside:
            continue
        if first == start:
            return [start, start]
        # breadth-first, neighbours in sorted order, so ties break the same way
        queue = [[start, first]]
        seen = [start, first]
        while queue:
            path = queue.pop(0)
            for nxt in sorted(adjacency.get(path[-1], ())):
                if nxt == start:
                    found = path + [start]
                    if best is None or len(found) < len(best) or (
                        len(found) == len(best) and found < best
                    ):
                        best = found
                    queue = []
                    break
                if nxt in inside and nxt not in seen:
                    seen.append(nxt)
                    queue.append(path + [nxt])
    return best


def _cycle_positions(graph: Graph, path: list) -> tuple:
    """The span of the first edge, and every other edge as a note.

    The edge is a value dependency, but it is *written* as the import that
    brought the name in, so that is where the reader is sent.
    """
    spans = []
    for i in range(len(path) - 1):
        info = graph.modules.get(path[i])
        nxt = graph.modules.get(path[i + 1])
        if info is None or nxt is None:
            continue
        where = None
        for edge in info.imports:
            if edge.target == path[i + 1]:
                where = edge.path_span or edge.span
                break
        if where is None:
            where = getattr(info.node, "span", None)
        spans.append((where, "%s needs %s here" % (info.name, nxt.name)))
    if not spans or spans[0][0] is None:
        return (None, ())
    return (spans[0][0], tuple(s for s in spans[1:] if s[0] is not None))


# --------------------------------------------------------------------------
# the access-site gate: fields, constants and methods
# --------------------------------------------------------------------------
#
# The import-site gate cannot see `v.grow()` — nothing was imported. So the
# same `*` is checked again where a member is *reached*. The rule is closed by
# construction and cannot fire on a name it does not understand:
#
#   a member access `x.m` is an error only when the program declares at least
#   one `m` and *not one of them* is reachable from here.
#
# No candidate at all means the name belongs to a builtin (`.match`, `.try`) or
# to something sema will reject on its own — silence, not a guess. One reachable
# candidate means the access may stand, and any type error is sema's.

_COMPARISONS = frozenset({"==", "!=", "<=", ">=", "=>"})


def _write_target(node: Any) -> Optional[Any]:
    """The member being written, for the shapes an assignment can take.

    `CONTRACT.md` has no `Assign`: `Let` binds a `str`, so `c.total = 5` has to
    arrive as a `Binary` with an `=` operator — but a node named `Assign` is
    read too, so this gate does not depend on that reading being right.
    """
    kind = _kind(node)
    if kind == "Binary":
        op = getattr(node, "op", "")
        if isinstance(op, str) and op.endswith("=") and op not in _COMPARISONS:
            lhs = getattr(node, "lhs", None)
            if _kind(lhs) == "Member":
                return lhs
        return None
    if kind in ("Assign", "Store", "Set"):
        for attr in ("target", "lhs", "place"):
            value = getattr(node, attr, None)
            if _kind(value) == "Member":
                return value
    if kind in ("Let", "ExprStmt"):
        value = getattr(node, "target", None)
        if _kind(value) == "Member":
            return value
    return None


def _member_span(info: ModuleInfo, node: Any) -> Any:
    """The member name itself — the smallest offending node, per TESTING.md."""
    span = getattr(node, "span", None)
    source = info.source
    name = getattr(node, "name", None)
    if source is None or span is None or not isinstance(name, str):
        return span
    lo, hi = _span_bounds(source, span)
    dot = source.data.rfind(b".", lo, hi)
    if dot != -1:
        found = source.word_span(name, dot + 1, hi)
        if found is not None:
            return found
    found = source.word_span(name, lo, hi)
    return found or span


def _check_accesses(graph: Graph, info: ModuleInfo, diags: list) -> None:
    if info.node is None:
        return

    writes: list = []
    accesses: list = []
    for node in _walk(info.node):
        target = _write_target(node)
        if target is not None:
            writes.append(id(target))
        if _kind(node) == "Member":
            accesses.append(node)

    for node in accesses:
        name = getattr(node, "name", None)
        if not isinstance(name, str) or not name:
            continue
        candidates = graph.members.get(name, ()) + graph.functions.get(name, ())
        if not candidates:
            continue  # not a name this program declares: not this gate's call

        reachable = [c for c in candidates if graph.visible(c, info.dotted)]
        if not reachable:
            owner = sorted(candidates, key=lambda c: c.sort_key)[0]
            diags.append(Diag(
                span=_member_span(info, node),
                message="%s is not exported by module %s" % (
                    name, graph.modules[owner.module].name),
            ))
            continue

        if id(node) not in writes:
            continue

        # `*` on a field means readable outside the module; mutation only ever
        # goes through exported methods (DESIGN.md, Declarations).
        fields = [c for c in reachable if c.kind == FIELD]
        if not fields:
            continue
        if any(c.module == info.dotted for c in fields):
            continue
        owner = sorted(fields, key=lambda c: c.sort_key)[0]
        diags.append(Diag(
            span=_member_span(info, node),
            message="%s is not writable outside module %s" % (
                name, graph.modules[owner.module].name),
        ))


# --------------------------------------------------------------------------
# the merged graph
# --------------------------------------------------------------------------

def _merge(graph: Graph) -> None:
    """One table for the whole program — the reason `Vec<Circle>` works."""
    entities: dict = {}
    members: dict = {}
    functions: dict = {}

    def keep(table: dict, key: str, entity: Entity) -> None:
        bucket = table.setdefault(key, [])
        if not any(e.identity == entity.identity for e in bucket):
            bucket.append(entity)

    for dotted in graph.order:
        info = graph.modules[dotted]
        for name in sorted(info.decls):
            for entity in info.decls[name]:
                keep(entities, entity.qualified, entity)
                if entity.kind == FN:
                    keep(functions, name, entity)
                if entity.kind == VARIANT:
                    keep(members, name, entity)
        for type_name in sorted(info.types):
            for member_name in sorted(info.types[type_name]):
                for entity in info.types[type_name][member_name]:
                    keep(entities, entity.qualified, entity)
                    if entity.kind == VARIANT:
                        continue  # already added above, from decls
                    keep(members, member_name, entity)

    # A qualified name is a *set* too: `std.core.result::Res` is `Res<T>` and
    # `Res<T, E>`, and arity is what tells them apart.
    graph.entities = {
        k: tuple(sorted(entities[k], key=lambda e: e.sort_key)) for k in sorted(entities)
    }
    graph.members = {
        k: tuple(sorted(v, key=lambda e: e.sort_key)) for k, v in sorted(members.items())
    }
    graph.functions = {
        k: tuple(sorted(v, key=lambda e: e.sort_key))
        for k, v in sorted(functions.items())
    }


def _topological(graph: Graph) -> tuple:
    """Modules in dependency order; cyclic ones keep their sorted order."""
    order: list = []
    state: dict = {}

    def visit(dotted: str) -> None:
        mark = state.get(dotted)
        if mark == "done" or mark == "open":
            return
        state[dotted] = "open"
        info = graph.modules.get(dotted)
        if info is not None:
            for dep in info.deps:
                if dep in graph.modules:
                    visit(dep)
        state[dotted] = "done"
        order.append(dotted)

    for dotted in sorted(graph.modules):
        visit(dotted)
    return tuple(order)


def _diag_key(diag: Any) -> tuple:
    span = getattr(diag, "span", None)
    if span is None:
        return ("", 0, 0, getattr(diag, "message", ""))
    start = getattr(span, "start", (0, 0)) or (0, 0)
    return (getattr(span, "file", ""), start[0], start[1],
            getattr(diag, "message", ""))


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

PRELUDE = "std.core"


def build(
    root: str,
    parse: Optional[Callable[[str, str], Any]] = None,
    *,
    parsed: Optional[dict] = None,
    extra_roots: Iterable[str] = (),
    prelude: Optional[str] = PRELUDE,
) -> Graph:
    """Resolve a compilation root into one module graph.

    `parse(path, text)` returns an `ast.Module` — or `(Module, diags)`. It is
    injected rather than imported: `modules.py` sits above `cst.py` and never
    reaches down into it. `parsed` takes an already-built `{path: Module}` map
    instead, for callers that have parsed the tree themselves.
    """
    files = discover(root, extra_roots)
    index = _module_index(files)

    graph = Graph(os.path.abspath(root), None)
    diags: list = []

    for f in files:
        source = None
        node = None
        if parsed is not None and f.path in parsed:
            node = parsed[f.path]
            try:
                with open(f.abspath, "r", encoding="utf-8") as handle:
                    source = Source(f.path, handle.read())
            except OSError:
                source = None
        elif parse is not None:
            try:
                with open(f.abspath, "r", encoding="utf-8") as handle:
                    text = handle.read()
            except OSError as exc:
                diags.append(Diag(
                    span=Span(file=f.path, start=(1, 1), end=(1, 1)),
                    message="cannot read %s: %s" % (f.path, exc.strerror),
                ))
                continue
            source = Source(f.path, text)
            result = parse(f.path, text)
            if isinstance(result, tuple) and len(result) == 2:
                node, produced = result
                if produced:
                    diags.extend(produced)
            else:
                node = result

        graph.modules[f.dotted] = ModuleInfo(
            name=f.name,
            dotted=f.dotted,
            path=f.path,
            node=node,
            source=source,
            decls={},
            types={},
            imports=(),
            exports={},
            scope={},
        )

    for dotted in sorted(graph.modules):
        info = graph.modules[dotted]
        _collect_decls(info)
        if info.node is not None:
            info.imports = tuple(
                _import_edge(info, node, index) for node in _import_nodes(info.node)
            )

    graph.prelude = index.get(prelude) if prelude else None
    graph.order = _topological(graph)
    _merge(graph)

    resolver = _Resolver(graph)
    resolver.solve()
    for dotted in graph.order:
        graph.modules[dotted].exports = resolver.exports(dotted)
    for dotted in graph.order:
        _module_scope(graph, resolver, graph.modules[dotted], diags)

    _cycles(graph, diags)  # after scopes: an init edge is a resolved name

    for dotted in graph.order:
        _check_accesses(graph, graph.modules[dotted], diags)

    graph.diags = tuple(sorted(diags, key=_diag_key))
    return graph


resolve = build
