#!/usr/bin/env python3
"""A map of `bootstrap/gen_c.py` whose coordinates still resolve.

`docs/GENC_REFERENCE_MAP.md` is built out of hundreds of claims shaped
`symbol (line)`, `symbol line`, and `file:line`. Every one of them is a
promise that a reader who jumps there lands on the thing being
described. Nothing kept that promise: the map was written against a
5731-line gen_c.py, the file is 6576 lines now, and every claim below
the first insertion point had drifted. A map with shifted coordinates is
worse than no map -- it sends a reader CONFIDENTLY to the wrong
function, which costs more than sending them nowhere.

The document also named the revision it was written against, and that
was wrong too, in a way no reader could have caught: at the commit it
named, gen_c.py is 5651 lines -- the very number the opening sentence
says the file is NOT. A header that identifies itself cannot be trusted
to identify itself. So nothing here reads the document's own account of
what it describes; every claim is checked against the file on disk.

HOW A CLAIM IS FOUND. Every integer in the prose is a candidate, because
the document writes line references at least six ways -- `(1082)`,
`1082-1085`, `4885/4902`, `line 4241`, a bare `| 362 |` table cell, and
`gen_c.py:5709`. Keying on any one spelling would have read a fraction
of the document and reported a clean bill for the rest. Numbers inside
`code spans` are skipped (they are values, not coordinates), as are the
few that a unit word marks as quantities.

WHAT EACH KIND OF CLAIM IS CHECKED AGAINST, strongest first.

  def    the nearest symbol is defined in gen_c.py, so the line must
         fall inside that definition. A range must either sit within
         the definition or cover its first line.
  quote  a sentence the document quotes must appear within the lines.
  path   `file:line` -- the file must exist and hold that line.
  text   the nearest symbol is NOT a definition (a local, a struct
         field, a generated C name), so all that can be checked is that
         it literally occurs in the claimed lines.
  loose  a number with no symbol and no quotation near it. Only its
         bounds are checkable.

WHAT THIS CANNOT CHECK. Green here is not the document being true.

  * It checks COORDINATES, never prose. A paragraph can describe the
    wrong thing entirely at a line number that resolves. One claim here
    pointed at `Makefile:52-56` and said those lines documented the
    determinism harness; they are an unrelated target, and the numbers
    were in bounds the whole time. A human found that, and a human is
    still what finds it.
  * A `def` claim is satisfied anywhere inside the definition, because
    the document legitimately cites both a function's first line and
    call sites within its body, and nothing distinguishes them. Inside
    a 400-line function that is a wide target.
  * A `loose` claim has nothing to anchor to. They are counted and
    printed separately -- that number is the document saying how much
    of itself it cannot defend, and the repair for any one of them is
    to put a symbol or a quotation beside it.
  * A `text` claim on a token as common as `self` would pass almost
    anywhere. Those are counted as weak rather than folded into the
    pass total.
  * Numbers it declined to read are counted as `unread`. That count is
    not zero and is not meant to be: it is the residue this script is
    honest about rather than silently dropping.
  * It cannot know about a claim the document SHOULD make and does not.

The counts are the point of the counting. `refmap: N claims checked`
dropping is how you find out that the document changed shape and this
script quietly stopped reading half of it.
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
# How far a symbol may sit from the number it anchors. Wide enough for
# "`sym`, 448-466", narrow enough that the next sentence's symbol does
# not adopt an orphan.
REACH = 32

CODESPAN = re.compile(r"`[^`]*`")
# Three digits, or a two-digit RANGE -- the document cites the module
# docstring as `7-24`, but a bare small number in prose is a value
# ("on `Range(10, 13)` they are 0,1,2"), not a coordinate.
NUMBER = re.compile(r"(?<![\w.])(?:(\d{3,4})(?:\s*[-–]\s*(\d{2,4}))?"
                    r"|(\d{1,2})\s*[-–]\s*(\d{2,4}))(?![\w.])")
PATH = re.compile(r"([\w./-]*(?:\.py)|Makefile):(\d+)(?:[-–](\d+))?")
QUOTED = re.compile(r"\"([^\"]{8,160})\"[^()\"]{0,25}$")
IDENT = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
DEFLINE = re.compile(r"^\s*(?:def|class)\s+(\w+)|^\s*(\w+)\s*=\s*\S")
# Numbers a unit word marks as quantities rather than coordinates.
QUANTITY = re.compile(r"^\s*(?:bytes?|lines?|-bit|%|,\s*\d+\s*\))|^(?:st|nd|rd|th)\b")
NOT_A_REF = re.compile(r"(?:code|exit|byte|version|abi|column|col)\s+$", re.I)


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
    text after it never matches; the prefix still pins the line.
    """
    return norm(re.split(r"[<%]", quote)[0])


