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

Native LSP config — no plugins needed (nvim 0.10+). `editor/nvim/zen.lua` in this repo IS
that config: source it from your `init.lua` and it starts the server and installs the
buffer-local motions (`gd`, `K`, `gO`, `]m`, `[m`).

```lua
vim.g.zen_lsp = { cmd = { "/path/to/zen/zen", "lsp" } }   -- absolute path to the built `zen`
dofile("/path/to/zen/editor/nvim/zen.lua")
```

It returns a table, so `require("zen")` works too when `editor/nvim/` is on the
runtimepath, and `require("zen").setup{ cmd = …, root_markers = …, keymaps = false }`
re-installs with different options.

Or wire it by hand, if you want only the server:

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

### The motions

| key | request | what it does |
| --- | --- | --- |
| `gd` | `textDocument/definition` | jump to the declaration, across modules |
| `K` | `textDocument/hover` | signature + doc comment |
| `gO` | `textDocument/documentSymbol` | the buffer's outline, in the location list |
| `]m` / `[m` | `textDocument/documentSymbol` | next / previous function-or-method |

`]m`/`[m` are Vim's method motions. Normally they are tree-sitter textobjects, and Zen has
had no grammar to bind them to since the Python purge deleted it; `zen.lua` drives them
from the same symbol list `gO` shows instead, so they land on a method declared INSIDE a
type body — where a brace heuristic cannot reach.

Notes:

- Build the server first: `make` at the repo root produces `./zen`.
- If the `zen` binary lives outside its checkout, point `ZEN_ROOT` at the checkout so
  `std.*` imports resolve: `cmd = { "zen", "lsp" }, cmd_env = { ZEN_ROOT = "/path/to/zen" }`.
- The server implements: `initialize`, `shutdown`, `exit`, `textDocument/didOpen`,
  `textDocument/didChange` (full sync), `textDocument/didClose` (clears diagnostics),
  `textDocument/definition` (go-to-definition), `textDocument/hover`,
  `textDocument/completion`, `textDocument/documentSymbol` (the outline) and
  `textDocument/semanticTokens/full` (semantic highlighting, which overrides the `syntax/`
  file where it has an opinion). Anything else — `references`, `rename`,
  `implementation`, `signatureHelp` — gets a clean JSON-RPC `MethodNotFound`.
- **Outline** (`gO`, `]m`, `[m`) lists the buffer's top-level declarations — functions,
  types, globals — with a type's METHODS nested under it, inherent methods included, under
  the name the source writes (the parser hoists them into mangled `impl_*` functions, which
  never reach the client). Two things it does not list, both because the AST gives them no
  source position: struct FIELDS and enum VARIANTS. And a symbol's `range` covers its name
  (stretched over its methods), not its full source extent — no declaration carries an end
  offset, so folding by symbol will not do anything useful.
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
- Semantic tokens, go-to-definition, hover, completion and the outline are recent; a `zen`
  binary older than they are simply will not advertise them. If highlighting looks flat,
  `gd` does nothing, `K` says "No information available" or `gO` is empty, rebuild (`make`)
  and confirm with the sanity check below — the reply must contain `semanticTokensProvider`,
  `definitionProvider`, `hoverProvider`, `completionProvider` and `documentSymbolProvider`.
- Positions are proper 0-based UTF-16 LSP positions (non-ASCII lines squiggle correctly).

Quick sanity check from a shell (expect a `capabilities` reply):

```sh
printf 'Content-Length: 58\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | ./zen lsp
```
