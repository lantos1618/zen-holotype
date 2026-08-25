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
        grepping for them would find nothing but prose and diagnostics --
        `if` occurs 101 times in src/ and `as` 605 and `?` 94, and the count
        in CODE is zero for all three. 52 of the `if`s are inside string
        literals, which is to say a grep would report the compiler's own
        error messages as style violations. That is the whole argument for
        parsing over grepping, restated.
  every parameter has a name AND a type
        the grammar requires the name; `tools/parse/cst.py` requires the type
        and reports which half is missing (`(i32, i32) i32` is missing NAMES,
        `(a, b) i32` is missing types). `make ufcs` parses all of src/ with
        cst.py, so the check runs tree-wide already.
  match arms align their `=>`      the formatter, `make fmt`.
  500/800-line caps               `tools/gates/line_cap.zen`, `make cap`.
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
  "method chains over nested calls", in general
        requires knowing the NATURAL receiver, and nothing in the source
        says which parameter that is. The ONE case where the source does
        say is gated -- see `ufcs` below, which reads the receiver off the
        callee's own first parameter and off its module's subject rather
        than guessing.
  "no magic numbers"
        measured, not gated: zero `== <printable ascii int>` comparisons
        exist in src/ today. A gate would have to guess whether `n == 32`
        counts a bit width or an ASCII space, and guessing wrong on a rule
        this cheap to eyeball is how a gate gets deleted.
  a membership run written with `==` on a PRIMITIVE
        `member` below reads `.eq` and stops there. `b == ' ' || b == '\t'
        || b == '\n'` is the same shape and cannot be rewritten: `is_in` is
        bounded on Eq and no primitive implements Eq, which is a compile
        error and not a style opinion. Four runs in src/ are out of reach
        for that reason -- std/core/byte.zen, std/lex/lex_byte.zen,
        std/json/json_read.zen, gen/gen_c/gen_c_fat.zen. Measured while
        writing this: a `u8.impl(Eq, ..)` in std/core/num.zen satisfies the
        bound and leaves every `==` in the emitted C exactly as it was, so
        the block is a decision nobody has made rather than a hard one.
        Reporting them meanwhile would be an instruction nobody can carry
        out, which is how a gate gets switched off.
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

ONLY `ABBREV_OWED` CARRIES ENTRIES TODAY, seventeen of them. `UFCS_OWED` and
`IMPORT_OWED` stand empty, and empty is where a count-keyed ledger ends up --
its terminal state, not a switched-off gate: every violation anywhere fails
this run, so reading an empty ledger as a hole and refilling it would weaken
the gate. An entry is earned only by code whose fix would touch files other
lanes hold open -- the seventeen abbreviation debts did, which is why they
are written down here instead of renamed away. Same shape as
`tools/gates/faults_reachable.zen` and `ufcs_collisions.py`: an entry is a debt, not an
exemption, deleting a line is how one closes, and a stale entry is an error --
so the debt can shrink and cannot quietly grow.

`UFCS_OWED` AND `IMPORT_OWED` ARE KEYED BY FILE AND VALUED WITH A COUNT, which
the abbreviation ledger is not, and the difference is deliberate. A file-keyed
ledger with no
number exempts the file: `gen_c_expr.zen` could take a hundred more and the
gate would say nothing. A count cannot go stale on an unrelated edit the way a
LINE NUMBER does -- it moves only when someone adds or removes a violation,
which is exactly when the ledger should have to be touched. So the debt here
is monotone in the strong sense: not "no new dirty files" but "no new sites,
anywhere", and paying one down is a one-character edit that shows up in the
diff.
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
    "src/std/ast/ast_find.zen:blk": "block",
    "src/gen/gen_c/gen_c_decl.zen:blk": "block",
    "src/gen/gen_c/gen_c_fat.zen:tp": "tparam",
    "src/gen/gen_c/gen_c_inline.zen:blk": "block",
    "src/gen/gen_c/gen_c_mono.zen:tp": "tparam",
    "src/gen/gen_c/gen_c_own.zen:blk": "block",
    "src/gen/gen_c/gen_c_range.zen:blk": "block",
    "src/gen/gen_c/gen_c_scope.zen:blk": "block",
    "src/gen/gen_c/gen_c_settle.zen:blk": "block",
    "src/gen/gen_c/gen_c_stmt.zen:blk": "block",
    "src/std/parse/parse_expr.zen:tps": "tparams",
    "src/std/parse/parse_type.zen:tps": "tparams",
    "src/sema/sema_cand.zen:tp": "tparam",
    "src/sema/sema_decl.zen:tp": "tparam",
    "src/sema/sema_depth.zen:tp": "tparam",
    "src/sema/sema_hoist.zen:blk": "block",
    "src/sema/sema_inst.zen:tp": "tparam",
}

