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

CC      ?= cc
CFLAGS  ?= -std=gnu11 -fwrapv -w
ZENC    := $(ROOT)/zenc
GEN_C   := $(HERE)zenc.gen.c
SOURCES := $(HERE)zenc.gen.c $(HERE)zenrt.c

.PHONY: zenc regen clean oracle

# The standalone, Python-free compiler binary: driver.zen is the entry (emitted as zen_main); zenrt.c
zenc:
	$(CC) $(CFLAGS) $(SOURCES) -o $(ZENC)

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
	cd $(ROOT) && $(ZENC) build tests/oracle.zen -o /tmp/zo_oracle && /tmp/zo_oracle
