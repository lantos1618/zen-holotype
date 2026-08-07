# Zen. See docs/PLAN.md for what each target gates.

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PY      ?= python3
ROOT    ?= src

.PHONY: all build seed test test-zen lint parse design cap faults fixpoint determinism grammar grammar-test fmt clean help

all: test

## build: what a newcomer runs. needs only a C compiler.
##
## TWO steps and not one, because the compiler emits C and does not link:
## `zen build <root> --emit-c -o <file.c>` is the whole interface (see
## src/zen/zen_cli.zen). This target used to say `-o zen-new` with no
## --emit-c, which the driver accepts, writes nothing for, and exits 0
## on -- so `build` produced no binary and every target standing on it
## (test-zen, fmt, determinism) could not run at all.
build: seed/zen.c
	$(CC) $(CFLAGS) seed/zen.c -o zen
	./zen build $(ROOT) --emit-c -o zen-new.c
	$(CC) $(CFLAGS) zen-new.c -o zen-new && mv zen-new zen && rm -f zen-new.c

## seed: regenerate AND stage, in one target. never two commands —
## commit-then-regenerate ships a seed one change stale, and only a
## full feature test catches it.
seed: zen
	./zen build $(ROOT) --emit-c -o seed/zen.c
	git add seed/zen.c

## test: the corpus and must-fail suites, against the bootstrapper
test: parse design cap faults
	$(PY) tests/run.py

## faults: every fault the compiler declares must have a site that raises
## it. Green here does NOT mean every diagnostic works — it means none is
## silently absent. The seven that are absent are written down in the
## script's OWED ledger, so the debt can shrink and cannot quietly grow.
faults:
	$(PY) scripts/faults_reachable.py

## cap: STYLE.md's line caps. Over 500 prints a note; over 800 fails,
## unless the path carries a written reason in scripts/line_cap.py.
cap:
	$(PY) scripts/line_cap.py

## design: every complete example in DESIGN.md must parse. PLAN.md 0.1 asks
## for this; nothing was checking it, and the document had drifted from the
## language it defines. A ```groovy fragment fence is read, not parsed.
design: grammar
	$(PY) scripts/design_examples.py

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