# THE UFCS DEBT, keyed by file and valued with THE NUMBER OF SITES that file
# still writes `f(be, ..)` where `be.f(..)` resolves to the same function.
#
# NOT an exemption list, and not a claim that these files are allowed to do
# it: every entry is a mechanical edit nobody has made time for. The ledger
# is EMPTY, and empty is its terminal state: `3a976841d` paid out 1153 sites
# across 40 files and left nothing here, and `debt()` fails this run on the
# first new site anywhere in src/. An entry goes back only with code whose
# rewrite would collide with another lane's open files, and never as a
# standing allowance.
#
# THE NUMBER IS THE POINT. A bare file list would exempt the file, and
# `gen_c_expr.zen` could take a hundred more without a word. Bring the number
# down with the code; the gate fails either way round, on a file that grew and
# on a number that overstates.
UFCS_OWED: dict[str, int] = {
}

# THE UNUSED-IMPORT DEBT, keyed by file and valued with THE NUMBER OF NAMES
# that file imports and never writes again. It opened at 1208 of the 5191
# imported names in src/, across 89 files -- nearly a quarter of the module
# graph was fiction and nothing had ever looked. 1195 went in the change that
# wrote the rule, and the residue of 13 went with the Python bootstrapper.
#
# THE LEDGER IS EMPTY, AND THAT IS THE WHOLE POINT OF THE ENTRY. Every one of
# the 13 was a BOOTSTRAP RESOLUTION DEFECT: a method reached through a FIELD was
# resolved by the bootstrapper against the FIELD'S TYPE NAME as the importing
# file spelled it, but only when that method name had a COMPETITOR reachable in
# the same compilation -- `c.types.write_name(..)` needed `Types` because
# `sema_diag.zen:336` declares a FREE FUNCTION of that name and the bootstrapper
# picked it. The self-hosted compiler always resolved all 13 correctly. So when
# the bootstrapper was deleted the imports became dead, and were removed and
# measured rather than assumed: `make test` 529/0/4 and `make fixpoint` green
# with every one of them gone.
#
# KEEP THE LEDGER, EMPTY. `debt()` errors on an entry whose file no longer has
# that many violations, so an empty dict is not a disabled gate -- it is a gate
# that now fails on the FIRST new unused import anywhere in src/.
IMPORT_OWED: dict[str, int] = {}

# The abbreviations STYLE.md names. Not a general "short name" check -- `len`,
# `cap`, `ptr`, `env`, `alloc` are words here and the document says so.
ABBREVS = ("blk", "nd", "tp", "tps")

# Names that name nothing. STYLE.md's table, as suffixes.
VAGUE = ("_utils", "_util", "_helpers", "_helper", "_common", "_misc")

# The `// helpers` banner -- "the smell that catches all three" tests.
BANNER = re.compile(r"^\s*//\s*(helpers?|utils?|misc|common)\s*[.:]?\s*$", re.I)


def module_path(rel: str) -> str:
    """The dotted form an import writes: `src/sema/sema_ty.zen` -> `sema.sema_ty`."""
    return rel[len("src/"):-len(".zen")].replace("/", ".")


