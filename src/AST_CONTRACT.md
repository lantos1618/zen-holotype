# The AST contract

Frozen so the lexer, parser, sema and `gen_c` can be built against it in
parallel, without reading `src/std/ast/`. `PLAN.md` calls `src/std/ast/ast.zen` the keystone:
one AST with three consumers — the compiler, `@meta` and `gen_c` — and `@meta`
returning these exact node types is what makes stage 5 free rather than a
parallel universe.

**Nothing here is Zen's design.** `docs/DESIGN.md` is the law. Where they
disagree, the design wins and this file is the bug. `bootstrap/CONTRACT.md` is
the Python bootstrapper's AST — prior art, not a spec, and the deliberate
divergences from it are listed at the end.

---

## Layout

```
src/std/ast/ast.zen         the module surface: starred re-exports, nothing else
src/std/ast/ast_span.zen    where a node is: Pos, Span, Trivia, TriviaRun, Ident
src/std/ast/ast_id.zen      how a node is named: ExprId, TypeId, PatternId, BlockId
src/std/ast/ast_node.zen    what a node is: every form
src/std/ast/ast_arena.zen   where nodes live: Ast
```

`src/std/ast/ast.zen` is module `std.ast` — a folder carries its root beside its
children, so this is the same module path `src/std/ast.zen` would have been, and
every reference to it in `DESIGN.md` and `PLAN.md` still reads correctly.

It is a folder because the node set alone is 650 lines and the whole is over
900: `STYLE.md` fails the build past 800 and asks for a justification past 500.
The split is by subject and the three subjects are the three lines above.

**`ast_node.zen` is one file, and the reason first given for it was wrong.**
Declarations hold expressions, expressions hold types, a type holds an
expression (`[u8, i32.BITS]`), a block holds statements and a statement holds a
declaration — one strongly-connected component, certainly. But the claim that
followed, that module cycles are a compile error, is **false**:
`bootstrap/modules.py` says the opposite in as many words, and gives this
language's own example — "`std.core.display` needing `String` while `std.text`
wants `Display` is a real cycle and a legal one". An import cycle is not a
problem a whole-program compiler has.

So the file could be split by category and would compile. It is one file
because the subjects genuinely are one subject, which is STYLE.md's actual
rule — split by subject, never by size — and not because the compiler forbids
the alternative. The two genuinely lower layers were lifted out and the rest
was not; that judgement stands on its own, and anyone who disagrees with it
should know they are free to act.

---

## The shape, in four rules

**1. A node is a wrapper struct plus a kind enum.**

```groovy
Expr* = { kind*: ExprKind, span*: Span, leading*: TriviaRun, trailing*: TriviaRun }
ExprKind* = Name(Name) | Call(Call) | Binary(Binary) | ..
```

So `e.span` needs no match, and `e.kind.match({ Binary(b) => .. })` binds the
typed node in the arm. This is the shape `DESIGN.md`'s `DumpAst` is already
written against — "the kind is an ordinary enum carrying the node as payload, so
the arm BINDS the typed node and overload resolution just works".

Six families are shaped this way: `Type`, `Pattern`, `Expr`, `Stmt`, `Decl`,
`Member`. `Block`, `Module`, and the leaves (`Arg`, `Arm`, `Param`, `TParam`,
`Variant`, `ImportName`) carry `span`/`leading`/`trailing` directly and have no
kind.

**2. A child node is an id, never a value.**

`ExprId`, `TypeId`, `PatternId`, `BlockId`, each `{ index*: u32 }`. `Ast` is the
only thing that turns one back into a node.

Two reasons, and only the first is about layout. An `Expr` containing an `Expr`
has no size, so recursion needs *some* indirection. And `DESIGN.md` decision 3
says sema is memoized queries — `type_of(node)` — which means a node reference
is a `Map` key and must be `Eq + Hash`. A tree of values has no identity at all
and `Ptr<T>` exports none, so an id is the only shape in which that law can be
obeyed. All four id types impl `Eq` and `Hash` here.

