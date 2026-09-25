# Generated files and build workspace

Zen keeps generated compiler bootstrap code in Git, while ordinary build products
and review measurements stay local. Do not edit generated files by hand unless
the generated-file policy below explicitly says to do so.

## Generated and derived files

| Path | Source of truth | Regenerate with | Commit policy |
| --- | --- | --- | --- |
| `seed/zen.c` | `src/` | `make seed` | Required bootstrap artifact; commit with its source batch |
| `grammar/src/parser.c` | `grammar/grammar.js` | `make grammar` | Generated parser; follow the repository's parser policy when changing the grammar |
| `grammar/src/node-types.json` | `grammar/grammar.js` | Tree-sitter generation | Generated metadata; commit when the grammar changes |
| `grammar/zen.so` | `grammar/src/parser.c` | `make grammar` | Never commit |
| `editors/vscode/out/*` | `editors/vscode/src/extension.ts` | the editor's TypeScript build | Never commit |
| `editors/vscode/node_modules/` | `editors/vscode/package-lock.json` | `npm ci` or `make editorcheck` | Never commit |
| `grammar/node_modules/` | `grammar/package-lock.json` | `npm ci` or `make grammar` | Never commit |
| `build/**` | The current source tree | the relevant `make` target | Never commit |
| `tests/bench/out/` | benchmark inputs and executables | benchmark targets | Never commit |

The generated seed is intentionally large. Review its generated diff, not its
hand-edited contents. Run `make -j1 seed verify` after a compiler source batch
so regeneration and verification share one build prerequisite.

## Local build workspace

`build/` is disposable. It contains compiler objects, generated C, caches,
performance data, review packs, and source-health output. These categories can be
cleaned independently:

```sh
make clean-obj      # objects and the grammar shared library
make clean-reports  # test results, profiles, reviews, and source-health reports
make clean          # all build products and test outputs
make clean-all      # explicit alias for a complete local reset
```

`make clean` removes tracked-independent build products but does not remove
source, tests, or the checked-in seed. `clean-obj` is useful when reclaiming space
without losing expensive profiling or review evidence. Keep `build/` when a
verification run is in progress, and avoid running cleanup concurrently with
`make check`, `make verify`, or another build.

## Search and editor hygiene

Search and navigation should normally exclude:

```text
build/
node_modules/
editors/vscode/out/
scripts/__pycache__/
tests/__pycache__/
```

Keep `seed/zen.c` searchable only when bootstrap debugging requires it. For
ordinary compiler work, search `src/`, `tests/`, `docs/`, and `grammar/` first.
