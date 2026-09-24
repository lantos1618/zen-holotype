# Parallel compiler work

Build once for a source batch, then run independent test selections against that
compiler. Rebuild after the next related batch of source changes. Use a separate
build directory when comparing compiler configurations or source snapshots.
`make verify` remains the complete required gate after the work is combined.

## Development commands

| Command or variable | Purpose |
| --- | --- |
| `make dev-build` | Build a compiler in `build/dev/zen` with its own generated C, objects, and incremental state. |
| `make dev-check` | Build that compiler, then run the selected corpus tests. |
| `make dev-run` | Run tests with an existing compiler; perform no build. |
| `DEV_DIR=build/lanes/parser` | Give a worker its own build artifacts and compiler. |
| `DEV_ZEN=/path/to/zen` | Select the compiler output/input explicitly; defaults to `DEV_DIR/zen`. |
| `ROOT=/path/to/source` | Select the compiler sources to bootstrap. |
| `J=4` | Limit C compilation workers for a build. |
| `TEST_J=4` | Limit test workers; defaults to `J`. |
| `FILTER='corpus/parse/*'` | Select test IDs by glob; an omitted filter selects the whole corpus. |
| `TEST_ARGS='--timings'` | Forward extra runner options, including repeated filters, shards, and timing reports. |

For a focused iteration:

```sh
make dev-check DEV_DIR=build/lanes/parser FILTER='corpus/parse/*' J=4 TEST_J=4
make dev-run DEV_DIR=build/lanes/parser FILTER='corpus/parse/parser_precedence'
```

The second command checks one case without rebuilding. Development runs reuse
eligible passing results; `TEST_ARGS='--no-result-cache'` forces execution.
They also use ccache for native objects when available through `CACHE`;
`CACHE=` disables object caching. See [test iteration](TEST_ITERATION.md) for
result-cache invalidation and eligibility. An empty selection
returns an error. Use `python3 tests/run.py --list --filter 'corpus/parse/*'` to
inspect a selection before running it. `dev-check` runs the corpus selection;
formatting, grammar, determinism, warning, sanitizer, and other required gates
remain in `make verify`.

## Share one built compiler across test workers

Create a batch compiler, then leave its output untouched until every test worker
finishes. Tests already use separate temporary directories, so separate test
processes can safely share that compiler. Give timing reports and logs distinct
paths.

This example runs two shards. Shards are one-based partitions of the sorted,
filtered test IDs, so `1/2` and `2/2` together cover the selection. Each process
still validates test discovery and fixture structure.

```sh
make dev-build DEV_DIR=build/lanes/batch J=8

make dev-run DEV_DIR=build/lanes/batch TEST_J=4 \
  TEST_ARGS='--shard 1/2 --timings --timings-json build/lanes/batch/shard-1.json' \
  > build/lanes/batch/shard-1.log 2>&1 &
shard_one_pid=$!

make dev-run DEV_DIR=build/lanes/batch TEST_J=4 \
  TEST_ARGS='--shard 2/2 --timings --timings-json build/lanes/batch/shard-2.json' \
  > build/lanes/batch/shard-2.log 2>&1 &
shard_two_pid=$!

shard_one_status=0
wait "$shard_one_pid" || shard_one_status=$?
shard_two_status=0
wait "$shard_two_pid" || shard_two_status=$?
test "$shard_one_status" -eq 0 && test "$shard_two_status" -eq 0
```

Check both logs when a shard fails. Waiting for each PID preserves either
worker's failure; a bare `wait` does not provide that aggregate result. The
same pattern works with disjoint `FILTER` selections instead of shards.

## Separate compiler builds

Give each independently built compiler a different `DEV_DIR`. For example,
workers can run these commands concurrently:

```sh
make dev-check DEV_DIR=build/lanes/loops FILTER='corpus/loop-basic/*' J=4 TEST_J=4
make dev-check DEV_DIR=build/lanes/meta FILTER='corpus/meta/*' J=4 TEST_J=4
```

Choose worker counts across all concurrent processes. Two builds with `J=4`
can run eight C compilations at once; test workers also launch native tools.
A lane's build and test steps run sequentially. Measure before giving every
lane all available CPUs.

Artifact isolation does not isolate source edits. On a shared checkout, assign
non-overlapping file ownership and finish the source batch before building.
For independent revisions, use separate worktrees/checkouts containing the
intended changes. `ROOT` can select a source snapshot, but the committed seed,
native process floor, test fixtures, and test standard library still come from
the checkout running the command.

The development variables affect `dev-*` targets only. Canonical `make build`
and `make verify` continue to use `./zen` and their existing gate directories.
Do not point different build directories at the same `DEV_ZEN`, rebuild a lane
while its tests are running, or run `make clean` while workers use `build/`.

## Validation measurements

On September 6, 2026, two `dev-build` processes bootstrapped the full compiler
from one isolated source snapshot into separate temporary lane directories.
With `J=4` per lane and the machine's existing ccache, both completed in
16.15 seconds total. Their compiler outputs and build state were separate;
the canonical `./zen` checksum stayed unchanged.

Two concurrent `dev-check` calls then reused those builds and ran the nine
`loop-basic` cases and seven `meta` cases, with `TEST_J=2` per lane. All 16
passed in 1.40 seconds total. These are single observations on a shared
16-CPU development machine, not timing budgets or a comparison with serial
execution.

The Make targets were also checked for failure propagation: a failed lane
build prevented test execution, and an unmatched test filter failed the
command. A dry run confirmed that development filters, shards, and compiler
paths do not alter the canonical `make verify` commands. `runnercheck`, which
is included in `verify`, exercises shard partitioning and timing-report
behavior without compiling the language implementation.
