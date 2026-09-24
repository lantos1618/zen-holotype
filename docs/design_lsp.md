# Language server

The language server is a transport and workspace owner over compiler queries.
It does not carry a second parser, AST, formatter, name resolver, or type
checker.

## Request surface

The server advertises Full document sync and these requests:

| request | owner |
|---|---|
| hover | sema type and declaration queries |
| definition | sema resolution plus AST declaration spans |
| document symbols | the parsed buffer's top-level declarations |
| completion | trigger scan, then sema members or visible world names |
| code actions | undefined-name diagnostics plus world exports |
| formatting | the same `fmt.render` used by `zen fmt` |
| semantic tokens/full | lexer tokens refined by sema facts |

Diagnostics are notifications, not a request. References, rename, signature
help, range/on-type formatting, and semantic-token range/delta are not
advertised. Unknown requests receive JSON-RPC `-32601`.

## Transport and lifecycle

`zen lsp` reads and writes JSON-RPC 2.0 frames over stdio. The framing layer
owns `Content-Length`; the JSON layer owns request values; the server owns
protocol state. Shutdown returns a response and refuses subsequent requests;
only `exit` terminates the process. Exit succeeds after shutdown and fails
otherwise, including before initialization. Notifications before initialization
are ignored except for exit. Cancellation notifications are currently ignored:
checking is synchronous and cannot observe them while a query is running.

Malformed JSON-RPC envelopes receive `-32600`. The stdio transport limits
headers to 8 KiB and bodies to 16 MiB, and exits unsuccessfully on invalid or
oversized frames without writing unframed text to stdout.

`Stdin.read` blocks for exactly the requested byte count. The frame reader must
therefore ask for only the bytes missing from the current header or body; a
fixed-size read can deadlock while the editor waits for a reply.

## Positions

Compiler spans use 1-based byte columns. LSP positions use 0-based UTF-16 code
units; the server does not advertise another encoding. Conversion is
centralized in `lsp_pos.zen`; query handlers do not perform their own arithmetic.
Missing, negative, or nonnumeric position fields are rejected as invalid
parameters. Position conversion clamps offsets to the available buffer.

## Documents and builds

Open buffers form an overlay read before disk. Each `Document` owns an arena
containing its URI, decoded filesystem path, and text. Replacing one buffer
retires only that buffer; the overlay map borrows descriptors from document
owners. Identical text preserves storage so cached compiler facts remain valid.
Retirement consumes the extracted document payload into a local owner so its
destructor runs. Replacement metadata is prepared before old buffers retire;
allocation failure rolls back the new buffer and preserves the old overlay.

Full-text change events are validated before mutation and applied in order.
An empty event list preserves the text. Older or equal versions cannot replace
a versioned buffer, and changes cannot implicitly open a document. Versionless
messages remain accepted for existing embedded clients only while a document
has no recorded version. Ranged changes are refused under Full sync.

URI conversion decodes escaped bytes for filesystem access and escapes paths
for emitted URIs. It supports local file URIs, localhost, VS Code remote
connection authorities, and the relative `file://` paths used by embedded
clients. Raw filesystem paths remain literal. Invalid escapes and escaped NUL
bytes remain literal rather than becoming filesystem control bytes.

Sync is Full because compilation is whole-program; applying incremental edits would add a second text-range
implementation without making compilation incremental.

One `WorkspaceTurn` owns the environment, workspace, URIs, open documents, and
temporary request storage for a publication turn. A checked build can serve
both diagnostic publication and semantic queries. The cache retains one entry;
queries for imported modules reuse it when the compilation root matches and
the snapshot is current. Queries for different independent graphs may rebuild.

A build has its own arena. Replacing the build explicitly releases that arena,
so whole-program AST and sema memos do not accumulate for the life of the
editor. Answers retained beyond replacement must be copied into session-owned
or turn-owned storage, according to how long they are needed.

No workspace means no diagnostics: a lone-module check would report imported
names as undefined. Queries whose safe failure is silence may still answer from
the buffer alone.

## Diagnostics

Lex, parse, and sema diagnostics are values. They are grouped by the URI named
by each span and published once per file. Publishing an empty list is how the
server clears errors that were fixed; omitting a file would leave stale errors
on screen. Notes become LSP `relatedInformation` so their second span remains
navigable.

A dirty workspace publication checks every open entry and combines diagnostics
from its import graphs before clearing previous results. A graph already in the
current build is reused; diagnostics copied between builds belong to the turn.
The last published bodies occupy one replaceable arena and suppress duplicate
notifications. Read-only settlements do not rebuild retained diagnostic lists.
Closing an independent document retires its results; an imported closed file
can still have diagnostics from another open entry's graph.

A buffer with syntax errors is normal editor input. Formatting therefore
returns an empty edit list for lexical faults, parse faults, a failed faithful
guard, or an already-formatted file. It does not turn a half-typed buffer into a
modal error.

## Known gaps

- Local and pattern binding spans exist while sema checks a scope, but no
  resolved local-definition memo survives `check_all`; definition returns null.
- Completion does not yet include locals, parameters, or every UFCS candidate.
- References need a durable reverse resolution index; rename depends on it.
- Signature help needs overload candidates plus the active argument position.
- Independent open graphs are checked synchronously after changes. A bounded
  cache per graph and dependency-aware scheduling remain performance work.
- Stdio cannot observe a quiet interval, so real-editor debounce/coalescing is
  limited by the blocking input capability.

## Clients and gates

`editors/nvim/zen.lua` uses tree-sitter for base highlighting and the LSP for
semantic features. The VS Code extension uses a minimal TextMate grammar for
strings/comments/bracket correctness and semantic tokens for language-aware
colour.

`tests/corpus/lsp/` is the executable capability map. It covers framing,
lifecycle, UTF-8/UTF-16 conversion, overlays, build sharing, diagnostics and
clearing, every advertised query, and refusals. A new advertised capability
must land with a corpus case; a missing handler must not be advertised.

`make lspcheck` runs real-process regressions for lifecycle, synchronization,
URI escaping, independent diagnostics, malformed requests, and frame limits.
It is included in `make verify`. Ownership sanitizer checks also run that
protocol suite against a standalone ASan-instrumented LSP executable, including
leak detection after replacement, closure, and graceful shutdown. The
corpus includes a counting-allocator regression for idle diagnostic sessions.
