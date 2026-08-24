# file-io lane

All six verified against `./runzen.sh` semantics through a byte-identical copy
whose only change is running the compiled program with cwd = the staging dir
(`tests/run.py:763` does `cwd=work`; the repo-root run would scatter scratch
files into the shared tree). Both oracles agreed byte-for-byte on all six.

- write_read_round_trip_keeps_nul_and_tabs -- strcpy-style NUL truncation, or a write/read that eats `\0`, `\t`, `\n`, `\\` or `\"`; the hash line pins all 20 bytes through str's own Hash impl.
- read_returns_whole_file_in_order -- a short read (single fread over refills), an off-by-one at either end, or a second open served from a stale cursor/descriptor; head/mid/tail spot bytes pin order, not just length.
- missing_path_names_not_found_on_both_doors -- any FsError ordinal remap (variant reorder in env.zen without updating gen_c_runtime.zen's ZG_FS_* block), or a miss mapped to Failed/OK-with-zero on either the read or the write floor.
- empty_file_reads_as_zero_not_stale -- skipping the truncate on a zero-length `wb` write (stale 19 bytes come back), or a length cached across reads; is_empty crosses the same length by another door.
- write_onto_directory_is_isdir -- trusting fopen's success on a directory (glibc fails only at first fwrite) so IsDir degrades to Failed/Ok; also catches an errno map that degrades to NotFound.
- rewrite_replaces_instead_of_appending -- opening for append instead of truncate "wb": shrinking 20 to 6 bytes leaves the old tail behind; fresh-read comparison catches a stale buffer too.

Notes for reviewers:

- The tests use bare relative paths ("roundtrip.bin"), not "src/<file>":
  the harness runs the binary with cwd = work and stages the test dir as
  work/src, so bare names are the portable spelling and never depend on
  where the runner was invoked. T3/T5 do reference "src" itself, which is
  the staged test directory under both run.py and runzen.sh staging.
- No compiler bugs found. Every prediction derived from src/std/env/env.zen,
  text_str.zen (hash constants), hash.zen (Hasher) and gen_c_fs/gen_c_runtime
  matched the oracle exactly, including the FNV-style value
  13453576393224285621 computed by hand before running.
TESTS: 6
