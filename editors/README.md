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

**Now the honest part — this server answers hover and semantic tokens,
publishes diagnostics, and refuses everything else:**

- **Diagnostics work, and they are all three phases.** Open or edit a `.zen`
  file in a workspace and the server builds the root behind it and publishes
  what lex, parse and sema found — squiggles, in the editor, as you type.
  They are **grouped per file**, so an error in a module you are not looking
  at is reported against *that* file and not against the one on screen; and
  a file whose errors you have fixed receives an empty list, so nothing
  stale is left underlined. A parse diagnostic's second position — "the
  parser gave up here" — arrives as `relatedInformation`, which your editor
  renders as somewhere to jump to.
- **Diagnostics need a workspace, and there is no fallback.** With no
  `rootUri` the server publishes nothing at all, deliberately: without a
  root the only thing it could check is the open file standing alone, and
  that reports every imported name as undefined — a screenful of red about
  a program that is fine. Silence is the honest answer there.
- **A build runs per change, and this is the cost.** There is no timed
  debounce and there cannot be one yet — the server is single-threaded with
  a blocking read and no clock, so it has no way to notice that you have
  stopped typing. What it does instead: changes that arrive together cost
  one build, and a change that carries the bytes the buffer already held
  costs none. In a file that imports most of the compiler a build is about
  a second, so expect diagnostics to lag your typing in a large module and
  to be instant in a leaf one. `docs/design_lsp.md` §5 has the reasoning
  and names what would have to exist for a real debounce.
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
- **Colour comes from two different places, and only one of them is the
  server.** Neovim gets it from tree-sitter and always did; nothing about
  Neovim changed when `semanticTokens` landed, and nothing needs to. VS
  Code gets it from the server, because VS Code cannot load the
  tree-sitter grammar this repository already has — `textDocument/
  semanticTokens`, out of the compiler's own lexer and, when the
  diagnostics' build is clean, its checker. Comments, literals, numbers,
  keywords and operators are always coloured; **types, functions and
  parameters get their own colours where sema settled the name — and an
  identifier it said nothing about is `variable`, because this server
  does not guess.** With no workspace, a change not yet built, or a file
  with errors, the answer is the lexer's: never grey, never wrong. The
  section below has the argument.

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
`require("zen").filetype()`, `.treesitter()`, `.lsp()`. Both halves work.

**`.lsp()` deliberately declines the server's semantic tokens.** Neovim
paints them above tree-sitter, and tree-sitter's answer needs no build
and no workspace — it is there on the first frame, in any state of
brokenness, where the server's sharper answer arrives with the
diagnostics' build and steps back to lexical the moment the file has
errors. Leaving the server's on would replace a sooner answer with a
later one and repaint the buffer on every settle. Set
`vim.g.zen_semantic_tokens = true` before `setup()` to take the server's
anyway — it now can tell a type from a function, which is the day that
flag was waiting for.

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

If the default `./zen` is not there, `zen` is looked up on the extension
host's `PATH` before anyone is told to go and build something. A
`zen.server.path` you set yourself is reported as written if it misses —
never silently replaced — so a stale setting cannot start a different
binary than the one you asked for.

A server that exits is not restarted on its own; *Zen: Restart Language
Server* (`zen.restartServer`) stops what is left and starts a fresh one
without reloading the window — which is also the way to pick up a binary
you just rebuilt.

Open a `.zen` file, hover over an expression. If anything goes wrong, the
**Zen** output channel says what; set `zen.trace.server` to `verbose` to see
the frames.

### Syntax highlighting in VS Code: from the compiler's lexer, not from a grammar

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
and the server answers it.** `src/lsp/lsp_colour.zen` is the encoder: one
`scan`, a `TokenKind` mapped to a legend index, and the protocol's delta
encoding. The colours come from the compiler's own lexer, so they cannot
disagree with the compiler about what a token is — and no second grammar
and no third generated artifact entered the tree.

**The lexical half needs nothing.** No build, no `Checker`, no workspace,
nothing read from any disk. So unlike hover and diagnostics — which need
a root and about a second — colour appears on an unsaved buffer, in a
folder-less window, and in a file that does not parse. A half-typed
string literal costs the colour of that literal and nothing else.