The index is a `u32` because `std.core.num` carries only lossless conversions,
and `u32` is the widest integer with both `to_usize` (to index the arena) and
`to_u64` (to hash). Four billion nodes.

Optional children are `Res<TypeId>` and friends: `None` means absent. That is
`Res<T>` doing its ordinary job — absence carries no reason, because there is
none to carry.

**3. Only four families are arena'd.** Declarations, members, arms, arguments,
parameters, type parameters, variants, import names and statements are held **by
value** inside their parent's `Vec`, because none of them closes a cycle. If you
have a `Decl`, you have the whole declaration; if you have an `ExprId`, you need
the `Ast`.

**4. Trivia lives in one list, and a node names a run of it.**

`Ast.trivia` holds every comment and blank in the compilation in source order.
A node carries `leading` and `trailing`, each a `TriviaRun { at, len }`. `len`
of 0 is no trivia, which is almost every node.

This is two words per node. Two `Vec<Trivia>` would be sixteen — a `Vec` is eight
words here, because the `Alloc` it grows through is a fat value — paid on every
node in the tree to describe something almost no node has.

---

## Spans

`tests/corpus/parse/POSITIONS.md` is the authority and every one of its rows is
representable. The conventions it fixes:

- Lines and columns are **1-based**; a column counts **bytes**.
- A span is `start..end`, **half-open**: `end` is one past the last byte.
- A span **includes** the node's own delimiters and all its children, and
  **excludes** the separator that follows it. The comma after a field belongs to
  the field list, not to the field.
- A **statement's** span includes its `;`. The expression inside it does not:
  `Ok(0);` is `25:5..25:11`, `Ok(0)` is `25:5..25:10`.
- A node's span does **not** include its leading trivia.
- `Module.span` is the whole file, `1:1` to one past the last byte — trivia
  included, because there is nothing outside it for the trivia to be beside.

`Span` carries `file`, relative to the compilation root, always. An absolute
path makes two checkouts of one tree emit different bytes, and traps print it.

**Spans POSITIONS.md demands that are not nodes.** A token is not a node, but
some tokens need locating anyway, and each of these is a named field rather than
a node:

| field | token | why it is load-bearing |
|---|---|---|
| `Binary.op_span`, `Unary.op_span` | the operator | a trap prints `file:line:col` and `DESIGN.md` fixes that position as the operator token |
| `Arm.arrow_span` | `=>` | the formatter aligns arms on it |
| `Match.name_span` | `match` | kept for `fmt` and the LSP; **not** where "is not exhaustive" points — see below |
| `Function.params_span`, `FnType.params_span`, `Lambda.params_span` | `( .. )` | wrap-or-not is a decision about the whole list |
| `Match.arms_span`, `Call.args_span`, `FixedArray.args_span` | `{ .. }` / `( .. )` | same |
| `Struct.body_span`, `Impl.body_span` | `{ .. }` | a struct body holds members, not statements, so it is not a `Block` and has no span of its own otherwise |
| `Enum.leading_bar` | `\|` of the one-variant form | `Res<Span>`: present or not, and where |

**"is not exhaustive" points at the whole match expression, not at the `match` token.** An earlier version of this table said the opposite and it was wrong: every `tests/must-fail/sema/match_*` test asserts the receiver's position, and `TESTING.md` requires "the first byte of the smallest offending node". The offending node is the match expression, whose first byte is the receiver's — `s.match({` at column 5 is asserted as `9:5`, and `(n == 0).match({` as `8:5`, the `(`. `name_span` still exists because `fmt` and the LSP want the keyword; no diagnostic uses it.

Every **name** is an `Ident { text, span }` rather than a bare `str`, because
rename, go-to-definition and "no such field" all point at the name and not at
the node containing it. A dotted name — `std.core.result`, `Shape.Unit` — is a
`QualifiedName { segments, span }`.

