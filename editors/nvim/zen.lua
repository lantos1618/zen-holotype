-- editors/nvim/zen.lua
--
-- Zen in Neovim: a filetype, tree-sitter highlighting, and the language
-- server. Copy this file to `~/.config/nvim/lua/zen.lua` and `require("zen")`
-- from your `init.lua`, or paste its body straight in.
--
-- Requires Neovim 0.11 or newer for `vim.lsp.config`/`vim.lsp.enable`. The
-- 0.10-and-earlier route is at the bottom of this file.
--
-- ONE SETTING MATTERS. `M.cmd` below is how the server is launched: the
-- stdio transport has landed, so `zen lsp` with no arguments speaks
-- JSON-RPC over its own stdin/stdout, and this config attaches. What can
-- still be wrong on a new machine is `M.root` — it must point at the
-- checkout this file was copied from.

local M = {}

-- The repository this file was copied out of. Everything below that needs a
-- path off the Zen checkout reads it from here, so there is one place to
-- edit. `vim.env.ZEN_ROOT` wins if it is set.
M.root = vim.env.ZEN_ROOT or vim.fn.expand("~/src/zen")

-- THE SINGLE SETTING. How the language server is launched.
--
-- This is the standard shape: an editor launches a command and speaks
-- JSON-RPC over its stdin and stdout with `Content-Length` framing. It is
-- what `docs/design_lsp.md` §4 specifies and what `docs/design_lsp.md:258`
-- writes verbatim.
--
-- THIS WORKS. `Env` grew a `Stdin` capability, so `zen lsp` with no
-- arguments reads `Content-Length` frames from stdin and writes replies to
-- stdout. The two-FILE form (`zen lsp <requests> <replies>`) still exists
-- because a corpus test cannot hold a pipe open, and both reach the same
-- serve loop — but an editor wants this one.
--
-- WHAT YOU GET: hover, and diagnostics. Everything else comes back
-- `-32601 no handler`.
--
-- COLOUR DOES NOT COME FROM HERE, and this is the one place that is
-- worth restating rather than assuming. The server now answers
-- `textDocument/semanticTokens`, and NOTHING ABOUT THAT CHANGES
-- NEOVIM: colour here comes from tree-sitter, below, over the grammar
-- this repository already ships, and it did so before the server could
-- read a pipe. That answer exists for VS CODE, which cannot load a
-- tree-sitter grammar from an extension and had no colour at all
-- without it.
--
-- AND THE OVERLAY IS TURNED OFF HERE, in `M.lsp()`, which is the one
-- behaviour change the new request forced on this file. Neovim's built-in
-- client requests semantic tokens the moment a server advertises them and
-- paints them ABOVE tree-sitter — 125 against 100 — so leaving it on
-- would replace a query that knows a type by its POSITION with a lexer
-- that cannot tell a type from a variable at all, and every `Vec` and
-- `i32` in the buffer would lose its colour to `@lsp.type.variable`.
-- That is a downgrade bought by a feature, so it is declined: this
-- server's colour exists for VS Code, which has no grammar to lose.
--
-- DIAGNOSTICS ARE REAL NOW, so `:h vim.diagnostic` fills and squiggles
-- appear. Opening or editing a `.zen` file builds the root behind it and
-- publishes what the lexer, the parser and sema found. They are grouped
-- PER FILE, so a mistake in a module you are not looking at underlines
-- that module and not this buffer; a file you have fixed is cleared
-- rather than left underlined; and a parse diagnostic's second position
-- arrives as `relatedInformation`, which Neovim shows in the float.
--
-- They need a workspace. `root_markers` below is what supplies one, and
-- a buffer opened outside any of them gets NO diagnostics on purpose:
-- without a root the only thing the server could check is the file
-- standing alone, which reports every imported name as undefined.
--
-- AND A BUILD RUNS PER CHANGE, so expect a lag while you type in a
-- module that imports most of the compiler — about a second here — and
-- none in a leaf one. There is no timed debounce and there cannot be one
-- yet; see the note at the bottom of this file.
--
-- HOVER answers on an identifier's USE, on a parameter or a local at its
-- DECLARATION, on a written type name, and on a function's name — where
-- it gives the declaration back, `add = (a: i32, b: i32) i32`. With a
-- workspace it answers IMPORTED names too, because the open buffer is
-- checked as part of a build. It answers nothing on a struct's or enum's
-- own name, on a pattern binder, or on anything whose type did not
-- resolve; `null` there means "not known", never "no type".
M.cmd = { M.root .. "/zen", "lsp" }

-- ---------------------------------------------------------------------
-- 1. the filetype
--
-- `.zen` is not a filetype Neovim knows, and nothing below fires without
-- this line.
-- ---------------------------------------------------------------------

function M.filetype()
  vim.filetype.add({ extension = { zen = "zen" } })
end

-- ---------------------------------------------------------------------
-- 2. highlighting, from the grammar that is already in the repository
--
-- `grammar/` is this project's tree-sitter grammar and `docs/PLAN.md:147`
-- says it "outlives the bootstrapper as the editor/LSP grammar". So there
-- is nothing to install from a registry and nothing to write: point Neovim
-- at the shared object `make grammar` builds, and add this directory to
-- the runtimepath so `queries/zen/highlights.scm` is found.
--
-- `make grammar` must have been run — it writes `grammar/zen.so`, which is
-- generated and deliberately not committed (see `.gitignore`).
--
-- Neovim's own tree-sitter runtime and the `--abi 14` the Makefile passes
-- to `tree-sitter generate` agree; this was checked against Neovim 0.12.2.
-- If a future Neovim refuses the ABI, regenerate with a different `--abi`
-- rather than vendoring a second copy of the parser.
-- ---------------------------------------------------------------------