**What it colours, and what it refuses to.** Comments, string and
character literals, numbers, `true`/`false`/`consume`/`@Self`/`@meta`/
`@scope`, and the operators — always. **Types, functions and parameters
get their own colours where the diagnostics' build settled the name**:
a name that resolved to a struct, enum or alias is `type`, a call that
resolved to a function is `function`, a formal parameter at its
declaration and its uses is `parameter`. That answer is sema's, read off
the checker's memos by `src/lsp/lsp_names.zen` — never a guess from
capitalisation, which would be a second, wrong, specification of what a
name means. **An identifier sema said nothing about is `variable`**: a
local, a field, an import binding, a name in a file whose build has
errors. A wrong answer is worse than none, and a file that does not
compile keeps its lexical colours rather than going grey. Delimiters —
`(`, `)`, `{`, `}`, `,`, `;`, `.`, `:` — are left in your theme's
default foreground for the same reason: a brace is structure and calling
it an operator would be inventing a fact.

What the semantic half does not yet classify, because sema never wrote
the answer down: a function named but not called, a type named in value
position, an enum variant, a constant, a type written inside a struct or
impl body. Those stay `variable` until the memo exists; the list is in
`src/lsp/lsp_names.zen`'s header.

**If a `.zen` file is still grey with the server running**, the cause is
almost certainly not the server: VS Code applies semantic tokens only
when semantic highlighting is on. `editor.semanticHighlighting.enabled`
defaults to `configuredByTheme` and every stock theme enables it, but if
yours does not, set it to `true`. The **Zen** output channel says this at
startup rather than leaving you to find it.

`.zen` files also get bracket matching, comment toggling and correct word
selection from `language-configuration.json` (which is configuration, not
a grammar; its `wordPattern` is copied from the one `identifier` rule in
`grammar/grammar.js`).

