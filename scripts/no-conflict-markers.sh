#!/usr/bin/env bash
# The conflict-marker tripwire, in ONE place so CI and integrate.sh cannot disagree about what a
# conflict marker is. Both call this; neither carries its own copy of the pattern.
#
# Catches BOTH the outer markers (<<<<<<< / >>>>>>>) AND the middle dividers a botched resolution
# leaves behind after the outer ones are deleted: the merge separator `=======` (exactly seven '='
# alone on a line — the `$` anchor avoids markdown h1 rules and `====…` comment banners of other
# widths) and the diff3 base divider `||||||| ` (seven pipes + a space). A stray middle line has
# shipped to main before; it is just as corrupt as an outer marker.
set -euo pipefail
root=$(git rev-parse --show-toplevel) || { echo "FAIL: not a git repository"; exit 2; }
cd "$root"

MARKERS='^(<<<<<<< |>>>>>>> |\|\|\|\|\|\|\| |=======$)'
# Read git grep's status EXPLICITLY. `if git grep …; then fail; fi` treats every non-zero status as
# "clean", and git grep exits 128 outside a repository — the same shape ci.yml:25-27 records as having
# made this gate unfailable when it ran before checkout. 0 = matches (fail), 1 = no matches (pass),
# anything else = the gate itself is broken and must not report success.
rc=0
git grep -nE "$MARKERS" >/dev/null 2>&1 || rc=$?
case "$rc" in
  0) git grep -nE "$MARKERS" | head -20; echo "FAIL: conflict markers present"; exit 1 ;;
  1) ;;
  *) echo "FAIL: conflict-marker scan could not run (git grep exit $rc; not a git repository?)"; exit 2 ;;
esac
