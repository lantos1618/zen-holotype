#!/usr/bin/env python3
"""Every fault the compiler declares must have a site that raises it.

A fault variant is a PROMISE: it is a sentence in `message()` saying the
compiler will tell you when you break a particular rule. A variant that
is declared, worded, and never constructed keeps the promise nowhere --
the program that breaks the rule compiles, and the enum reads complete
to anyone auditing it. That is this repository's recurring failure mode
in its purest form: a gate that cannot fail.

Five of them were found this way, all at once, by a grep no cheaper than
this file. So the grep lives here and runs in the build.

WHAT IT DOES NOT CATCH, and this matters because the check is green
today. A construction site is not a diagnostic anyone can reach -- the
site may sit behind a condition that is never true. This script proves
only that somebody wrote the raise. The must-fail suite is what proves
the rule is enforced; this is the cheap standing check underneath it.

GREEN HERE DOES NOT MEAN EVERY DIAGNOSTIC WORKS. It means no fault is
silently absent: the ones still absent are written down in OWED
below, each against the work that owes it. Closing one is deleting its
line -- and the count is not written here, because a number in a comment
is the next thing to go stale. OWED's length is the count. Adding a variant without a raise site and without an OWED entry is
what turns this red -- so the debt can shrink and cannot quietly grow.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# fault enum -> the file that declares it. The declaring file is skipped
# when hunting for construction sites: `message()` mentions every variant
# by name and would match all of them.
ENUMS = {
    "SemaFault": ROOT / "src/sema/sema_diag.zen",
    "GenFault": ROOT / "src/gen/gen_diag.zen",
}

# THE DEBT. Every entry is a rule `docs/DESIGN.md` states, worded in
# `message()`, that no program can currently trigger -- so the program
# that breaks the rule compiles. Each is against the work that owes it.
#
# Deleting a line is how a hole closes. Adding one requires a reason
# that names the law and what blocks it, because the alternative to
# writing it down here is the enum reading complete while it is not,
# which is the state this file was written to end.
OWED = {
    "InfiniteSize":
        "a field cycle that never reaches an indirection. sema.zen:35 "
        "admits it; the layout walk does not terminate rather than "
        "reporting.",
}

VARIANT = re.compile(r"^\s*[|=]\s*([A-Z]\w*)\s*\(")


def variants_of(decl: Path, enum: str) -> list[str]:
    """The variant names in `enum`'s declaration, in source order."""
    found, inside = [], False
    for line in decl.read_text().splitlines():
        if line.startswith(f"{enum}* ="):
            inside = True
        elif inside and line and not line[0].isspace():
            break
        if not inside:
            continue
        m = VARIANT.match(line if line.startswith(f"{enum}* =") is False else line.split("=", 1)[1])
        if m:
            found.append(m.group(1))
    return found


def constructed(name: str, decl: Path) -> bool:
    """Is `name` built anywhere outside its own declaring file?"""
    call = re.compile(rf"\b{re.escape(name)}\s*\(")
    for path in ROOT.joinpath("src").rglob("*.zen"):
        if path == decl:
            continue
        if call.search(path.read_text()):
            return True
    return False


def main() -> int:
    unreachable = []
    for enum, decl in ENUMS.items():
        if not decl.exists():
            print(f"faults: {decl.relative_to(ROOT)} is gone; this script names it")
            return 1
        names = variants_of(decl, enum)
        if not names:
            print(f"faults: found no variants of {enum} in {decl.relative_to(ROOT)}."
                  f" The declaration moved or changed shape, and this check just"
                  f" stopped checking -- fix the script, do not delete it.")
            return 1
        for name in names:
            if name in OWED or constructed(name, decl):
                continue
            unreachable.append((enum, name, decl))

    for enum, name, decl in unreachable:
        print(f"{decl.relative_to(ROOT)}: {enum}.{name} is declared and worded,"
              f" and nothing constructs it")
    if unreachable:
        print(f"\nfaults: {len(unreachable)} promised diagnostic(s) that cannot fire."
              f"\n  Raise it, or add it to OWED in {Path(__file__).name} with the law"
              f"\n  it enforces and what blocks it. An enum that reads complete and"
              f"\n  is not is worse than one that admits the hole.")
        return 1

    # A name in OWED that HAS a raise site is a hole someone closed and
    # did not delete. Silent staleness here would let the ledger drift
    # back into the fiction it replaced, so it is an error too.
    paid = [name for enum, decl in ENUMS.items()
            for name in variants_of(decl, enum)
            if name in OWED and constructed(name, decl)]
    for name in paid:
        print(f"faults: {name} is in OWED and something constructs it now."
              f" Delete its line from {Path(__file__).name} — the debt is paid.")
    if paid:
        return 1

    total = sum(len(variants_of(d, e)) for e, d in ENUMS.items())
    print(f"faults: {total} declared, {total - len(OWED)} constructed,"
          f" {len(OWED)} owed and written down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
