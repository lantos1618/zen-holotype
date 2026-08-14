# Zen. See docs/PLAN.md for what each target gates.

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PY      ?= python3
ROOT    ?= src

.PHONY: all build seed test test-zen lint parse design cap dupcomments faults refmap ufcs style fixpoint determinism grammar grammar-test fmt bench asan leak profile clean help

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
## full feature test catches it. Depends on `build`, not `zen`: there
## is no `zen` rule — `build` is what produces ./zen, and a name with
## no rule fails after `make clean` and goes stale while it exists.
seed: build
	./zen build $(ROOT) --emit-c -o seed/zen.c
	git add seed/zen.c

## test: the corpus and must-fail suites, against the bootstrapper.
##
## `grammar-test` and `dupcomments` joined this list on 2026-08-10. Both
## existed as targets nobody ran, which is the same disease `grammar-test`
## was written to cure: a check outside `make test` is a check that goes
## stale unobserved. If either one makes this target too slow to run, split
## it out deliberately and say where it runs instead — do not just drop it.
test: parse design cap dupcomments faults refmap ufcs style grammar-test
	$(PY) tests/run.py

## faults: every fault the compiler declares must have a site that raises
## it. Green here does NOT mean every diagnostic works — it means none is
## silently absent. The seven that are absent are written down in the
## script's OWED ledger, so the debt can shrink and cannot quietly grow.
faults:
	$(PY) scripts/faults_reachable.py

## refmap: docs/GENC_REFERENCE_MAP.md points at gen_c.py by line number,
## hundreds of times. gen_c.py grew 845 lines under it and every claim
## below the first insertion moved -- a map with shifted coordinates
## sends a reader confidently to the wrong function. Green means the
## coordinates resolve; it does NOT mean the prose is true.
refmap:
	$(PY) scripts/refmap.py

## ufcs: no `x.f(..)` may have two answers. a method on T and a free
## function taking T as its first parameter are the same call under UFCS,
## and Zen has no overloading — so the two compilers pick differently and
## the corpus, built by only one of them, sees nothing. that is how a
## stray `}` after every block got past 227 green tests.
ufcs: grammar
	$(PY) scripts/ufcs_collisions.py

## cap: STYLE.md's line caps. Over 500 prints a note; over 800 fails,
## unless the path carries a written reason in scripts/line_cap.py.
cap:
	$(PY) scripts/line_cap.py

## dupcomments: no comment block may sit immediately above a copy of itself.
## A merge or a bad paste leaves that behind and it survives review, because
## a reader who has already read the paragraph does not notice reading it
## again — gen_c_inline.zen held twelve such pairs and gen_c_settle.zen six.
## ADJACENT only: the same explanation above two sibling helpers is somebody's
## judgement about where a reader needs it, and this gate does not overrule it.
dupcomments:
	$(PY) scripts/dup_comments.py

## style: the rest of STYLE.md — where a file lives, what it is named,
## which way its imports point, whether an impl sits with its type. The
## document said "most of these are one rule with a test attached" and
## `cap` was the only rule that had one. Parses with bootstrap/cst.py
## rather than grepping: every `if` and every `as` in src/ is inside a
## comment, so a regex finds only prose. The syntax laws — no if, no
## while, no ternary, no `as`, no fourth `@` entry — are the GRAMMAR's,
## and `make parse` is where they fail; this does not duplicate them.
style: grammar
	$(PY) scripts/style.py

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

## grammar-test: the grammar's contract, both halves. This used to be
## `npx tree-sitter test`, which reported "Total parses: 0" and exited 0 --
## grammar/ has no corpus directory, so the target passed on an empty set.
## The real check is scripts/grammar_test.py: every tests/parse/errors/*.zen
## must FAIL to parse, and every .zen under tests/corpus and example must
## keep parsing. A green run prints both counts; a count dropping is how you
## notice the fixtures moved.
grammar-test: grammar
	$(PY) scripts/grammar_test.py

## fmt: the whole tree must already be formatted.
##
## `find`, and not a directory argument, because `zen fmt` takes FILES.
## std.env.Fs has no listing on purpose, and unlike a build a format
## cannot compute its own file set from an entry's imports: a file
## nobody imports still has to be formatted. Same shape as `parse`
## above, for the same reason. This said `--check src example tests`,
## which named three directories at a command that has never been able
## to open one.
##
## THREE EXCLUSIONS, and each is a suite whose BYTES are the test.
## must-fail/ and tests/parse/ exist to not parse, and a formatter
## refuses a file it cannot parse. tests/corpus/lex/ carries a BOM, a
## CRLF, a missing final newline and trailing whitespace on purpose --
## formatting those files would delete the seven tests in them.
fmt: build
	@find $(ROOT) example tests/corpus -name '*.zen' \
	    -not -path 'tests/corpus/lex/*' -print0 \
	  | xargs -0 --no-run-if-empty ./zen fmt --check

## bench: the tests/bench gate. Drivers under tests/bench/drivers/ mirror
## the bench bodies (constructing a Bencher needs trait dispatch gen_c does
## not have yet), run under an external wall clock minus the null driver's
## floor, and are reported against the budgets in bench_budgets.zen and the
## rolling median in tests/bench/baseline.json. NOT in `test`: wall clocks
## are slow and noisy, and a gate that reddens on a loaded machine teaches
## people to read past red. Over budget warns; only an absurd miss fails.
bench:
	$(PY) scripts/bench.py

## asan: the compiler under AddressSanitizer + LeakSanitizer, built as
## zen-asan (./zen is never clobbered), running one representative compile.
## The deliberate argv-rows allocation is suppressed BY NAME in
## tests/bench/lsan.supp -- widen that file and real leaks go quiet.
asan: seed/zen.c
	$(CC) -std=c99 -O1 -g -fsanitize=address,leak seed/zen.c -o zen-asan
	tests/bench/asan.sh ./zen-asan

## leak: valgrind's answer to the same question. definite leaks only --
## still-reachable memory is where the deliberate argv rows land, and
## reporting them would fail every run on a known-non-bug.
leak: build
	tests/bench/leak.sh ./zen

## profile: a frame-pointer build (zen-fp) self-compiles under perf record
## -g; report and stacks land in tests/bench/out/. flamegraph.svg only when
## the FlameGraph scripts are already on PATH -- they are never vendored.
profile: seed/zen.c
	CC=$(CC) bash scripts/profile.sh

clean:
	rm -f zen zen-new zen-asan zen-fp grammar/zen.so
	rm -rf build/ tests/bench/out/

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
