# Zen. See docs/PLAN.md for what each target gates.

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PY      ?= python3
ROOT    ?= src

.PHONY: all build seed test lint fixpoint determinism grammar fmt clean help

all: test

## build: what a newcomer runs. needs only a C compiler.
build: seed/zen.c
	$(CC) $(CFLAGS) seed/zen.c -o zen
	./zen build $(ROOT) -o zen-new && mv zen-new zen

## seed: regenerate AND stage, in one target. never two commands —
## commit-then-regenerate ships a seed one change stale, and only a
## full feature test catches it.
seed: zen
	./zen build $(ROOT) --emit-c -o seed/zen.c
	git add seed/zen.c

## test: the corpus and must-fail suites, against the bootstrapper
test:
	$(PY) tests/run.py

## test-zen: the same suites, against a built zen binary
test-zen: build
	$(PY) tests/run.py --toolchain zen

## lint: every test conforms to the format in docs/TESTING.md
lint:
	$(PY) tests/lint.py

## fixpoint: the strongest oracle. zen-1 and zen-2 must emit
## byte-identical C. worthless unless gen_c is deterministic.
fixpoint: build
	./scripts/fixpoint.sh

## determinism: five checks that gen_c is a pure function of input
determinism: build
	ZEN=./zen tests/determinism/check.sh

## grammar: regenerate the tree-sitter parser and run its corpus
grammar:
	cd grammar && npx tree-sitter generate && npx tree-sitter test

## fmt: the whole tree must already be formatted
fmt: build
	./zen fmt --check $(ROOT) example tests

clean:
	rm -f zen zen-new
	rm -rf build/

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
