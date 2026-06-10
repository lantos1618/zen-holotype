" Vim syntax for Zen (zen-lang). Install: copy editor/vim/* into ~/.vim/ (or your runtimepath).
if exists("b:current_syntax") | finish | endif

syn keyword zenKeyword return match loop impl break continue
syn match   zenAtWhile "@while"
syn keyword zenType i32 i64 u8 bool str void Self Ptr MutPtr RawPtr Vec Opt Result String
syn keyword zenBool true false
syn match   zenDecl "^[A-Za-z_][A-Za-z0-9_]*\*\?\ze\s*[:=]"
syn match   zenVariant "\.\zs[A-Z][A-Za-z0-9_]*"
syn match   zenNumber "\<\d\+\>"
syn match   zenNumber "\<0x[0-9A-Fa-f]\+\>"
syn match   zenChar "'\\\?.'"
syn region  zenString start=+"+ skip=+\\"+ end=+"+
syn match   zenComment "//.*$"
syn match   zenOperator ":=\|=>\|==\|!=\|<=\|>=\|&&\|||\|<<\|>>"

hi def link zenKeyword  Keyword
hi def link zenAtWhile  Repeat
hi def link zenType     Type
hi def link zenBool     Boolean
hi def link zenDecl     Function
hi def link zenVariant  Constant
hi def link zenNumber   Number
hi def link zenChar     Character
hi def link zenString   String
hi def link zenComment  Comment
hi def link zenOperator Operator

let b:current_syntax = "zen"