def sources():
    """(relative path, Path, parsed module) for every file under src/."""
    from tools.parse import cst

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

    "`std.parse` may depend on `std.text`. `std.text` may never depend on
    `std.parse`." The compiler's own frontend lives INSIDE std now --
    `std.lex`, `std.parse`, `std.ast`, the sublayer an ordinary program
    imports to parse Zen -- so the boundary runs through std: everything
    under `src/std/` imports std only, and PLAIN std (all of it but the
    sublayer) may not import the sublayer. The sublayer itself may import
    plain std, and its members may import each other. The general rule
    needs a layer order this repository has not written down; the std
    boundary is the half that is unambiguous, and it is the half that
    inverts the whole module graph when it breaks.
    """
    sublayer = ("std.lex", "std.parse", "std.ast")

    def in_slayer(mod: str) -> bool:
        return any(mod == s or mod.startswith(s + ".") for s in sublayer)

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
            elif not in_slayer(mod) and in_slayer(imp.path):
                bad.append((rel, f"imports `{imp.path}`; plain std may not"
                                 f" depend on the compiler sublayer -- the"
                                 f" sublayer reads std, never the reverse"))
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


def or_operands(node):
    """`a || b || c` as a flat list. `||` is left-associative, so a chain
    of n is one tree nested to the left with n leaves."""
    if kind(node) == "Binary" and node.op == "||":
        return or_operands(node.lhs) + or_operands(node.rhs)
    return [node]


def subject(node):
    """The name an operand asks about — `name`, `n.name` — or None.

    Only a path of members, because two operands are the SAME subject
    exactly when they spell it the same way, and anything with a call or an
    index in it is a repeated computation this rule has no opinion about.
    """
    if kind(node) == "Path":
        return node.name
    if kind(node) == "Member":
        base = subject(node.base)
        return None if base is None else f"{base}.{node.name}"
    return None


def eq_literal(node):
    """The subject of `x.eq(<literal>)` or `x == <literal>`, or None.

    `==` COUNTS, AND IT USED TO NOT. The reason it did not was that `is_in`
    is bounded on Eq and no primitive implemented one, so a run of
    `b == ' ' || b == '\\t'` had no is_in form to be rewritten into and
    reporting it would have been an instruction nobody could carry out --
    which is how a gate gets switched off. `std.core.num` and
    `std.core.bool` impl Eq now, so the rewrite exists for every subject.

    A RANGE IS STILL NOT MEMBERSHIP. `b >= 'a' && b <= 'z'` is an `&&`, so
    it reaches this function whole and answers None, which BREAKS the run
    rather than joining it -- `gen_name.zen`'s letter ranges and
    `gen_c_fat.zen`'s `is_word_byte` stay unreported, as they must:
    enumerating twenty-six characters is worse than the range.
    """
    if kind(node) == "Binary" and node.op == "==":
        return subject(node.lhs) if kind(node.rhs) == "Literal" else None
    if kind(node) != "Call" or kind(node.callee) != "Member":
        return None
    if node.callee.name != "eq" or len(node.args) != 1:
        return None
    arg = node.args[0]
    if arg.name is not None or kind(arg.value) != "Literal":
        return None
    return subject(node.callee.base)


def longest_run(operands):
    """The longest run of consecutive operands asking ONE subject for
    equality against a literal, as (length, subject).

    A RUN and not the whole chain, because `is_c_integer(name) ||
    name.eq("f32") || ..` is a predicate followed by a membership test and
    the tail is still one. Anything else ends the run — a range test, a
    different question, a comparison against a value rather than a literal —
    which is what keeps this off `gen_name.zen`'s letter ranges and
    `sema_check.zen`'s eight different questions.
    """
    best, run, held = (0, None), 0, None
    for operand in operands:
        found = eq_literal(operand)
        run = run + 1 if found is not None and found == held else 1
        held = found
        if held is not None and run > best[0]:
            best = (run, held)
    return best


def rule_member(files):
    """Three or more `||` asking one subject for equality is `x.is_in([..])`.

    "A run of `||` spells the same question once per answer and repeats the
    subject every time." The rewrite is mechanical and the reading is not a
    judgement: the subject, the question and the answer set are each written
    once.
    """
    checked, bad = 0, []
    for rel, _, module in files:
        inner = set()
        for node in nodes(module):
            if kind(node) == "Binary" and node.op == "||":
                inner.add(id(node.lhs))
        for node in nodes(module):
            if kind(node) != "Binary" or node.op != "||" or id(node) in inner:
                continue
            checked += 1
            run, held = longest_run(or_operands(node))
            if run >= 3:
                bad.append((f"{node.span}",
                            f"{run} `||` asking `{held}` for equality against"
                            f" a literal — that is a membership test, and it"
                            f" is written `{held}.is_in([..])`"))
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


def kind(node) -> str:
    return type(node).__name__


def ty_name(ty) -> str | None:
    """The plain name a type writes, or None if it does not write one.

    A union, an array, a function type and a `()` name no declaration, so
    none of them can be a receiver. `Vec<str>` names `Vec`: the arguments
    do not change which function a dot finds.
    """
    return getattr(ty, "name", None) if kind(ty) == "Named" else None


def nodes(root):
    """Every Node under `root`, the dataclass fields walked generically."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        for name in getattr(node, "__dataclass_fields__", {}):
            value = getattr(node, name)
            if hasattr(value, "__dataclass_fields__"):
                stack.append(value)
            elif isinstance(value, tuple):
                stack.extend(v for v in value
                             if hasattr(v, "__dataclass_fields__"))


