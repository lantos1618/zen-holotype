# Zen in Neovim

Two pieces: the vim filetype/syntax files (shared with vim, in `editor/vim/`) and the
`zen lsp` language server for live diagnostics.

## 1. Filetype + syntax + buffer options

Link (or copy) the vim runtime files into your config — all three, including
`ftplugin/`, which carries `commentstring` (`gc`/`gcc` do nothing without it) and the
4-space indent `zen fmt` emits:

```sh
mkdir -p ~/.config/nvim/ftdetect ~/.config/nvim/syntax ~/.config/nvim/ftplugin
ln -s /path/to/zen/editor/vim/ftdetect/zen.vim ~/.config/nvim/ftdetect/zen.vim
ln -s /path/to/zen/editor/vim/syntax/zen.vim   ~/.config/nvim/syntax/zen.vim
ln -s /path/to/zen/editor/vim/ftplugin/zen.vim ~/.config/nvim/ftplugin/zen.vim
```

These must land under `~/.config/nvim` itself: lazy.nvim (and so LazyVim) resets
`runtimepath` at startup, which drops any other directory you appended.

Check it took — empty `commentstring` or `shiftwidth=2` means the `ftplugin` link is
missing:

```sh
nvim path/to/file.zen -c 'echo &filetype &commentstring &shiftwidth' -c 'sleep 2' -c qa
```

## 2. Language server (`zen lsp`)

`zen lsp` is a diagnostics language server over stdio (JSON-RPC, full-document sync).
On every open/change it runs the real check pipeline and pushes `publishDiagnostics` —
the same errors `zen check` prints, as squiggles, including errors surfaced from imported
sibling modules.

Native LSP config — no plugins needed (nvim 0.10+). Paste into your `init.lua`:

```lua
vim.api.nvim_create_autocmd("FileType", {
  pattern = "zen",
  callback = function(args)
    vim.lsp.start({
      name = "zen-lsp",
      cmd = { "/path/to/zen/zen", "lsp" },   -- absolute path to the built `zen` binary
      -- project root: the directory that identifies the project (imports resolve
      -- relative to each file's own directory, so root detection is forgiving).
      root_dir = vim.fs.root(args.buf, { ".git", "driver.zen", "build.zen" })
        or vim.fn.getcwd(),
    })
  end,
})
```

Notes:

- Build the server first: `make` at the repo root produces `./zen`.
- If the `zen` binary lives outside its checkout, point `ZEN_ROOT` at the checkout so
  `std.*` imports resolve: `cmd = { "zen", "lsp" }, cmd_env = { ZEN_ROOT = "/path/to/zen" }`.
- The server implements: `initialize`, `shutdown`, `exit`, `textDocument/didOpen`,
  `textDocument/didChange` (full sync), `textDocument/didClose` (clears diagnostics),
  `textDocument/definition` (go-to-definition) and `textDocument/semanticTokens/full`
  (semantic highlighting, which overrides the `syntax/` file where it has an opinion).
  Anything else gets a clean JSON-RPC `MethodNotFound` — hover and completion are not
  implemented yet, so leave those to other tooling.
- Semantic tokens and go-to-definition are recent; a `zen` binary older than they are
  simply will not advertise them. If highlighting looks flat or `gd` does nothing,
  rebuild (`make`) and confirm with the sanity check below — the reply must contain
  `semanticTokensProvider` and `definitionProvider`.
- Positions are proper 0-based UTF-16 LSP positions (non-ASCII lines squiggle correctly).

Quick sanity check from a shell (expect a `capabilities` reply):

```sh
printf 'Content-Length: 58\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | ./zen lsp
```
