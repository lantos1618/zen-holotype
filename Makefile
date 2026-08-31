# Zen. See docs/PLAN.md for what each target gates.

# BASH, AND `-o pipefail`, FOR EVERY RECIPE. A pipeline's exit status is its
# LAST command's, so a failing gate on the left of a pipe can otherwise leave
# the build green.
# /bin/sh here is dash, which has no `pipefail` at all, so this cannot be a
# `set -o pipefail` line inside a recipe; it has to be the shell make invokes.
# The same trap is waiting in every terminal an agent works in -- docs/STYLE.md,
# "a pipeline reports the wrong exit status", has the incantation for that side.
SHELL       := /bin/bash
.SHELLFLAGS := -o pipefail -c

CC      ?= cc
CFLAGS  ?= -O2 -std=c99
PROFILE_CFLAGS ?= -O2 -std=c99 -g -fno-omit-frame-pointer
PY      ?= python3
ROOT    ?= src

# HOW MANY C COMPILERS AT ONCE. `cc -O2` is superlinear in a translation
# unit's size, and the backend's own output is the extreme case: the
# 110,451-line single unit took 70.4s where the SAME code, emitted one
# file per module and compiled with -j16, took 8.4s. That ratio is why
# `--emit-c-dir` exists. Lower it on a small box.
J       ?= $(shell nproc 2>/dev/null || echo 4)

# ccache WHEN IT IS INSTALLED, and nothing to install or configure when
# it is not. It only ever helps a `-c` compile: a command that compiles
# AND LINKS is uncacheable, which is why no recipe below spells both on
# one line -- that single fact is what made ccache report
# "Uncacheable calls: 4/4" for every build this project ever ran.
# `make CACHE=` turns it off.
CACHE   ?= $(shell command -v ccache 2>/dev/null)
ZCC      = $(CACHE) $(CC)

.PHONY: all build seed test lint parse cap dupcomments faults lextile determinism grammar fmt asan leak profile clean help

all: test

