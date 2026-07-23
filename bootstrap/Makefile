# Python-free build + regen for the self-hosted Zen compiler.
#
# The compiler IS the `zenc` binary: cc compiles bootstrap/{zenc.gen.c,zenrt.c}.
# zenc.gen.c is the committed C emitted from the Zen compiler sources plus driver.zen. NO Python is
# in this loop.
#
#   make -f bootstrap/Makefile zen      # build the standalone compiler binary
#   make -f bootstrap/Makefile regen    # rebuild zen, then regenerate zenc.gen.c with it
#
# `regen` reproduces the committed bootstrap/zenc.gen.c byte-for-byte (the fixpoint), via the
# binary's --build-self mode — the old generator path, but with zero Python.
# Verify:  make -f bootstrap/Makefile regen && git diff --quiet bootstrap/zenc.gen.c

# This Makefile's own directory (bootstrap/) and the project root (its parent), resolved so the
# targets work regardless of the cwd `make -f` is invoked from.
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(HERE)..)

# Use ccache transparently when it's installed (caches the ~7 MB zenc.gen.c recompile); plain `cc`
# otherwise, so the build is byte-identical whether or not ccache is present. An explicit `CC=...`
# in the environment still wins (this only sets the default).
CCACHE  := $(shell command -v ccache 2>/dev/null)
# GNU make predefines CC=cc with origin "default", so `CC ?= ...` would never actually select ccache.
# Override only that built-in default; a command-line/environment CC remains authoritative.
ifeq ($(origin CC),default)
CC      := $(if $(CCACHE),ccache cc,cc)
endif
# Apple Clang treats generated forward calls as errors unless this diagnostic
# is made non-fatal. (The runtime itself defines macOS's ucontext feature macro.)
# -Wno-builtin-declaration-mismatch: Zen's C floor models heap pointers as `uint8_t*` and sizes as
# `int64_t` (the language has no u64/size_t or void*), so its `malloc`/`memcpy` foreign prototypes
# deliberately differ from the C builtins. The calls are ABI-compatible on LP64 (ffi-verify checks
# the ABI class of every foreign prototype against the real system headers); matching the builtins
# exactly needs a size_t/void* mapping in the language — see STATUS.md's defects ledger. Every OTHER
# warning is left enabled: no blanket -w.
# -O2 -fno-strict-aliasing: matches the repo-root build.zen's default `zen` target. Measured on the
# seed: ~2x faster self-compile (--build-self 5.5s vs 10.3s at -O0), 17% smaller binary, byte-
# identical emitted C, zero new warnings. -fno-strict-aliasing is REQUIRED with -O2: the emitted C
# is void*-punning and relies on strict aliasing being off (-O0/-O1 keep it off implicitly).
CFLAGS  ?= -std=gnu11 -O2 -fno-strict-aliasing -Wno-error=implicit-function-declaration -fwrapv -Wno-builtin-declaration-mismatch
ZENC    := $(ROOT)/zen
GEN_C   := $(HERE)zenc.gen.c
SOURCES := $(HERE)zenc.gen.c $(HERE)zenrt.c
HEADERS := $(HERE)zenrt.h

.PHONY: zen build regen clean harness harness-fast difftest docs-check ffi-verify setup-git resolve-seed

# The standalone, Python-free compiler binary: driver.zen is the entry (emitted as zen_main); zenrt.c
# supplies the runtime. Keep the friendly phony target as an alias, but put the recipe on the real file:
# an unchanged `make zen` must only check mtimes, not recompile the ~7 MB generated C seed. The
# Makefile is also a prerequisite because changing its default compiler flags must rebuild the binary.
zen: $(ZENC)

# Build to a per-builder pid temp then atomically `mv` it into place: two concurrent `make` runs (e.g.
# parallel `make harness`) each compile their own temp and never see a half-written `$(ZENC)`, since a
# direct `cc -o $(ZENC)` truncates-then-writes and a racing `./zen` exec could hit a partial binary.
$(ZENC): $(SOURCES) $(HEADERS) $(HERE)Makefile
	$(CC) $(CFLAGS) $(SOURCES) -o $(ZENC).$$$$.tmp && mv -f $(ZENC).$$$$.tmp $(ZENC)

