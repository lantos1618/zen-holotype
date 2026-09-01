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
protocol state. `initialize`, `initialized`, `shutdown`, `exit`, and
`$/cancelRequest` are handled separately from text-document queries.

`Stdin.read` blocks for exactly the requested byte count. The frame reader must
therefore ask for only the bytes missing from the current header or body; a
fixed-size read can deadlock while the editor waits for a reply.

## Positions

Compiler spans use 1-based byte columns. LSP positions use 0-based UTF-16 code
units unless the client negotiates UTF-8. Conversion is centralized in
`lsp_pos.zen`; query handlers do not perform their own arithmetic. Invalid or
out-of-range positions produce an empty/null answer appropriate to the request,
not a guessed location.

## Documents and builds

Open buffers form an overlay read before disk. Sync is Full because compilation
is whole-program; applying incremental edits would add a second text-range
implementation without making compilation incremental.

One `WorkspaceTurn` owns the environment, workspace, URIs, open documents, and
temporary request storage for a publication turn. A settled document state
shares one checked build across diagnostics and queries.

A build has its own arena. Replacing the build explicitly releases that arena,
so whole-program AST and sema memos do not accumulate for the life of the
editor. Answers retained beyond replacement must be copied into session-owned
storage.

No workspace means no diagnostics: a lone-module check would report imported
names as undefined. Queries whose safe failure is silence may still answer from
the buffer alone.

## Diagnostics

Lex, parse, and sema diagnostics are values. They are grouped by the URI named
by each span and published once per file. Publishing an empty list is how the
server clears errors that were fixed; omitting a file would leave stale errors
on screen. Notes become LSP `relatedInformation` so their second span remains
navigable.

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