## build: what a newcomer runs. needs only a C compiler.
##
## TWO steps and not one, because the compiler emits C and does not link:
## `zen build <root> --emit-c-dir <dir>` is the whole interface (see
## src/zen/zen_cli.zen). This target used to say `-o zen-new` with no
## --emit-c, which the driver accepts, writes nothing for, and exits 0
## on -- so `build` produced no binary and every target standing on it
## (test, fmt, determinism) could not run at all.
##
## ONE FILE PER MODULE, NOT ONE PER PROGRAM. `--emit-c-dir` writes
## build/c/<module>.c beside a build/c/zen.h; `-j` then compiles 152
## units at once instead of one of 110,451 lines, and each unit is a
## `-c` compile a cache can skip. THE SEED IS STILL ONE FILE: `make
## seed` writes seed/zen.c with `--emit-c -o`, and the line below
## compiles it as one unit, because a newcomer must be able to build
## this compiler out of exactly one committed C file.
build: seed/zen.c
	@mkdir -p build/obj
	$(ZCC) $(CFLAGS) -c seed/zen.c -o build/obj/seed.o
	$(CC) build/obj/seed.o -o zen
	rm -rf build/c && mkdir -p build/c
	./zen build $(ROOT) --emit-c-dir build/c
	ls build/c/*.c | xargs -P $(J) -I{} $(ZCC) $(CFLAGS) -c {} -o {}.o
	$(CC) build/c/*.o -o zen-new && mv zen-new zen

## seed: regenerate AND stage, in one target. never two commands —
## commit-then-regenerate ships a seed one change stale, and only a
## full feature test catches it. Depends on `build`, not `zen`: there
## is no `zen` rule — `build` is what produces ./zen, and a name with
## no rule fails after `make clean` and goes stale while it exists.
seed: build
	./zen build $(ROOT) --emit-c -o seed/zen.c
	git add seed/zen.c

## test: the corpus, must-fail and example suites, against the built ./zen.
##
## It depends on `build` because there is no second implementation any more:
## the Python bootstrapper was deleted once `--toolchain zen` carried the whole
## corpus (528/528), and with it went `refmap`, whose only job was to keep
## docs/GENC_REFERENCE_MAP.md pointing into bootstrap/gen_c.py.
##
test: build lint parse cap dupcomments faults lextile
	$(PY) tests/run.py

## faults: every fault the compiler declares must have a site that raises
## it. Green here does NOT mean every diagnostic works — it means none is
## silently absent. Any that are absent are written down in the script's
## OWED ledger, so the debt can shrink and cannot quietly grow; the
## ledger is empty today, and a name in it that gains a raise site is an
## error too, so it cannot drift back into fiction.
##
## A Zen gate — tests/gates/faults_reachable.zen; see `gate` above. It reads
## the variant list off `std.parse`, where the python it replaced matched a
## regex demanding a leading `|`: that missed the FIRST variant of every enum,
## so `SemaFault.UndefinedName` and `GenFault.Unsupported` were exempt from
## this check for its whole life. Proved by mutation -- delete every
## construction of `UndefinedName` and the python stays green.
faults: build
	@mkdir -p build/gates
	@$(call gate,faults_reachable)
	@$(call nonempty,faults,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/faults_reachable "$${files[@]}"

## A GATE IS A ZEN PROGRAM. `$(call gate,name)` compiles
## tests/gates/<name>.zen with ./zen and leaves the binary in build/gates/.
## The compilation root is tests/gates, whose `std` is a SYMLINK to src/std:
## a module path is COMPUTED (`<folder>/<folder>.zen`), never searched for, so
## a program importing `std.lex` needs `std` under its own root and the
## symlink is what puts it there without copying the tree.
##
## Gates are Zen programs, compiled with the compiler they check.
gate = ./zen build tests/gates --entry $(1).zen --emit-c -o build/gates/$(1).c \
	&& $(ZCC) $(CFLAGS) -c build/gates/$(1).c -o build/gates/$(1).o \
	&& $(CC) build/gates/$(1).o -o build/gates/$(1)

# THE ONE DOOR FOR "a gate over a file set must have files". Six targets
# carried hand-copies of this assertion and the copies drifted (#799): a
# find that matches nothing hands a gate zero inputs and reads exit 0,
# which is this repo's recorded shape for a check that cannot fail --
# "checked everything, clean" and "checked nothing" may not be the same
# answer. Expands to a shell fragment that fills `files` from the find(1)
# spelled verbatim by the second argument (paths, predicates, an optional
# `| LC_ALL=C sort -z`) and exits 2 naming the gate if it matched nothing.
# Semicolon-join it to the consumer ON THE SAME LINE so `files` stays in
# one shell:
##
##     @$(call nonempty,cap,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
##       build/gates/line_cap "$${files[@]}"
define nonempty
mapfile -d '' files < <(find $(2)) && test $${#files[@]} -gt 0 || { echo "$(1): found no .zen files — this gate is checking nothing" >&2; exit 2; }
endef

## cap: a structural-review prompt. Long files print notes but do not fail:
## line count finds candidates, while STYLE.md names the architectural smells
## that decide whether a split is useful. No-input and read failures stay red,
## because a review that inspected nothing is not a successful review.
##
## THE FILE LIST COMES FROM `find` AND NOT FROM THE GATE. `std.env.Fs` has no
## listing, on purpose ("no open handle, seek, listing, or permission
## surface"), so a gate over a file SET cannot compute its own inputs. Same
## shape as `fmt` and `parse` below, and the same assertion for the same
## reason: an empty list must not read as a clean report. `LC_ALL=C` because the
## report is ordered by path and a locale-dependent order is a diff nobody
## asked for.
cap: build
	@mkdir -p build/gates
	@$(call gate,line_cap)
	@$(call nonempty,cap,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  build/gates/line_cap "$${files[@]}"

## dupcomments: no comment block may sit immediately above a copy of itself.
## A merge or a bad paste leaves that behind and it survives review, because
## a reader who has already read the paragraph does not notice reading it
## again — gen_c_inline.zen held twelve such pairs and gen_c_settle.zen six.
## ADJACENT only: the same explanation above two sibling helpers is somebody's
## judgement about where a reader needs it, and this gate does not overrule it.
## A Zen gate — tests/gates/dup_comments.zen; see `gate` above.
dupcomments: build
	@mkdir -p build/gates
	@$(call gate,dup_comments)
	@$(call nonempty,dupcomments,$(ROOT) -name '*.zen' -print0 | LC_ALL=C sort -z); \
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
## A Zen gate — tests/gates/lex_tiling.zen; see `gate` above.
lextile: build
	@mkdir -p build/gates
	@$(call gate,lex_tiling)
	@$(call nonempty,lextile,$(ROOT) example tests/corpus tests/gates -name '*.zen' -print0 | LC_ALL=C sort -z); \
	  files+=(build.zen); \
	  build/gates/lex_tiling "$${files[@]}"

## parse: every .zen the tree claims is valid must parse, and every
## tests/parse/errors fixture must fail to parse. cheap, and example/ is also
## compiled by `tests/run.py`. must-fail/ is excluded because the compiler's
## rejection -- not tree-sitter's -- is what those tests assert.
##
## THE FILE COUNT IS ASSERTED. A find that matches nothing leaves xargs
## with no work and exits 0, which is this repo's own recorded shape for
## a gate that cannot fail; one renamed directory would have retired
## this check in silence.
##
## `-l`/`--lang-name` ARE MANDATORY. The CLI otherwise resolves the
## language through ~/.cache/tree-sitter/lib/<name>.so, a cache keyed by
## language NAME and shared with every other checkout of this grammar on
## the box -- so a parse gate could execute whichever tree regenerated
## last rather than the one being gated (that divergence is exactly how
## the #770 ruling was briefly "disproven"). `-l` names THIS tree's
## zen.so and bypasses the cache; `--lang-name zen` tells the CLI which
## symbol to load from it.
parse: grammar
	@$(call nonempty,parse,$(ROOT) example tests/corpus -name '*.zen' -print0); \
	  files+=(build.zen); \
	  cd grammar && npx tree-sitter parse --quiet --stat -l "$$(pwd)/zen.so" --lang-name zen "$${files[@]/#/../}"
	@$(call nonempty,parse-errors,tests/parse/errors -name '*.zen' -print0); \
	  cd grammar; \
	  set +e; report="$$(npx tree-sitter parse --quiet --stat -l "$$(pwd)/zen.so" --lang-name zen "$${files[@]/#/../}" 2>&1)"; rc=$$?; set -e; \
	  printf '%s\n' "$$report"; \
	  test $$rc -eq 1; \
	  grep -Fq "Total parses: $${#files[@]}; successful parses: 0; failed parses: $${#files[@]};" <<<"$$report"

## lint: every test conforms to the format in docs/TESTING.md.
##
## Pure Python over the test tree, about one second.
lint:
	$(PY) tests/lint.py

## determinism: five checks that gen_c is a pure function of input
determinism: build
	ZEN=./zen tests/determinism/check.sh

## grammar: regenerate the parser and build the shared object cst.py loads.
## --abi 14 is not optional: the CLI defaults to 15, and py-tree-sitter
## rejects anything above 14 with "Incompatible Language version".
grammar: grammar/zen.so

grammar/zen.so: grammar/grammar.js grammar/tree-sitter.json
	cd grammar && npx tree-sitter generate --abi 14
	@mkdir -p build/obj
	$(ZCC) -fPIC -I grammar/src -c grammar/src/parser.c -o build/obj/grammar-parser.o
	$(CC) -shared -o grammar/zen.so build/obj/grammar-parser.o

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
## `tests/gates` IS IN THE LIST because the gates are Zen programs now and
## a gate nothing formats drifts like any other file -- all three landed
## unformatted the day they were written. `find` does not follow symlinks,
## so `tests/gates/std` (the symlink `gate` compiles against) contributes
## nothing here and src/std is not counted twice.
##
## THE FILE COUNT IS ASSERTED, for the reason `parse` gives above, and
## more sharply here: this recipe used to end `xargs --no-run-if-empty`,
## which is an instruction to do nothing and succeed when the find comes
## up empty.
fmt: build
	@$(call nonempty,fmt,$(ROOT) example tests/corpus tests/gates -name '*.zen' \
	  -not -path 'tests/corpus/lex/*' -print0); \
	  files+=(build.zen); \
	  ./zen fmt --check "$${files[@]}"

## asan: the compiler under AddressSanitizer + LeakSanitizer, built as
## zen-asan (./zen is never clobbered), running one representative compile.
## The deliberate argv-rows allocation is suppressed BY NAME in
## tests/bench/lsan.supp -- widen that file and real leaks go quiet.
asan: seed/zen.c
	@mkdir -p build/obj
	$(ZCC) -std=c99 -O1 -g -fsanitize=address,leak -c seed/zen.c -o build/obj/seed-asan.o
	$(CC) -fsanitize=address,leak build/obj/seed-asan.o -o zen-asan
	tests/bench/asan.sh ./zen-asan

## leak: valgrind's answer to the same question. definite leaks only --
## still-reachable memory is where the deliberate argv rows land, and
## reporting them would fail every run on a known-non-bug.
leak: build
	tests/bench/leak.sh ./zen

## profile: -O2 keeps samples representative; -g and frame pointers make them
## readable and walkable. Separate objects leave ordinary ./zen untouched.
profile: build
	ls build/c/*.c | xargs -P $(J) -I{} $(ZCC) $(PROFILE_CFLAGS) -c {} -o {}.profile.o
	$(CC) build/c/*.c.profile.o -o zen-fp

clean:
	rm -f zen zen-new zen-asan zen-fp grammar/zen.so
	rm -rf build/ tests/bench/out/

help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## //'