def with_body(module):
    """(function, owning type name or None) for every body in the module."""
    for decl in module.decls:
        if kind(decl) == "Function" and decl.body:
            yield decl, None
        elif kind(decl) == "Struct":
            for member in decl.fields:
                if kind(member) == "Function" and member.body:
                    yield member, decl.name
        elif kind(decl) == "Impl":
            for entry in decl.entries:
                if kind(entry) == "Function" and entry.body:
                    yield entry, decl.target


# HOW MANY MODULES THE `ufcs` RULE IS ALLOWED NOT TO COVER. See the check in
# main() for what an exemption is and why this is a ceiling.
UFCS_EXEMPT_CEILING = 63


def ufcs_world(files):
    """What a dot can find: free functions, methods, and each module's subject.

    `free` maps a name to every top-level function declaring it whose first
    parameter names a declared type -- the definition of a UFCS candidate,
    DESIGN.md:406. `methods` is consulted only to stay off `make ufcs`'s
    ground: a name that is BOTH is that gate's finding, not this one's.

    THE PRINCIPAL TYPE is the one thing here that is a judgement, so it is
    made twice and both ways have to agree. A type is a module's principal
    type when it is the first parameter of a strict majority of that
    module's free functions AND some module in the same folder declares it
    -- the folder's subject, in other words. Both halves earn their keep.
    Without the majority, a module with one `Foo` helper claims `Foo`.
    Without the folder, `zen_cli.zen`'s little classifiers over `str` make
    `str` principal and the check asks for `name.not_written()`, which is
    the natural-receiver mistake the header says this file does not make:
    the operation is about the CLI, and the string is only its input.
    """
    free = collections.defaultdict(list)
    methods = collections.defaultdict(set)
    folder_of = {}
    declared = collections.defaultdict(set)
    firsts = collections.defaultdict(collections.Counter)

    for rel, _, module in files:
        folder_of[module_path(rel)] = Path(rel).parent.as_posix()
        for decl in module.decls:
            if kind(decl) in ("Struct", "Enum"):
                declared[decl.name].add(Path(rel).parent.as_posix())

    for rel, _, module in files:
        mod = module_path(rel)
        for decl in module.decls:
            if kind(decl) == "Function" and decl.params:
                tparams = {t.name for t in decl.tparams}
                name = ty_name(decl.params[0].ty)
                if name and name not in tparams:
                    free[decl.name].append((mod, name, len(decl.params)))
                    firsts[mod][name] += 1
            elif kind(decl) == "Struct":
                for member in decl.fields:
                    if kind(member) == "Function" and member.params:
                        if ty_name(member.params[0].ty) in ("@Self", decl.name):
                            methods[decl.name].add(member.name)
            elif kind(decl) == "Impl":
                for entry in decl.entries:
                    if kind(entry) == "Function" and entry.params:
                        methods[decl.target].add(entry.name)

    principal = {}
    for mod, counted in firsts.items():
        name, n = counted.most_common(1)[0]
        if n * 2 > sum(counted.values()) and folder_of[mod] in declared.get(name, ()):
            principal[mod] = name
    return free, methods, principal