function M.treesitter()
  local so = M.root .. "/grammar/zen.so"
  if vim.fn.filereadable(so) == 0 then
    vim.notify("zen: " .. so .. " missing — run `make grammar` in " .. M.root,
      vim.log.levels.WARN)
    return
  end

  vim.treesitter.language.add("zen", { path = so })

  -- where queries/zen/highlights.scm lives. `:h runtimepath` — a directory
  -- on the runtimepath is searched for `queries/<lang>/<name>.scm`.
  vim.opt.runtimepath:prepend(M.root .. "/editors/nvim")

  vim.api.nvim_create_autocmd("FileType", {
    pattern = "zen",
    callback = function(args)
      pcall(vim.treesitter.start, args.buf, "zen")
    end,
  })
end

-- ---------------------------------------------------------------------
-- 3. the language server
--
-- `root_markers` looks for `build.zen` first because `DESIGN.md` makes a
-- build file a program and `docs/PLAN.md`'s tree puts `build.zen` at the
-- repository root — it is the marker that means "this is a Zen project".
-- `.git` is the fallback for a tree that has not got one yet.
--
-- No `lspconfig`, no plugin. `vim.lsp.config` and `vim.lsp.enable` are
-- built in from 0.11.
-- ---------------------------------------------------------------------

function M.lsp()
  vim.lsp.config("zen", {
    cmd = M.cmd,
    filetypes = { "zen" },
    root_markers = { "build.zen", ".git" },
  })
  vim.lsp.enable("zen")

  -- KEEP TREE-SITTER'S COLOUR, DECLINE THE SERVER'S. See the header: the
  -- server's semantic tokens are LEXICAL, so every identifier comes back
  -- as `variable`, and Neovim paints semantic tokens above tree-sitter.
  -- Left on, `Vec` and `i32` would stop being types on screen.
  --
  -- The capability is dropped rather than the tokens being requested and
  -- discarded: a client that never advertises `semanticTokens` is never
  -- sent them, so this costs one request per buffer rather than hiding
  -- one. Set `vim.g.zen_semantic_tokens = true` to keep them — worth
  -- doing on the day the server tells a type from a function.
  vim.api.nvim_create_autocmd("LspAttach", {
    callback = function(args)
      if vim.g.zen_semantic_tokens then
        return
      end
      local client = vim.lsp.get_client_by_id(args.data.client_id)
      if client and client.name == "zen" then
        client.server_capabilities.semanticTokensProvider = nil
        -- Nil-ing the capability stops FUTURE requests; it does not stop
        -- the engine if Neovim's own LspAttach handler ran first and
        -- already started it. `stop` makes the decline order-independent.
        vim.lsp.semantic_tokens.stop(args.buf, client.id)
      end
    end,
  })
end

function M.setup()
  M.filetype()
  M.treesitter()
  M.lsp()
end

return M

-- ---------------------------------------------------------------------
-- WHAT THE SERVER ANSWERS, so nothing above promises more than it has
--
--   textDocument/hover     the type under the cursor, a declared name's
--                          own type, or a function's signature. `K`.
--   semanticTokens/full    colour, from the lexer — DECLINED HERE, see
--                          `M.lsp()`; tree-sitter's is better
--   publishDiagnostics     lex, parse and sema, grouped per file
--   initialize / shutdown  lifecycle
--   didOpen/didChange/didClose   Full sync, no incremental
--
-- Everything else — definition, documentSymbol, completion, references,
-- formatting, rename — is refused BY NAME with JSON-RPC `-32601`. Neovim
-- surfaces that as "method not supported", which is the honest answer and
-- not a bug in this config.
--
-- WHY DIAGNOSTICS LAG YOUR TYPING, and why there is no setting for it.
-- The server marks a document changed and builds at the next point where
-- it has answered everything that had arrived. That collapses a batch of
-- changes into one build and means a superseded build never starts — but
-- over a pipe the reader holds one message at a time, so in practice it
-- is one whole-program build per keystroke. A timed debounce is what
-- `docs/design_lsp.md` §5 asks for and it cannot be written yet: the
-- server is single-threaded, its read blocks, and there is no clock, so
-- it has no way to notice that you have stopped typing. What it does do
-- is skip a change that carries bytes the buffer already held.
--
-- POSITION ENCODING. Neovim advertises `utf-8` among its
-- `general.positionEncodings`, and this server does not claim it — it sends
-- no `positionEncoding` in its capabilities, which per the specification
-- means UTF-16. That is deliberate: `src/lsp/lsp_pos.zen` converts, and a
-- client that short-circuits to bytes never exercises the conversion. If
-- you are testing that code, test it from VS Code, which cannot speak
-- anything but UTF-16.
--
-- RESTARTING. Neovim reuses a client with the same name and root, so a
-- server that crashed is silently not restarted. `:LspRestart` if you have
-- a plugin providing it, otherwise `:lua vim.lsp.stop_client(vim.lsp.get_clients())`
-- and reopen the buffer.
--
-- ---------------------------------------------------------------------
-- NEOVIM 0.10 AND EARLIER — no `vim.lsp.config`, so start it by hand:
--
--   vim.api.nvim_create_autocmd("FileType", {
--     pattern = "zen",
--     callback = function(args)
--       vim.lsp.start({
--         name = "zen",
--         cmd = { "zen", "lsp" },
--         root_dir = vim.fs.root(args.buf, { "build.zen", ".git" }),
--       }, { bufnr = args.buf })
--     end,
--   })
--
-- This is `docs/design_lsp.md:255`'s snippet unchanged. It is equivalent;
-- `vim.lsp.enable` is the newer spelling of the same autocmd.
-- ---------------------------------------------------------------------
