# tests/corpus/env-args

Command-line arguments: none, several, unicode. The seam under every test
here is `zg_argv_vec` (`src/gen/gen_c/gen_c_main.zen`): C hands the process
`argc`/`argv`, and the generated prologue must turn that into a real
`Vec<str>` on `Env.argv` — a `(Env){0}` made `env.argv.len` 0 in every
program this tree ever compiled, which is why `argv_is_populated`
(`tests/corpus/env/`) exists and why these tests go further than it can.

The runner passes no arguments, so "none" is the one case exercised
directly; "several" and "unicode" are pinned through rows built in-program
over the same `str` shape argv hands over, plus content assertions on the
one row every run has (argv[0], always ending in `/prog`). A test that
needed real extra arguments would pin the harness, not the compiler —
nothing in `tests/run.py` passes them.

One harness trap worth writing down, found the hard way: under `runzen.sh`
argv[0] is `<mktemp-dir>/prog` and its byte length is a stable 24, which
tempts an absolute-length expectation. Under `tests/run.py` the binary
lives at `<workroot>/<tid-with-dashes-mangled>/prog`, so argv[0]'s length
is a function of THE TEST'S OWN NAME — four of these tests were written
with `len 24` and failed only in the real gate. The length is asserted for
SELF-consistency (last '/' at len-5, bytes==chars on an ASCII path); only
the "/prog" tail and individual bytes are pinned absolutely.

## One line per test: what one-line compiler change breaks it

- argv0_names_the_program — write `rows[i].len = strlen(argv[i]) - 1` (any truncation): the last-slash check moves off `len-5` even though the tail still prints.
- past_the_last_row_is_none — emit `.len = 0` in the Vec literal (revert the `(Env){0}` fix): count prints 0 and the last row reads as None; equally, `.len = argc + 1` leaks a row past the end.
- argv_rows_survive_two_walks — reset or free the row array when main's first read of `env.argv` ends (a cursor-shaped lowering): pass 1 drops or mangles the row.
- argv_row_bytes_are_raw_utf8 — copy each row through a signed `char` (narrowing 103/'g' to -1): first/last byte print negative garbage while lengths still look right.
- multibyte_row_decodes_by_codepoint — count lead bytes instead of assembling continuation payloads (or truncate at the first high bit): "日本" reports 6-and-3 instead of 6-and-2, or 3-and-1.
- many_rows_sum_their_lengths — fill only part of `rows[]` while claiming `.len = argc`, or write every slot from `argv[0]`: the sum moves off 18 even though the row count still prints 6.
- argv_rows_key_a_map_by_content — hash `data` (the pointer) in str's Hash impl instead of walking bytes: the duplicate "alpha" inserts a second entry and `get("alpha")` misses.
- argv_row_hash_pins_the_seed — change `STR_HASH_SEED` to 0 (the silent-default failure): empty-hash becomes 0 and hash("prog") moves off 1787684418322129931.

## Compiler bugs found while writing this lane

None that survived into an encoded expectation. Two things worth recording:

1. **`Range.find` with a closure calling `.len` on the element emits C that
   does not compile** (`request for member 'zu_m3len' in something not a
   structure or union`). Program:

   ```
   hit ::= Range(0, env.argv.len).find((p) { p.len > 3 });
   ```

   In the emitted C the loop-body parameter is used as a struct
   (`zu_l1p.zu_m3len`) where it was passed as something else — looks like
   the pred closure's parameter type is not resolved through the Range
   bound before lowering. Same shape when the body is a fold accumulator
   over the elements (`loop(0, (h, i, p, acc) { acc + p.len })`): the fold's
   element parameter loses its type too. Not encoded: it is a rejection
   (must-fail territory), not wrong stdout, and it belongs to whoever owns
   the loop-family lowering.

2. **`env.vars` is zeroed** — `get("ANYTHING")` is None for every name,
   including ones actually in the environment (checked directly:
   `ZEN_TEST_MARKER=hello-42 ./prog` prints absent). The generated prologue
   builds `(Env){ .zu_m4argv = zg_argv_vec(argc, argv) }` and leaves every
   other field at zero; nothing calls `getenv`. Consistent with gen_c_main's
   comment that argv is "the one field the C runtime actually hands us", so
   probably a known stage boundary rather than a bug — but no corpus test in
   tests/corpus/env/ pins vars either way, and the div-mod-traps suite
   RELIES on vars.get returning None for a name never set, which passes for
   the wrong reason if vars is simply always empty.

TESTS: 8