def rule_import(files, parser):
    """An imported name the file never writes again.

    `A, B, C = some.module.path` binds three names, and a name that appears
    nowhere else in the file is a dependency the file does not have. It reads
    as one, though, which is the cost: `gen_c_loop.zen` declared nine and used
    two, so eight of its nine module edges were fiction to anyone tracing the
    graph by eye.

    IDENTIFIER TOKENS, not a grep. A name surviving only in a comment or in a
    diagnostic string literal is exactly the case being hunted, and a grep
    counts both as uses.

    A `*` NAME IS EXPORTED ONWARD, so the file's own surface uses it. That is
    what a folder root is for, and `lsp/lsp_decl.zen` and
    `std/parse/parse_token.zen` re-export the same way without being roots.
    Skipping starred names subsumes the root-file exemption exactly: measured
    while writing this, no root file imports an unused name unstarred, so the
    two readings agree on 647 names and only this one also covers the nine
    re-exports that are not in a root.
    """
    checked, hits = 0, []
    for rel, path, module in files:
        on_import = set()
        for imp in module.imports:
            on_import.update(range(imp.span.start[0], imp.span.end[0] + 1))
        used = {name for name, line in identifiers(path, parser)
                if line not in on_import}
        for imp in module.imports:
            for name, exported in imp.names:
                checked += 1
                if exported or name in used:
                    continue
                hits.append((rel, f"{rel}:{imp.span.start[0]}",
                             f"`{name}` is imported from `{imp.path}` and never"
                             f" written again — the file does not have that"
                             f" dependency"))
    return checked, hits


def rule_ufcs(files):
    """A free function on the module's principal type is CALLED on it.

    `be.declare_temp(ty, name)`, not `declare_temp(be, ty, name)`. The
    receiver column is what makes the order-critical sequence visible, and
    a formatter may not produce it -- reordering statements is not a
    formatter's to do, so this is the author's.

    EVERY CONDITION BELOW EXISTS TO MISS RATHER THAN INVENT, because a hit
    is an instruction to edit code and a wrong one costs a compile:

      the argument is a PARAMETER, spelled bare, with a written type.
            A `x ::= ..` local's type is inference, and this script does
            not implement Zen's. A name rebound anywhere in the body --
            by a `let`, a lambda parameter, a match binder, an assignment
            -- is dropped from the frame entirely rather than scoped
            properly, so a body that reuses the name is simply skipped.
      the callee is REACHABLE through a dot from here.
            Declared in this very module (`cands_of` in sema_call.zen:271
            offers the calling module's own names, exported or not -- 209
            calls in the tree already do this and bootstrap), or imported
            by name from the module that declares it. An exported function
            in a module this one never imported also travels with the type
            and is NOT claimed: that is `travelled_cands`, and skipping it
            is the largest deliberate miss here.
      exactly ONE free function in the tree declares that name.
            Two, and which one a dot picks is a resolution question this
            script would be guessing at.
      the arities match, and the call writes no type arguments and no name
      on the first argument.
            `f<T>(x)` and `f(x: v)` are shapes the rewrite is not obviously
            total over, and neither is common enough to be worth the risk.
      the receiver type has no method of that name.
            That is `make ufcs`'s finding. One fact, one place.
    """
    free, methods, principal = ufcs_world(files)
    checked, hits = 0, []
    # HOW MUCH OF THE TREE THIS RULE CANNOT SEE. `principal.get(home) != recv`
    # below is a `continue`, so a module with no principal type is exempt from
    # this rule ENTIRELY and contributes nothing to say so. Today that is 63
    # of the 159 modules with free functions -- 40% -- and the number was
    # nowhere in the output. Returned so main() can hold it to a ceiling.
    homes = {home for cands in free.values() for home, _, _ in cands}
    exempt = len(homes - set(principal))

    for rel, _, module in files:
        mod = module_path(rel)
        imported = {n: imp.path for imp in module.imports for n, _ in imp.names}
        for fn, own in with_body(module):
            tparams = {t.name for t in fn.tparams}
            frame = {}
            for p in fn.params:
                name = ty_name(p.ty)
                name = own if name == "@Self" else name
                if name and name not in tparams:
                    frame[p.name] = name
            rebound = {p.name for p in fn.params if ty_name(p.ty) is None}
            for node in nodes(fn.body):
                if kind(node) == "Let":
                    rebound.add(node.name)
                elif kind(node) == "Lambda":
                    rebound.update(p.name for p in node.params)
                elif kind(node) == "PatVariant" and node.binder:
                    rebound.add(node.binder)
                elif kind(node) == "Binary" and node.op == "=" \
                        and kind(node.lhs) == "Path":
                    rebound.add(node.lhs.name)
            for name in rebound:
                frame.pop(name, None)
            if not frame:
                continue
            for node in nodes(fn.body):
                if kind(node) != "Call" or kind(node.callee) != "Path":
                    continue
                checked += 1
                called = node.callee.name
                if node.targs or not node.args or called in rebound:
                    continue
                first = node.args[0]
                if first.name is not None or kind(first.value) != "Path":
                    continue
                recv = frame.get(first.value.name)
                cands = free.get(called)
                if recv is None or not cands or len(cands) != 1:
                    continue
                home, takes, count = cands[0]
                if takes != recv or count != len(node.args):
                    continue
                if principal.get(home) != recv:
                    continue
                if not (home == mod or imported.get(called) == home):
                    continue
                if called in methods.get(recv, ()):
                    continue
                recv = first.value.name
                hits.append((rel, f"{node.span}",
                             f"`{called}({recv}, ..)` is `{recv}.{called}(..)`"
                             f" — the receiver column is what makes the"
                             f" order-critical sequence visible"))
    return checked, hits, exempt


