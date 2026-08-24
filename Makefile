# Zen. See docs/PLAN.md for what each target gates.

# BASH, AND `-o pipefail`, FOR EVERY RECIPE. A pipeline's exit status is its
# LAST command's, so `find ... | xargs ./zen fmt --check` reports the status of
# xargs and `$(PY) scripts/x.py | tail` reports the status of tail -- a failing
# gate on the left of a pipe exits 0 and the build goes green on a red check.
# /bin/sh here is dash, which has no `pipefail` at all, so this cannot be a
# `set -o pipefail` line inside a recipe; it has to be the shell make invokes.
# The same trap is waiting in every terminal an agent works in -- docs/STYLE.md,
# "a pipeline reports the wrong exit status", has the incantation for that side.
SHELL       := /bin/bash
.SHELLFLAGS := -o pipefail -c

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PY      ?= python3
ROOT    ?= src

# `editors` IS IN THIS LIST BECAUSE `editors/` IS ALSO A DIRECTORY. Without
# it make finds the directory, calls the target up to date, and runs the
# script never — a gate that cannot fail because it cannot run.
.PHONY: all build seed test lint parse design cap dupcomments faults lextile ufcs style editors fixpoint determinism grammar grammar-test fmt bench bench-allocs emit-runs asan leak profile clean help

all: test

## build: what a newcomer runs. needs only a C compiler.
##
## TWO steps and not one, because the compiler emits C and does not link:
## `zen build <root> --emit-c -o <file.c>` is the whole interface (see
## src/zen/zen_cli.zen). This target used to say `-o zen-new` with no
## --emit-c, which the driver accepts, writes nothing for, and exits 0
## on -- so `build` produced no binary and every target standing on it
## (test, fmt, determinism) could not run at all.
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

## test: the corpus and must-fail suites, against the built ./zen.
##
## It depends on `build` because there is no second implementation any more:
## the Python bootstrapper was deleted once `--toolchain zen` carried the whole
## corpus (528/528), and with it went `refmap`, whose only job was to keep
## docs/GENC_REFERENCE_MAP.md pointing into bootstrap/gen_c.py.
##
## `grammar-test` and `dupcomments` joined this list on 2026-08-10. Both
## existed as targets nobody ran, which is the same disease `grammar-test`
## was written to cure: a check outside `make test` is a check that goes
## stale unobserved. If either one makes this target too slow to run, split
## it out deliberately and say where it runs instead — do not just drop it.
## `bench-allocs` joined it on 2026-08-16, for the third time the same
## disease has been diagnosed here: tests/bench was run by no target in
## `all`, so `allocs_op: 0` -- cited in src/ as a thing that fails the
## build -- was a number nothing had ever computed.
test: build parse design cap dupcomments faults lextile ufcs style grammar-test editors bench-allocs
	$(PY) tests/run.py

