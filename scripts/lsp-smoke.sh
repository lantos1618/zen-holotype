#!/usr/bin/env bash
# lsp-smoke.sh — end-to-end smoke test for `zenc lsp` (the diagnostics-only Language Server).
#
# Feeds a framed JSON-RPC session over stdin (initialize -> didOpen[error] -> didChange[clean] ->
# shutdown -> exit) and asserts the pushed `textDocument/publishDiagnostics` notifications:
#   1. didOpen of a program with an `undefined-name` error  -> ONE diagnostic, 0-based range, code.
#   2. didChange to a clean program                         -> EMPTY diagnostics array (squiggles cleared).
#
# Runs the compiler in-tree; ZEN_ROOT points the resolver at this checkout's std/ so imports resolve.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZENC="$ROOT/zen"
export ZEN_ROOT="$ROOT"

if [ ! -x "$ZENC" ]; then
  echo "lsp-smoke: $ZENC not built; run 'make' first" >&2
  exit 2
fi

# frame BODY -> `Content-Length: <bytes>\r\n\r\n<BODY>` on stdout (byte-exact length).
frame() {
  local body="$1"
  local len
  len=$(printf '%s' "$body" | wc -c)
  printf 'Content-Length: %d\r\n\r\n%s' "$len" "$body"
}

URI="file://$ROOT/tmp-lsp-smoke.zen"
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"capabilities":{}}}'
INITED='{"jsonrpc":"2.0","method":"initialized","params":{}}'
# an undefined name `x`; the "\n" is a JSON escape, so the server decodes it to a real newline.
OPEN='{"jsonrpc":"2.0","method":"textDocument/didOpen","params":{"textDocument":{"uri":"'"$URI"'","languageId":"zen","version":1,"text":"main = () i32 { x }\n"}}}'
CHANGE='{"jsonrpc":"2.0","method":"textDocument/didChange","params":{"textDocument":{"uri":"'"$URI"'","version":2},"contentChanges":[{"text":"main = () i32 { 0 }\n"}]}}'
SHUTDOWN='{"jsonrpc":"2.0","id":2,"method":"shutdown"}'
EXIT='{"jsonrpc":"2.0","method":"exit"}'

OUT=$( { frame "$INIT"; frame "$INITED"; frame "$OPEN"; frame "$CHANGE"; frame "$SHUTDOWN"; frame "$EXIT"; } | "$ZENC" lsp )

echo "===== server stdout ====="
printf '%s\n' "$OUT"
echo "========================="

fail=0
check() { # DESC PATTERN
  if printf '%s' "$OUT" | grep -qF "$2"; then
    echo "PASS: $1"
  else
    echo "FAIL: $1 (missing: $2)"
    fail=1
  fi
}

# initialize handshake
check "initialize result advertises full textDocumentSync" '"capabilities":{"textDocumentSync":1}'
# error diagnostic: undefined-name at 0-based line 0, character 16..17 (1-based 1:17)
check "publishDiagnostics for the document"      '"method":"textDocument/publishDiagnostics"'
check "undefined-name code"                      '"code":"undefined-name"'
check "0-based range start (line 0, char 16)"    '"start":{"line":0,"character":16}'
check "0-based range end   (line 0, char 17)"    '"end":{"line":0,"character":17}'
check "severity Error"                           '"severity":1'
check "source zen"                               '"source":"zen"'
# clean rediagnose: empty diagnostics array clears the squiggle
check "cleared diagnostics on clean didChange"   '"diagnostics":[]}}'

if [ "$fail" -eq 0 ]; then
  echo "lsp-smoke: OK"
  exit 0
fi
echo "lsp-smoke: FAILED" >&2
exit 1