def debt(hits, ledger, label):
    """A count-keyed ledger, applied. Returns the lines to print.

    A file over its number has grown the debt and every site in it is
    reported; a file under it has paid some down and the number must come
    with it, which is the same staleness rule every other ledger here runs.
    """
    counted = collections.Counter(rel for rel, _, _ in hits)
    bad = [(where, why) for rel, where, why in sorted(hits)
           if counted[rel] > ledger.get(rel, 0)]
    for rel, owed in sorted(ledger.items()):
        now = counted.get(rel, 0)
        if now < owed:
            bad.append((rel, f"{label} says {owed} and {now} are left."
                             f" Bring the number down with the code —"
                             f" a ledger that overstates is one nobody reads"))
    return bad


def stale(ledger, seen, label):
    """A ledger entry whose violation is gone is a fiction the next reader
    trusts. Same rule the ledgers in tools/gates/faults_reachable.zen and
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
    # Eleven rules over zero files is eleven rules reporting "0 violations". Every
    # count printed below would be 0 and the gate would be green on nothing.
    if not files:
        print("style: found no .zen files under src/ -- every rule below would"
              " report 0 sites and 0 violations. That is a setup error, not a"
              " clean tree.", file=sys.stderr)
        return 2

    from tools.parse import cst
    parser = cst.parser()

    abbrev_n, abbrev_bad, abbrev_seen = rule_abbrev(files, parser)
    ufcs_n, ufcs_hits, ufcs_exempt = rule_ufcs(files)
    import_n, import_hits = rule_import(files, parser)
    results = [
        ("prefix   ", "a prefix names its own folder", *rule_prefix(files), 0),
        ("root     ", "a folder has its root file", *rule_root(files), 0),
        ("vague    ", "a file name means something", *rule_vague(files), 0),
        ("layer    ", "std depends only on std", *rule_layer(files), 0),
        ("impl-home", "an impl goes with its type", *rule_impl_home(files), 0),
        ("verb     ", "no `get_*`, no `do_*`", *rule_verb(files), 0),
        ("banner   ", "no `// helpers` section", *rule_banner(files), 0),
        ("member   ", "a run of `||` on one subject is `is_in([..])`",
         *rule_member(files), 0),
        ("abbrev   ", "abbreviations are words", abbrev_n, abbrev_bad,
         len(ABBREV_OWED)),
        ("ufcs     ", "a free function on the principal type is called on it",
         ufcs_n, debt(ufcs_hits, UFCS_OWED, "UFCS_OWED"),
         sum(UFCS_OWED.values())),
        ("import   ", "an imported name is used by the file that imports it",
         import_n, debt(import_hits, IMPORT_OWED, "IMPORT_OWED"),
         sum(IMPORT_OWED.values())),
    ]

    failed = 0
    for _, rule, _, bad, _ in results:
        for where, why in bad:
            print(f"{where}: {why}")
            failed += 1
    if failed:
        print(f"\nstyle: {failed} violation(s) of docs/STYLE.md."
              f"\n  Fix it, or -- for the three rules that carry a ledger --"
              f" write it into"
              f"\n  ABBREV_OWED (with the word it should be), UFCS_OWED or"
              f" IMPORT_OWED (with"
              f"\n  the file's new count) in {Path(__file__).name}, so the debt"
              f" can shrink and"
              f"\n  cannot quietly grow.")
        return 1

    if stale(ABBREV_OWED, abbrev_seen, "ABBREV_OWED"):
        return 1

    # EACH RULE'S OWN COUNT, not just the file list's. The guard above asks
    # whether there are files; it does not ask whether any rule still finds
    # anything IN them, and ten of these eleven could fall to zero with the
    # eleventh keeping `files` non-empty. Every `checked` below is a loop
    # counter, and a loop that runs zero times adds no violation and reports
    # as a clean pass -- so `layer 0 checked, 0 violations — std depends only
    # on std` is a sentence this gate would print, in full, over a rule that
    # had stopped reading imports altogether. That rule is the one the notes
    # record as caught by nothing else in the tree.
    #
    # Zero and not a floor per rule: a floor for eleven rules is eleven
    # numbers to keep, and `checked` here counts SITES, which move with every
    # ordinary commit. Zero is the line that cannot be crossed by honest
    # work, and it is the same line `cap`, `parse`, `fmt`, `lextile`,
    # `faults` and `dupcomments` draw at their file lists.
    # A MODULE WITH NO PRINCIPAL TYPE IS EXEMPT FROM `ufcs` ENTIRELY, and
    # nothing said so. `principal` is a strict-majority vote over each
    # module's free-function first parameters; a module that has no majority
    # has no subject, every candidate call in it is skipped, and `checked`
    # keeps counting the call sites anyway -- so the rule can quietly stop
    # covering a file while its number goes UP.
    #
    # Five modules currently sit one function away from losing their vote
    # (sema.sema_pin, std.ast.ast_node, std.core.bool, std.core.result,
    # std.lex.lex_diag), so this is not a theoretical drift: one added helper
    # whose first parameter is not the subject retires the rule for that whole
    # file, permanently and silently.
    #
    # A CEILING, not a floor, and it ratchets the way every other ledger here
    # does: 63 is what the tree had when this was written, going down is free,
    # and going up is a deliberate line in a commit. Modules are added rarely
    # enough that this is not a number anyone re-baselines by habit.
    #
    # THE DECISION THIS LANE MADE, measured and not assumed. The 62 exempt
    # modules split in two. Twenty-nine elect a type by strict majority but
    # the majority is declared in another folder -- `lsp.lsp_names` votes
    # `Alloc` 20 of 20, `gen.gen_name` votes `String` 30 of 38, every
    # `lsp_*` votes a sema type. Granting any of them its vote through this
    # rule's own machinery surfaces real conversions: 384 sites across those
    # 29 (`lsp/` 159, `gen/` 135, `sema/` 73), which is the campaign
    # UFCS_OWED's history records as finished at 1153 sites -- reopened, not
    # a documentation gap. The other 33 have no majority to declare:
    # `fmt.fmt_break` takes `Alloc` 19, `Src` 12 and `Vec` 5 as first
    # parameters, and no single subject is true there to grant. So the
    # ceiling holds where it is, and the way down runs through code --
    # one file's conversions at a time -- not through this table.
    if ufcs_exempt > UFCS_EXEMPT_CEILING:
        print(f"style: {ufcs_exempt} module(s) have no principal type and are"
              f" exempt from the `ufcs` rule, up from {UFCS_EXEMPT_CEILING}."
              " A module loses its subject when no single type is the first"
              " parameter of a strict majority of its free functions, and"
              " every call in it then goes unchecked while `ufcs N checked`"
              " keeps rising. Give the new module a subject, or raise"
              f" UFCS_EXEMPT_CEILING in {Path(__file__).name} and say which"
              " module and why.", file=sys.stderr)
        return 1

    silent = [name.strip() for name, _, checked, _, _ in results if not checked]
    if silent:
        print(f"style: {', '.join(silent)} checked 0 sites. A rule that finds"
              " nothing reports no violations and reads exactly like a clean"
              " tree. src/ moved, the parse stopped yielding declarations, or"
              " the rule broke -- fix it, do not read this as green.",
              file=sys.stderr)
        return 2

    for name, rule, checked, _, owed in results:
        note = f", {owed} written down" if owed else ""
        print(f"  {name}  {checked:5} checked, 0 violations{note}  — {rule}")
    sites = sum(checked for _, _, checked, _, _ in results)
    owed = sum(owed for _, _, _, _, owed in results)
    print(f"style: {len(results)} rules, {sites} sites, 0 violations,"
          f" {owed} written down;"
          f" {ufcs_exempt} module(s) have no principal type for `ufcs` to"
          f" check against (ceiling {UFCS_EXEMPT_CEILING})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