# The self-hosted path: after bootstrap, zen builds zen through the repo-root build.zen (project
# mode). Writes ./zen-next (-O2, the next-generation compiler) + ./zen-debug (-g); promote with
# `mv zen-next zen`. This Makefile keeps only what CANNOT go through build.zen: the cc-seed
# bootstrap above (no zen exists yet) and the seed-regen fixpoint below.
build: zen
	cd $(ROOT) && $(ZENC) build

# Regenerate through a PID-specific temp and replace the seed only when its bytes changed. A fixpoint
# regen must preserve zenc.gen.c's mtime; otherwise the following `make zen` recompiles ~7 MB of
# identical C for no reason. The temp also keeps a failed/interrupted emission away from the seed.
# `--build-self` reads <srcroot>/bootstrap/sources.txt, strips imports, concatenates in graph/SCC order,
# and emits the same C the committed file holds. This is the replacement for the old Python generator.
regen: zen
	@tmp=$(GEN_C).$$$$.tmp; \
	trap 'rm -f "$$tmp"' 0 1 2 15; \
	$(ZENC) --build-self "$$tmp" $(ROOT) || exit $$?; \
	if cmp -s "$$tmp" $(GEN_C); then rm -f "$$tmp"; else mv -f "$$tmp" $(GEN_C); fi; \
	trap - 0 1 2 15

clean:
	rm -f $(ZENC)

# The Zen-native correctness harness (tests/harness.zen) — the self-hosted replacement for the pytest
# value/verdict harness. Build it with the freshly-built `zenc`, then run it from the repo ROOT (the
# harness drives `./zen` + `tests/harness_runner.c` and reads bootstrap/zenc.gen.c via relative paths).
# The harness exits 0 when all cases pass and 1 when any fail, so counts cannot wrap through POSIX's
# 8-bit process status.
#   make -f bootstrap/Makefile harness
harness: zen
	cd $(ROOT) && ZO=/tmp/zo_harness.$$$$ && ZC=/tmp/zo_hcache.$$$$ && export ZENC_CACHE_DIR=$$ZC && $(ZENC) build tests/harness.zen -o $$ZO && $$ZO; rc=$$?; rm -rf $$ZO $$ZC; exit $$rc

# Fast smoke subset of the harness: runs only the quick deterministic correctness
# suites (value + verdict) via ZEN_HARNESS_FAST and SKIPS the slow subprocess-heavy suites (modules /
# build / boundaries / misc / fuzz / fixpoint). For inner-loop iteration only — the full `make
# harness` above stays the merge gate. See tests/harness.zen for which suites the flag selects.
#   make -f bootstrap/Makefile harness-fast
harness-fast: zen
	cd $(ROOT) && ZO=/tmp/zo_harness_fast.$$$$ && ZC=/tmp/zo_hfcache.$$$$ && export ZENC_CACHE_DIR=$$ZC && $(ZENC) build tests/harness.zen -o $$ZO && ZEN_HARNESS_FAST=1 $$ZO; rc=$$?; rm -rf $$ZO $$ZC; exit $$rc

# Differential gate (module-system campaign): compare two zenc binaries over the whole fixture +
# example + dispatch corpus — check stdout/stderr/exit, emitted C bytes, run exit/stdout. Diffs not
# listed in scripts/difftest-allow.txt fail the target. Defaults compare the built compiler with
# itself (a self-consistency smoke); point OLD at a saved baseline for the real gate:
#   make -f bootstrap/Makefile difftest OLD=/tmp/zenc-b4-baseline
OLD ?= $(ZENC)
NEW ?= $(ZENC)
difftest: zen
	cd $(ROOT) && ./scripts/difftest.sh $(OLD) $(NEW)

docs-check:
	cd $(ROOT) && ./scripts/check-docs.sh

# FFI drift gate: prove std's hand-written foreign prototypes (src/std/c/libc.zen and friends)
# match the REAL system headers. Reuses `zenc emit` (foreign decls lower to bare C prototypes),
# then compares them against glibc's declarations — libm verbatim under gcc's conflicting-types
# rule, the rest slot-by-slot at ABI-class level (scripts/ffi_abi_check.h, g++ static_assert).
# Linux/glibc only; skips cleanly elsewhere. Fast (~2s).
ffi-verify: zen
	cd $(ROOT) && ./scripts/ffi_verify.sh $(ZENC)

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
