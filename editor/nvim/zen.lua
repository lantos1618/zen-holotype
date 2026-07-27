-- editor/nvim/zen.lua — the Neovim side of `zen lsp`, as one sourceable file.
--
--   vim.g.zen_lsp = { cmd = { "/path/to/zen/zen", "lsp" } }
--   dofile("/path/to/zen/editor/nvim/zen.lua")
--
-- Loading it installs a FileType=zen autocmd that starts the server, and an LspAttach autocmd that
-- installs the buffer-local motions below. It returns a table, so `require("zen")` works too when
-- this directory is on the runtimepath; `M.setup{...}` re-installs with different options.
--
-- The motions, and what each is answered by:
--   gd       textDocument/definition
--   K        textDocument/hover
--   gO       textDocument/documentSymbol   (the outline, in the location list)
--   ]m / [m  textDocument/documentSymbol   (next/previous FUNCTION-or-METHOD symbol)
--
-- `]m`/`[m` are Vim's method motions. They are normally tree-sitter or `{`-heuristic driven; Zen has
-- no tree-sitter grammar, so they are driven here by the SAME symbol list `gO` shows — which is the
-- compiler's own parse of the buffer, hoisted methods un-mangled back to the name the source writes.

local M = {}

local SK_METHOD = 6
local SK_FUNCTION = 12

local defaults = {
  cmd = { "zen", "lsp" },
  root_markers = { ".git", "driver.zen", "build.zen" },
  keymaps = true,
}

-- LSP `character` is a UTF-16 code-unit offset; a cursor column is a byte offset.
local function byte_col(bufnr, lnum, character)
  local line = vim.api.nvim_buf_get_lines(bufnr, lnum, lnum + 1, false)[1] or ""
  local ok, col = pcall(vim.str_byteindex, line, "utf-16", character, false)
  if ok then
    return col
  end
  ok, col = pcall(vim.str_byteindex, line, character, true)
  if ok then
    return col
  end
  return math.min(character, #line)
end

-- flatten a documentSymbol reply into { line, character } marks for the kinds we jump to. Handles
-- both reply shapes: DocumentSymbol[] (nested, `selectionRange`) and SymbolInformation[] (flat,
-- `location.range`), so this keeps working against a server that answers the other one.
local function collect(node, kinds, out)
  for _, sym in ipairs(node or {}) do
    local range = sym.selectionRange or sym.range or (sym.location or {}).range
    if range and kinds[sym.kind] then
      out[#out + 1] = range.start
    end
    collect(sym.children, kinds, out)
  end
  return out
end

-- every function/method symbol of the current buffer, in source order.
local function method_marks(bufnr)
  local params = { textDocument = vim.lsp.util.make_text_document_params(bufnr) }
  local res = vim.lsp.buf_request_sync(bufnr, "textDocument/documentSymbol", params, 1000)
  local marks = {}
  for _, r in pairs(res or {}) do
    collect(r.result, { [SK_FUNCTION] = true, [SK_METHOD] = true }, marks)
  end
  table.sort(marks, function(a, b)
    if a.line ~= b.line then
      return a.line < b.line
    end
    return a.character < b.character
  end)
  return marks
end

-- jump to the next (dir 1) or previous (dir -1) function/method symbol, `count` times.
function M.goto_method(dir, count)
  local bufnr = vim.api.nvim_get_current_buf()
  local marks = method_marks(bufnr)
  if #marks == 0 then
    return
  end
  local cur = vim.api.nvim_win_get_cursor(0)
  local line, char = cur[1] - 1, cur[2]
  local target
  for _ = 1, math.max(count or 1, 1) do
    target = nil
    for i = 1, #marks do
      local m = dir > 0 and marks[i] or marks[#marks + 1 - i]
      local after = m.line > line or (m.line == line and m.character > char)
      local before = m.line < line or (m.line == line and m.character < char)
      if (dir > 0 and after) or (dir < 0 and before) then
        target = m
        break
      end
    end
    if not target then
      break
    end
    line, char = target.line, target.character
  end
  if target then
    vim.cmd("normal! m'") -- the jumplist entry, so `` gets you back
    vim.api.nvim_win_set_cursor(0, { target.line + 1, byte_col(bufnr, target.line, target.character) })
  end
end

function M.attach_keymaps(bufnr)
  local function map(lhs, rhs, desc)
    vim.keymap.set("n", lhs, rhs, { buffer = bufnr, silent = true, desc = desc })
  end
  map("gd", vim.lsp.buf.definition, "zen: go to definition")
  map("K", vim.lsp.buf.hover, "zen: hover")
  map("gO", vim.lsp.buf.document_symbol, "zen: document symbols")
  map("]m", function()
    M.goto_method(1, vim.v.count1)
  end, "zen: next function/method")
  map("[m", function()
    M.goto_method(-1, vim.v.count1)
  end, "zen: previous function/method")
  vim.bo[bufnr].omnifunc = "v:lua.vim.lsp.omnifunc"
end

function M.setup(opts)
  local cfg = vim.tbl_deep_extend("force", defaults, vim.g.zen_lsp or {}, opts or {})
  local group = vim.api.nvim_create_augroup("zen_lsp", { clear = true })
  vim.api.nvim_create_autocmd("FileType", {
    group = group,
    pattern = "zen",
    callback = function(args)
      vim.lsp.start({
        name = "zen-lsp",
        cmd = cfg.cmd,
        cmd_env = cfg.cmd_env,
        -- imports resolve relative to each file's own directory, so root detection is forgiving.
        root_dir = vim.fs.root(args.buf, cfg.root_markers) or vim.fn.getcwd(),
      })
    end,
  })
  if cfg.keymaps then
    vim.api.nvim_create_autocmd("LspAttach", {
      group = group,
      callback = function(args)
        local client = vim.lsp.get_client_by_id(args.data.client_id)
        if client and client.name == "zen-lsp" then
          M.attach_keymaps(args.buf)
        end
      end,
    })
  end
  return M
end

M.setup()

return M
