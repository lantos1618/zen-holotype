fuzz reproducers — campaign 2026-07-28 (test/fuzz-campaign)

Saved reproducers for the findings of a long fuzz run (tools/fuzz-diff.zen,
tools/fuzz-corpus.zen, tools/fuzz-mutate.zen via scripts/fuzz-run.sh,
scripts/alloc-fuzz/*, hand-directed probes).

EXTENSION: every file here is `*.zen.txt`, NOT `*.zen`, on purpose. Three repo
gates enumerate Zen sources with a bare glob and would swallow these:
  * scripts/fmt-check.sh          find src tests examples tools -name '*.zen'
  * tests/harness_fmt_roundtrip   ls tests/fixtures/zen/*.zen
  * tests/harness_build           explicit paths only (safe)
Several reproducers here CRASH or are deliberately malformed, so a `*.zen` name
would turn the fmt gate and the fmt-roundtrip harness red. The compiler accepts
any extension (`./zen check foo.zen.txt` works), so the repros still run.

Each file's header carries the exact command and the observed output.
