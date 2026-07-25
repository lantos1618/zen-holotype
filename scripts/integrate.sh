#!/usr/bin/env bash
# integrate.sh — THE merge-verification ritual, mechanized. Run from a branch that has just
# merged origin/main (conflicts resolved; seed: take main's, it gets regenerated below).
# Prints MERGE-READY only if EVERY gate passes. No step may be skipped by hand — that's the point.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

# one integration at a time per box — concurrent full harnesses thrash and OOM
exec 9>/tmp/zenc-integrate.lock
flock 9 || { echo "another integrate.sh holds the lock"; exit 1; }

echo "== gate 0: no conflict markers in tracked files"
# shared with .github/workflows/ci.yml — one definition of "conflict marker"
bash scripts/no-conflict-markers.sh

echo "== gate 1: bootstrap + regen from merged sources"
export ZENC_CACHE_DIR="$(mktemp -d /tmp/zenc-integrate.XXXXXX)"
trap 'rm -rf "$ZENC_CACHE_DIR"' EXIT
make >/dev/null
make regen

echo "== gate 2: converge fixpoint (max 3 cycles)"
ok=""
for i in 1 2 3; do
  cp bootstrap/zenc.gen.c /tmp/integrate_seed.$$
  # intermediate rebuilds at -O1: convergence needs a correct compiler, not a fast one
  touch bootstrap/zenc.gen.c && make CFLAGS="-O1 -std=gnu11 -fwrapv -fno-strict-aliasing -Wno-builtin-declaration-mismatch" >/dev/null && make regen
  if cmp -s bootstrap/zenc.gen.c /tmp/integrate_seed.$$; then ok=1; break; fi
done
# leave a final -O2 binary in place for the gates that follow
touch bootstrap/zenc.gen.c && make >/dev/null
rm -f /tmp/integrate_seed.$$
[ -n "$ok" ] || { echo "FAIL: seed did not converge in 3 cycles"; exit 1; }
echo "   fixpoint byte-stable"

echo "== gate 3: warning-free -O2 seed compile"
warn=$(cc -O2 -std=gnu11 -fwrapv -fno-strict-aliasing -Wno-builtin-declaration-mismatch -c bootstrap/zenc.gen.c -o /dev/null 2>&1 | wc -l)
[ "$warn" -eq 0 ] || { echo "FAIL: $warn warning lines at -O2"; exit 1; }

echo "== gate 4: full harness with explicit ALL-PASS assertion"
make harness 2>&1 | tee /tmp/integrate_h.$$ | tail -3
grep -q "zen harness: ALL PASS" /tmp/integrate_h.$$ || { rm -f /tmp/integrate_h.$$; echo "FAIL: no ALL PASS"; exit 1; }
rm -f /tmp/integrate_h.$$

echo "== gate 5: whole-tree fmt clean (shared file set, per-file)"
# shared with .github/workflows/ci.yml — one definition of the fmt file set
bash scripts/fmt-check.sh || { echo "FAIL: fmt drift (files named above)"; exit 1; }

# gates 6+7: the Makefile gates CI's `gate` runs but the local ritual historically did NOT — the exact
# gap that let PR #633 report MERGE-READY locally while CI went red on docs-check. Run them here so a
# nonzero exit ABORTS before MERGE-READY prints.
echo "== gate 6: docs-check (doc link / reference integrity)"
make docs-check >/dev/null || { echo "FAIL: docs-check (broken doc link/reference)"; exit 1; }

echo "== gate 7: ffi-verify (FFI binding surface)"
make ffi-verify >/dev/null || { echo "FAIL: ffi-verify (FFI binding drift)"; exit 1; }

git add bootstrap/zenc.gen.c
echo "MERGE-READY (seed staged at verified fixpoint — include it in the merge commit)"
