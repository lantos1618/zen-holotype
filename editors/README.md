# Editors

Clients for `zen lsp`. Two of them, because the language server had none:
`src/lsp/` answers requests and there was no way for an editor to launch it
or talk to it.

```
editors/
├── README.md                      this file
├── .gitignore
├── nvim/
│   ├── zen.lua                    filetype, tree-sitter, and vim.lsp
│   └── queries/zen/highlights.scm a QUERY over grammar/, not a second grammar
└── vscode/
    ├── package.json               the language contribution and the settings
    ├── language-configuration.json
    ├── tsconfig.json
    ├── .vscodeignore
    └── src/extension.ts           launch the server, and explain any failure
```

---

## Read this first: what you actually get

**The transport works.** `Env` grew a `Stdin` capability, so `zen lsp` with
no arguments reads `Content-Length` framed JSON-RPC from stdin and writes
replies to stdout — the standard shape, what `docs/design_lsp.md` §4
specifies, and what both clients already assumed. Nothing in either client
had to change when it landed.

Verified end to end against the shipped `./zen`, driving it over a real
pipe: `initialize` answers with `hoverProvider: true`, `didOpen` is
accepted, `textDocument/hover` on `s` in `s = a + b` answers `i32`,
`shutdown` answers, and the process exits **0**.

**Now the honest part — this server answers hover and nothing else:**

- **No diagnostics.** The server never sends `publishDiagnostics`. No
  squiggles is correct behaviour, not a failure, and no amount of waiting
  will produce any. Errors still only come from running the compiler.
- **Hover answers at a use AND at a declaration.** Probing every identifier
  position in a four-line function, **10 of 12** answer; the two that do not
  are a space and a brace, which must not. A parameter or a local at its
  declaration answers with its type, a written type name with what it
  resolves to, and a function's name with its declaration handed back —
  `add = (a: i32, b: i32) i32`. It was **3 of 12** before, answering only at
  uses; see `docs/design_lsp.md` §2 for the table and the reasoning.
- **And it answers an IMPORTED name, which needs a build.** The server sends
  the open buffer through a real `zen build` of the root it works out from
  the document, so a type from another module resolves. That function is
  self-contained, so its 10 of 12 said nothing about a real file: the same
  twelve positions over a two-module root answered **4 of 12** before this
  and **9 of 12** after. The one still missing is the receiver of a field
  access, which `docs/design_lsp.md` §2 records as a sema bug.
- **What you have not saved is what gets checked.** The buffer is handed to
  the driver ahead of the disk, so hover describes what is on your screen,
  including a file that has never been written.
- **A `null` hover means "not known", never "no type".** A struct's or
  enum's own name, a pattern binder and a type parameter at its declaration
  all answer null, and so does anything whose type did not resolve. Hover
  refuses to print sema's `<unknown>` poison rather than show you a type
  that does not exist.
- **Everything else is refused by name** with `-32601`: definition,
  completion, symbols, formatting, rename, references. Hover on a document
  that was never opened is `-32602`, not null.
- **Colour does not come from the server** in either editor. Neovim gets it
  from tree-sitter today; VS Code gets none until `semanticTokens` lands.

If the launch shape ever changes, exactly one setting moves:

| editor | the setting | default |
|---|---|---|
| VS Code | `zen.server.path` + `zen.server.args` | `./zen` and `["lsp"]` |
| Neovim | `M.cmd` at the top of `nvim/zen.lua` | `{ <root>/zen, "lsp" }` |

Everything else in both clients is transport-independent.

---

## Build the server

```console
$ make build      # writes ./zen at the root of the checkout
$ make grammar    # writes grammar/zen.so — needed for Neovim highlighting
```

`grammar/zen.so` is generated and not committed (see the root `.gitignore`),
so `make grammar` is a required step for Neovim and not an optional one.

---

## Neovim

Needs Neovim **0.11 or newer** for `vim.lsp.config` / `vim.lsp.enable`.
There is a 0.10-and-earlier snippet at the bottom of `nvim/zen.lua`.

1. Copy `editors/nvim/zen.lua` to `~/.config/nvim/lua/zen.lua`.
2. Set `M.root` at the top of it to your Zen checkout, or export
   `ZEN_ROOT`, which wins.
3. In `init.lua`:

   ```lua
   require("zen").setup()
   ```

4. Open a `.zen` file. `:set filetype?` says `zen` and the buffer is
   highlighted by tree-sitter.
5. Put the cursor on an expression and press `K` for hover.

`setup()` is three independent pieces and you can take them one at a time —
`require("zen").filetype()`, `.treesitter()`, `.lsp()`. **The highlighting
half works today**; only `.lsp()` is waiting on the transport.

The server is started with `root_markers = { "build.zen", ".git" }`.
`build.zen` is first because `DESIGN.md` makes a build file a program and
`docs/PLAN.md`'s tree puts it at the repository root, so it is the marker
that means "this is a Zen project".

