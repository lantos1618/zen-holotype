" Vim ftplugin for Zen (zen-lang). Install: copy editor/vim/* into ~/.vim/ (or your runtimepath).
if exists("b:did_ftplugin") | finish | endif
let b:did_ftplugin = 1

" `gc`/`gcc` and every commenting plugin read this; empty means Neovim reports
" "Option 'commentstring' is empty" and leaves the line untouched.
setlocal commentstring=//\ %s
" line comments, plus the lexer's nested block comments
setlocal comments=s1:/*,mb:*,ex:*/,://

" `zen fmt` emits 4-space indents; match it so hand-typed code survives a format pass.
setlocal expandtab
setlocal shiftwidth=4
setlocal softtabstop=4
setlocal tabstop=4

" `gf` on a bare module path opens the .zen file
setlocal suffixesadd=.zen

let b:undo_ftplugin = "setlocal commentstring< comments< expandtab< shiftwidth< softtabstop< tabstop< suffixesadd<"
