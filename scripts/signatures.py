#!/usr/bin/env python3
"""The declared surface of `src/`, one line per declaration, grouped by file.

WHAT IT IS FOR. Reading 100k lines to find the two functions that should be
one is not a job anyone does twice. The surface -- names, parameter types,
field sets, variant payloads -- is where near-duplication is visible, and it
is two percent of the bytes. This prints that two percent so a reader (or a
model) can hold the whole tree at once.

WHY THE FILE PATH IS A HEADER AND NOT A COLUMN. `docs/STYLE.md`, "How files
are named and split": a prefix names its own folder and a file name means
something. So a signature's placement is part of the signature -- a `Span`
helper sitting in `gen_c_emit.zen` is a finding even when the signature
itself is fine -- and the grouping is what makes that legible.

IT PARSES, IT DOES NOT GREP. `tools/parse/cst.py`, the real grammar. STYLE.md:23
records why: `if` occurs 101 times in src/ and zero of them are code, 52 being
inside string literals. A regex over declarations would report the compiler's
own diagnostics as functions.

NOT A GATE. Nothing here passes or fails, there is no ledger, and `make test`
does not run it. It is a lens; when the answer it gives is wrong the fix is to
read the source, not to add an exemption.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# py-tree-sitter's deprecated-Language warning; `make grammar` builds the .so
# this path loads, and the noise is not this script's to report.
warnings.filterwarnings("ignore", category=FutureWarning)

# An expression is printed by slicing its source span, so a default reads the
# way it was written. Long ones are cut: past this, a default is a program and
# belongs in the file, not the digest.
EXPR_CUT = 48


class Source:
    """Byte offsets for a file, so a span can be sliced back to its text."""

    def __init__(self, path: Path):
        self.data = path.read_bytes()
        self.starts = [0]
        for i, byte in enumerate(self.data):
            if byte == ord("\n"):
                self.starts.append(i + 1)

    def slice(self, span) -> str:
        def offset(pos):
            line, col = pos
            return self.starts[min(line, len(self.starts)) - 1] + col - 1

        text = self.data[offset(span.start):offset(span.end)].decode("utf8", "replace")
        text = " ".join(text.split())
        return text if len(text) <= EXPR_CUT else text[:EXPR_CUT - 1] + "…"


def ty(node, src: Source) -> str:
    """A type, spelled the way a declaration spells it."""
    kind = type(node).__name__ if node is not None else "None"
    if kind == "Named":
        args = ", ".join(ty(a, src) for a in node.args)
        return f"{node.name}<{args}>" if node.args else node.name
    if kind == "Union":
        return " | ".join(ty(m, src) for m in node.members)
    if kind == "FnType":
        return f"({params(node.params, src)}) {ty(node.ret, src)}".rstrip()
    if kind == "ArrayType":
        return f"[{ty(node.elem, src)}; {src.slice(node.count.span)}]"
    if kind == "Infer":
        return "_"
    if kind == "Unit":
        return "()"
    return ""  # a missing type


def params(items, src: Source) -> str:
    """`::` is kept: a parameter the callee may write is a different contract
    from one it may only read, and that difference is what a reviewer looking
    for two functions that should be one needs to see."""
    out = []
    for p in items:
        spelled = ty(p.ty, src)
        sep = " :: " if p.mutable else ": "
        out.append(f"{p.name}{sep}{spelled}" if spelled else p.name)
    return ", ".join(out)


def tparams(items, src: Source) -> str:
    if not items:
        return ""
    out = []
    for t in items:
        bound = ty(t.bound, src) if t.bound is not None else ""
        out.append(f"{t.name}: {bound}" if bound else t.name)
    return "<" + ", ".join(out) + ">"


def signature(fn, src: Source) -> str:
    """`name*<T>(a: i32) Res<T>` -- the `*` is the export marker.

    A function that writes no return type gets a `Unit` carrying the whole
    declaration's span, which is how an omitted return is told apart from a
    written `()`. The distinction is worth keeping: `Res<(), E>` is a common
    real return and printing it as `Res<>` would invent a second spelling.
    """
    star = "*" if fn.exported else ""
    written = not (type(fn.ret).__name__ == "Unit" and fn.ret.span == fn.span)
    ret = ty(fn.ret, src) if written else ""
    head = f"{fn.name}{star}{tparams(fn.tparams, src)}({params(fn.params, src)})"
    return f"{head} {ret}".rstrip()


def form_tag(fn) -> str:
    """A bodiless member is a signature the implementor supplies; a `::=` one
    is overridable. Both change what the declaration MEANS, so both show."""
    return "" if fn.form == "sealed" else f"  [{fn.form}]"


def line(span) -> int:
    return span.start[0]


def is_trait(decl) -> bool:
    """A struct is read as a trait when every function member is bodiless and
    it stores nothing. HEURISTIC: Zen has no `trait` keyword -- a trait is a
    struct of signatures -- so this is a reading of the shape, not a fact the
    grammar states. A struct mixing storage with signatures reads as a struct.
    """
    fns = [f for f in decl.fields if type(f).__name__ == "Function"]
    storage = [f for f in decl.fields if type(f).__name__ == "Field"]
    return bool(fns) and not storage and all(f.body is None for f in fns)


def emit_struct(decl, src: Source, out: list) -> None:
    kind = "trait" if is_trait(decl) else "struct"
    star = "*" if decl.exported else ""
    out.append(f"{line(decl.span):5}  {kind} {decl.name}{star}{tparams(decl.tparams, src)}")
    for const in decl.consts:
        spelled = ty(const.ty, src)
        typed = f": {spelled}" if spelled else ""
        out.append(f"{line(const.span):5}    const {const.name}{typed}"
                   f" = {src.slice(const.value.span)}")
    for member in decl.fields:
        if type(member).__name__ == "Function":
            out.append(f"{line(member.span):5}    ."
                       f"{signature(member, src)}{form_tag(member)}")
            continue
        sep = "::" if member.mutable else ":"
        star = "*" if member.exported else ""
        default = "" if member.default is None else f" = {src.slice(member.default.span)}"
        out.append(f"{line(member.span):5}    {member.name}{star} {sep}"
                   f" {ty(member.ty, src)}{default}")


def emit_enum(decl, src: Source, out: list) -> None:
    star = "*" if decl.exported else ""
    out.append(f"{line(decl.span):5}  enum {decl.name}{star}{tparams(decl.tparams, src)}")
    for variant in decl.variants:
        payload = "" if variant.payload is None else f": {ty(variant.payload, src)}"
        out.append(f"{line(variant.span):5}    | {variant.name}{payload}")


def emit_impl(decl, src: Source, out: list) -> None:
    out.append(f"{line(decl.span):5}  impl {decl.target} : {decl.trait}")
    for entry in decl.entries:
        if type(entry).__name__ == "Function":
            out.append(f"{line(entry.span):5}    .{signature(entry, src)}")
        else:
            # `Circle.impl(Display, {text = describe})` -- the method is
            # supplied by naming an existing function, so the value is the
            # signature that matters and it lives elsewhere in the digest.
            out.append(f"{line(entry.span):5}    .{entry.name} = "
                       f"{src.slice(entry.value.span)}")


def emit_file(path: Path, module, out: list) -> None:
    src = Source(path)
    out.append("")
    out.append(f"### {path.relative_to(ROOT).as_posix()}")
    for decl in module.decls:
        kind = type(decl).__name__
        if kind == "Function":
            out.append(f"{line(decl.span):5}  fn {signature(decl, src)}{form_tag(decl)}")
        elif kind == "Struct":
            emit_struct(decl, src, out)
        elif kind == "Enum":
            emit_enum(decl, src, out)
        elif kind == "Impl":
            emit_impl(decl, src, out)
        elif kind == "Alias":
            star = "*" if decl.exported else ""
            out.append(f"{line(decl.span):5}  alias {decl.name}{star}"
                       f" = {ty(decl.target, src)}")
        elif kind == "Const":
            spelled = ty(decl.ty, src)
            typed = f": {spelled}" if spelled else ""
            out.append(f"{line(decl.span):5}  const {decl.name}{typed}"
                       f" = {src.slice(decl.value.span)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, help="write here instead of stdout")
    ap.add_argument("--root", default="src", help="subtree to walk (default: src)")
    args = ap.parse_args()

    if not (ROOT / "grammar" / "zen.so").exists():
        print("signatures: run `make grammar` first", file=sys.stderr)
        return 2

    from tools.parse import cst

    out: list[str] = []
    files = 0
    for path in sorted((ROOT / args.root).glob("**/*.zen")):
        module, diags = cst.parse_file(str(path), str(ROOT))
        if module is None:
            rel = path.relative_to(ROOT).as_posix()
            print(f"signatures: {rel} does not parse; `make parse` owns that")
            print(f"    {diags[0] if diags else ''}")
            return 1
        emit_file(path, module, out)
        files += 1

    text = "\n".join(out).lstrip("\n") + "\n"
    if args.out:
        args.out.write_text(text)
        print(f"signatures: {files} file(s), {text.count(chr(10))} lines,"
              f" {len(text.encode())} bytes -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