---

## VS Code

**This is written for a remote instance**, which changes the answer.
`package.json` declares `"extensionKind": ["workspace"]`, which is the
load-bearing line: without it VS Code may install the extension on the UI
side, where `activate()` runs on your laptop, `zen` is not on the PATH, the
workspace is not on the disk, and the failure reads as "the server crashed".
`docs/design_lsp.md` §6 has the full table of what runs where.

Build and install:

```console
$ cd editors/vscode
$ npm install
$ npm run compile
$ npx @vscode/vsce package --allow-missing-repository -o zen.vsix
$ code --install-extension zen.vsix
```

On a remote instance, run all of that **on the remote host** and install
into the remote's extension host (`code --install-extension` over the
Remote-SSH connection does this; or use *Extensions: Install from VSIX…* in
the palette with the window connected to the remote).

Then set the server path if it is not `./zen` relative to the workspace
folder:

```jsonc
// .vscode/settings.json, or the remote User settings
{
  "zen.server.path": "./zen",
  "zen.server.args": ["lsp"]
}
```

A relative path is resolved against the first workspace folder. A bare name
with no separator is left alone so it is looked up on `PATH`. Both are
resolved with the **extension host's** view of the filesystem — the remote
one — via `vscode.workspace.fs`, never `node:fs`.

Open a `.zen` file, hover over an expression. If anything goes wrong, the
**Zen** output channel says what; set `zen.trace.server` to `verbose` to see
the frames.

### Syntax highlighting in VS Code: there is none, on purpose

`docs/design_lsp.md` §6 sketches a `contributes.grammars` entry pointing at
`syntaxes/zen.tmLanguage.json`. **This extension deliberately does not ship
one, and that is a considered deviation from the design document rather than
an omission.**

Writing a TextMate grammar by hand means a second grammar, and
`docs/PLAN.md:137` names that as the failure the plan exists to avoid, in
those words: *"Never a second parser, never a second AST … Two grammars is
the failure this plan exists to avoid."* Generating one from
`grammar/grammar.js` would be no better — it would be a third generated
artifact, and `docs/PLAN.md:127` says a generated file without a gate
proving it fresh is *"a fork nobody is reading"*. This tree has exactly two
such files and each names its gate.

VS Code has no public API for loading a tree-sitter grammar from an
extension, so the grammar in `grammar/` cannot be reused there the way it is
in Neovim.

**The route that costs no second grammar is `textDocument/semanticTokens`,
lexical form.** `docs/design_lsp.md` §2 lists it as L2 with the query already
present — `scan` and `Token{kind, span}` in `src/lex/` — so the colours would
come from the compiler's own lexer, which cannot disagree with the compiler.
The server does not answer it yet.

Until then `.zen` files in VS Code get bracket matching, comment toggling
and correct word selection from `language-configuration.json` (which is
configuration, not a grammar; its `wordPattern` is copied from the one
`identifier` rule in `grammar/grammar.js`), and no colour.

---

## Syntax highlighting in Neovim: the existing grammar, reused

`grammar/` is this project's tree-sitter grammar and `docs/PLAN.md:147` says
it *"outlives the bootstrapper as the editor/LSP grammar"*. Neovim speaks
tree-sitter natively, so it is reused directly and there is nothing to
install from a registry:

- `nvim/zen.lua` calls `vim.treesitter.language.add("zen", { path = <root>/grammar/zen.so })`
  — the shared object `make grammar` builds from the committed
  `grammar/src/parser.c`.
- `nvim/queries/zen/highlights.scm` is a **query**, not a grammar. It names
  nodes the one grammar already produces. It cannot disagree with the
  compiler about what parses — only about what colour something is — and if
  a rule in `grammar.js` is renamed it fails loudly at query-compile time
  rather than silently.

The query is deliberately structural. Zen has almost no keywords, and a
type is a bare identifier, so a name is a type when it stands in a type
*position* — every one of which is a named field in the grammar. Where the
grammar genuinely does not know, the query does not guess: in `Left(Blank)`
the outer name is a constructor and the inner one is left uncoloured,
because whether it binds a payload or names a variant is a scope question
and therefore sema's.

---

## What the server answers today

| request | today |
|---|---|
| `initialize` / `shutdown` | **works** |
| `initialized` / `exit` / `$/cancelRequest` | notifications, no reply |
| `textDocument/didOpen` / `didChange` / `didClose` | **works**, Full sync only |
| `textDocument/hover` | **works** — a type, a declared name's type, or a function's signature |
| everything else | **refused by name** with JSON-RPC `-32601` |

"Everything else" is `textDocument/definition`, `documentSymbol`,
`completion`, `references`, `formatting`, `semanticTokens`, `signatureHelp`
and `rename`. The refusal names the method and points at
`docs/design_lsp.md`. An editor showing "method not supported" for those is
the server being honest, not this configuration being wrong.

