# Zen in VS Code

A minimal LSP client wiring `zen lsp` (diagnostics over stdio) into VS Code.

## Install

```sh
cd editor/vscode
npm install                     # pulls vscode-languageclient (the only dependency)
ln -s "$PWD" ~/.vscode/extensions/zen-lsp-client   # or: npx vsce package && code --install-extension *.vsix
```

Then in VS Code settings set `zen.serverPath` to the absolute path of the built `zen`
binary (`make` at the repo root produces it), or put `zen` on your `PATH`. If the binary
lives outside its checkout, also export `ZEN_ROOT=/path/to/zen` so `std.*` imports resolve.

## What you get

- `.zen` files registered as the `zen` language
- live squiggles from the real compiler pipeline on open/change (full sync), cleared on
  close; errors inside imported sibling modules are surfaced on the importing file

- go-to-definition, hover and completion, all served from the OPEN BUFFER (never the
  saved file) and all resolved textually, so they keep working while the file is
  mid-edit and does not parse. Their exact reach — same-file top-level declarations,
  plus names bound by the file's import records — is spelled out in
  [`editor/nvim/README.md`](../nvim/README.md#2-language-server-zen-lsp)
- semantic highlighting from the compiler's own lexer

Anything else the server answers with a clean JSON-RPC `MethodNotFound`, so the client
degrades gracefully.

## No-npm alternative

Any generic LSP client works. Point it at command `zen`, args `["lsp"]`, stdio transport,
language id `zen`, file pattern `*.zen`, root = the directory holding your `.git` or
`driver.zen`.
