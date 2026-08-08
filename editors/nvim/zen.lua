-- editors/nvim/zen.lua
--
-- Zen in Neovim: a filetype, tree-sitter highlighting, and the language
-- server. Copy this file to `~/.config/nvim/lua/zen.lua` and `require("zen")`
-- from your `init.lua`, or paste its body straight in.
--
-- Requires Neovim 0.11 or newer for `vim.lsp.config`/`vim.lsp.enable`. The
-- 0.10-and-earlier route is at the bottom of this file.
--
-- ONE SETTING MATTERS. `M.cmd` below is how the server is launched, and it
-- is the only line that changes when the stdio transport lands. Read
-- `editors/README.md` before assuming it works — as of this commit the
-- server cannot be spoken to over a pipe, and this config will fail to
-- attach. The highlighting half works today regardless of the server.

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
-- IT DOES NOT WORK YET, and the reason is one missing capability rather
-- than a missing server: `Env` has `argv, vars, out, mem, fs, net, threads`
-- (`src/std/env/env.zen:147`) and nothing that reads a byte stream, so
-- `zen lsp` today takes two FILE arguments instead of a pipe. Run
-- `zen lsp` with no arguments and it says so. Until that lands, Neovim will
-- report the server exiting immediately; see `editors/README.md`.
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
--   textDocument/hover     the type under the cursor. `K` in Neovim.
--   initialize / shutdown  lifecycle
--   didOpen/didChange/didClose   Full sync, no incremental
--
-- Everything else — definition, documentSymbol, completion, references,
-- formatting, rename — is refused BY NAME with JSON-RPC `-32601`. Neovim
-- surfaces that as "method not supported", which is the honest answer and
-- not a bug in this config.
--
-- There are no diagnostics yet either: sema's are values but lex's and
-- parse's are printed and dropped by the driver, and half a diagnostics
-- story is worse than none. So `:h vim.diagnostic` will stay empty.
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
