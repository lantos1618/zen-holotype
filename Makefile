# Zen. See docs/PLAN.md for what each target gates.

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PY      ?= python3
ROOT    ?= src

.PHONY: all build seed test test-zen lint parse fixpoint determinism grammar grammar-test fmt clean help

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
test: parse
	$(PY) tests/run.py

## parse: every .zen the tree claims is valid must parse. cheap, and it
## is the only thing standing behind example/ -- nothing else compiles
## it, because it is written against stage 5. must-fail/ is excluded on
## purpose: those files exist to NOT parse.
parse: grammar
	@find src example tests/corpus -name '*.zen' -print0 \
	  | xargs -0 -- sh -c 'cd grammar && npx tree-sitter parse --quiet --stat \
	      $$(for f in "$$@"; do echo "../$$f"; done)' --

## test-zen: the same suites, against a built zen binary
test-zen: build
	$(PY) tests/run.py --toolchain zen

## lint: every test conforms to the format in docs/TESTING.md
lint:
	$(PY) tests/lint.py

## fixpoint: the strongest oracle. zen-1 and zen-2 must emit
## byte-identical C. worthless unless gen_c is deterministic.
fixpoint: grammar build
	./scripts/fixpoint.sh

## determinism: five checks that gen_c is a pure function of input
determinism: build
	ZEN=./zen tests/determinism/check.sh

## grammar: regenerate the parser and build the shared object cst.py loads.
## --abi 14 is not optional: the CLI defaults to 15, and py-tree-sitter
## rejects anything above 14 with "Incompatible Language version".
grammar: grammar/zen.so

grammar/zen.so: grammar/grammar.js grammar/tree-sitter.json
	cd grammar && npx tree-sitter generate --abi 14
	$(CC) -shared -fPIC -o grammar/zen.so grammar/src/parser.c -I grammar/src

## grammar-test: the tree-sitter corpus
grammar-test: grammar
	cd grammar && npx tree-sitter test

## fmt: the whole tree must already be formatted
fmt: build
	./zen fmt --check $(ROOT) example tests

clean:
	rm -f zen zen-new grammar/zen.so
	rm -rf build/

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
