; editors/nvim/queries/zen/highlights.scm
;
; Highlighting for Zen in Neovim, as a QUERY over grammar/grammar.js.
;
; This file is not a grammar and must never become one. `docs/PLAN.md:137`
; is explicit — "Never a second parser, never a second AST ... Two grammars
; is the failure this plan exists to avoid" — and `docs/PLAN.md:147` says
; the tree-sitter grammar "outlives the bootstrapper as the editor/LSP
; grammar". A query names nodes the one grammar already produces; it cannot
; disagree with it about what parses, only about what colour something is.
;
; Every node name and every field name below is read off `grammar/grammar.js`.
; If a rule there is renamed, this file goes stale loudly (the query fails to
; compile and Neovim says which line), not silently.
;
; PRECEDENCE: Neovim resolves overlapping captures on the same node in favour
; of the LAST matching pattern in the file. So the general case is written
; first and the specific case after it — `member_expression` property as a
; field, then the same property as a method call. Reordering this file
; changes its output.

; ---------------------------------------------------------------------
; comments and literals
; ---------------------------------------------------------------------

(line_comment) @comment
(block_comment) @comment

(string_literal) @string
(char_literal) @character
(number_literal) @number
(boolean_literal) @boolean

; ---------------------------------------------------------------------
; operators and punctuation
;
; Matched THROUGH THE `operator` FIELD rather than by listing the tokens.
; The token list is the obvious way to write this and it is wrong twice in
; this grammar: `*` is both multiplication (D1) and the export marker (law
; 6), and `<` `>` are both comparison and the brackets of `Vec<T>`. A field
; says which one is meant; a bare token cannot.
;
; `+ - *` trap on overflow and `+% -% *%` wrap — the same operation with a
; different overflow rule, so one colour covers both.
; ---------------------------------------------------------------------

(binary_expression operator: _ @operator)
(unary_expression operator: _ @operator)
(declaration operator: _ @operator)
(declaration_statement operator: _ @operator)
(let_statement operator: _ @operator)
(member_declaration operator: _ @operator)
(record_field operator: _ @operator)
(member_declaration mutability: _ @punctuation.delimiter)
(parameter mutability: _ @punctuation.delimiter)
(match_arm "=>" @operator)

[ "." "," ";" ] @punctuation.delimiter
[ "(" ")" "[" "]" "{" "}" ] @punctuation.bracket
(type_parameters [ "<" ">" ] @punctuation.bracket)
(type_arguments [ "<" ">" ] @punctuation.bracket)

; `|` separates enum variants (R1) and builds an anonymous union in type
; position (D3). One token, one meaning per position, one colour.
"|" @punctuation.delimiter

; ---------------------------------------------------------------------
; the three-entry `@` namespace, and the one word that is a keyword
;
; Zen has almost no keywords: `consume`, `true`, `false`, and `@Self` /
; `@meta` / `@scope`, which are tokens rather than identifiers precisely so
; no user binding can collide with one.
; ---------------------------------------------------------------------

"consume" @keyword.operator
"@meta" @function.macro
(self_type) @type.builtin
(scope_expression) @variable.builtin
(inferred_type) @type.builtin
(variadic_type) @punctuation.special

; `*` — "this name crosses a module boundary", law 6. It is the single most
; load-bearing character in a Zen declaration and it should be visible.
(export_marker) @attribute

; ---------------------------------------------------------------------
; types
;
; A type is a bare identifier in this grammar — there is no qualified type,
; because imports bind locally. So a name is a type when it stands in a
; type POSITION, and every such position is a named field.
; ---------------------------------------------------------------------

(generic_type name: (identifier) @type)
(type_arguments (identifier) @type)
(type_parameter name: (identifier) @type.definition)
(type_bound (identifier) @type)

(declaration type: (identifier) @type)
(let_statement type: (identifier) @type)
(member_declaration type: (identifier) @type)
(parameter type: (identifier) @type)
(typed_meta_argument type: (identifier) @type)
(function return_type: (identifier) @type)
(function_signature return_type: (identifier) @type)
(array_type element: (identifier) @type)
(variant_payload type: (identifier) @type)
(union_type left: (identifier) @type)
(union_type right: (identifier) @type)

; `Circle.impl(Rect, { .. })` — D16. Both names are types and `impl` is the
; method that declares.
(impl_declaration
  target: (identifier) @type
  method: (identifier) @function.method.call
  trait: (identifier) @type)

; ---------------------------------------------------------------------
; declarations
;
; `R1a`: what a declaration declares is read off the SHAPE OF ITS VALUE, so
; that is what these patterns match on. A declaration whose value is neither
; a function nor a type body is deliberately left alone rather than guessed
; at — `json_pkg = Package(url: "..")` is a module constant and colouring it
; as a function would be a lie the grammar does not tell.
; ---------------------------------------------------------------------

(declaration
  name: (declaration_name name: (identifier) @function)
  value: [(function) (function_signature)])

(declaration_statement
  name: (declaration_name name: (identifier) @function)
  value: [(function) (function_signature)])

(declaration
  name: (declaration_name name: (identifier) @type)
  value: [(struct_body) (enum_body) (generic_type)])

(declaration_statement
  name: (declaration_name name: (identifier) @type)
  value: [(struct_body) (enum_body)])

(enum_variant name: (identifier) @constructor)

(member_declaration
  name: (declaration_name name: (identifier) @variable.member))

(member_declaration
  name: (declaration_name name: (identifier) @function.method)
  value: [(function) (function_signature)])

(record_field
  name: (declaration_name name: (identifier) @variable.member))

(record_field
  name: (declaration_name name: (identifier) @function.method)
  value: [(function) (function_signature)])

; ---------------------------------------------------------------------
; parameters, fields, calls
; ---------------------------------------------------------------------

(parameter name: (identifier) @variable.parameter)
(named_argument name: (identifier) @variable.parameter)
(typed_meta_argument name: (identifier) @variable.parameter)

(member_expression property: (identifier) @variable.member)

; UFCS: `x.f(a)` "never names `f`" as a bare name (DESIGN.md:394), so the
; only place a method call is visible is here — and it must come after the
; plain-field pattern above, since both match the same identifier.
(call_expression
  function: (member_expression property: (identifier) @function.method.call))

(call_expression
  function: (identifier) @function.call)

; ---------------------------------------------------------------------
; patterns
;
; `Left(Blank)` and `Ok(n)` are the same three tokens and whether the inner
; name binds a payload or names a variant is a question about scope — which
; is sema's, not a highlighter's. So the OUTER name is a constructor and the
; inner one is left uncoloured rather than guessed.
; ---------------------------------------------------------------------

(wildcard_pattern) @character.special
(destructure_pattern name: (path_pattern) @constructor)
(match_arm pattern: (path_pattern) @constructor)

(ERROR) @error
