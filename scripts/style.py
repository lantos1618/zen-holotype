#!/usr/bin/env python3
"""The rules in `docs/STYLE.md` that a machine can settle.

STYLE.md opens by claiming "most of these are one rule with a test attached"
and then attaches a test to two of them -- the line caps (`make cap`) and, by
implication, the formatter. Everything else was a preference with a paragraph,
which is the state the document itself says loses arguments.

WHAT IS ALREADY GATED SOMEWHERE ELSE, and is deliberately NOT re-checked here.
One fact, one place; a second copy is the stale one.

  no `if`, no `while`, no ternary, no `?`, no `as` cast, no fourth `@` entry,
  no adjacent-string concatenation
        `grammar/grammar.js` cannot express any of them, so `make parse` is
        the gate. Each was mutation-checked against the real grammar while
        writing this file: every one is a parse ERROR. A style script
        grepping for `if` would only ever find the word in prose -- all 99
        occurrences of `\\bif\\b` in src/ are inside comments, and all 549
        of `\\bas\\b`, and all 90 of `?`. That is the whole argument for
        parsing over grepping, restated.
  every parameter has a name AND a type
        the grammar requires the name; `bootstrap/cst.py` requires the type
        and reports which half is missing (`(i32, i32) i32` is missing NAMES,
        `(a, b) i32` is missing types). `make ufcs` parses all of src/ with
        cst.py, so the check runs tree-wide already.
  match arms align their `=>`      the formatter, `make fmt`.
  500/800-line caps               `scripts/line_cap.py`, `make cap`.
  no free fn shadowing a method   `scripts/ufcs_collisions.py`, `make ufcs`.

WHAT THIS FILE CANNOT CHECK, and so leaves to review. Naming them is the
point: an unstated gap reads as coverage.

  the stranger test, the second-caller rule, the direction test in general
        all three ask what a function is ABOUT. The one mechanical corollary
        -- std may not depend upward -- is `layer` below. The rest is a
        judgement about meaning and belongs in review.
  "say what it is, not what it does to you"
        `get_`/`do_` are gateable and gated (`verb`). The rest of the rule
        needs to know what the function means.
  "method chains over nested calls"
        requires knowing the NATURAL receiver. `f(x, a)` is only wrong when
        `x` is what the operation is about, and nothing in the source says
        which parameter that is.
  "no magic numbers"
        measured, not gated: zero `== <printable ascii int>` comparisons
        exist in src/ today. A gate would have to guess whether `n == 32`
        counts a bit width or an ASCII space, and guessing wrong on a rule
        this cheap to eyeball is how a gate gets deleted.
  "no `Alloc` parameter, no allocation"
        needs a call graph. A crude version flags 2306 of 3628 functions,
        nearly all of them methods reaching an allocator through `self`.
  "a `.then` inside a loop is usually a missing loop word"
        WRITTEN AND DROPPED, and the reason is the interesting one. The
        structural check works -- 29 of the 141 `.then` calls in src/ sit
        inside a `.loop` -- but "usually" is load-bearing. Two of the 29 are
        `std/core/loop/loop_find.zen:45`, which is the definition of `find`
        and cannot be written any other way, and `lsp/lsp_pos.zen:80`, whose
        author left a comment arguing the case: "a break would buy a shorter
        walk and cost the one thing worth having here -- a body with a single
        exit." A gate that reports a deliberate decision its author already
        defended in a comment is the gate people switch off. The 29 are
        listed in STYLE.md as a list to read, which is what a rule with real
        exceptions deserves.
  comment density, "a name that needs a comment is the wrong name",
  "one behaviour per test", `::` vs `:` being the right marker,
  "smallest correct change"
        judgement, all of them.

ONE RULE CARRIES A LEDGER because the tree violates it today. Same shape as
`faults_reachable.py` and `ufcs_collisions.py`: an entry is a debt, not an
exemption, deleting a line is how one closes, and a stale entry is an error --
so the debt can shrink and cannot quietly grow. Fixing the 147 abbreviation
sites touches files three other lanes hold open, which is why they are written
down here instead of renamed.
"""

from __future__ import annotations

