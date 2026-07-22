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

No hover/completion/goto yet — the server answers anything unimplemented with a clean
JSON-RPC `MethodNotFound`, so the client degrades gracefully.

## No-npm alternative

Any generic LSP client works. Point it at command `zen`, args `["lsp"]`, stdio transport,
language id `zen`, file pattern `*.zen`, root = the directory holding your `.git` or
`driver.zen`.