**There are no diagnostics.** Every piece one needs now exists — sema's
were always values, lex's and parse's are collected on the build, and the
driver has a public entry that hands a build back — so what is left is the
request and a policy about when to send it. Half a diagnostics story is
worse than none, which is why it is not half-wired.

**Hover builds the root, once per hover.** There is no cache and no
debounce, so a hover in a file that imports most of the compiler takes
about a second on this machine; one in a leaf module is imperceptible.
`docs/design_lsp.md` §5 names debounce and coalescing as the answer and
`docs/PLAN.md:317` names where the real fix goes if that is not enough.

**A workspace is required for the imported half.** The root is computed
from the open document — climb out of every directory that holds its own
name — with `initialize`'s `rootUri` as the floor it may not pass. A client
that sends no `rootUri` gets the old lone-module answer, which is still
honest: it types what the file declares and answers `null` for what it
imports.

`zen fmt` exists as a command but wiring `textDocument/formatting` to it is
a separate change and `docs/design_lsp.md` does not ask for it yet. Neither
client configures a formatter.

---

## Driving the server today, without an editor

The file transport is not a toy — a server that can be driven from a file is
a server a test can drive. Frame each message with its **byte** length and
CRLF:

```
Content-Length: 74\r\n\r\n{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"rootUri":null}}
```

Concatenate the frames into one file and:

```console
$ ./zen lsp requests.jsonrpc replies.jsonrpc
```

`replies.jsonrpc` comes back framed the same way. This is how the behaviour
described above was checked.

---

## What was verified, and what was not

Verified here, by running it:

- **The server answers hover over a real pipe.** `zen lsp` with no
  arguments, driven by a framed session on stdin: `initialize` returned
  `{"textDocumentSync":1,"hoverProvider":true}`, `didOpen` was accepted,
  hover answered `i32`, `shutdown` returned `null`, and the process exited
  **0**. The file transport (`zen lsp <requests> <replies>`) still works and
  is what the corpus drives, since a test cannot hold a pipe open.
- **Hover's real coverage was measured, not assumed.** Every identifier
  position in `add = (a: i32, b: i32) i32 { s = a + b; s }` was probed over
  a real pipe, twice. It was **3 of 12** — the two parameter *uses* and the
  local's *use*, with declaration sites, type names and the function name
  answering null. It is now **10 of 12**: everything above answers, and the
  two that stay null are a space and the body's brace. The same table is a
  corpus test, `tests/corpus/lsp/hover_answers_at_a_declaration`, so the
  number is a gate and not a claim in a README.
- **And then measured again on a file that imports something**, because the
  program above imports nothing and 10 of 12 turned out to be a fact about
  the program rather than about hover. Twelve positions over a two-module
  root, same pipe: **4 of 12** before the build landed, **9 of 12** after.
  That table is also a corpus test,
  `tests/corpus/lsp/hover_answers_an_imported_name`, which additionally
  pins that the unsaved buffer beats the file on disk and that a buffer
  with an unclosed brace produces no stray output in the frame stream.
- **The tree-sitter grammar loads in Neovim 0.12.2** via
  `vim.treesitter.language.add` at the `--abi 14` the Makefile passes, and
  parses.
- **The highlights query compiles and covers the real tree.** Swept over all
  **159** `.zen` files in `src/`: 287,645 captures and **zero** `ERROR`
  nodes.
- **`nvim/zen.lua` loads and works.** `vim.filetype.match({filename="x.zen"})`
  returns `zen`; opening `src/lsp/lsp_hover.zen` gives a buffer with
  `filetype=zen` and an active tree-sitter highlighter with real captures.
- **The VS Code extension compiles and packages.** `tsc` under `strict`,
  then a 207-file `.vsix` including `vscode-languageclient` at runtime.

**Not verified, and why:**

- **The extension has never run inside VS Code.** There is no VS Code on
  this machine and no display. Everything above about the extension was
  checked with `tsc`, `vsce`, and a stubbed host. The manual steps in the
  VS Code section are the exact steps and they are untested end to end.
- **`"extensionKind": ["workspace"]` placing the extension on the remote
  host is unverified** — it needs a real remote connection to observe. It
  is what `docs/design_lsp.md` §6 specifies and the reasoning is recorded
  there.
- **Hover has not been observed inside either editor.** The transport it
  needs now exists and the server is verified answering over it directly,
  but neither client has been watched attaching to it — the Neovim run
  above predates the transport and has not been repeated, and there is no
  VS Code on this machine. This is the single most valuable thing left to
  check, and it is a five-minute check for anyone with an editor open.
- **Colour rendering was not eyeballed.** The Neovim highlighting is
  verified as *captures produced at the right ranges*, not as pixels. Which
  capture group maps to which colour is your colourscheme's business.