def quote_line(want: str, lines: list[str], reach: int = 8) -> int | None:
    """The line a quoted sentence STARTS on, or None.

    Source wraps a sentence over several lines, so the search is over a
    sliding window. The answer is the LAST window that still contains the
    whole sentence: once the window starts past the sentence's first line
    it can no longer hold all of it. Matching a prefix instead would be
    wrong in a way this file was bitten by -- "generic instantiation did
    not terminate" and the same words followed by "at `%s`" are two
    different diagnostics, and a prefix picks the first one.
    """
    hit = None
    for i in range(1, len(lines) + 1):
        if want in norm(" ".join(lines[i - 1:i - 1 + reach])):
            hit = i
    return hit


def resolve(name: str) -> Path | None:
    base = name.split("/")[-1]
    for candidate in (ROOT / name.lstrip("/"), ROOT / "bootstrap" / base, ROOT / base):
        if candidate.is_file():
            return candidate
    return None


def symbol_in(span: str) -> str | None:
    """The identifier a code span names, or None if it names no one thing."""
    text = span.strip("`").split("=")[0].strip().lstrip(".")
    text = re.sub(r"\(.*$", "", text).strip()
    return text if IDENT.match(text) else None


class Claim:
    def __init__(self, kind, line, shown, lo, hi, sym=None, path=None, at=None):
        self.kind, self.line, self.shown = kind, line, shown
        self.lo, self.hi, self.sym, self.path = lo, hi, sym, path
        self.at = at  # (start, end) columns of the number itself


def anchors_of(line: str) -> list[tuple[int, str]]:
    """(column where it ends, symbol) for every code span naming an identifier."""
    out = []
    for m in CODESPAN.finditer(line):
        sym = symbol_in(m.group(0))
        if sym:
            out.append((m.end(), sym))
    return out


def harvest(doc: str, known: set[str] | None = None) -> tuple[list[Claim], int]:
    """Every coordinate the document states, bound to whatever anchors it.

    `known` is the set of names gen_c.py defines. A table row states its
    line first and names the symbol afterwards, so the row's own symbol is
    the anchor -- but only when it is one gen_c.py defines, or every such
    row would anchor on whatever builtin the row happens to mention.

    Returns the claims and a count of numbers deliberately not read, so
    the residue is reported rather than disappearing.
    """
    known = known or set()
    claims: list[Claim] = []
    unread = 0
    fence = False

    for n, raw in enumerate(doc.splitlines(), 1):
        if raw.lstrip().startswith("```"):
            fence = not fence
            continue

        for m in PATH.finditer(raw):
            name, lo, hi = m.group(1), int(m.group(2)), m.group(3)
            sym = None
            if name.endswith("gen_c.py"):
                on = DEFLINE.match(raw)
                near = [s for end, s in anchors_of(raw[: m.start()])]
                sym = (on.group(1) or on.group(2)) if on else (near[-1] if near else None)
            claims.append(Claim("path", n, m.group(0), lo, int(hi) if hi else lo,
                                sym=sym, path=name, at=m.span()))
        if fence:
            continue

        # Code spans hold values, not coordinates. Blanking them keeps every
        # column where it was, so anchor distances stay meaningful.
        masked = CODESPAN.sub(lambda m: " " * len(m.group(0)), raw)
        masked = PATH.sub(lambda m: " " * len(m.group(0)), masked)
        found = anchors_of(raw)
        # A table row puts the number first and names the symbol after it.
        row = (found[0][1] if raw.lstrip().startswith("|")
               and found and found[0][1] in known else None)

        for m in NUMBER.finditer(masked):
            lo = int(m.group(1) or m.group(3))
            hi = int(m.group(2) or m.group(4) or lo)
            if QUANTITY.match(masked[m.end():]) or NOT_A_REF.search(masked[: m.start()]):
                unread += 1
                continue
            shown = m.group(0)
            before = [(end, s) for end, s in found if end <= m.start()]
            sym = None
            if before and m.start() - before[-1][0] <= REACH:
                sym = before[-1][1]
            elif row:
                sym = row
            if sym:
                claims.append(Claim("sym", n, f"`{sym}` {shown}", lo, hi, sym=sym,
                                    at=m.span()))
                continue
            quote = QUOTED.search(masked[: m.start()].rstrip(" ("))
            if quote:
                claims.append(Claim("quote", n, f'"{quote.group(1)[:44]}..." {shown}',
                                    lo, hi, sym=quote.group(1), at=m.span()))
            else:
                claims.append(Claim("loose", n, shown, lo, hi, at=m.span()))
    return claims, unread