import collections
import re
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# py-tree-sitter's deprecated-Language warning; `make grammar` builds the .so
# this path loads, and the noise is not this check's to report.
warnings.filterwarnings("ignore", category=FutureWarning)

# THE ABBREVIATION DEBT, keyed "<file>:<abbreviation>", valued with THE WORD
# IT SHOULD BE. The value is deliberately the fix and not an excuse: STYLE.md
# names `blk`, `nd`, `tp` as the abbreviations that are not words, so there is
# no reading under which an entry here is correct as written. `nd` is already
# at zero and has no entry.
#
# Keyed by FILE and not by line, for the reason ufcs_collisions.py gives: a
# line number moves whenever someone edits above it, and a ledger that goes
# stale on an unrelated edit is a ledger people learn to silence.
ABBREV_OWED: dict[str, str] = {
    "src/ast/ast_find.zen:blk": "block",
    "src/gen/gen_c/gen_c_decl.zen:blk": "block",
    "src/gen/gen_c/gen_c_fat.zen:tp": "tparam",
    "src/gen/gen_c/gen_c_inline.zen:blk": "block",
    "src/gen/gen_c/gen_c_mono.zen:tp": "tparam",
    "src/gen/gen_c/gen_c_own.zen:blk": "block",
    "src/gen/gen_c/gen_c_range.zen:blk": "block",
    "src/gen/gen_c/gen_c_scope.zen:blk": "block",
    "src/gen/gen_c/gen_c_settle.zen:blk": "block",
    "src/gen/gen_c/gen_c_stmt.zen:blk": "block",
    "src/parse/parse_expr.zen:tps": "tparams",
    "src/parse/parse_type.zen:tps": "tparams",
    "src/sema/sema_cand.zen:tp": "tparam",
    "src/sema/sema_decl.zen:tp": "tparam",
    "src/sema/sema_depth.zen:tp": "tparam",
    "src/sema/sema_hoist.zen:blk": "block",
    "src/sema/sema_inst.zen:tp": "tparam",
    "src/sema/sema_type.zen:blk": "block",
}

# The abbreviations STYLE.md names. Not a general "short name" check -- `len`,
# `cap`, `ptr`, `env`, `alloc` are words here and the document says so.
ABBREVS = ("blk", "nd", "tp", "tps")

# Names that name nothing. STYLE.md's table, as suffixes.
VAGUE = ("_utils", "_util", "_helpers", "_helper", "_common", "_misc")

# The `// helpers` banner -- "the smell that catches all three" tests.
BANNER = re.compile(r"^\s*//\s*(helpers?|utils?|misc|common)\s*[.:]?\s*$", re.I)


def sources():
    """(relative path, Path, parsed module) for every file under src/."""
    from bootstrap import cst

    out = []
    for path in sorted(ROOT.glob("src/**/*.zen")):
        rel = path.relative_to(ROOT).as_posix()
        module, diags = cst.parse_file(str(path), str(ROOT))
        if module is None:
            print(f"style: {rel} does not parse; `make parse` owns that failure")
            print(f"    {diags[0] if diags else ''}")
            return None
        out.append((rel, path, module))
    return out


def rule_prefix(files):
    """A prefixed file's prefix must name its own folder.

    "A prefix must name the file's own folder. If it names something else,
    that something is a folder waiting to happen." A file with no `_` is
    untouched -- `core/scope.zen` is one file about one thing.

    This subsumes STYLE.md's separate "a prefix family of two has earned the
    folder" trigger: if every prefix names its own folder, a family living in
    someone else's folder cannot exist.
    """
    checked, bad = 0, []
    for rel, _, _ in files:
        stem, folder = Path(rel).stem, Path(rel).parent.name
        if "_" not in stem:
            continue
        checked += 1
        if stem != folder and not stem.startswith(folder + "_"):
            bad.append((rel, f"prefix `{stem.split('_')[0]}` names no folder;"
                             f" this file sits in `{folder}`"))
    return checked, bad


