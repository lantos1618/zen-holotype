#!/usr/bin/env python3
"""Two definitions must never answer one `x.f(..)`.

DESIGN.md:396 states the rule and even promises this check: "the candidates
are the members of `x`'s type, its impls' and its bounds' methods, and every
exported free function whose **first parameter type** is `x`'s type. Two
modules may both declare `size` as long as they take different first
parameters -- and if they take the same one, that is a real collision and is
reported." Nothing was reporting it.

WHY IT MATTERS MORE HERE THAN IN A LANGUAGE WITH OVERLOADING. Zen has none:
one name, one function, always. So two candidates for one call is not a
resolution question the language has an answer to -- it is a coin flip, and
the two implementations flip it differently. `gen_c_own.zen:132` wrote
`be.close_block()` when a `close_block` method on `CBackend` and a
`close_block` free function taking `(be :: CBackend)` both existed. `./zen`
took the method; `bootstrap/` took the free function and emitted a stray `}`
after every block, so the fixpoint could not clear stage 2.

**It was invisible to all 227 passing corpus tests**, because the corpus is
compiled by `./zen`, which happened to pick the branch the author meant. That
is the signature of the class: an ambiguity costs nothing at all until a
second implementation disagrees, and by then it presents as miscompiled
output a hundred lines from the declaration. Cheap to detect, expensive to
debug, so the detection lives in the build.

A PLAIN GREP FOR DUPLICATE NAMES DOES NOT FIND THIS, which is why nothing
did. A method is indented inside a struct body and a free function sits at
column 0; they are never duplicate top-level names. The collision only exists
because UFCS makes `be.f()` and `f(be)` the same call, so finding it means
knowing which parameter is the receiver -- a parse, not a scan.

HOW IT PARSES. `tools/parse/cst.py`, the real grammar, not a regex over source
text. What stays heuristic is the step after: matching a first parameter's
type name to a struct declaration. That is name resolution, and this script
does not implement Zen's. It resolves through the file's own imports where it
can, falls back to a tree-wide unique spelling where it cannot, and gives up
when a spelling is ambiguous -- `Span`, `Pos` and `Diag` are each declared by
more than one module. Every one of those choices is made to MISS a collision
rather than invent one, because this runs on every `make test` and a gate
nobody can make green gets deleted.

ALSO DELIBERATELY MISSED: aliases (`A = B` then a free function on `A`),
differing arities (`x.f(a)` picks the 2-parameter candidate unambiguously),
and variadics (where arity is not a number). Each is a real hole. None is
worth a false positive.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# py-tree-sitter's deprecated-Language warning; `make grammar` builds the .so
# this path loads, and the noise is not this check's to report.
warnings.filterwarnings("ignore", category=FutureWarning)

# THE DEBT, keyed "<module of the free function>:<Type>.<name>".
#
# NOT an exemption list. With no overloading there is no shape a second
# candidate can take that is deliberate, so nothing belongs here permanently
# -- every entry is a collision that IS a defect and is written down because
# it is latent: nothing calls it through a dot today, so it is miscompilation
# waiting for a call site rather than miscompilation now.
#
# All four found on the first run, and all four are the same thing: a private
# helper someone wrote without noticing the type already had that method.
#
# TWO OF THE FOUR WERE LIVE, and the first report of them said all four were
# dead. `at(argv, i)` ran three times in the CLI's argument scan and
# `at(out, j)` twice in the emitter's insertion sort -- both shadowing
# `Vec.at`, which returns `Res<T>` where the helpers returned the element
# with a default. So do not read a finding here as latent until you have
# grepped for the call sites: "nothing calls it yet" is a claim about the
# tree, not a property of the collision, and it is the claim most likely to
# be wrong.
#
# Deleting a line is how one closes; the staleness check below makes that
# mandatory rather than optional. Adding a line requires this sentence to be
# written again for the new case, which is the point.
OWED: dict[str, str] = {}


def modules():
    """(module path, Module) for every source file, or None on a parse error.

    The module path is the dotted form an import writes: `src/sema/sema_ty.zen`
    is `sema.sema_ty`, matching DESIGN.md's `<folder>/<folder>.zen` layout.
    """
    from tools.parse import cst

    out = []
    for path in sorted(ROOT.glob("src/**/*.zen")):
        rel = path.relative_to(ROOT).as_posix()
        module, diags = cst.parse_file(str(path), str(ROOT))
        if module is None:
            print(f"ufcs: {rel} does not parse; `make parse` owns that failure")
            print(f"    {diags[0] if diags else ''}")
            return None
        out.append((rel[len("src/"):-len(".zen")].replace("/", "."), module))
    return out


def receiver(fn, tparams: set[str], own: str | None) -> str | None:
    """The type name `fn`'s first parameter binds, if it names a receiver.

    `None` when there is no first parameter, when its type is not a plain
    name (a union, an array, a function type -- none of which a struct
    declaration can be), or when the name is one of `fn`'s own type
    parameters, which resolves per instantiation and not to a declaration.
    """
    if not fn.params:
        return None
    name = getattr(fn.params[0].ty, "name", None)
    if name is None or name in tparams:
        return None
    # `@Self` inside a struct body means the struct being declared. `::` vs
    # `:` on the parameter is not consulted: mutability does not change which
    # candidates a call site has, only what they may do.
    return own if name == "@Self" else name


def arity(fn) -> int | None:
    """The parameter count, or `None` when arity is not a number.

    A variadic parameter makes one function answer many arities, so comparing
    counts would be comparing the wrong thing. Skipping is the false negative
    this file prefers.
    """
    if any(getattr(p.ty, "name", None) == "..." for p in fn.params):
        return None
    return len(fn.params)


def method_table(files) -> dict[str, dict[str, list]]:
    """type name -> method name -> [(arity, span)].

    A method is a member function whose first parameter is the receiver. A
    member function whose first parameter is something else is an ASSOCIATED
    function -- `Duration.seconds(n: u64)`, DESIGN.md:412 -- reached as
    `Type.name(..)` and never through a value, so it is not a UFCS candidate
    and cannot collide with one.

    Impl entries count. `Circle.impl(Display, {text: ..})` is what makes
    `circle.text()` resolve, so it puts `text` in `Circle`'s method set as
    surely as writing it in the body would.
    """
    table: dict[str, dict[str, list]] = {}

    def put(ty, fn):
        n = arity(fn)
        if n is not None:
            table.setdefault(ty, {}).setdefault(fn.name, []).append((n, fn.span))

    for _, module in files:
        for decl in module.decls:
            kind = type(decl).__name__
            if kind == "Struct":
                tparams = {t.name for t in decl.tparams}
                for member in decl.fields:
                    if type(member).__name__ != "Function":
                        continue
                    if receiver(member, tparams, decl.name) == decl.name:
                        put(decl.name, member)
            elif kind == "Impl":
                for entry in decl.entries:
                    if type(entry).__name__ == "Function" and entry.params:
                        put(decl.target, entry)
    return table


def declared_in(files) -> dict[str, list[str]]:
    """struct name -> the module paths declaring it."""
    where: dict[str, list[str]] = {}
    for path, module in files:
        for decl in module.decls:
            if type(decl).__name__ == "Struct":
                where.setdefault(decl.name, []).append(path)
    return where


def resolves(name: str, module, where: dict[str, list[str]]) -> bool:
    """Does `name`, written in `module`, denote the struct this script found?

    Three ways, in order of how much they prove:

      1. `module` declares it. Certain.
      2. `module` imports it from a path that declares it. Certain -- this is
         the whole point of DESIGN.md:389, "a name that is not imported is not
         visible", and it is what keeps `Diag` in `lex` from being read as
         `Diag` in `sema`.
      3. Exactly one module in the tree declares the spelling. Not proof, but
         the only wrong answer it can give needs a SECOND declaration, and
         there is none. This is what covers the prelude, which no file writes
         an import line for.

    A spelling declared by several modules and imported by none of them
    reaches no case and is dropped. That is a miss, on purpose.
    """
    homes = where.get(name)
    if not homes:
        return False
    for imp in module.imports:
        if imp.path in homes and any(n == name for n, _ in imp.names):
            return True
    return len(homes) == 1


def main() -> int:
    if not (ROOT / "grammar" / "zen.so").exists():
        print("ufcs: run `make grammar` first", file=sys.stderr)
        return 2

    files = modules()
    if files is None:
        return 1

    methods = method_table(files)
    where = declared_in(files)

    collisions, owed, scanned = [], [], 0
    for path, module in files:
        for decl in module.decls:
            if type(decl).__name__ != "Function":
                continue
            ty = receiver(decl, {t.name for t in decl.tparams}, None)
            if ty is None or not resolves(ty, module, where):
                continue
            scanned += 1
            n = arity(decl)
            for other, span in methods.get(ty, {}).get(decl.name, []):
                if other != n:
                    continue
                # Keyed by MODULE and not by line: a line number moves every
                # time someone edits above it, and a ledger that goes stale
                # on an unrelated edit is a ledger people learn to silence.
                key = f"{path}:{ty}.{decl.name}"
                if key in OWED:
                    owed.append(key)
                else:
                    collisions.append((ty, decl.name, n, decl.span, span))

    for ty, name, n, free, method in collisions:
        print(f"{free}: free function `{name}` takes {ty} as its first parameter")
        print(f"{method}: and so does the method of that name")
        print(f"    both answer `x.{name}(..)` at arity {n}, and Zen has no"
              f" overloading — one of them is dead or wrong.")

    if collisions:
        print(f"\nufcs: {len(collisions)} ambiguous call target(s)."
              f"\n  Rename one, or delete it if it is a copy of the other — it"
              f"\n  usually is. The two compilers will not agree here and the"
              f"\n  corpus cannot tell you which one it got, because the corpus is"
              f"\n  built by only one of them. If it cannot be fixed today, write"
              f"\n  it into OWED in {Path(__file__).name} with the sentence saying"
              f"\n  why, so the debt can shrink and cannot quietly grow.")
        return 1

    # A ledger entry whose collision is gone is a fiction the next reader
    # trusts. Same rule the ledger in tools/gates/faults_reachable.zen runs.
    stale = sorted(set(OWED) - set(owed))
    for key in stale:
        print(f"ufcs: {key} is in OWED and no longer collides."
              f" Delete its line from {Path(__file__).name} — the debt is paid.")
    if stale:
        return 1

    # "0 ambiguous over 3210 sites" and "0 ambiguous over nothing at all" are
    # the same verdict line with a different number in it, and the second one
    # is what a moved src/, a renamed struct field on the CST, or a parse that
    # yielded no functions produces. A setup error must not be able to
    # impersonate a result -- scripts/fixpoint.sh says it in those words.
    if not scanned or not methods:
        print(f"ufcs: scanned {scanned} free function(s) against {len(methods)}"
              f" type(s) with methods -- one of those is zero, so this gate"
              f" checked nothing. src/ moved, or the parse stopped yielding"
              f" declarations. Fix the script; do not read this as green.",
              file=sys.stderr)
        return 2

    print(f"ufcs: {scanned} ufcs free function(s) over {len(methods)} type(s)"
          f" with methods, {len(owed)} ambiguous and written down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