---

## Who owns a piece of trivia

The parser decides this once; everything downstream just reads it.

- **Leading**: the run gathered before a node's first token, owned by the
  **outermost** node that begins at that token. `POSITIONS.md` row 2 is the
  case: the three comment lines at the top of the file are the leading trivia of
  the `Point` *declaration*, not of its name and not of the module.
- **Trailing**: the run between a node's last token and the next newline, owned
  by the outermost node whose span ends before it on that line. `x: i32, // the x`
  belongs to the field.
- **End of file**: `Module.trailing`. It has nowhere else to go, and a formatter
  that drops it fails its own round trip.

The protocol for building a run, and it is the whole of it:

```groovy
mark = tree.trivia_mark();
tree.add_trivia(item).try();      // once per piece, in source order
run = tree.trivia_run(mark);
```

A run must be contiguous, which is why the mark exists. `no_trivia()` is the
empty run.

---

## The node table

Fields are listed in declaration order. `Res<X>` means optional.

### Declarations — `Decl { kind, span, leading, trailing }`

| `DeclKind` | fields | notes |
|---|---|---|
| `Struct(Struct)` | `name, exported, tparams, members, body_span` | |
| `Enum(Enum)` | `name, exported, tparams, variants, leading_bar` | |
| `Alias(Alias)` | `name, exported, tparams, target` | `Alias = Shape` binds `Alias` to `Shape` **itself**; sema resolves it away |
| `Function(Function)` | `name, exported, form, tparams, params, params_span, ret, body` | |
| `Impl(Impl)` | `target, bound, members, body_span` | `Circle.impl(Rect, {..})`: `target` is `Circle` (an `Ident`, never qualified — an impl lives in its target's module, so there are no orphan impls), `bound` is the type `Rect` |
| `Import(Import)` | `names, module` | `Res*, Ok* = std.core.result` |
| `Const(Const)` | `name, exported, mutable, type, value` | a module-level value binding |

`Import` is a `DeclKind` and not a second list on `Module`, so `Module.decls` is
the file in source order. A formatter that has to merge two lists back into one
order will get it wrong once.

**`Function.form`** is `DESIGN.md`'s method table, verbatim:

| form | written | body |
|---|---|---|
| `Required` | `= sig` | none |
| `Sealed` | `= sig {..}` | yes |
| `Default` | `::= sig {..}` | yes |
| `Hook` | `::= sig` | none |

A plain top-level function with a body is `Sealed`. `form` and `body` are not
redundant: `form` records whether `=` or `::=` was written.

**`Function.ret` is optional** because a lambda may omit it and mean `()`. A
*declaration* must write one — law 6 at a module boundary, grammar D15a inside
one — and that is sema's rule, not a shape.

### Members — `Member { kind, span, leading, trailing }`

What a **struct body**, an **impl body** and a **record literal** are all made
of. One node for the three, because `DESIGN.md` has one rule for them: "a struct
whose fields happen to be functions, used as a bound, is what other languages
call a trait — nothing marks it special".

| `MemberKind` | fields |
|---|---|
| `Field(Field)` | `name, exported, mutable, type, value` |
| `Const(Const)` | `name, exported, mutable, type, value` |
| `Function(Function)` | as above |

**The Field/Const split is syntactic, and it is the grammar's R4:** inside a
**struct body**, `name: T = value` (immutable, with a value) is a constant — one
value per type — and `name :: T = value` (mutable, with a value) is a field with
a default. `Const` therefore **never** appears in an impl body or a record
literal, where `name: value` supplies a field and is a `Field` with no type.

The parser applies R4 in one place so nothing downstream has to remember it.
The residue — **an immutable field with a default is unspellable** — is now a
decision and not a hole: `DESIGN.md`'s "Declarations" section states R4 and
prices it, which is what this file asked for.

### Types — `Type { kind, span, leading, trailing }`

| `TypeKind` | fields | source |
|---|---|---|
| `Named(Named)` | `name, args` | `i32`, `Vec<T>`, `Map<K, V>` |
| `Union(Union)` | `members` | `A \| B` |
| `Fn(FnType)` | `tparams, params, params_span, ret` | `(a: i32, b: i32) i32` |
| `Array(ArrayType)` | `elem, count` | `[u8, 64]`, `[u8, i32.BITS]` |
| `Unit` | | `()` |
| `SelfType` | | `@Self` |
| `Infer` | | the `_` of `Res<Cfg, _>` |
| `Variadic` | | the `...` of `args: ...` |

**`vararg<T>` IS NOT A `TypeKind`, and that is the design.** It is an ordinary
`Named` applied to one argument, resolving to an ordinary declared struct
(`std/collections/collections_vararg.zen`), so the parser, the type store and
the layout have no case for it at all — only a CALL does. `sema_vararg.zen` owns
what it may be written next to; `docs/design_vararg.md` owns why.

`Union` is **flat**: `A | B | C` is one `Union` of three members, never a
`Union` of a `Union`. Error-set merging is then a concatenation and set equality
is not a tree walk.

There is **no qualified type**. Imports bind locally, so a type is always
reachable by a bare name; `std.core.Res` is a design change, not a missing node.

`FnType.params` names every parameter, exactly as a declaration does —
`(i32, i32) i32` says nothing about which `i32` is which. Names are
documentation: two `FnType`s differing only in parameter names are one type and
declaring both is an error at the declaration site.

### Expressions — `Expr { kind, span, leading, trailing }`

| `ExprKind` | fields | source |
|---|---|---|
| `Name(Name)` | `text` | a bare identifier |
| `Literal(Literal)` | `kind, text` | |
| `Unit` | | `()` |
| `SelfType` | | `@Self` in value position |
| `Scope` | | `@scope` |
| `Meta(Meta)` | `value, name, type` | `@meta(n)` / `@meta(self: @Self)` |
| `Paren(Paren)` | `inner` | `(n == 0)` |
| `Array(ArrayLit)` | `elems` | `[0, 1, 2]` |
| `FixedArray(FixedArray)` | `type, elems, args_span` | `[i32, 4](2, 3, 5, 7)` |
| `Lambda(Lambda)` | `tparams, params, params_span, ret, body` | |
| `Call(Call)` | `callee, targs, args, args_span` | |
| `Match(Match)` | `scrutinee, name_span, arms, arms_span` | |
| `Try(Try)` | `operand, name_span` | `.try()` |
| `Record(Record)` | `entries` | `{ src: Path(..), deps: [..] }` |
| `Access(Access)` | `base, name` | `p.x`, `Shape.Unit`, `i32.MAX` |
| `Index(Index)` | `base, index, op_span` | `buf[i]` |
| `Unary(Unary)` | `op, op_span, operand` | |
| `Binary(Binary)` | `op, op_span, lhs, rhs` | |
| `Consume(Consume)` | `operand` | `consume f` |
| `Block(BlockId)` | | a block in value position |

`Literal.text` is the **raw source slice** — quotes, escapes and all, exactly as
written. The formatter reprints it byte for byte, so decoding here would make
`"\n"` and a literal newline indistinguishable on the way out. The lexer has
already rejected an unknown escape, a leading zero and a multi-byte char
literal, so decoding is total by the time sema wants it.

`Paren` is a node because `POSITIONS.md` asserts a span for it, and because a
formatter re-deriving parentheses from precedence is a formatter that will
eventually print `a + b * c` for `(a + b) * c`.

`Try` is **not** a `Call`. `DESIGN.md` makes `.try()` the non-local-exit
intrinsic: there is no `try` field on `Res` and no function of that name, so
parsing it as a call creates a name that must be special-cased everywhere it
could be shadowed. `h.break(v)` is the opposite call: it *is* a `Call`, and sema
recognises it.

`Match` is **not** a `Call` either, even though `DESIGN.md` says match "is a
method". Its argument is an arm list, which is not an expression and could not
be passed to anything else; and exhaustiveness is "a load-bearing correctness
property, not a lint", so the node it is checked on should not be one the
checker has to recognise by the callee's spelling.

`BinOp` is `Add Sub Mul Div Rem AddWrap SubWrap MulWrap Equal NotEqual Less
LessEq Greater GreaterEq And Or`. `UnOp` is `Not Neg Addr`. There are no bitwise
operators. The wrapping forms are separate operators, not a flag on the trapping
ones — they generate different C, and a flag is one `!` away from generating the
wrong one.

### Patterns — `Pattern { kind, span, leading, trailing }`

| `PatternKind` | fields | source |
|---|---|---|
| `Name(PatName)` | `name` | `None`, `Macos`, `Shape.Unit`, **and** the `n` of `Ok(n)` |
| `Destructure(Destructure)` | `name, binder` | `Ok(n)`, `Circle(c)`, `Ok(_)`, `Left(Full(n))` |
| `Wild` | | `_` |
| `Literal(Literal)` | | `true`, `3` |

`Name` deliberately covers both a nullary variant and a binder: `Left(Blank)` and
`Ok(n)` are the same three tokens, and which one it is depends on what is in
scope. That is sema's question, and a parser answering it is a parser guessing.

`Destructure.binder` is a full `PatternId` and not a name, which is what makes
`Unit` and `Unit(_)` different nodes. They must be, or the formatter invents or
deletes a pair of parentheses.

### Statements — `Stmt { kind, span, leading, trailing }`

| `StmtKind` | fields | source |
|---|---|---|
| `Bind(Bind)` | `target, type, mutable, value` | `x = e;`, `x: T ::= e;`, `self.len = self.len + 1;` |
| `Expr(ExprStmt)` | `expr` | `println("done");` |
| `Decl(Decl)` | | a struct, enum, impl or function-with-body inside a body |
| `Block(BlockId)` | | a bare block |

`Bind.target` is an **expression**, not a name: a member access and an index are
binding targets too, and narrowing it to an `Ident` makes `self.len = ..`
unrepresentable.

`Decl` is a statement kind because an enum "may be declared anywhere, not only
at module level", and a declaration takes no `;` wherever it stands. So a local
`add_i32 = (a: i32, b: i32) i32 { a + b }` is `StmtKind.Decl` holding a
`Function`, **not** a `Bind` holding a `Lambda`. See "open questions" — the two
are the same thing semantically and `DESIGN.md` does not say which is written.

### Blocks and modules

```groovy
Block*  = { stmts, value, span, leading, trailing }
Module* = { name, decls, span, leading, trailing }
```

`Block.value` is the trailing expression written **without** a `;`.
`DESIGN.md` also lets a `;`-terminated tail (`Ok(0);`) be the block's value, but
that is a typing rule and not a syntactic one, so the AST records what was
written and sema decides. A formatter must not add or remove that semicolon.

`Module.name` is the dotted module path; the file is `span.file`, which every
node already carries.

---

## `Ast` — the arena

```groovy
tree ::= alloc.Ast();          // ufcs on Alloc, beside its type, like Vec and Map

id = tree.add_expr(node).try();      // -> Res<ExprId, AllocError>
e  = tree.expr_at(id);               // -> Expr

tree.add_type / type_at
tree.add_pattern / pattern_at
tree.add_block / block_at
tree.add_module / module_at / module_count
tree.trivia_mark / add_trivia / trivia_run / trivia_at
```

**A node is added once and never mutated.** An id handed out points at the same
node forever, which is what makes it a legal key for a memoized query. A
transformation builds a new node and gets a new id — `@meta`'s `AddFoo(Circle)`
"returns a new one", and nodes are values.

**`expr_at` and friends TRAP, they do not return `Res`.** An id past the end of
its arena is a compiler bug, not input a caller can act on. Routing it through
`Res` would put `.try()` on every child access in the tree and destroy the
signal that makes `.try()` readable. `Vec.get` still returns `Res` — a lookup
that can legitimately miss is not a bug.

**Ids are indices assigned in creation order**, which makes them a pure function
of the source. Nothing here is an address, so `gen_c` stays deterministic.

`functions* = (self: Module, a: Alloc) Res<Vec<Function>, AllocError>` collects a
module's function declarations in source order. It is `DESIGN.md`'s test
discovery — "change the filter, change what a test is".

---

## What is deliberately NOT a node

- **A token.** `;`, `,`, `.`, `{`, `(` have no nodes. The seven span fields in
  the table above are the complete list of tokens anything needs to locate.
- **`ref` / `val` / `iso`.** They have no syntax. Capabilities are inferred and
  the only thing ever written is `consume`, which is `ExprKind.Consume`.
- **A qualified type.** Imports bind locally.
- **An export node.** `*` is a `bool` on the declaration, the member, the field
  and the import name. Re-export is an import whose bindings are starred, so
  there is no second mechanism to represent.
- **An arm list, a parameter list, an argument list, a struct body.** They are
  `Vec`s and a span, not nodes: nothing ever holds one on its own.
- **`h.break(v)`.** An ordinary `Call`. Sema recognises it; the parser does not.
- **A separate `Method` node.** A method is a `Function` inside a `Member`.
- **`Res` hoisting, `.then`, the `loop` family.** Ordinary calls. None of them
  is syntax.
- **A parent pointer.** Nodes are values in an arena; a walk carries its own
  context. Adding one makes every node mutable and every id ambiguous.
- **A type after inference.** `Type` is a *written* type. What sema computes is
  sema's, keyed on an id — that is what the ids are for.

---

## Divergences from `bootstrap/CONTRACT.md`

`gen_c` eventually consumes both, so each of these is deliberate and named.

| this AST | the bootstrapper | why |
|---|---|---|
| children are ids into `Ast` | children are Python object references | `type_of(node)` needs a hashable identity; Python gets one free |
| trivia is a `TriviaRun` into one list | `leading` / `trailing` tuples per node | sixteen words a node, in a language with no free tuple |
| `Paren` is a node | absent | `POSITIONS.md` asserts a span for it, and `fmt` cannot re-derive parentheses |
| `Match` is an `ExprKind` | `Match` node, same call | agreement, recorded because `POSITIONS.md` labels the row `Call` |
| `TParam.bounds` is a list | `TParam.bound` is one type or none | `<K: Eq + Hash, V>` has two, and `+` is not `\|` |
| `SelfType` is its own `TypeKind` | `@Self` is a `Named` | `@Self` "is not a name you could have written yourself"; a name-shaped one can be shadowed |
| `Struct.members` is one ordered list | `Struct(fields, consts)`, two lists | source order is what the formatter reprints |
| `Member` also serves impl bodies and record literals | `Impl.entries` is its own thing | one rule for fields and methods, per `DESIGN.md` |
| `Import` is a `DeclKind` | `Module(decls, imports)`, two lists | same reason: source order |
| `Const` is also a `DeclKind` | `Const` only inside `Struct` | module-level constants exist (`STR_HASH_SEED*: u64 = ..`) |
| `Bind.target` is an `Expr` | `Let.name` is a `str` | `self.len = ..` and `buf[i] = ..` are binding targets |
| `Destructure.binder` is a `Pattern` | `PatVariant.binder` is a `str` or none | nested patterns, and `Unit` vs `Unit(_)` |
| `Access` | `Member` | `Member` is taken by what a struct body is made of |
| `Name` (expression) | `Path` | `Path` is a prelude type (a filesystem path) |
| operator, arrow, `match`, params, args, body spans | absent | `POSITIONS.md` rows, and the trap position is the operator token |
| `Variadic` is a `TypeKind` | absent | `args: ...` is in `DESIGN.md`'s `String.add` |
| four id types, not one | n/a | passing a `TypeId` where an `ExprId` belongs is unrepresentable |

---

## What `DESIGN.md` does not settle

Each of these was decided here because a data definition cannot abstain. Each
needs a sentence in `DESIGN.md`, and until it has one, this file is the only
place the decision is written down.

1. **Is a local `f = (a: i32) i32 { .. }` a declaration or a binding of a
   lambda?** `DESIGN.md:1294` says "functions are just bindings of lambdas, so
   they're values", and writes one at `1297` with no `;`. `DESIGN.md:219` says
   "a binding inside a body is a statement. semicolon." The grammar resolves it
   as a `declaration_statement` — no `;` — and this AST follows the grammar:
   `StmtKind.Decl` holding a `Function`. **The AST can hold either**, so nobody
   is blocked, but two spellings of one thing is a formatter bug waiting.

2. **A struct-body constant and a field with a default are the same syntax.**
   `MAX*: i32 = 2147483647` and `verbose :: bool = false` differ only in `:`
   versus `::`, which `DESIGN.md` uses for mutability and not for storage. The
   grammar's R4 makes `:` + a value mean *constant*, at the cost of leaving an
   immutable field with a default **unspellable**. That cost belongs in
   `DESIGN.md`, priced, not in a grammar comment. **Settled:** `DESIGN.md`'s
   "Declarations" section now states R4 and its price, and "Constants on a type"
   says the spelling decides everywhere. The AST is unchanged.

3. **Does a node's span include its leading trivia?** `POSITIONS.md` says no and
   `Module` is the exception. Both are followed here; `DESIGN.md` says neither.

4. **Is a column a byte, a codepoint, or a UTF-16 unit?** `POSITIONS.md` says
   byte; `DESIGN.md` says byte for a trap and is silent for a node.

5. **Does a statement's span include its `;`?** `POSITIONS.md` says yes.
   `DESIGN.md` is silent.

6. **How deep may a pattern path be?** The grammar allows `a.b.c.d`;
   `DESIGN.md` writes only `Shape.Unit`. `QualifiedName` holds any depth and
   sema must reject what the language does not mean.

7. **`DESIGN.md`'s own `DumpAst` reads `param.value` and `Enum.fields`.** Neither
   exists: a parameter has a `type`, and an enum has `variants`. `build.zen`'s
   `f.params.get(0).try().type` — the one semantic use — is honoured. The
   `DumpAst` block is illustrative and needs correcting.

8. **`Module.functions` is a function taking an `Alloc`, not a field.**
   `DESIGN.md:1059` writes `b.module(Path("src")).functions`. Collecting into a
   `Vec` allocates, and law 1 says no `Alloc` parameter means no allocation. The
   example needs one more argument.

---

## Known bootstrapper bugs this AST runs into

Not fixed here; `bootstrap/` belongs to another agent. Each is a reproducer.

1. **A re-export through a folder root does not bind an enum or a plain
   function**, and loses names beside them in the same import list. This is why
   the two corpus tests under `tests/corpus/ast/` import from `std.ast.ast_node`,
   `std.ast.ast_span`, `std.ast.ast_id` and `std.ast.ast_arena` directly rather
   than from `std.ast`. **Consumers should write `= std.ast` and will be able
   to once this is
   fixed**; the leaf paths are a workaround, not the contract.

2. **`type ...Eq is part of a by-value cycle`** — reported for `src/` as it
   stands, without any file of this AST's. A struct whose field is a function
   type taking `@Self` is not a by-value cycle; a function type is a pointer.

3. **A string literal containing `//` breaks the next string literal in the
   file.** The trivia corpus test therefore stores a comment's text without its
   markers, which is not what a real lexer will do.
