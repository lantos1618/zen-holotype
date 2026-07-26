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
  `textDocument/definition` (go-to-definition), `textDocument/hover`,
  `textDocument/completion` and `textDocument/semanticTokens/full` (semantic
  highlighting, which overrides the `syntax/` file where it has an opinion). Anything
  else gets a clean JSON-RPC `MethodNotFound`.
- **Hover** (`K`) shows the declaration under the cursor: its signature in a fenced
  `zen` block — a type shows its whole field block — followed by the `//` comment
  written above it. It covers the file's own top-level declarations; over a name the
  file IMPORTS it names the origin module instead. Over a local, a field, or a name
  declared in another file there is nothing it can honestly say, and it returns no
  hover rather than a guess.
- **Completion** (`<C-x><C-o>` with `omnifunc=v:lua.vim.lsp.omnifunc`, or any
  completion plugin) offers the buffer's top-level declarations (with their signature
  as the detail), the names its `{ … } = module` import records bind (with the origin
  module), and the language's keywords and builtin type names. It does NOT offer
  locals, struct fields, or members after a `.` — which is why the server advertises no
  trigger characters: typing `.` will not pop a member list, because there is no
  member list to serve.
- Both are answered TEXTUALLY, from the buffer the client has open. That is why they
  still work in a half-typed file that does not parse — the moment you most want them —
  and it is also the reason for the limits above.
- Semantic tokens, go-to-definition, hover and completion are recent; a `zen` binary
  older than they are simply will not advertise them. If highlighting looks flat, `gd`
  does nothing or `K` says "No information available", rebuild (`make`) and confirm
  with the sanity check below — the reply must contain `semanticTokensProvider`,
  `definitionProvider`, `hoverProvider` and `completionProvider`.
- Positions are proper 0-based UTF-16 LSP positions (non-ASCII lines squiggle correctly).

Quick sanity check from a shell (expect a `capabilities` reply):

```sh
printf 'Content-Length: 58\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | ./zen lsp
```