## faults: every fault the compiler declares must have a site that raises
## it. Green here does NOT mean every diagnostic works — it means none is
## silently absent. Any that are absent are written down in the script's
## OWED ledger, so the debt can shrink and cannot quietly grow; the
## ledger is empty today, and a name in it that gains a raise site is an
## error too, so it cannot drift back into fiction.
##
## A Zen gate — tools/gates/faults_reachable.zen; see `gate` above. It reads
## the variant list off `std.parse`, where the python it replaced matched a
## regex demanding a leading `|`: that missed the FIRST variant of every enum,
## so `SemaFault.UndefinedName` and `GenFault.Unsupported` were exempt from
## this check for its whole life. Proved by mutation -- delete every
## construction of `UndefinedName` and the python stays green.
faults: build
	@mkdir -p build/gates
	@$(call gate,faults_reachable)
	@mapfile -d '' files < <(find $(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  test $${#files[@]} -gt 0 \
	    || { echo "faults: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  build/gates/faults_reachable "$${files[@]}"

## ufcs: no `x.f(..)` may have two answers. a method on T and a free
## function taking T as its first parameter are the same call under UFCS,
## and Zen has no overloading — so the two compilers pick differently and
## the corpus, built by only one of them, sees nothing. that is how a
## stray `}` after every block got past 227 green tests.
ufcs: grammar
	$(PY) scripts/ufcs_collisions.py

## A GATE IS A ZEN PROGRAM. `$(call gate,name)` compiles
## tools/gates/<name>.zen with ./zen and leaves the binary in build/gates/.
## The compilation root is tools/gates, whose `std` is a SYMLINK to src/std:
## a module path is COMPUTED (`<folder>/<folder>.zen`), never searched for, so
## a program importing `std.lex` needs `std` under its own root and the
## symlink is what puts it there without copying the tree.
##
## THE COMPILER NOW GATES ITSELF, and the trade is deliberate. A gate written
## in Zen cannot run until ./zen builds, so a broken compiler takes its own
## style checks down with it -- where `scripts/*.py` would still have run.
## What it buys is ONE implementation of "what is a Zen file" instead of two,
## which is the same trade PLAN.md records for deleting the bootstrapper: a
## second implementation that still builds is one that drifts. ~0.3s a gate,
## so they are rebuilt every run rather than carrying a staleness rule.
gate = ./zen build tools/gates --entry $(1).zen --emit-c -o build/gates/$(1).c \
	&& $(CC) $(CFLAGS) build/gates/$(1).c -o build/gates/$(1)

## cap: STYLE.md's line caps. Over 500 prints a note; over 800 fails,
## unless the path carries a written reason in tools/gates/line_cap.zen.
##
## THE FILE LIST COMES FROM `find` AND NOT FROM THE GATE. `std.env.Fs` has no
## listing, on purpose ("no open handle, seek, listing, or permission
## surface"), so a gate over a file SET cannot compute its own inputs. Same
## shape as `fmt` and `parse` below, and the same assertion for the same
## reason: an empty list must not read as "0 over 800". `LC_ALL=C` because the
## report is ordered by path and a locale-dependent order is a diff nobody
## asked for.
cap: build
	@mkdir -p build/gates
	@$(call gate,line_cap)
	@mapfile -d '' files < <(find $(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  test $${#files[@]} -gt 0 \
	    || { echo "cap: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  build/gates/line_cap "$${files[@]}"

## dupcomments: no comment block may sit immediately above a copy of itself.
## A merge or a bad paste leaves that behind and it survives review, because
## a reader who has already read the paragraph does not notice reading it
## again — gen_c_inline.zen held twelve such pairs and gen_c_settle.zen six.
## ADJACENT only: the same explanation above two sibling helpers is somebody's
## judgement about where a reader needs it, and this gate does not overrule it.
## A Zen gate — tools/gates/dup_comments.zen; see `gate` above.
dupcomments: build
	@mkdir -p build/gates
	@$(call gate,dup_comments)
	@mapfile -d '' files < <(find $(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  test $${#files[@]} -gt 0 \
	    || { echo "dupcomments: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  build/gates/dup_comments "$${files[@]}"

## lextile: the tokens tile the file, and every line:col in them is right.
##
## THE ONE PROPERTY NOTHING ELSE CHECKS. `make fmt` proves the formatter
## reprints a file, but the formatter reads the TEXT a span slices — so a span
## whose line:col is wrong reprints perfectly and points the editor's squiggle
## at the wrong character. Positions were unmeasured in this tree until this
## gate: 664 files, both ends of every token, against a second walk over the
## bytes that shares no line with lex_cursor.zen.
##
## It also proves the token stream RECONSTRUCTS the file: tokens in order,
## never overlapping, nothing but whitespace between two of them, and the last
## one ending at the last byte. A dropped byte has nowhere to hide.
##
## must-fail/ and tests/parse/errors are excluded for the reason `parse`
## excludes them: those files exist NOT to lex, and their faults are the
## must-fail suite's assertion, not this one's.
##
## Proved non-vacuous by mutation — stop `bump` counting the newline and the
## position check goes red on the first file with two lines in it.
## A Zen gate — tools/gates/lex_tiling.zen; see `gate` above.
lextile: build
	@mkdir -p build/gates
	@$(call gate,lex_tiling)
	@mapfile -d '' files < <(find $(ROOT) example tests/corpus tests/bench tools/gates -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  test $${#files[@]} -gt 0 \
	    || { echo "lextile: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  build/gates/lex_tiling "$${files[@]}"

## editors: the VS Code extension's contributions still resolve. EVERY
## FAILURE HERE IS A SILENT ONE -- VS Code does not report a `grammars`
## entry whose path is missing or whose `scopeName` disagrees with the
## grammar file's own, it simply contributes nothing, and .zen falls back
## to no tokenization at all. That fallback is what put the `(` inside
## `add_bytes("(zg_fs_kind(")` into bracket matching, while colour kept
## working because that comes from the server. Nothing else gates
## editors/, and a check nobody runs is a check that
## goes stale.
editors:
	$(PY) scripts/editors_check.py

## style: the rest of STYLE.md — where a file lives, what it is named,
## which way its imports point, whether an impl sits with its type. The
## document said "most of these are one rule with a test attached" and
## `cap` was the only rule that had one. Parses with tools/parse/cst.py
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
## is the only thing standing behind example/ and tests/bench -- nothing
## else compiles either one. example/ is written against stage 5;
## tests/bench holds the bench bodies, which no target builds (bench.py
## builds the DRIVERS that mirror them) and bench_budgets.zen, which is
## read by a regex. must-fail/ and tests/parse/errors are excluded on
## purpose: those files exist to NOT parse, and grammar-test owns them.
##
## THE FILE COUNT IS ASSERTED. A find that matches nothing leaves xargs
## with no work and exits 0, which is this repo's own recorded shape for
## a gate that cannot fail; one renamed directory would have retired
## this check in silence.
parse: grammar
	@mapfile -d '' files < <(find $(ROOT) example tests/corpus tests/bench -name '*.zen' -print0); \
	  test $${#files[@]} -gt 0 \
	    || { echo "parse: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  cd grammar && npx tree-sitter parse --quiet --stat "$${files[@]/#/../}"

## lint: every test conforms to the format in docs/TESTING.md
lint:
	$(PY) tests/lint.py

## fixpoint: the strongest oracle. zen-1 and zen-2 must emit
## byte-identical C. worthless unless gen_c is deterministic. Stands on
## seed/zen.c alone now that the Python stage 0 is gone, so it needs
## neither the grammar nor ./zen.
fixpoint:
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
##
## `tools/gates` IS IN THE LIST because the gates are Zen programs now and
## a gate nothing formats drifts like any other file -- all three landed
## unformatted the day they were written. `find` does not follow symlinks,
## so `tools/gates/std` (the symlink `gate` compiles against) contributes
## nothing here and src/std is not counted twice.
##
## THE FILE COUNT IS ASSERTED, for the reason `parse` gives above, and
## more sharply here: this recipe used to end `xargs --no-run-if-empty`,
## which is an instruction to do nothing and succeed when the find comes
## up empty.
fmt: build
	@mapfile -d '' files < <(find $(ROOT) example tests/corpus tools/gates -name '*.zen' \
	    -not -path 'tests/corpus/lex/*' -print0); \
	  test $${#files[@]} -gt 0 \
	    || { echo "fmt: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  ./zen fmt --check "$${files[@]}"

## emit-runs: consecutive writes into one buffer that a single `fmt` would
## collapse. A LEDGER, not a rule: scripts/emit_runs_owed.txt records the
## backlog per file and this fails if any file EXCEEDS its number, so a
## conversion lane ratchets it down and nothing puts it back. Undercounts a
## statement wrapped over several lines -- scripts/emit-runs.awk says why.
emit-runs:
	@n=$$(find src -name '*.zen' | wc -l); \
	  test "$$n" -gt 0 \
	    || { echo "emit-runs: found no .zen files — this gate is checking nothing" >&2; exit 2; }; \
	  find src -name '*.zen' | sort \
	  | xargs awk -f scripts/emit-runs.awk -v mode=ledger \
	  | sed 's/^    "//; s/": /|/; s/,$$//' | sort > $@.now; \
	  awk -F'|' 'NR==FNR { owed[$$1]=$$2; next } \
	    { if ($$2 > owed[$$1]) { \
	        printf "%s: %d collapsible writes, ledger says %d\n", $$1, $$2, owed[$$1]; \
	        bad=1 } } \
	    END { if (bad) exit 1 }' scripts/emit_runs_owed.txt $@.now \
	  || { rm -f $@.now; echo "emit-runs: a file grew -- collapse the run or update scripts/emit_runs_owed.txt" >&2; exit 1; }; \
	  printf "emit-runs: %d file(s), %d call(s) owed\n" \
	    "$$(wc -l < $@.now)" "$$(awk -F'|' '{s+=$$2} END {print s+0}' $@.now)"; \
	  rm -f $@.now

## bench-allocs: the half of tests/bench that is not a stopwatch, and so
## the half that belongs in `test`. Each driver is linked through
## `ld --wrap=malloc` and compiled at N and 2N iterations; the slope is
## allocations and bytes per op, the same integers on every machine, and
## over the budgets in bench_budgets.zen FAILS. ~2 seconds. The budgets
## are ceilings measured at libc, not at the Zen allocator -- bench.py's
## header says exactly what that does and does not prove.
bench-allocs: build
	$(PY) scripts/bench.py --allocs-only

## bench: the same drivers with the wall clock as well, against the ns_op
## budgets and the rolling median in tests/bench/baseline.json. Drivers
## under tests/bench/drivers/ mirror the bench bodies (constructing a
## Bencher needs trait dispatch gen_c does not have yet) and are timed
## whole-process minus the null driver's floor. THE CLOCK IS WHAT KEEPS
## THIS OUT OF `test`, not the drivers: wall clocks are slow and noisy,
## and a gate that reddens on a loaded machine teaches people to read
## past red. Over budget warns; only an absurd miss fails.
bench: build
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
