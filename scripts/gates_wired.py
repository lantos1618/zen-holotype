#!/usr/bin/env python3
"""Every gate this repository owns is REACHED by `make all`.

THE FAILURE THIS EXISTS FOR, which has happened at least four times here:

  - `scripts/scope.py` sat on main for a month with `grep -rn scope.py Makefile
    .github/` returning nothing, while STYLE.md's table promised `make scope`
    and its prose said the rule was enforced "and now also at `make test`".
  - `make grammar-test` was `npx tree-sitter test` over a directory that does
    not exist: "Total parses: 0", exit 0.
  - `tests/parse/errors/` (26 must-not-parse fixtures) and `tests/bench/` were
    run by no target at all, so `allocs_op: 0` -- cited in src/ as a number
    that fails the build -- was a number nothing had ever computed.
  - `editors` was a target whose name is also a DIRECTORY, so make found the
    directory, called the target up to date, and ran the script never.

Every one of those reported success while doing nothing, and every one was
found by accident. The common shape is not a bug in a gate -- it is a gate
NOBODY CALLS, and no gate can detect that about itself. So this one asks the
question from outside: for each driver in the tree, is there a target whose
recipe runs it, and is that target reachable from `all`?

TWO WAYS TO BE UNREACHED, and the second is the quiet one:

  UNINVOKED   no recipe anywhere mentions the file. This is scope.py's case.
  ORPHANED    a recipe runs it, but no chain of prerequisites leads from `all`
              to that target. `make lint` is real and green and nothing in a
              default build ever asks for it. That is a legitimate choice --
              which is why it goes in the ledger with the reason, rather than
              being invisible.

THE LEDGER is scripts/UNWIRED.txt. Every entry is a driver that `make all`
deliberately does not reach, with the sentence saying why. It ratchets in both
directions: a driver that is neither wired nor written down is an error, AND a
name in the ledger that becomes reachable is an error too -- so a debt cannot
quietly grow, and a debt somebody paid cannot sit there pretending.
(`tools/gates/faults_reachable.zen`'s `owed` is the same shape, for the same
reason.)

THE THIRD CHECK is the `editors` case, and it is a property of make rather than
of any script: a phony target whose name matches a file or directory in the
tree is a target make will consider up to date and never run. `.PHONY` is what
prevents it. So every target `all` reaches must either be declared `.PHONY` or
have a real file to build.

WHAT THIS DOES NOT DO: judge whether a gate that runs can fail. That is each
gate's own problem, and the good ones in this tree answer it with an assertion
that their input set is non-empty (`cap`, `parse`, `fmt`, `lextile`, `faults`,
`dupcomments`, `emit-runs`) or with a live positive control
(`scripts/asan_corpus.sh`). This one only answers "does anybody call it".

    0   every driver is reached from `all`, or is written down
    1   a driver is unreached and not written down, or the ledger is stale,
        or a reachable target is neither .PHONY nor a real file
    2   the harness could not run: no Makefile, or no drivers found -- which
        would make this the empty-set gate it exists to catch

2 IS NOT A PASS.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = ROOT / "Makefile"
LEDGER = ROOT / "scripts" / "UNWIRED.txt"

# WHERE A DRIVER LIVES. Three directories and one file pattern, and each is
# here because something in it is (or was) a gate:
#   scripts/         the python, shell and awk gates. Their DATA files
#                    (a ledger, a budget list) are not drivers and are not
#                    matched: a ledger is read by a driver, never run
#   tools/gates/     the Zen gates, compiled by `$(call gate,<stem>)`
#   tests/**/*.sh    asan.sh, leak.sh, check.sh, regression.sh -- shell gates
#                    that live beside the suite they drive
#   tests/*.py       run.py and lint.py, the two suite runners
DRIVER_GLOBS = (
    "scripts/*.py", "scripts/*.sh", "scripts/*.awk",
    "tools/gates/*.zen",
    "tools/**/*.sh",
    "tests/**/*.sh", "tests/*.py",
)

# NOT DRIVERS, and the distinction is "is it run, or is it imported". These are
# a package that scripts/style.py imports; they have no recipe of their own and
# never should. Their coverage is style.py's coverage.
LIBRARIES = ("tools/parse/",)

# A target line: `name: prereqs`. Excludes `:=` assignments, pattern rules and
# the `.PHONY`/`.SHELLFLAGS` specials, which are not targets to run.
TARGET = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_./-]*)\s*:(?!=)\s*(.*)$")
PHONY = re.compile(r"^\.PHONY\s*:\s*(.*)$")

# The root make is asked for. Everything under it is what a plain `make` runs.
ROOT_TARGET = "all"


def read_makefile() -> tuple[dict[str, list[str]], dict[str, str], set[str]]:
    """(prereqs by target, recipe text by target, phony names).

    A recipe line is a TAB-indented line after a target, or a continuation of
    one -- which is why `$(call gate,...)` inside a `\\`-continued line still
    lands in the right target's text.
    """
    prereqs: dict[str, list[str]] = {}
    recipes: dict[str, str] = {}
    phony: set[str] = set()
    current: str | None = None
    for raw in MAKEFILE.read_text(encoding="utf-8").splitlines():
        m = PHONY.match(raw)
        if m:
            phony.update(m.group(1).split())
            current = None
            continue
        if raw.startswith("\t"):
            if current:
                recipes[current] = recipes.get(current, "") + raw + "\n"
            continue
        m = TARGET.match(raw)
        if m:
            current = m.group(1)
            # A second rule for one target adds prerequisites; it does not
            # replace them.
            prereqs.setdefault(current, []).extend(m.group(2).split())
            recipes.setdefault(current, "")
            continue
        if raw.strip() and not raw.startswith("#"):
            current = None
    return prereqs, recipes, phony


def reachable_from(prereqs: dict[str, list[str]], root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        t = stack.pop()
        if t in seen:
            continue
        seen.add(t)
        stack.extend(prereqs.get(t, []))
    return seen


def read_ledger() -> dict[str, str]:
    """path -> reason. `#` comments and blank lines ignored; a line is
    `<path><whitespace><reason>`."""
    out: dict[str, str] = {}
    if not LEDGER.is_file():
        return out
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, reason = line.partition(" ")
        out[path] = reason.strip()
    return out


def drivers() -> list[str]:
    out: set[str] = set()
    for pattern in DRIVER_GLOBS:
        for p in ROOT.glob(pattern):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if any(rel.startswith(lib) for lib in LIBRARIES):
                continue
            out.add(rel)
    return sorted(out)


def invokers(rel: str, recipes: dict[str, str]) -> set[str]:
    """Which targets' recipes run this driver.

    Two spellings. A script is named by PATH (`$(PY) scripts/style.py`), so the
    path is what is searched for. A Zen gate is named by STEM, because
    `$(call gate,line_cap)` is what compiles and runs it -- searching for the
    path would find nothing and report every Zen gate as dead.
    """
    stem = Path(rel).stem
    needles = [rel]
    if rel.startswith("tools/gates/"):
        needles = [f"gate,{stem}", f"gates/{stem}"]
    return {t for t, body in recipes.items()
            if body and any(n in body for n in needles)}


def main() -> int:
    if not MAKEFILE.is_file():
        print(f"gates_wired: no Makefile at {MAKEFILE}", file=sys.stderr)
        return 2

    prereqs, recipes, phony = read_makefile()
    if ROOT_TARGET not in prereqs:
        print(f"gates_wired: the Makefile has no `{ROOT_TARGET}` target, so"
              " there is no root to measure reachability from -- this gate"
              " cannot run", file=sys.stderr)
        return 2

    found = drivers()
    if not found:
        print("gates_wired: found no gate drivers under "
              f"{', '.join(DRIVER_GLOBS)} -- either the tree moved or these"
              " globs stopped matching, and this gate just stopped checking",
              file=sys.stderr)
        return 2

    live = reachable_from(prereqs, ROOT_TARGET)
    ledger = read_ledger()

    bad: list[str] = []
    wired = 0
    for rel in found:
        calls = invokers(rel, recipes)
        reached = sorted(calls & live)
        if reached:
            wired += 1
            if rel in ledger:
                bad.append(
                    f"{rel}: in scripts/UNWIRED.txt, but `make "
                    f"{reached[0]}` runs it and `{ROOT_TARGET}` reaches that."
                    " The debt is paid -- delete the line."
                )
            continue
        if rel in ledger:
            continue
        if calls:
            bad.append(
                f"{rel}: ORPHANED. {', '.join(sorted(calls))} run(s) it, but"
                f" nothing leads from `{ROOT_TARGET}` to that target, so a"
                " plain `make` never does. Put it in the prerequisite chain,"
                " or write it into scripts/UNWIRED.txt with the reason."
            )
        else:
            bad.append(
                f"{rel}: UNINVOKED. No recipe in the Makefile mentions it. A"
                " gate nobody calls is a gate that goes stale unobserved --"
                " wire it up, write it into scripts/UNWIRED.txt, or delete it."
            )

    # THE `editors` CASE. A target whose name is also a path is a target make
    # calls up to date and never runs -- silently, with no output at all.
    for target in sorted(live):
        if target in phony:
            continue
        if not recipes.get(target) and target not in prereqs:
            continue
        # A FILE THE BUILD PRODUCES is not the `editors` case, and asking
        # whether that path EXISTS answers a different question: a build
        # product does not exist until something builds it. This check was
        # written with `(ROOT / target).exists()` here, and it made the
        # gate's verdict move with a build artifact instead of with the
        # Makefile -- green on a worktree holding a stale `grammar/zen.so`,
        # red on a clean checkout of the very same commit. A gate that
        # answers differently on two identical trees is not a gate.
        #
        # What actually separates the two cases is the RECIPE. A file
        # target's recipe WRITES a file of that name -- `grammar/zen.so`'s
        # is `$(CC) -shared -fPIC -o grammar/zen.so ...`, so the target
        # appears in it as a whole word (or as `$@`). The `editors` target's
        # recipe was `$(PY) scripts/editors_check.py`, which writes nothing
        # called `editors`; the substring is there, the WORD is not, which
        # is why this splits before it looks.
        recipe = recipes.get(target, "")
        if target in recipe.split() or "$@" in recipe:
            continue
        bad.append(
            f"{target}: reached from `{ROOT_TARGET}` but neither declared"
            " .PHONY nor a file this build produces. If a file or directory of"
            " that name ever appears, make will call it up to date and run its"
            " recipe never."
        )

    stale = [p for p in ledger if p not in found]
    for p in stale:
        bad.append(f"{p}: named in scripts/UNWIRED.txt and does not exist."
                   " Delete the line.")

    for line in bad:
        print(f"gates_wired: {line}", file=sys.stderr)
    if bad:
        print(f"\ngates_wired: {len(bad)} problem(s).", file=sys.stderr)
        return 1

    print(f"gates_wired: {len(found)} driver(s), {wired} reached from "
          f"`{ROOT_TARGET}`, {len(ledger)} written down as deliberately not")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
