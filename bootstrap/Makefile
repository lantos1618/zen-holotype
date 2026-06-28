# Python-free build + regen for the self-hosted Zen compiler.
#
# The compiler IS the `zenc` binary: cc compiles bootstrap/{zenc.gen.c,zenrt.c,driver.c}
# (zenc.gen.c is the committed C the Zen frontend emits for the bootstrap compiler sources). NO Python is in
# this loop — this Makefile is the binary-only replacement for the old Python generator.
#
#   make -f bootstrap/Makefile zenc     # build the standalone compiler binary
#   make -f bootstrap/Makefile regen    # rebuild zenc, then regenerate zenc.gen.c with it
#
# `regen` reproduces the committed bootstrap/zenc.gen.c byte-for-byte (the fixpoint), via the
# binary's --build-self mode — the old generator path, but with zero Python.
# Verify:  make -f bootstrap/Makefile regen && git diff --quiet bootstrap/zenc.gen.c

# This Makefile's own directory (bootstrap/) and the project root (its parent), resolved so the
# targets work regardless of the cwd `make -f` is invoked from.
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(HERE)..)

# Use ccache transparently when it's installed (caches the ~3MB zenc.gen.c recompile); plain `cc`
# otherwise, so the build is byte-identical whether or not ccache is present. An explicit `CC=...`
# in the environment still wins (this only sets the default).
CCACHE  := $(shell command -v ccache 2>/dev/null)
CC      ?= $(if $(CCACHE),ccache cc,cc)
CFLAGS  ?= -std=gnu11 -fwrapv -w
ZENC    := $(ROOT)/zenc
GEN_C   := $(HERE)zenc.gen.c
SOURCES := $(HERE)zenc.gen.c $(HERE)zenrt.c

.PHONY: zenc regen clean oracle oracle-fast setup-git resolve-seed

# The standalone, Python-free compiler binary: driver.zen is the entry (emitted as zen_main); zenrt.c
# Built to a per-builder pid temp then atomically `mv`d into place: two concurrent `make` runs (e.g.
# parallel `make oracle`) each compile their own temp and never see a half-written `$(ZENC)`, since a
# direct `cc -o $(ZENC)` truncates-then-writes and a racing `./zenc` exec could hit a partial binary.
zenc:
	$(CC) $(CFLAGS) $(SOURCES) -o $(ZENC).$$$$.tmp && mv -f $(ZENC).$$$$.tmp $(ZENC)

# Regenerate bootstrap/zenc.gen.c with the binary (no Python): `--build-self` reads
# <srcroot>/bootstrap/sources.txt, strips imports, concatenates in graph/SCC-checked order, and emits
# the same C the committed file holds. This is the replacement for the old Python regen command.
regen: zenc
	$(ZENC) --build-self $(GEN_C) $(ROOT)

clean:
	rm -f $(ZENC)

# The Zen-native correctness oracle (tests/oracle.zen) — the self-hosted replacement for the pytest
# value/verdict harness. Build it with the freshly-built `zenc`, then run it from the repo ROOT (the
# oracle drives `./zenc` + `tests/oracle_runner.c` and reads bootstrap/zenc.gen.c via relative paths).
# The oracle's exit code is the failing-case count, so `make oracle` fails iff any case fails.
#   make -f bootstrap/Makefile oracle
oracle: zenc
	cd $(ROOT) && ZO=/tmp/zo_oracle.$$$$ && $(ZENC) build tests/oracle.zen -o $$ZO && $$ZO; rc=$$?; rm -f $$ZO; exit $$rc

# Fast SMOKE subset of the oracle (~13s vs ~3min): runs only the quick deterministic correctness
# suites (value + verdict) via ZEN_ORACLE_FAST and SKIPS the slow subprocess-heavy suites (modules /
# build / boundaries / misc / fuzz / fixpoint). For inner-loop iteration only — the full `make
# oracle` above stays the merge gate. See tests/oracle.zen for which suites the flag selects.
#   make -f bootstrap/Makefile oracle-fast
oracle-fast: zenc
	cd $(ROOT) && ZO=/tmp/zo_oracle_fast.$$$$ && $(ZENC) build tests/oracle.zen -o $$ZO && ZEN_ORACLE_FAST=1 $$ZO; rc=$$?; rm -f $$ZO; exit $$rc

# Register the local git merge driver that auto-resolves the generated seed (bootstrap/zenc.gen.c).
# `.gitattributes` maps that path to `merge=zenseed`; this points the driver at scripts/zenseed-merge.sh.
# Merge drivers live in LOCAL git config (not committed), so every clone must run this once.
# After a merge/rebase that touched the seed, run `make resolve-seed` to reproduce it from source.
setup-git:
	cd $(ROOT) && git config merge.zenseed.name "zen generated-seed (regen from .zen source after merge)" \
	  && git config merge.zenseed.driver '$(ROOT)/scripts/zenseed-merge.sh %O %A %B %P' \
	  && echo "registered merge.zenseed driver; run 'make -f bootstrap/Makefile resolve-seed' after a seed merge"

# Reproduce + stage the committed seed from the .zen sources after a merge/rebase resolved the seed
# conflict (the seed is a build artifact, so a textual merge is meaningless — regen is the truth).
# Use AFTER the conflict is resolved to a clean file (the zenseed driver does this automatically, or
# `git rebase -X theirs` / `git checkout --theirs bootstrap/zenc.gen.c` by hand): builds zenc from the
# resolved seed, regenerates the byte-exact seed, and stages it. Commit it yourself (or, mid-rebase,
# `git add bootstrap/zenc.gen.c && git rebase --continue`).
resolve-seed: regen
	cd $(ROOT) && git add bootstrap/zenc.gen.c && echo "seed regenerated + staged — commit it (or 'git rebase --continue' if mid-rebase)"
