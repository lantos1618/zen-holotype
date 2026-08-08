#!/usr/bin/env python3
"""A map of `bootstrap/gen_c.py` whose coordinates still resolve.

`docs/GENC_REFERENCE_MAP.md` is built out of hundreds of claims shaped
`symbol (line)` and `file:line`. Every one of them is a promise that a
reader who jumps there lands on the thing being described. Nothing kept
that promise: the map was written against a 5731-line gen_c.py, the file
is longer now, and every claim below the first insertion point had
drifted. A map with shifted coordinates is worse than no map -- it sends
a reader CONFIDENTLY to the wrong function, which is more expensive than
sending them nowhere.

The document also named the revision it was written against, and that
was wrong too, in a way no reader could have caught: at the commit it
named, gen_c.py is 5651 lines -- the very number the opening sentence
says the file is NOT. A header that identifies itself cannot be trusted
to identify itself. So nothing here reads the document's own account of
what it describes; every claim is checked against the file on disk.

FOUR KINDS OF CLAIM, strongest first.

  def    `sym` (N)      -- sym is defined in gen_c.py; N must be its
                           definition line, or inside N-M.
  quote  "text" (N)     -- the sentence must appear within N-M.
  path   file.py:N      -- the file must exist and hold that line, and
                           if a `def`/`class`/assignment sits on the
                           same line of the doc, it is checked as `def`.
  text   `sym` (N)      -- sym is NOT a definition (a local, a struct
                           field, an emitted C name), so all that can be
                           checked is that it literally occurs in N-M.

WHAT THIS CANNOT CHECK, and it matters, because green here is not the
same as the document being true.

  * It checks COORDINATES, never prose. A paragraph may describe the
    wrong thing entirely at a line number that resolves. One claim in
    this document pointed at `Makefile:52-56` and said it documented the
    determinism harness; those lines are a different target altogether,
    and the numbers were in bounds the whole time. Nothing below would
    have caught it. A human found it and a human is still what finds it.
  * A bare `(N-M)` with no symbol and no quote next to it has nothing to
    anchor to, so only its bounds are checked. Those are counted and
    printed SEPARATELY -- a large range-only count is the document
    telling you how much of itself it cannot defend, and the repair for
    any one of them is to put a symbol or a quotation beside it.
  * A `text` claim on a token as common as `self` passes almost
    anywhere. Those are counted as weak and printed, rather than being
    quietly folded into the pass total.
  * It cannot know about a claim the document SHOULD make and does not.

The printed counts are the point of the counting: `refmap: N claims
checked` dropping is how you notice that the document changed shape and
this script stopped reading half of it.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs/GENC_REFERENCE_MAP.md"
SUBJECT = ROOT / "bootstrap/gen_c.py"

# A token occurring on more than this many lines makes a `text` claim
# vacuous -- it would pass at almost any number.
COMMON = 100

PAREN = re.compile(r"\((\d{2,4})(?:[-–](\d+))?\)")
PATH = re.compile(r"([\w./-]*(?:\.py)|Makefile):(\d+)(?:[-–](\d+))?")
TICK = re.compile(r"`([^`]+)`[*_\s]*$")
QUOTED = re.compile(r"\"([^\"]{8,160})\"[^()\"]{0,25}$")
IDENT = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
ONLINE = re.compile(r"^\s*(?:def|class)\s+(\w+)|^\s*(\w+)\s*=\s*\S")


def definitions(src: str) -> dict[str, list[tuple[int, int]]]:
    """name -> [(first line, last line)] for every def, class and assignment.

    Class members are recorded under both `member` and `Class.member`, so
    the document may name either.
    """
    found: dict[str, list[tuple[int, int]]] = {}

    def add(name, node):
        span = (node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno)
        found.setdefault(name, []).append(span)

    def walk(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                add(child.name, child)
                if owner:
                    add(f"{owner}.{child.name}", child)
                walk(child, child.name if isinstance(child, ast.ClassDef) else owner)
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        add(target.id, child)
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                add(child.target.id, child)

    walk(ast.parse(src), "")
    return found


def norm(text: str) -> str:
    """Comment punctuation and line wrapping removed, so a sentence the
    document quotes can be matched against source that wraps it."""
    return re.sub(r"\s+", " ", re.sub(r"[#\"'`]", " ", text)).strip()


def literal_of(quote: str) -> str:
    """The part of a quotation before any `<name>` or `%s` stand-in.

    The document writes a format string's placeholder as `<name>`, so the
    text after it never matches. The prefix still pins the line.
    """
    return norm(re.split(r"[<%]", quote)[0])


def resolve(name: str) -> Path | None:
    base = name.split("/")[-1]
    for candidate in (ROOT / name.lstrip("/"), ROOT / "bootstrap" / base, ROOT / base):
        if candidate.is_file():
            return candidate
    return None


class Claim:
    def __init__(self, kind, line, shown, lo, hi, sym=None, path=None):
        self.kind, self.line, self.shown = kind, line, shown
        self.lo, self.hi, self.sym, self.path = lo, hi, sym, path


def harvest(doc: str) -> list[Claim]:
    """Every coordinate the document states, bound to what anchors it."""
    claims: list[Claim] = []
    fence = False
    for n, line in enumerate(doc.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue

        for m in PATH.finditer(line):
            name, lo, hi = m.group(1), int(m.group(2)), m.group(3)
            shown = m.group(0)
            sym = None
            if name.endswith("gen_c.py"):
                on = ONLINE.match(line)
                tick = TICK.search(line[: m.start()].rstrip(" ,("))
                if on:
                    sym = on.group(1) or on.group(2)
                elif tick and IDENT.match(tick.group(1)):
                    sym = tick.group(1)
            claims.append(Claim("path", n, shown, lo, int(hi) if hi else lo,
                                sym=sym, path=name))
        if fence:
            continue

        for m in PAREN.finditer(line):
            lo, hi = int(m.group(1)), m.group(2)
            hi = int(hi) if hi else lo
            before = line[: m.start()]
            tick = TICK.search(before)
            quote = QUOTED.search(before)
            if tick and IDENT.match(tick.group(1).split("=")[0].strip().lstrip(".")):
                sym = tick.group(1).split("=")[0].strip().lstrip(".")
                claims.append(Claim("sym", n, f"`{sym}` {m.group(0)}", lo, hi, sym=sym))
            elif quote:
                claims.append(Claim("quote", n, f'"{quote.group(1)[:48]}..." {m.group(0)}',
                                    lo, hi, sym=quote.group(1)))
            else:
                claims.append(Claim("range", n, m.group(0), lo, hi))
    return claims


def main() -> int:
    for path in (DOC, SUBJECT):
        if not path.is_file():
            print(f"refmap: {path.relative_to(ROOT)} is gone; this script names it")
            return 1

    src = SUBJECT.read_text()
    lines = src.splitlines()
    defs = definitions(src)
    occurs: dict[str, list[int]] = {}
    whole = norm(" ".join(lines))

    claims = harvest(DOC.read_text())
    if not claims:
        print("refmap: parsed no claims out of docs/GENC_REFERENCE_MAP.md."
              " The document changed shape and this check just stopped"
              " checking -- fix the script, do not delete it.")
        return 1

    stale: list[tuple[Claim, str]] = []
    tally = {"def": 0, "quote": 0, "path": 0, "text": 0, "range": 0}
    weak = 0

    def occurrences(sym: str) -> list[int]:
        if sym not in occurs:
            word = re.compile(rf"\b{re.escape(sym)}\b")
            occurs[sym] = [i for i, s in enumerate(lines, 1) if word.search(s)]
        return occurs[sym]

    def check_def(claim: Claim, spans) -> None:
        if any(claim.lo <= start <= claim.hi for start, _ in spans):
            return
        where = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in spans)
        stale.append((claim, f"`{claim.sym}` is defined at {where}"))

    for claim in claims:
        if claim.kind == "path":
            target = resolve(claim.path)
            if target is None:
                stale.append((claim, f"no file named {claim.path} in the tree"))
                continue
            count = len(target.read_text().splitlines())
            if claim.hi > count:
                stale.append((claim, f"{claim.path} has only {count} lines"))
                continue
            if claim.sym and claim.sym in defs:
                tally["def"] += 1
                check_def(claim, defs[claim.sym])
            else:
                tally["path"] += 1

        elif claim.kind == "quote":
            tally["quote"] += 1
            want = literal_of(claim.sym)
            if len(want) < 8:
                continue
            if want in norm(" ".join(lines[claim.lo - 1:claim.hi])):
                continue
            hint = "that sentence is nowhere in the file"
            if want in whole:
                near = [i for i, s in enumerate(lines, 1) if want[:40] in norm(s)]
                hint = (f"it reads at {near[0]}" if near
                        else "it is in the file, wrapped across other lines")
            stale.append((claim, hint))

        elif claim.kind == "range":
            tally["range"] += 1
            if claim.hi > len(lines):
                stale.append((claim, f"gen_c.py has only {len(lines)} lines"))

        elif claim.sym in defs:
            tally["def"] += 1
            check_def(claim, defs[claim.sym])

        else:
            tally["text"] += 1
            seen = occurrences(claim.sym)
            if not seen:
                stale.append((claim, f"`{claim.sym}` does not occur in the file at all"))
            elif len(seen) > COMMON:
                weak += 1
            elif not any(claim.lo <= i <= claim.hi for i in seen):
                shown = ", ".join(str(i) for i in seen[:6])
                more = " ..." if len(seen) > 6 else ""
                stale.append((claim, f"`{claim.sym}` occurs at {shown}{more}"))

    for claim, why in stale:
        print(f"docs/GENC_REFERENCE_MAP.md:{claim.line}: {claim.shown} -- {why}")

    checked = sum(tally.values())
    print(f"\nrefmap: {checked} claims checked "
          f"({tally['def']} def, {tally['quote']} quoted, {tally['path']} path, "
          f"{tally['text']} presence, {tally['range']} range-only"
          f"{f', {weak} too common to mean much' if weak else ''}), "
          f"{len(stale)} stale")

    if stale:
        print("  Each line above names where the symbol actually is. A number you\n"
              "  cannot verify is worse than one you delete: if a claim names\n"
              "  something that no longer exists, SAY SO in the document -- a\n"
              "  function that was removed is information, and repointing the\n"
              "  claim at a similar name destroys it.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
