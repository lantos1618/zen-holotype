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
cd "$(git rev-parse --show-toplevel)"

MARKERS='^(<<<<<<< |>>>>>>> |\|\|\|\|\|\|\| |=======$)'
if git grep -nE "$MARKERS" >/dev/null 2>&1; then
  git grep -nE "$MARKERS" | head -20
  echo "FAIL: conflict markers present"
  exit 1
fi