def rule_root(files):
    """Every folder holding .zen files has its `<folder>/<folder>.zen` root.

    "a folder root is a file of starred re-exports, so a folder is the unit
    at which a subject controls its own surface. Files sharing a prefix in
    someone else's folder have no root, which means every consumer imports
    the individual files and every internal move breaks them."
    """
    folders = collections.defaultdict(set)
    for rel, _, _ in files:
        folders[Path(rel).parent.as_posix()].add(Path(rel).stem)
    bad = [(f + "/", f"no {Path(f).name}.zen — the folder has no surface, so"
                     f" every consumer imports its files one by one")
           for f, stems in folders.items() if Path(f).name not in stems]
    return len(folders), sorted(bad)


def rule_vague(files):
    """No `_utils`/`_helpers`/`_common`/`_misc`, and no `parse2.zen`.

    Straight from STYLE.md's table of "names that mean nothing". The digit
    case only fires when stripping the digits leaves a file that EXISTS --
    `text_utf8.zen` is a subject whose name ends in 8, `parse2.zen` next to
    `parse.zen` is one subject cut in half.
    """
    stems = {Path(rel).stem for rel, _, _ in files}
    bad = []
    for rel, _, _ in files:
        stem = Path(rel).stem
        if stem.endswith(VAGUE):
            bad.append((rel, "a list of things that belong somewhere else —"
                             " apply the stranger test to each"))
        cut = re.match(r"^(.*?)_?\d+$", stem)
        if cut and cut.group(1) in stems:
            bad.append((rel, f"one subject cut in half; `{cut.group(1)}` is"
                             f" the other half, and neither name means anything"))
    return len(files), bad


def rule_layer(files):
    """The direction test, in its one mechanical form: std depends only on std.

    "`parse` may depend on `std.text`. `std.text` may never depend on
    `parse`." The general rule needs a layer order this repository has not
    written down; the std boundary is the half that is unambiguous, and it is
    the half that inverts the whole module graph when it breaks.
    """
    checked, bad = 0, []
    for rel, _, module in files:
        mod = rel[len("src/"):-len(".zen")].replace("/", ".")
        if not (mod == "std" or mod.startswith("std.")):
            continue
        for imp in module.imports:
            checked += 1
            if not (imp.path == "std" or imp.path.startswith("std.")):
                bad.append((rel, f"imports `{imp.path}`; std may not depend"
                                 f" upward, and a trait sits BELOW the types"
                                 f" that satisfy it"))
    return checked, bad


def rule_impl_home(files):
    """`A.impl(B, {..})` lives in A's module.

    "This is the direction test applied to impls, and getting it backwards
    inverts the whole module graph -- a trait sits *below* the types that
    satisfy it, so `std.core.eq` importing `str` is the layering already
    broken."

    An impl whose target this script cannot find a declaration for is
    skipped, not reported: that is name resolution, and like
    ufcs_collisions.py this file would rather miss than invent.
    """
    home = collections.defaultdict(list)
    for rel, _, module in files:
        for decl in module.decls:
            if type(decl).__name__ in ("Struct", "Enum", "Alias"):
                home[decl.name].append(rel)
    checked, bad = 0, []
    for rel, _, module in files:
        for decl in module.decls:
            if type(decl).__name__ != "Impl":
                continue
            where = home.get(decl.target)
            if not where:
                continue
            checked += 1
            if rel not in where:
                bad.append((rel, f"`{decl.target}.impl({decl.trait}, ..)` but"
                                 f" {decl.target} is declared in {where[0]};"
                                 f" an impl goes with the type"))
    return checked, bad


def rule_verb(files):
    """No `get_*`, no `do_*`.

    "Say what it is, not what it does to you. `view`, `add`, `grow`,
    `consume` -- not `get_view`, `append_item`, `do_grow`." Only the two
    prefixes are gateable; `append_item` needs to know what the thing is.
    """
    def functions(module):
        for decl in module.decls:
            kind = type(decl).__name__
            if kind == "Function":
                yield decl
            elif kind == "Struct":
                yield from (f for f in decl.fields
                            if type(f).__name__ == "Function")
            elif kind == "Impl":
                yield from (e for e in decl.entries
                            if type(e).__name__ == "Function")

    checked, bad = 0, []
    for rel, _, module in files:
        for fn in functions(module):
            checked += 1
            if fn.name.startswith(("get_", "do_")):
                bad.append((f"{fn.span}", f"`{fn.name}` says what it does to"
                                          f" you; name what it IS"))
    return checked, bad


