#!/usr/bin/env bash
# The fmt gate's FILE SET, in ONE place so CI and integrate.sh cannot disagree about which files
# have to be formatted. Both call this; neither carries its own `find`.
#
# They had drifted: CI globbed `src tests examples driver.zen build.zen` while integrate.sh also
# included `tools`, so a misformatted tools/*.zen passed CI and only failed on someone's local
# ritual. Same failure shape as the boundary suite's stale file set — two lists, written apart,
# with nothing comparing them.
#
# tests/fixtures/fmt/*_unformatted.zen are excluded: they are the fmt oracle's INPUT fixtures and
# are deliberately unformatted.
#
# Checked PER FILE so every offender is named, not just the first one.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

# The `find` roots are asserted, not assumed. `2>/dev/null` used to hide a missing root, so renaming
# `tools/` would have silently shrunk the checked set — the exact drift this file exists to prevent,
# just centralised. A missing root now fails, and a corpus that collapses below FLOOR fails too (a
# zero-iteration loop would otherwise `exit 0` having checked nothing).
ZEN=${ZEN:-./zen}
FLOOR=${FMT_CHECK_FLOOR:-300}
for root in src tests examples tools driver.zen build.zen; do
  [ -e "$root" ] || { echo "::error::fmt-check: missing root '$root' — the checked file set has drifted"; exit 2; }
done
files=$(find src tests examples tools driver.zen build.zen -name '*.zen' \
          ! -path 'tests/fixtures/fmt/*_unformatted.zen' | LC_ALL=C sort)
count=$(printf '%s\n' "$files" | grep -c '\.zen$')
[ "$count" -ge "$FLOOR" ] || { echo "::error::fmt-check: only $count .zen files found (floor $FLOOR) — the file set collapsed"; exit 2; }
bad=0
for f in $files; do
  if ! "$ZEN" fmt --check "$f"; then
    echo "::error file=$f::$f is not zenc-fmt clean — run '$ZEN fmt $f' and commit the result"
    bad=1
  fi
done
exit $bad
