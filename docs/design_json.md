# JSON

`src/std/json/` has four public layers. They share JSON grammar, but not
ownership models.

## Current surface

- `read` parses one complete value into a caller-owned `Jsons` arena.
- `Decoder.feed` incrementally emits `JsonEvent` values and may stop between
  any two input bytes. `finish` rejects an incomplete document.
- `Nest`, `obj`, `arr`, and `write_text` write JSON through the caller's output
  state.
- `value.to_json(alloc)` encodes a concrete record. The compiler performs
  type-directed call-site lowering over its fields; primitive spelling and
  string escaping stay in `std.json`.

The DOM reader and streaming decoder deliberately remain separate owners. A
DOM parse owns a retained tree; a decoder owns token and nesting state only
until it emits events. Forcing both through a temporary `Jsons` arena would
make streaming allocate and retain values it is meant to release.

## Shared grammar

`json_read.zen` owns primitive token validation and decoding. The streaming
decoder uses the same token doors for quoted text, escapes, numbers, booleans,
and null rather than carrying a second JSON grammar. Both paths reject raw
control bytes in strings.

`JsonEvent.Number` retains the validated spelling. Numeric interpretation is a
consumer decision, avoiding an implicit precision or range policy in the
streaming layer.

## Streaming contract

A feed may end inside a UTF-16 escape, quoted token, number, keyword, or nested
container. Only complete events are appended. `finish` is the boundary that
turns an unfinished token or container into `JsonFault`; bytes after one root
value are trailing input.

This is chunk streaming, not actor ownership. An actor or HTTP/2 receiver may
own a `Decoder` and feed each received body chunk into it, but JSON does not
create workers, mailboxes, or backpressure policy.

## Remaining typed work

Typed record encoding is implemented. A general typed decoder is not: it needs
a schema that maps JSON keys to fields, constructs the target value, reports
missing/unknown fields, and defines integer conversion. That schema should be
plain data derived from the compiler's existing AST, not a parallel reflection
tree or a generated parser per type.

The current behavior is held by `tests/corpus/json/`, especially
`typed_record_to_json`, `streaming_decoder_crosses_chunks`, and
`read_and_stream_reject_raw_controls`.