def rule_banner(files):
    """No `// helpers` section.

    "The smell that catches all three: a file with a `// helpers` section at
    the bottom. That section is a list of things that belong somewhere else,
    sorted by the order you needed them."
    """
    checked, bad = 0, []
    for rel, path, _ in files:
        checked += 1
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNER.match(line):
                bad.append((f"{rel}:{n}", "a `// helpers` section — everything"
                                          " under it belongs somewhere else"))
    return checked, bad


def identifiers(path, parser):
    """Every identifier TOKEN in the file, with its line.

    A token and not a regex match, because `blk` occurs in prose too and a
    comment mentioning a bad name is not a bad name. This is the same
    argument ufcs_collisions.py makes for parsing.
    """
    tree = parser.parse(path.read_bytes())
    stack, out = [tree.root_node], []
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "identifier":
            out.append((node.text.decode(), node.start_point[0] + 1))
    return out


def rule_abbrev(files, parser):
    """The abbreviations STYLE.md names are not words. Carries a ledger."""
    checked, bad, seen = 0, [], set()
    for rel, path, _ in files:
        checked += 1
        for name, line in identifiers(path, parser):
            if name not in ABBREVS:
                continue
            key = f"{rel}:{name}"
            if key in ABBREV_OWED:
                seen.add(key)
            else:
                bad.append((f"{rel}:{line}", f"`{name}` is not a word — and"
                                             f" STYLE.md names it"))
    return checked, bad, seen


def stale(ledger, seen, label):
    """A ledger entry whose violation is gone is a fiction the next reader
    trusts. Same rule the OWED ledgers in faults_reachable.py and
    ufcs_collisions.py run."""
    gone = sorted(set(ledger) - seen)
    for key in gone:
        print(f"style: {key} is in {label} and no longer violates the rule."
              f" Delete its line from {Path(__file__).name} — the debt is paid.")
    return gone


def main() -> int:
    if not (ROOT / "grammar" / "zen.so").exists():
        print("style: run `make grammar` first", file=sys.stderr)
        return 2

    files = sources()
    if files is None:
        return 1

    from bootstrap import cst
    parser = cst.parser()

    abbrev_n, abbrev_bad, abbrev_seen = rule_abbrev(files, parser)
    results = [
        ("prefix   ", "a prefix names its own folder", *rule_prefix(files), 0),
        ("root     ", "a folder has its root file", *rule_root(files), 0),
        ("vague    ", "a file name means something", *rule_vague(files), 0),
        ("layer    ", "std depends only on std", *rule_layer(files), 0),
        ("impl-home", "an impl goes with its type", *rule_impl_home(files), 0),
        ("verb     ", "no `get_*`, no `do_*`", *rule_verb(files), 0),
        ("banner   ", "no `// helpers` section", *rule_banner(files), 0),
        ("abbrev   ", "abbreviations are words", abbrev_n, abbrev_bad,
         len(ABBREV_OWED)),
    ]

    failed = 0
    for _, rule, _, bad, _ in results:
        for where, why in bad:
            print(f"{where}: {why}")
            failed += 1
    if failed:
        print(f"\nstyle: {failed} violation(s) of docs/STYLE.md."
              f"\n  Fix it, or -- for `abbrev`, the one rule that carries a"
              f"\n  ledger -- write it into ABBREV_OWED in"
              f" {Path(__file__).name} with the"
              f"\n  word it should be, so the debt can shrink and cannot"
              f" quietly grow.")
        return 1

    if stale(ABBREV_OWED, abbrev_seen, "ABBREV_OWED"):
        return 1

    for name, rule, checked, _, owed in results:
        note = f", {owed} written down" if owed else ""
        print(f"  {name}  {checked:5} checked, 0 violations{note}  — {rule}")
    sites = sum(checked for _, _, checked, _, _ in results)
    owed = sum(owed for _, _, _, _, owed in results)
    print(f"style: {len(results)} rules, {sites} sites, 0 violations,"
          f" {owed} written down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
