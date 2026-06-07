# Python-free build + regen for the self-hosted Zen compiler.
#
# The compiler IS the `zenc` binary: cc compiles bootstrap/{zenc.gen.c,zenrt.c,main.c}
# (zenc.gen.c is the committed C the Zen frontend emits for std/*.zen). NO Python is in
# this loop — this Makefile is the replacement for bootstrap/generate.py.
#
#   make -f bootstrap/Makefile zenc     # build the standalone compiler binary
#   make -f bootstrap/Makefile regen    # rebuild zenc, then regenerate zenc.gen.c with it
#
# `regen` reproduces the committed bootstrap/zenc.gen.c byte-for-byte (the fixpoint), via the
# binary's --build-self mode — exactly what generate.py used to do, but with zero Python.
# Verify:  make -f bootstrap/Makefile regen && git diff --quiet bootstrap/zenc.gen.c

# This Makefile's own directory (bootstrap/) and the project root (its parent), resolved so the
# targets work regardless of the cwd `make -f` is invoked from.
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(HERE)..)

CC      ?= cc
CFLAGS  ?= -std=gnu11 -w
ZENC    := $(ROOT)/zenc
GEN_C   := $(HERE)zenc.gen.c
SOURCES := $(HERE)zenc.gen.c $(HERE)zenrt.c $(HERE)main.c

.PHONY: zenc regen clean

# The standalone, Python-free compiler binary.
zenc:
	$(CC) $(CFLAGS) $(SOURCES) -o $(ZENC)

# Regenerate bootstrap/zenc.gen.c with the binary (no Python): the `--build-self` mode reads the
# compiler SOURCES under <srcroot> (the project root), strips imports, concatenates, and emits the
# same C the committed file holds. This is the replacement for `python3 bootstrap/generate.py`.
regen: zenc
	$(ZENC) --build-self $(GEN_C) $(ROOT)

clean:
	rm -f $(ZENC)
