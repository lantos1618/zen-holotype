" Vim syntax for Zen (zen-lang). Install: copy editor/vim/* into ~/.vim/ (or your runtimepath).
if exists("b:current_syntax") | finish | endif

syn keyword zenKeyword return match loop impl
syn match   zenAtWhile "@while"
syn keyword zenType i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 bool void Self Ptr MutPtr RawPtr Vec Opt Result
syn keyword zenType StringLiteral StringView StringCstr String
syn keyword zenBool true false
syn match   zenDecl "^[A-Za-z_][A-Za-z0-9_]*\*\?\ze\s*[:=]"
syn match   zenVariant "\.\zs[A-Z][A-Za-z0-9_]*"
syn match   zenNumber "\<\d\+\>"
syn match   zenNumber "\<0x[0-9A-Fa-f]\+\>"
syn match   zenChar "'\\\?.'"
" a raw literal `"""…"""` spans lines and honours no escapes — declared first so the
" three-quote open wins over the empty-string reading of the first two quotes.
syn region  zenRawString start=+"""+ end=+"""+ keepend
syn region  zenString start=+"+ skip=+\\"+ end=+"+
syn match   zenComment "//.*$"
syn match   zenOperator ":=\|=>\|==\|!=\|<=\|>=\|&&\|||\|<<\|>>"
syn match   zenOperator "[|&^~]"

hi def link zenKeyword  Keyword
hi def link zenAtWhile  Repeat
hi def link zenType     Type
hi def link zenBool     Boolean
hi def link zenDecl     Function
hi def link zenVariant  Constant
hi def link zenNumber   Number
hi def link zenChar     Character
hi def link zenString   String
hi def link zenRawString String
hi def link zenComment  Comment
hi def link zenOperator Operator

let b:current_syntax = "zen"
