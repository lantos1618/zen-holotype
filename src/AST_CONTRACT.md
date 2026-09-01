# AST contract

This document records the invariants shared by the parser, semantic checker,
formatter, language server, `@meta`, and code generator. The declarations in
`src/std/ast` are the source of truth for exact fields and variants; this file
explains the relationships that are not obvious from one declaration alone.

## Module layout

| file | responsibility |
|---|---|
| `ast.zen` | public `std.ast` surface |
| `ast_span.zen` | positions, spans, identifiers, and trivia runs |
| `ast_id.zen` | typed arena identifiers |
| `ast_node.zen` | declarations, members, types, expressions, patterns, and statements |
| `ast_arena.zen` | immutable node and trivia storage |
| `ast_find.zen` | source-position queries |
| `ast_named.zen` | named-node queries used by editor features |

The split is by responsibility. Node declarations remain together because they
form one model: declarations contain expressions, expressions contain types,
types may contain expressions, and statements may contain declarations.

## Node identity and shape

The main node families use a wrapper containing common source information and
a kind enum containing the family-specific payload:

```zen
Expr = {
    kind: ExprKind,
    span: Span,
    leading: TriviaRun,
    trailing: TriviaRun,
}

ExprKind = Name(Name) | Call(Call) | Binary(Binary) | ...
```

This gives every consumer direct access to source information while preserving
typed payloads in matches.

Recursive children are typed identifiers rather than embedded nodes:

- `ExprId`
- `TypeId`
- `PatternId`
- `BlockId`

`Ast` is the only component that resolves those identifiers. The identifiers
are distinct types so an expression cannot accidentally be used where a type is
required. They are stable arena indices and may be used as semantic memo keys.

Declarations, members, statements, arms, arguments, parameters, type
parameters, variants, and import names are stored by value in their parent's
ordered vectors. Their exact fields live in `ast_node.zen` and should not be
duplicated here.

Optional children use `Res<Id>`: `None` means the child was not written.

## Source positions

All AST spans follow the same rules:

- Lines and columns are 1-based.
- Columns count source bytes.
- Spans are half-open: `end` is one byte past the node.
- A span includes the node's delimiters and children but excludes the separator
  following the node.
- A statement span includes its semicolon; its expression span does not.
- Leading trivia is outside the node span.
- A module spans the complete source file.
- File names are relative to the compilation root.

Names use `Ident { text, span }` so diagnostics and editor operations can point
at the name itself. Dotted names use `QualifiedName` with separately located
segments.

Some punctuation needs a span without becoming a node. These fields are part
of the contract:

| field | located syntax |
|---|---|
| `Binary.op_span`, `Unary.op_span` | operator |
| `Index.op_span` | opening `[` |
| `Arm.arrow_span` | `=>` |
| `Match.name_span`, `Try.name_span` | intrinsic name |
| `Function.params_span`, `FnType.params_span`, `Lambda.params_span` | parameter list |
| `Call.args_span`, `FixedArray.args_span`, `Match.arms_span` | argument or arm list |
| `Struct.body_span`, `Impl.body_span` | member body |
| `Enum.leading_bar` | optional leading `|` |

Diagnostics should point at the smallest offending node or token. Consumers
must not substitute a nearby convenience span when a specific field exists.

## Trivia ownership

`Ast.trivia` stores comments and blank-line markers once, in source order. A
node refers to contiguous portions of that list through `leading` and
`trailing` `TriviaRun` values.

- Leading trivia belongs to the outermost node beginning at the following
  token.
- Same-line trailing trivia belongs to the outermost node ending before it.
- Trivia immediately before a closing brace belongs to the enclosed block.
- Remaining end-of-file trivia belongs to the module.

Every trivia item must be owned by exactly one run. The parser establishes that
ownership; formatters and editor features consume it without reassigning it.

## Important syntax distinctions

These forms have dedicated nodes because later phases need their written shape:

- `Paren` preserves explicit parentheses and their span.
- `Try` represents the `.try()` intrinsic rather than an ordinary member call.
- `Match` owns an arm list and is not an ordinary call.
- `Consume` records an explicit move.
- `Bind.target` is an expression, allowing local, field, and index targets.
- `Destructure.binder` is a full pattern, allowing nested patterns.
- A block records whether its final value was written without a semicolon.

The parser does not decide whether a pattern name is a binder or a nullary
variant. That depends on semantic scope and is resolved by sema.

Literal nodes retain their raw source spelling, including quotes and escapes.
The lexer has validated that spelling; preserving it lets the formatter emit
the same bytes.

Union types are stored as a flat member list. `vararg<T>` is an ordinary named
type, while `args: ...` uses the dedicated `Variadic` written-type form.

## Arena behavior

Nodes are appended once and never mutated. Transformations create new nodes and
receive new identifiers. Consequently:

- an identifier always resolves to the same node;
- semantic memos keyed by identifiers remain valid;
- identifier allocation depends on source traversal, not memory addresses;
- emitted output does not depend on allocator addresses.

`expr_at`, `type_at`, `pattern_at`, and `block_at` trap for an invalid
identifier. Such an identifier is an internal compiler error, not recoverable
source input. Operations that may legitimately miss continue to return `Res`.

## Deliberate non-nodes

The AST does not introduce nodes for:

- punctuation that has no independent consumer;
- parameter, argument, arm, or member lists;
- export markers;
- qualified types, because imports bind names locally;
- methods, which are functions stored as members;
- `h.break`, which remains an ordinary call recognized by sema;
- library operations such as `.then`, result hoisting, and loop functions;
- parent pointers;
- inferred types, which belong to sema's identifier-keyed memos.

When a new syntax form is added, update `ast_node.zen`, its parser, source-span
tests, semantic queries, formatter behavior, and this document only if it
changes one of these cross-component contracts.