**Bracket-pair colorization and bracket-pair guides are defaulted off for
Zen, because with no grammar they cannot be trusted.** Those two features
match the `brackets` from `language-configuration.json` over the *raw
buffer text* — they see every `{` in the file, including the one in a
comment or a string, and paint it as structure. The server does not step
in: `src/lsp/lsp_colour.zen` deliberately emits no semantic tokens for
delimiters (a brace is structure, not an operator), so there is no
colour-token answer to outrank the guess, and the guessing feature wins
by being the only one on the field. Turning the guess *on* would colour a
`{` inside `// {` or `"{"` exactly like a real one, which is a wrong
answer about structure — and this server's position, everywhere else, is
that a wrong answer is worse than none. So `package.json` ships
`configurationDefaults` for `[zen]` setting
`editor.bracketPairColorization.enabled` and `editor.guides.bracketPairs`
to `false`. These are **defaults**, not walls: if you want the guessing
back, set both to `true` in your own settings and the extension will not
argue. The `brackets` in `language-configuration.json` stay — plain
bracket matching and `Ctrl+Shift+\` do not highlight anything, so they
can afford to guess.

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
| `textDocument/semanticTokens/full` | **works** — lexical always; `type`/`function`/`parameter` when the diagnostics' build is clean |
| `textDocument/publishDiagnostics` | **works** — lex, parse and sema, grouped per file, cleared when fixed |
| everything else | **refused by name** with JSON-RPC `-32601` |

"Everything else" is `textDocument/definition`, `documentSymbol`,
`completion`, `references`, `formatting`, `signatureHelp`, `rename`, and
`semanticTokens` in its `range` and `full/delta` shapes. The refusal names
the method and points at `docs/design_lsp.md`. An editor showing "method
not supported" for those is the server being honest, not this
configuration being wrong.

**`range` and `full/delta` are refused ON PURPOSE and are not advertised.**
A client asks for either only when the server said it had it, so the
capability is a bare `full: true`. Advertising one this server does not
answer would produce `-32601` on every colour request, which VS Code
renders as no colour at all with nothing on screen to say why.

**Diagnostics are published, and they are the whole story or none of it.**
Sema's come off the `Checker` the driver hands back; lex's and parse's come
off the build itself. A server showing type errors and silently swallowing
syntax errors would teach you to distrust it, so both go out together.
Every one is severity **Error** — this compiler has one tally and no phase
produces anything a build survives, so there is nothing else to be.

**Hover builds the root, once per hover; a change builds it once too.**
There is no cache, so a hover or an edit in a file that imports most of the
compiler takes about a second on this machine and a leaf module is
imperceptible. `docs/design_lsp.md` §5 says why the debounce it asks for
cannot be written against a blocking read with no clock, and what the two
mitigations that *were* possible are; `docs/PLAN.md:317` names where the
real fix goes if that is not enough.

**A workspace is required for the imported half, and for diagnostics at
all.** The root is computed from the open document — climb out of every
directory that holds its own name — with `initialize`'s `rootUri` as the
floor it may not pass. A client that sends no `rootUri` gets the old
lone-module answer for hover, which is still honest: it types what the file
declares and answers `null` for what it imports. Diagnostics get nothing at
all in that state, because the same lone-module check that makes hover go
quiet would make diagnostics go loud and wrong.

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
- **Diagnostics were driven over a real pipe too**, against a two-module
  project outside the checkout: `didOpen` of a buffer with an unclosed `(`
  came back as one `publishDiagnostics` naming `file:///…/app.zen` with the
  `relatedInformation` intact, a `didChange` closing it came back as the
  same uri with `"diagnostics":[]`, `shutdown` answered, the process exited
  **0** and there was not one byte on stdout that was not a frame. The same
  session and a per-file grouping table are corpus tests —
  `tests/corpus/lsp/diagnostics_publish_and_clear` and
  `diagnostics_are_written_as_the_protocol_spells_them` — and six mutations
  were run against them (drop the parse diagnostics, drop the clearing on
  either of its two routes, drop the note, drop the grouping, drop the
  unchanged-bytes skip). All six went red.
- **Colour was driven over a real pipe, with a REALISTIC `initialize`.**
  Not a minimal one: the probe sends the `capabilities` object VS Code
  sends, including `textDocument.semanticTokens` with its 23 token types,
  10 modifiers, `formats: ["relative"]`, `requests: {range, full: {delta}}`
  and `multilineTokenSupport: false`. That distinction is not pedantry —
  every gate in this repository drives the server directly, which is
  exactly why nine of them could not see that `zen lsp` exited 2 on the
  `--stdio` a real client appends. `zen lsp --stdio` answered
  `initialize` with the legend, answered `semanticTokens/full`, answered
  `shutdown` and exited **0**.
- **The encoding was decoded back and checked by eye**, and then frozen as
  `tests/corpus/lsp/colour_comes_from_the_lexer`, which does the decoding
  inside the test: every five-integer group is added up and handed to
  `to_pos`, so each row prints the bytes it colours. **Ten mutations were
  run against it and nine went red** — `deltaLine` made absolute,
  `deltaStartChar` never relative, two legend indices swapped, the legend
  written out of index order, UTF-16 units counted as bytes, `length`
  taken in bytes, multi-line splitting disabled, zero-length runs emitted,
  `Ident` recoloured, and `range: true` advertised with no handler. The
  tenth is an equivalent mutant and `docs/design_lsp.md` §2 says why.
- **The semantic half is gated the same way.**
  `tests/corpus/lsp/colour_comes_from_the_build` drives a two-module
  project through framed JSON-RPC and pins that a type, a function and a
  parameter come back as three DISTINCT indices, that the answer rides
  the diagnostics' build (no second build beside the tokens request),
  that a file with an undefined name is answered lexically — every
  identifier `variable` — and that fixing it brings the semantic answer
  back. Mutations run against it: parameters recoloured `function`, and
  written types recoloured `variable` — both went red.
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
- **Colour rendering was not eyeballed, in either editor.** The Neovim
  highlighting is verified as *captures produced at the right ranges*, not
  as pixels; which capture group maps to which colour is your
  colourscheme's business. The VS Code colours are verified as *the right
  five-integer groups over a real pipe*, decoded back to the exact bytes
  they cover — but nobody has watched VS Code paint them. **This is the
  five-minute check worth doing**: reload the window with a `.zen` file
  open and comments should go grey, string and character literals should
  take your theme's string colour, numbers its number colour, `true` and
  `@Self` its keyword colour, and — in a file whose build is clean —
  types, functions and parameters should each take their own.
  If instead everything is grey, look at the **Zen** output channel: it
  says whether the server started, and it names
  `editor.semanticHighlighting.enabled` as the setting that discards
  correct tokens without a word.
