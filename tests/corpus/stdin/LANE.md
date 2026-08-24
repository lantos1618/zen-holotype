# tests/corpus/stdin

Byte-counted stdin: what `env.in.read` answers, in order, at the edges
of a stream. Each dir holds `main.zen` + `main.stdin` (bytes fed to the
PROGRAM — absent `.stdin` would be /dev/null) + `main.expected`.

- an_empty_stream_answers_zero_and_no_error -- end-of-input is `Ok(0)`, never `Err`; flip `io_chain`'s `fread==0` arm to assign `Closed` and this prints "was an error"
- one_line_arrives_whole_with_its_newline -- a read returns exactly the peer's bytes; strip the trailing `\n` in the floor (or stop early like a text layer) and "got 16" fails against 17
- no_trailing_newline_is_still_whole_bytes -- a stream ending mid-word ends all the same and the NEXT read answers `Ok(0)` once; return the previous count again instead of 0 and "first 13 second 0" goes red
- a_refused_read_consumes_nothing -- the room check precedes any byte movement and names `Full`; move `zg_stdin_read`'s `n > cap - len` test after the `fread` (or map the wrong ordinal) and the retry sees end of input instead of "abcdefg\nhij"
- a_long_line_reassembles_from_chunks -- 86 bytes reassemble across 14 passes of 7; drop the `advance_len` write-back so later chunks overwrite offset 0, or answer the first chunk forever, and head/`mid`/`total 9113` all break
- one_read_spans_lines_without_discipline -- one read crosses three lines with `\n` as ordinary bytes at offsets 5 and 10; add line discipline to the floor and the byte table loses or moves its two 10s

## Compiler bugs found

None. Every behaviour the floor's C (`src/gen/gen_c/gen_c_stdin.zen`)
promises — room check before `fread`, `n==0` short-circuit, `Ok(0)` at
end of input with `len` untouched, `Err(Full)` consuming nothing,
byte-exact reassembly across chunked reads — held under these programs.

Two sharp edges worth knowing (language design, not bugs):
- `.try()` on `env.in.read` does not widen for you: a function whose
  signature says `AllocError` cannot `.try()` it ("no implicit error
  conversion... there is no From"); declare `Error = AllocError | IoError`.
- `Res<u8>` has no `Eq`, so `b.get(i) == Ok('x')` is rejected by sema;
  unwrap through `.match` first.

TESTS: 6
