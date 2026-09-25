# Zen architecture map

This is the repository-level map. For language rules, read `DESIGN.md`; for the
phase-by-phase implementation map, read `PLAN.md`.

## Top-level ownership

```text
grammar/     Tree-sitter grammar and generated parser metadata
seed/        Checked-in generated C bootstrap compiler
src/         Authored compiler and standard-library Zen sources
tests/       Corpus, must-fail, differential, quality, and benchmark checks
example/     Small projects demonstrating the language and tooling
editors/     Editor grammar and language-server integration
scripts/     Build, inventory, and review helper scripts
docs/        Binding design and maintained project documentation
build/       Disposable local build products and generated reports
```

The authored compiler and standard library are the source of truth. `seed/zen.c`
is generated from them for bootstrap and determinism checks; see
`GENERATED_FILES.md` before changing it.

## Compiler pipeline

```text
Zen source
    ↓
lexer       src/std/lex/
    ↓
parser      src/std/parse/
    ↓
AST         src/std/ast/
    ↓
semantic    src/sema/
    ↓
lowering    src/gen/gen_lower.zen, src/gen/gen_ir.zen
    ↓
backend     src/gen/gen_c/, src/gen/gen_js.zen, src/gen/gen_asm*
    ↓
generated program or system code
```

The `src/zen/` directory coordinates compiler modules and command execution.
`src/fmt/` owns source formatting, while `src/lsp/` exposes the language-server
protocol layer.

## Compiler module groups

- `src/std/lex/` tokenization and source scanning.
- `src/std/parse/` parser construction and syntax trees.
- `src/std/ast/` AST storage, traversal, spans, and named nodes.
- `src/sema/` name resolution, types, ownership, calls, effects, and diagnostics.
- `src/gen/` backend-neutral lowering plus C, JavaScript, and assembly emitters.
- `src/fmt/` formatting and source-preserving edit operations.
- `src/lsp/` protocol, document state, symbols, completion, hover, and serving.
- `src/zen/` top-level compiler and project orchestration.

Backend-independent generation belongs in `src/gen/`. Target-specific emission
belongs under `src/gen/gen_c/` or beside the corresponding backend entry point.
The C backend is currently the primary bootstrap path, so its files should not be
treated as general-purpose standard-library code.

## Standard library and capability boundaries

`src/std/` contains both reusable language facilities and runtime capabilities.
The main dependency direction is:

```text
core/text/mem
      ↓
collections and parsing
      ↓
AST, CLI, build, and higher-level facilities
      ↓
runtime capabilities such as actor, net, and process
```

`Env` is the root authority boundary. Facilities that access I/O, networking,
processes, threads, clocks, or page allocation receive their authority through
the environment or an explicit capability rather than ambient global state.
`Actor` and networking modules are therefore runtime/capability areas, while
`core`, `mem`, `collections`, and `text` are foundational areas.

This is an architectural guide, not a license for circular dependencies. When
refactoring, record the actual dependency direction before moving files.

## Tooling and projects

- `src/std/cli/` parses CLI arguments and coordinates commands.
- `src/std/build/` models projects, targets, dependencies, and build execution.
- `src/lsp/` implements editor-facing language intelligence.
- `src/fmt/` implements formatting and editor edits.
- `build.zen` describes the compiler's own project build.
- `example/` contains runnable projects that exercise backend and project APIs.

The CLI and build layers should remain thin coordinators. Parsing, project
loading, backend selection, and execution should each have an explicit owner so
that CLI behavior can be tested without embedding compiler implementation in
command parsing.

## Tests

The physical test layout follows the implementation phase:

```text
tests/corpus/       runnable programs grouped by feature or subsystem
tests/must-fail/    programs with required rejection diagnostics
tests/parse/        parser-specific support tests
tests/differential/ randomized or generated comparison checks
tests/quality/      harness, backend, editor, and project checks
tests/bench/        benchmark drivers and output
tests/gates/        source or compiler quality gates
```

The test runner already supports path/glob selection:

```sh
python3 tests/run.py --filter 'corpus/std/*'
make check FILTER='corpus/sema/*'
```

Prefer adding or reusing a focused test directory and filter before reorganizing
the large corpus. A behavior-oriented tag system can be added later if path
selection proves insufficient.

## Build and bootstrap flow

```text
Zen source in src/
    ↓ bootstrap compiler
generated C
    ↓ native compiler
./zen
    ↓ compiler build / tests
seed/zen.c and verification artifacts
```

`make build` is the normal incremental build. `make bootstrap` performs a fresh
bootstrap using a C compiler. `make seed` regenerates the checked-in bootstrap
file. `make check` is the cached development gate; `make verify` is the full
aggregate gate and includes fresh tests and compiler fixpoint checks.

The build workspace is disposable. Cleanup targets are documented in
`GENERATED_FILES.md`; do not treat `build/` as source.
