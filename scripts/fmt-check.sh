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

ZEN=${ZEN:-./zen}
bad=0
for f in $(find src tests examples tools driver.zen build.zen -name '*.zen' \
             ! -path 'tests/fixtures/fmt/*_unformatted.zen' 2>/dev/null | LC_ALL=C sort); do
  if ! "$ZEN" fmt --check "$f"; then
    echo "::error file=$f::$f is not zenc-fmt clean — run '$ZEN fmt $f' and commit the result"
    bad=1
  fi
done
exit $bad