def main() -> int:
    for path in (DOC, SUBJECT):
        if not path.is_file():
            print(f"refmap: {path.relative_to(ROOT)} is gone; this script names it")
            return 1

    src = SUBJECT.read_text()
    lines = src.splitlines()
    defs = definitions(src)
    whole = norm(" ".join(lines))
    occurs: dict[str, list[int]] = {}

    claims, unread = harvest(DOC.read_text(), set(defs))
    if not claims:
        print("refmap: parsed no claims out of docs/GENC_REFERENCE_MAP.md."
              " The document changed shape and this check just stopped"
              " checking -- fix the script, do not delete it.")
        return 1

    stale: list[tuple[Claim, str]] = []
    tally = dict.fromkeys(("def", "quote", "path", "text", "loose"), 0)
    weak = 0

    def occurrences(sym: str) -> list[int]:
        if sym not in occurs:
            word = re.compile(rf"\b{re.escape(sym)}\b")
            occurs[sym] = [i for i, s in enumerate(lines, 1) if word.search(s)]
        return occurs[sym]

    def check_def(claim: Claim, spans) -> None:
        # Satisfied by sitting inside the definition, or by covering its
        # first line -- the document cites both whole functions and lines
        # within them.
        for start, end in spans:
            if (claim.lo >= start and claim.hi <= end) or claim.lo <= start <= claim.hi:
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
            elif claim.sym in defs:
                tally["def"] += 1
                check_def(claim, defs[claim.sym])
            else:
                tally["path"] += 1

        elif claim.kind == "quote":
            tally["quote"] += 1
            want = literal_of(claim.sym)
            if len(want) < 8:
                continue
            # Where the sentence STARTS is what the claim names; it may
            # wrap past `hi`, so the span is not searched directly.
            at = quote_line(want, lines) if want in whole else None
            if at is not None and claim.lo <= at <= claim.hi:
                continue
            stale.append((claim, f"it reads at {at}" if at
                          else "that sentence is nowhere in the file"))

        elif claim.kind == "loose":
            tally["loose"] += 1
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
                stale.append((claim, f"`{claim.sym}` occurs at {shown}"
                                     f"{' ...' if len(seen) > 6 else ''}"))

    for claim, why in stale:
        print(f"docs/GENC_REFERENCE_MAP.md:{claim.line}: {claim.shown} -- {why}")

    checked = sum(tally.values())
    print(f"\nrefmap: {checked} claims checked ({tally['def']} def, "
          f"{tally['quote']} quoted, {tally['path']} path, {tally['text']} presence, "
          f"{tally['loose']} loose{f', {weak} too common to mean much' if weak else ''}), "
          f"{unread} not read, {len(stale)} stale")

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
