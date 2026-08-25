# The language server

Companion to `DESIGN.md`, `PLAN.md` and `TESTING.md`. Those say what the language is, what to build and how a gate fails; this says what `zen lsp` is, what of it already exists, and — the part that matters — what does not.

`DESIGN.md:45` has already decided the shape of this document:

> LSP, formatter, and race checker are the visible goals, and **two of those three are not tools.** … Only the LSP is a genuinely separate program, and even it is a thin server over compiler internals.

**Everything below is held to that.** A server is a transport, a coordinate conversion, and a table that maps a method name onto a query the compiler already answers. Where a query is missing, the fix belongs in `src/sema/` or `src/std/ast/`, not in `src/lsp/`. Where a query is *expensive*, `PLAN.md:345` already names the cause and the place the fix goes: "If this stage turns out to be expensive, the cause is stage 0.3 — a batch compiler recompiling the world per keystroke."

`STAGE` reads `4`, and `PLAN.md:74` puts the LSP at stage 4. This is not future work.

---

## 1. The thesis: three lists

### Already compiler internals — do not write a second one

| what | where |
|---|---|
| a cursor position finds its node | `src/std/ast/ast_find.zen:55` (`node_at`), `:106` (`expr_node_at`) |
| every node carries a half-open span with a 1-based byte column | `src/std/ast/ast_span.zen:22` (`Pos`), `:30` (`Span`, carrying `file`) |
| every **name** carries its own span | `src/std/ast/ast_span.zen:73` (`Ident`), `:82` (`QualifiedName`) |
| the type of an expression, memoized | `src/sema/sema_type.zen:59` (`type_of`), memo at `src/sema/sema_check.zen:101` |
| the type a written type node denotes | `src/sema/sema_denote.zen:50` (`type_from_ast`), memo at `src/sema/sema_check.zen:102` |
| which declaration a call resolved to | `src/sema/sema_check.zen:124` (`call_memo`) |
| what a name means in a module | `src/sema/sema_def.zen:180` (`defs_of`), `Def` with a `span` at `:64` |
| what a dot reaches | `src/sema/sema_member.zen:413` (`members_of`), `Found` with a `span` at `:63` |
| what a value of a type can be | `src/sema/sema_case.zen:42` (`cases_of`) |
| a diagnostic as a value with a position | `src/sema/sema_diag.zen:165` (`Diag`), `:177` (`message`), `:228` (`render`) |
| printing a `TyId` as text | `src/sema/sema_ty.zen:448` (`Types.name_of`) |
| tokens, with comments among them | `src/std/lex/lex_token.zen:96` (`Token`), `:75` (`LineComment`/`BlockComment`) |
| the whole pipeline, wired | `src/zen/zen_run.zen:35` (`build`) |

`PLAN.md:355` listed one precondition as **MISSING** — "a cursor position finds its node". It has since landed as `src/std/ast/ast_find.zen`, and that file's header says why it was the one absent: every other consumer walks downward from a root, and an editor arrives holding a position. **That table row is now green, and `PLAN.md` says so.**

### Genuinely new code

Five things, and only one of them is about the LSP.

1. ~~**JSON.** Nothing in this tree speaks it.~~ **LANDED** — and since moved: `std.json` is the value, the arena, the writer and the reader (`src/std/json/`, moved out of `src/lsp/` by the second-caller rule the move note below predicted), still gated by `corpus/lsp/json_round_trips_and_rejects` plus `corpus/std/json_serves_a_second_caller`. §4's "it moves" is spent; only §3's framing note remains to land.
2. ~~**Reading standard input.**~~ **LANDED.** `Env` now has `in: Stdin`, one byte-counted `read` with no line discipline, and its floor is `src/gen/gen_c/gen_c_stdin.zen`. §4 records what it cost and the one thing it turned out to require that this document did not anticipate.
3. **Writing exact bytes to stdout.** `Console` has exactly one member, `println` (`src/std/env/env.zen:38`), which appends exactly one `\n` (`TESTING.md:76`). A JSON-RPC frame is CRLF-delimited and unterminated.
4. **The position conversion.** §3. It is small, it is the classic bug, and it lives in one file.
5. **The server itself**: a document overlay, a dispatch table, and lifecycle state.

### Must NOT be reimplemented

- **A second parser or a second AST.** `PLAN.md:137`: "Never a second parser, never a second AST, never a 'just for the formatter' path." An error-recovering "IDE parser" is that mistake wearing a new hat.
- **A formatter.** `textDocument/formatting` calls stage 2's `zen fmt`. If `fmt` cannot format a buffer that is not on disk, fix `fmt`. **Honoured**: `src/lsp/lsp_fmt.zen` calls `fmt.render` and holds no printing rule of its own.
- **A diagnostics engine.** Every phase already produces diagnostics as values carrying spans. The server converts; it never decides what is wrong.
- **Name resolution.** `DESIGN.md:404` and `:406` specify exactly what is visible and exactly what a dot reaches. A completion list assembled by any other rule is a second, wrong, specification of the language.
- **An incremental compiler.** `DESIGN.md:67`: compilation is whole-program. `PLAN.md:397` lists incremental codegen under "what not to build". §5 says what that costs and what to do instead.

---

## 2. The request surface, staged

Four stages, named **L1–L4** so they are not confused with `PLAN.md`'s 0–5. All four sit inside `PLAN.md`'s stage 4.

| request | the query it needs | state today | stage |
|---|---|---|---|
| `initialize` / `initialized` | none — capability negotiation | **built**: `src/lsp/lsp_serve.zen` answers with `textDocumentSync: 1` and `hoverProvider: true`. Every request before it is `-32002` | L1 |
| `shutdown` / `exit` | none | **built** | L1 |
| `textDocument/didOpen` / `didChange` / `didClose` | an overlay the driver reads before the disk | **built, both halves** (Full sync). The server holds the buffer; `Build.overlay` is what the driver reads before `env.fs.read`, so an UNSAVED buffer — and a file that is on no disk at all — is what gets checked | L1 |
| `textDocument/publishDiagnostics` | diagnostics as values with spans | **built**, all three phases: `src/lsp/lsp_diag.zen`. Sema's come off the `Checker` `Build.whole` hands back (`src/sema/sema_check.zen:197,199`), lex's and parse's off the `Build`'s own `diag_count`/`diag_at`. Grouped by the URI each span names, one notification per file, and a file whose errors are gone gets an EMPTY list. The policy — when to send, and why it is not a timed debounce — is §5 | L1 |
| `textDocument/documentSymbol` | a module's declarations in source order, each with a span and a name-span | **built** — `src/lsp/lsp_symbol.zen`, and it turned out to need no build at all: kind, `Decl.span` and `Ident.span` are AST facts, so the buffer alone answers, flat `SymbolInformation`, top-level only | L2 |
| `textDocument/hover` | the type under the cursor, printed | **built, and widened** — `src/lsp/lsp_hover.zen` plus the name finder (now `src/std/ast/ast_named.zen`), still no new sema. See the hover section below for what it answers, what it refuses, and the measurement | L2 |
| `textDocument/definition` | the span a name was declared at | **built** — `src/lsp/lsp_def.zen`: `call_memo` for a call site, `defs_of` → the declaration's name-span for a module-level name, `expr_memo` + `members_of` → `Found.span` for a member, `type_memo` → the `Named` type's decl for a written type. Cross-module through the same build path hover uses. **Locals and pattern binders answer `null`** — the gap below | L2 |
| `textDocument/semanticTokens/full`, lexical | the token stream | **built**: `src/lsp/lsp_colour.zen`, over `scan` and `Token{kind, span}` (`src/std/lex/lex.zen:57`, `src/std/lex/lex_token.zen:96`) and nothing else. The one answer here that needs no build, no `Checker` and no workspace — see the colour section below | L2 |
| `textDocument/references` | for a `DeclId`, every node that resolved to it | **missing**. `call_memo` is that map, forward and for calls only. Nothing records a resolved bare *name*, and nothing inverts | L3 |
| `textDocument/completion` | the candidate set at a position | **built** — `src/lsp/lsp_compl.zen`: the backward scan below finds the trigger; after a dot a dummy identifier makes the access parse and `members_of`/`cases_of` answer, otherwise the in-scope names are collected from the world's tables and each is judged by `defs_of` (which still has no prefix form — the collection over-reads and `defs_of` filters), plus the three reserved words | L3 |
| `textDocument/codeAction` | which modules export a name the checker called undefined | **built** — `src/lsp/lsp_action.zen`, one `quickfix` kind: the auto-import. `context.diagnostics` is never read — the handler re-walks the shared checker's diags for `UndefinedName` (the name is structural, `NameFault`) and asks `World.exported_named`, a query that already existed in sema; the offer and the squiggle have one source. One action per exporting module, module order, no ranking — ambiguity is the client's list. The edit is one text line, `Name = dotted.module\n`, spelled UNSTARRED (a star is re-export) and inserted after the file's last import decl, or at the top when it has none. No workspace or no settled build answers `[]`, never an error. NOT covered: enum variants (`Ok`, `None`) — they are not `Def`s, they ride their enum's star, so an undefined variant name offers nothing; that is the `variant_defs` walk, a follow-up | L3 |
| `textDocument/formatting` | `parse \|> print` | **built** — `src/lsp/lsp_fmt.zen`, and it is `zen fmt` and not a copy of it: the open buffer goes through the same `render` the command line calls, so there is no second formatter to drift. One whole-document `TextEdit`, line 0 char 0 to a line past the last. Every refusal — a lexical fault, a parse fault, a failed re-lex guard, or a file already formatted — is an EMPTY EDIT LIST and never an error, because format-on-save asks about a half-typed buffer constantly and an error is a modal per save. Needs no build and no workspace. Note the formatter models the FILE, not the DECLARATION, so `rangeFormatting`/`onTypeFormatting` are not merely unimplemented but not yet expressible, and are deliberately not advertised | L3 |
| `textDocument/semanticTokens`, semantic | per-`Ident` resolution: is this a type, a function, a parameter? | ~~**missing**: `defs_of` per identifier in a file, and nothing memoizes on an `Ident`.~~ **LANDED** — and it turned out to need neither: `call_memo`, `type_memo` and the AST's own declaration kinds already answer type and function; the one genuinely new memo is `param_memo` (`src/sema/sema_check.zen`), keyed on the name EXPRESSION's `ExprId` since an `Ident` has no id. `src/lsp/lsp_names.zen` reads all of it off the diagnostics' build; `src/lsp/lsp_colour.zen` reclassifies only the `Ident`s it names | L4 |
| `textDocument/semanticTokens/range` and `/full/delta` | a sub-range, or a diff against a previous result | **missing, and deliberately not advertised.** A client asks for either one only when the server said it has it, so the capability is `full: true` and nothing more. Advertising one unanswered is `-32601`, which in VS Code renders as no colour at all with nothing on screen to say why | L3 |
| `textDocument/signatureHelp` | which overloads a call could mean, and which parameter the cursor is in | **missing**, and harder here than elsewhere: `DESIGN.md:505` resolves on declared parameter types *and arity*, so there is never one signature to show | L4 |
| `textDocument/rename` | references, plus a safety argument | **missing**, and see the hazard below | L4 |

**Three honest notes on that table.**

**Locals have no span, and it is not an oversight.** `Binding` is `{ name, ty, mutable }` (`src/sema/sema_check.zen:68`) and locals are released at scope exit (`detach_locals`, `:294`). Nothing about a local survives `check_all`. Go-to-definition on a parameter therefore does not work and cannot be made to work from outside sema: the fix is a `span` on `Binding` plus a per-function record of the bindings that were live, which is a change in `src/sema/` and is priced at L3, not at L2.

**Incomplete input is the completion problem, not resolution.** `x.` is not a parse. `f(a, ` is not a parse. So at the moment completion and signature help are wanted, there is no `Access` node and no `Call` node to ask about. This tree's parser reports and does not recover — `src/zen/zen_build.zen:341` states the position for the lexer and the same holds one level up. **Do not answer this by writing an error-recovering second parser.** The cheap answer, and the one this document recommended and completion now implements: the server scans *backwards from the cursor over the buffer's bytes* to find the trigger character and the base expression's end, asks `expr_node_at` about the base — which does parse — and never asks the parser about the incomplete part at all. `lsp_compl.zen` makes the base parseable with a dummy identifier rather than trimming, which is the same refusal said constructively. It is a lexical heuristic living entirely in `src/lsp/`, it is testable, and it does not put a second grammar in the tree. It will be wrong sometimes — its header says so.

### Hover, in full — because it was the first query built and it was measured

The first version of hover was one path: `expr_node_at` → `expr_memo` → `Types.name_of`. That is the type of an EXPRESSION, and it turned out to be half of what hovering is for. Probing every identifier position in

```
add = (a: i32, b: i32) i32 {
    s = a + b;
    s
}
```

against the shipped binary over a real pipe, **3 of 12 positions answered**: `a` and `b` where they are used in `a + b`, and `s` where it is used on the last line. The function's own name, both parameters at their declarations, the local at its declaration and all three `i32` returned `null`. The rule was "an identifier in expression position resolves; a binding site or a type name does not" — and a user hovers a declaration to ask what something IS at least as often as a use.

It is now **10 of 12** on that program, the two remaining being a space and a brace, which must stay `null`. The widening cost no new sema. It cost one new query — *which name is the cursor inside* — because a name is not a node (the finder lived in `src/lsp/lsp_decl.zen` and moved to `src/std/ast/ast_named.zen` when `definition` became its second caller):

| what a user hovers | where the answer comes from |
|---|---|
| an expression (`a` in `a + b`) | `node_at` → `expr_memo` |
| a **written type** (`i32`, `Vec<T>`, an alias) | `node_at` → `type_memo`, keyed on exactly that `TypeId` |
| a **parameter** at its declaration | the `Param`'s own `type`, → `type_memo` |
| a **local** at its declaration | the `Bind`'s annotation, or its value's `expr_memo` entry |
| a **constant or field** at its declaration | its annotation, or its value |
| a **function's name** | its declaration REPRINTED: `add = (a: i32, b: i32) i32` |
| everything else | `null` |

Three decisions in that table are worth ratifying or overruling rather than inheriting.

**A function's name answers with a reprinted declaration and not with its type.** `Types.write_fn` would produce `(i32, i32) i32`; `ast_node.zen` already argued why that is worse — "`(i32, i32) i32` says nothing about which `i32` is which" — and parameter names are correctly *not* in the type, since two signatures differing only in them are one type. So the names come from the AST and the types from the memo, and nothing in the string is invented. Type-parameter **bounds are dropped**: `<T: Eq + Hash>` reprints as `<T>`.

**A type name answers with what it RESOLVES to — and a PRIMITIVE also answers with what its prelude declaration says.** For an alias or a named type the answer is the resolved type (`Alias = Shape` hovers as `Shape`, `Res<Cfg, _>` with the hole filled as the checker filled it), and a name that resolves to nothing answers `null`, so even the plain cases say *this name is a type the checker knows*. A primitive has a second thing to say, because "a prelude declaration of a primitive's name IS that primitive" (DESIGN.md): the declaration is where the language keeps the description and the constants, so a written `i32` answers `i32 — members: MIN, MAX, BITS`, and `bool` — declared in `std.core.bool` with nothing but a doc line, which is the truth about bool — answers with that line. The enrichment is the build's: a lone-module check has no prelude to read, and there the bare name is the whole answer, as before. Richer still — a field list, a size — remains `documentSymbol`'s and `definition`'s answer wearing hover's clothes.

**Poison is refused everywhere rather than printed.** `Ty.Unknown` is what sema interns for "a type I could not compute and have already reported", and `Types.write_name` spells it `<unknown>`. Hover checks any type it is about to print, recursively, and answers `null` if poison is anywhere inside it — so a function whose return type did not resolve has no hover at all rather than a signature with a hole in it. **This gate is what made the next paragraph a measurement rather than a surprise**: it is why an unbuilt import failed loudly-by-silence instead of printing `<unknown>` at every position in `src/`.

#### And 10 of 12 was measured on a file that imports nothing

That program is self-contained — every type in it is `i32` — and **that is the only reason the number was 10.** The same twelve positions over a two-module root, driven through the shipped binary over a real pipe:

```
Point = app.shape                    // app/shape.zen declares Point

near = (q: Point, n: i32) i32 {
    s = q.x + n;
    s
}
```

**answered 4 of 12** while hover checked the open document as a lone module: the two written `i32`s, the parameter `n`, and `n` where it is used. `Point` resolved to nothing, sema interned poison, and the parameter typed by it, the local computed from it and the whole reprinted signature went `null` with it. **Every file in `src/` opens with an import**, so 10 of 12 described no file anyone works in.

With the overlay and `Build.whole` behind it (§5), the same twelve answer **9**. The three that do not are the import line, a space and a brace — the space and the brace must stay `null`, and the gate pins all three.

**The receiver of a field access** (`q` in `q.x`) was a third, and it was the row listed below as *a sema bug and not a hover one*: `expr_memo` had an entry for the whole `Access` and none for its base. `sema_member.base_of` records the base now — a name base is typed straight out of the scope and never reached `type_of`, which is what memoizes — so it answers, and this program is 9.

The gate is `tests/corpus/lsp/hover_answers_an_imported_name`, which ships the root, and asserts three separate failures at once: an imported name resolving, the **unsaved buffer** rather than the file being what gets checked (the disk names the parameter `p` and the buffer names it `q`), and the driver **not printing** the parse diagnostic from a buffer whose brace never closes.

**What still answers `null`, and why each is a fact about the compiler rather than about `src/lsp/`:**

- **A struct's or enum's own name** (`Foo` in `Foo = { .. }`). `type_memo` is keyed on a written `TypeId` and a declaration site has none. A *use* of `Foo` hovers. Fixing it means building the type a declaration denotes, in `src/sema/sema_denote.zen`.
- **A pattern binder** (`n` in `Ok(n) => ..`). There is no pattern memo, and `Binding` is released at scope exit — the same gap open question note above prices at L3 for go-to-definition, and the same fix closes both.
- **A type parameter at its declaration** (`T` in `<T>`). Same shape as a struct name.
- **An imported name, when there is no workspace.** With a `rootUri` this now answers, because the document is checked as part of a build (§5). Without one — a client that sends none, or the two-file form of `zen lsp` — the lone-module check is still what runs and an import still resolves to poison.
- **A closure's parameter**, whose `Param.type` is absent by construction.

**The gate is `tests/corpus/lsp/hover_answers_at_a_declaration`**, which is the 12-position probe plus three poison rows and three no-prelude fallback rows, driven through framed JSON-RPC, asserting the value AND the range — so a right type under the wrong underline is still red. Half its rows assert `null`; a widening that starts answering those is a regression even though it looks like more coverage.

### Colour, in full — because it is the second query built, and it cost the least of anything here

**`src/lsp/lsp_colour.zen`, and the lexical half of it is one `scan`.** No `Parser`, no `Checker`, no `Build`, nothing read from any disk. That is not an economy, it is the property that makes the answer worth having: hover and diagnostics both need a build and both go quiet without a workspace, and colour is the one thing a user notices the *instant* a file opens. It answers on an unsaved buffer, in a session with no `rootUri`, and in a file that does not parse — `src/std/lex/lex.zen`'s contract is that a file with lexical faults still yields tokens, so a half-typed string literal costs the colour of that literal and nothing else. **The semantic half rides the diagnostics' build** and is one paragraph below; it changes none of those properties, because where there is no clean build there is no semantic half and the lexical answer is what remains.

**Why this rather than a TextMate grammar** is `editors/README.md`'s argument and it stands unchanged: a second grammar is `PLAN.md:137`'s named failure, a generated one is `PLAN.md:127`'s ungated third artifact, and VS Code cannot load the tree-sitter grammar `grammar/` already holds. What this document said was the route that costs neither, and it was right; what it did not say is that the route is about two hundred lines.

**`Ident` IS ONE KIND AND COLOUR WANTS SEVERAL, AND THE LEXER'S ANSWER IS STILL TO REFUSE.** A lexer cannot tell a type from a function from a variable, and Zen makes that sharper than most languages: `DESIGN.md` has no keyword before a type, so `Vec`, `add` and `n` are the same token. Every `Ident` is therefore `variable`, lexically — **colouring by capitalisation was available and was rejected**: it would be a second, wrong, specification of what a name means, living in `src/lsp/`, which §1 says may never specify the language. It is the same rule that makes hover answer `null` rather than print `<unknown>`.

**The semantic row in the table above has now LANDED, and the refusal is why it could.** Because nothing ever guessed, the upgrade is additive: `lsp_names.zen` walks the `Checker` the diagnostics' build already produced — the AST's declaration kinds for declaration sites, `type_memo` for written types, `call_memo` for callees, and the one new memo, `param_memo`, for parameter uses — and `lsp_colour.zen` repaints exactly the `Ident` tokens that walk named. The walk runs only on a CLEAN build: with faults outstanding the memos hold poison, and the file keeps its lexical colours rather than a wrong answer or a grey one. What stays `variable` and why — a function named but not called, a type in value position, a variant, a constant, a local, a type inside a struct or impl body (no `type_memo` entry where `@Self` is in scope) — is listed in `lsp_names.zen`'s header, and the list is the honest map of what sema writes down.

**Delimiters are not coloured** — `(`, `)`, `[`, `]`, `{`, `}`, `,`, `;`, `.`, `:` — and operators are. That is the same refusal one step down: a brace is structure, and calling it `operator` would be this folder deciding something the lexer did not say.

**The three arithmetic decisions**, each of which is a way to ship colour that drifts:

- **The encoding is deltas from the PREVIOUS TOKEN**, and `deltaStartChar` is relative only when the two share a line. Wrong, and colour slides further off the further down a file you read — which looks like a rendering bug and is subtraction.
- **`character` and `length` are both UTF-16 code units**, so `end.offset - start.offset` is correct for exactly the ASCII half of the world. `lsp_pos.zen` gained `units_of` for the length and `wire_at` for the position; §3's rule that no other file converts is unchanged.
- **A multi-line token is SPLIT, one run per line**, because the standard encoding cannot express one unless the client advertised `multilineTokenSupport` — which this server does not ask about. Splitting was chosen over omitting: a block comment is the only token here that spans lines, it is also the one a reader most wants greyed, and omitting it leaves a hole in the middle of a file. A run of zero units — a blank line inside a block comment — is not emitted at all.

**The legend moved the capabilities from a constant to a writer**, and that is worth a sentence because it is the failure that cannot be seen: a `tokenType` is an INDEX into the array `initialize` advertised, so the list and the numbers spelled in two files drift silently — every colour in the file shifts by one and nothing errors. `lsp_colour.zen` owns both.

**The gate is `tests/corpus/lsp/colour_comes_from_the_lexer`**, which drives the server over framed JSON-RPC and then UNDOES the encoding: each five-integer group is added back up and the resulting `line:character` handed to `to_pos` — the inverse conversion — so the last column of every row is the bytes that group actually colours. A flat array of integers is unreviewable; a decoded row is. **Ten mutations were run against it and nine went red**: `deltaLine` made absolute, `deltaStartChar` never relative, two legend indices swapped, the legend's names written out of index order, UTF-16 units counted as bytes, the `length` taken in bytes, multi-line splitting disabled, zero-length runs emitted, `Ident` recoloured, and `range: true` advertised without a handler.

**The tenth came back green and it is not a hole in the test.** §3 below suggests mutating `step_at`'s `c.value < UTF8_MIN_4` into a comparison on `c.len`, and predicts red. It is green, because those two conditions are *equivalent over anything `codepoint_at` returns `Ok` for*: `four_byte` rejects `value < UTF8_MIN_4` as overlong and `three_byte` rejects `value >= UTF8_MIN_3` failures, so a decoded length of 4 and a value at or above 65536 are one fact. **§3's suggested mutation is an equivalent mutant and that paragraph should be read as naming the wrong one** — the mutation that does go red is counting `units` as `bytes`, and it reddens three tests.

**Rename is the request this language makes dangerous**, and it is worth writing down before someone ships it. Two rules collide with it. `DESIGN.md:406`: a UFCS call `x.f(..)` "never names `f`", so renaming an exported free function must rewrite call sites that do not contain that name in any bare-name position — a textual search finds them, and a textual search is exactly what a rename must not be. `DESIGN.md:146`: whether `A | B` is a union or a nominal enum "depends on what else is in scope", so renaming a *type* can silently change the meaning of an unrelated declaration in a module that imports it. Rename is L4 and it is L4 for a reason.

---

## 3. Positions

**This is the section that will produce the bugs.** It is also the one place `DESIGN.md` and `AST_CONTRACT.md` have already made the decision and left the work.

Two coordinate systems:

| | line | character |
|---|---|---|
| LSP | **0-based** | **UTF-16 code units** into the line |
| Zen | **1-based** | **1-based BYTE column** |

Zen's side is fixed in four places and is not negotiable: `DESIGN.md:49` ("a `line:col` with a 1-based byte column, from the lexer up"), `DESIGN.md:314` (a trap's column is a 1-based byte offset), `TESTING.md:49` (every `must-fail` position is a 1-based byte column), and `src/std/ast/ast_span.zen:22`, which anticipated this document in one sentence:

> `col` counts BYTES, not codepoints and not UTF-16 units — `str` is bytes everywhere else in this language, and an LSP converting to UTF-16 at the wire is its own, testable, step.

`src/AST_CONTRACT.md:480` lists "is a column a byte, a codepoint, or a UTF-16 unit?" as something `DESIGN.md` does not settle. **It is settled for Zen and it is settled for the wire; what was never written down is that they differ. This document is that sentence.**

### Where the conversion lives

`src/lsp/lsp_pos.zen`, and nowhere else. **No other file in `src/lsp/` may construct an LSP position or read one.** The rule is not tidiness: an off-by-one applied in two files is an off-by-one fixed once and then applied twice, and the 0-based/1-based line shift must live in the *same function* as the column conversion so that the two are read together.

Two functions, and they are inverses:

```
to_pos*  = (text: str, line: usize, character: usize) Pos   // wire -> Zen
to_wire* = (text: str, p: Pos) WirePos                      // Zen -> wire
```

Both take the document text, because **neither `Pos` carries a byte offset.** `src/std/lex/lex_token.zen:26` has one and `src/std/ast/ast_span.zen:22` deliberately does not — the offset dies at the parser boundary. So converting a column requires the bytes of the line, which means **the document store is a precondition for positions, not merely for sync.** That is a real ordering constraint on L1.

### The algorithm, and the one arithmetic fact

Walk to the start of line `line + 1` counting `\n`. Then walk forward decoding codepoints with `codepoint_at` (`src/std/text/text_utf8.zen:38`), which hands back a `Codepoint { value, len }` — `len` is the byte width, and the UTF-16 width is **1 when `value` is below 65536 and 2 otherwise**, because a codepoint at or above U+10000 is one surrogate pair. Written in decimal, because `DESIGN.md:101` puts hex outside v1.

Four decisions the algorithm has to make and a scanner cannot abstain from:

- **A character past the end of the line clamps to the end of the line.** The LSP specification says so, and a client that sends one is not making an error the server should report.
- **A character landing inside a multi-byte sequence rounds *down*** to the start of that sequence. There is no byte column between the two bytes of an `é`, and inventing one produces a span that slices a codepoint in half.
- **A CRLF line ending's `\r` is part of the line, not part of the terminator**, for the purpose of counting bytes — because `str` is bytes and the lexer already decided what a line is. The `\r` is therefore reachable as a column, which is correct and which a test must pin.
- **A tab is one code unit and one byte.** Editors render it wide; nothing here cares.

### How it is tested

A corpus test, in the format `TESTING.md:27` fixes, driving `to_pos` and `to_wire` over a table and printing both directions. This is the same shape `tests/corpus/cli/cli_reads_an_explicit_entry.zen` uses to pin `zen_cli.zen`: a pure function, handed values no real client would send, with its answers read back. **Both directions in one test**, because a conversion tested one way passes with the error present in both.

The table must contain, at minimum: ASCII; a 2-byte `é`; a 3-byte CJK character; a 4-byte emoji, which is the only row where UTF-16 and codepoints disagree; a position at end-of-line; a position past end-of-line; a CRLF line; a tab; an empty line; and the last line of a file with no trailing newline.

And then `TESTING.md:19`'s oracle, because this is exactly the code it exists for: **mutate the conversion — swap the 65536 for a comparison on `len`, drop the `+ 1` on the line — and watch a row go red.** If nothing goes red, the table is not the table.

**One correction to that sentence, made by running it.** Swapping the 65536 for `c.len < 4` is an EQUIVALENT MUTANT and stays green, correctly: `four_byte` rejects an overlong `value < UTF8_MIN_4` and `three_byte` rejects `value >= UTF8_MIN_3` failures, so over anything `codepoint_at` answers `Ok` for, "four bytes" and "at or above 65536" are the same fact. The mutation that does go red is counting the units as the bytes — `Step(units: c.len, ..)` — and it reddens `positions_convert_both_ways`, `diagnostics_are_written_as_the_protocol_spells_them` and `colour_comes_from_the_lexer` together. Dropping the `+ 1` on the line still reddens as promised.

---

## 4. Transport and lifecycle

### Framing

stdio, JSON-RPC 2.0, `Content-Length: <n>\r\n\r\n<body>`, `n` in bytes. `Content-Type` is optional and ignored on the way in; not written on the way out.

### Reading — the capability, as built

**This section was the plan; what follows is what landed, and the two differ in one important place.** `Env` now carries `in: Stdin` beside `out: Console`.

This is a **capability**, so it is added the way `Fs` was and for the reason `src/std/env/env.zen:83` gives: "Every member added here is a member the self-hosted compiler has to keep working forever." The narrowest member that can carry JSON-RPC:

```
Stdin* = {
    read* = (self: @Self, buf :: Vec<u8>, n: usize) Res<usize, IoError>
}
```

Blocking, byte-counted, no line discipline — a `Content-Length` body is bytes and a reader that splits on newlines corrupts it. **No `read_line`.** The framing header is found by reading and scanning, which the server does anyway.

Cost, as estimated: one declaration with no body in `src/std/env/env.zen`, plus its floor in `gen_c`, at 60–90 lines. **Actual: `src/gen/gen_c/gen_c_stdin.zen`, 253 lines holding the lowering *and* the emitted C**, plus six lines of recognition in `gen_c_cap.zen` and a `needs` flag in `gen_c_state.zen`. It is its own file rather than an addition to `gen_c_cap.zen` for a boring reason and a good one: `gen_c_runtime.zen` was 37 lines under the 800-line cap, and one capability is one subject.

**`Vec.reserve` was not in the estimate and the capability cannot exist without it.** `read` has no `Alloc`, so by law 1 it has no memory, so it can only fill capacity that already exists — the room is the caller's to make. Asking for more than there is comes back `Full`, which is not a short read: at the one place a caller must be able to tell truncation from end of input, the two must not look alike.

**And the sentence this document got wrong: `read` reads EXACTLY `n` bytes and blocks until it has them.** "Blocking, byte-counted" was written as though a pipe hands over what it has; `fread` does not, and C offers no way to ask how many bytes a stream holds. So a reader that asks for a fixed chunk waits for bytes the client will not send until it has been answered, while the client waits for that answer — a deadlock with no visible cause. The fix is `short_by` in `src/lsp/lsp_frame.zen`: **ask the envelope how many bytes are missing and read exactly that many**, one byte at a time while the headers are still arriving. Any future reader of a stream in this language has the same obligation.

**One line of the C floor is load-bearing and is not about reading at all: `fflush(stdout)` before the `fread`.** C block-buffers a stdout that is not a terminal, so a server that answers and then blocks is holding its own answer. C99 permits an implementation to flush interactive streams at a blocking read; doing it explicitly makes it true for a pipe.

### Writing — the floor already exists

`src/gen/gen_c/gen_c_runtime.zen:159` already emits `zg_print_bytes(const char *s, size_t n) { fwrite(s, 1, n, stdout); }` and `:160` the `zg_str` form. So exact-byte output is already in the runtime and only the Zen-side signature is missing.

**And nothing had to be added: the `print` sugar already writes exact bytes.** `src/gen/gen_c/gen_c_print.zen:52` recognises `print` beside `println` and `:102` appends the newline only for the second, so `print(s)` is `fwrite(s.data, 1, s.len, stdout)` and nothing else. That landed with the print floor and this document did not notice it. `L0`'s "byte-exact stdout" was already done.

The `Sink` question below therefore did not gate L1 and is still open on its own merits: `DESIGN.md:213` says "a console is a sink, a `String` is a sink", and `Console.impl(Sink, ..)` would make `Console` usable everywhere a `Sink` is.

**Cost to accept knowingly, when someone does it:** an impl of a bound is a fat value, and `gen_c_cap.zen`'s header records that this backend "does not build one yet" for `Alloc`. ~~That refusal is the single most likely thing to block L1~~ — it blocked nothing, because `print` was already there.

### JSON — what it costs

Nothing in the tree parses or emits JSON. Concretely:

- **The value type is an arena, not a tree.** `Json = Null | Bool | Num | Str | Arr | Obj` is recursive, and `src/AST_CONTRACT.md` rule 2 already settled what this tree does about recursion: a child is an id, never a value, because "an `Expr` containing an `Expr` has no size". JSON gets a `JsonId` and a `Json` arena for the same reason, not as a stylistic echo.
- **The reader must implement JSON's number and string grammars, which are not Zen's.** `1e10` and `-0` are JSON numbers; `DESIGN.md:99` rejects a leading zero and `:100` rejects `12.`. `é` is a **hex** escape in a language `DESIGN.md:101` gives no hex literals, and a `😀` pair must be recombined into one codepoint before it is UTF-8 encoded. That last item is the one that gets skipped and then reappears as a position bug in §3.
- **One nominal error, not a union.** `PLAN.md:222` puts error unions outside the seed subset, so the reader carries a single `JsonFault`.
- Estimate: **250–400 lines** for reader plus writer plus escapes, and a corpus test per `TESTING.md:27`.

**Where it goes: `src/std/json/`, where the second-caller rule has since moved it.** `STYLE.md`'s stranger test said JSON belongs in `std` on sight — "parses a JSON document" names no module — and `src/lsp/lsp_json.zen` started life with a header note saying exactly that: it would stay in `src/lsp/` only until something that is not the LSP wanted it. That caller arrived, and the module moved to `std.json` whole: same streaming arena, same lexeme-carrying numbers, same zero allocations on the reply path. Against that stands `src/std/env/env.zen`'s rule about members the compiler must keep working forever — and the answer to it is what this module always was, a transport primitive and not a document model, which the compiler will never need to parse.

### Lifecycle

| phase | rule |
|---|---|
| before `initialize` | every request answered `-32002 ServerNotInitialized`; every notification except `exit` dropped |
| `initialize` → result | server capabilities and `serverInfo`. Sync kind is **Full** (§5) |
| `initialized` | notification; work may begin |
| running | requests dispatched; `$/cancelRequest` **dropped**, see below |
| `shutdown` | reply `null`, stop accepting work, do not exit |
| `exit` | exit **0** if `shutdown` was received, **1** otherwise |

Those exit codes fit what is already there: `main` returns `Res<i32, AllocError>` (`src/zen/zen.zen:33`) and `usage` deliberately returns 2 rather than 1 (`src/zen/zen.zen:154`) because "this build found problems" and "I could not tell what you asked for" are different answers. The LSP adds a third pair and no new mechanism.

**`$/cancelRequest` is DROPPED, and this document used to say "recorded" and "honoured between requests" — as built it is neither.** A build is a build (§5); there is no yield point in `check_all`, the server is single-threaded, and a request is answered before the next message is read — so a cancel that arrives can only ever refer to work that is already finished, and recording it would be a field nothing reads. `lsp_serve.zen` drops it with `initialized`, `exit` and `didClose`, in the arm that names all four rather than leaving four empty branches. Saying this out loud beats a server that advertises cancellation it cannot perform.

### The CLI

`Cli.Later(str)` (`src/zen/zen_cli.zen:42`) already names `lsp` beside `test`, and `src/zen/zen.zen:53` already dispatches it to the server — the "not yet — see docs/PLAN.md for the stage it arrives at" answer at `:59` is `test`'s alone now. So `zen lsp` cost one branch and one call. **It takes no arguments in L1.** A root is discovered from `initialize`'s `rootUri`, and `--entry` (`src/zen/zen_cli.zen:51`) has an editor-side equivalent that L1 does not need: the server builds the root, and `DESIGN.md:430` already says the driver probes when no entry is named.

---

## 5. Document sync, and what a build actually is

### Can the compiler reparse one file? No.

`zen build` today, in order: `build` (`src/zen/zen_run.zen:35`) constructs a `Build`, resolves the entry with `entry_of` (`src/zen/zen_path.zen:217`), then `walk` (`src/zen/zen_build.zen:185`) breadth-first over the import graph, reading each module through `env.fs.read` (`:272`), lexing (`:332`) and parsing (`:364`) each into **one shared `Ast`**; then `back_end` (`:572`) and `check_tree` (`:586`) build **one `Checker`** over the finished tree and run `check_all` (`src/sema/sema_decl.zen:56`).

Three structural reasons a single file cannot be redone in place, each already written down in the tree:

1. **Ids are indices in creation order** (`src/AST_CONTRACT.md`, "Ast — the arena"). Re-parsing a module in the middle of the walk renumbers every node after it, and every memo is keyed on those ids.
2. **The `Checker` copies the `Ast` and requires it finished** — `src/zen/zen_build.zen:172` states it: "a `Checker` copies the `Ast` as a value, so a copy is a snapshot."
3. **Compilation is whole-program** (`DESIGN.md:67`), and `gen_c` emits each generic instantiation exactly once. There is no unit smaller than the program.

### So: full sync, whole builds, and a debounce

`TextDocumentSyncKind.Full`. **Incremental sync would be a lie**: the server would apply a range edit into a buffer and then hand the whole buffer to a whole-program compiler. It buys nothing and costs a second, subtly different, implementation of text-range arithmetic beside §3's.

The per-keystroke cost is one `zen build src`. The mitigations that are *not* incremental compilation:

- **Debounce.** Build after a quiet interval, not per `didChange`. The interval is a setting with a default; it is not a compiler concern.
- **Coalesce.** A `didChange` arriving during a build supersedes it; the build in flight is finished and its results discarded rather than published.
- **Never build on `didOpen` of a file already covered by the last build.**

`PLAN.md:345` is the standing note on this: if it is still too slow after that, the fix is in sema's query granularity and belongs there, not here.

#### Two of those three landed, and the DEBOUNCE cannot be written — BUILT 2026-08-08

**The first bullet is not implementable by this server and saying why is more useful than the bullet.** A quiet interval is something a server *observes*, and observing it needs one of three things this tree does not have: a non-blocking read, a read with a timeout, or a second thread. `Stdin.read` blocks until it has exactly the bytes it was asked for (§4, and it is the property that made `short_by` necessary); there is no clock capability; and `PLAN.md` puts threads at stage 5 while the compiler is written in the seed subset. A "debounce" built on a blocking read is a timer that fires when the next keystroke arrives, which is the opposite of the thing.

**What replaced it is a settle point, and it makes bullet two stronger rather than weaker.** `didOpen` and `didChange` MARK a document as owing a build and return; the transport calls `Server.settled` when it has answered every message it currently holds. So:

- **Coalescing is by construction.** Every change in one batch collapses to one build of the LAST buffer. The superseded build is never *started*, where the bullet above only asked for its results to be discarded — and "an older result must not overwrite a newer one" is then not a race that is handled but a race that cannot occur, because there is one build at a time and it is the newest document's.
- **Over a buffer this is a whole batch; over the pipe it is every message.** `short_by` asks for exactly one message's bytes, so `lsp_stdio.zen`'s reader holds one frame at a time and cannot know whether more is waiting. `serve` — which the corpus drives — coalesces properly, and `tests/corpus/lsp/diagnostics_publish_and_clear` measures it: two document notifications, one round of publishes. **Over a real editor it coalesces nothing yet, and the missing piece is a read that can say "nothing more is waiting".** That is the honest state and it is written in `lsp_diag.zen`'s header too.
- **The third bullet landed as the narrower thing a server can actually know**: `didOpen` or `didChange` carrying bytes the document already holds marks nothing at all. It does not know which modules the last build walked, so it cannot answer the bullet as written; it can answer "this buffer did not change", which is what an editor re-sending `didOpen` produces.

**And a refusal worth recording: no workspace, no diagnostics.** Hover degrades to a lone-module check when there is no `rootUri`, because hover's failure mode is silence. Diagnostics' failure mode is *noise* — a lone-module check reports every imported name as undefined, which for any real file is a screenful of red about a program that is fine — so this one does not degrade at all. Same for a `rootUri` the open document is not under, which climbs to an empty root.

### The overlay

`Fs.read` reads the disk (`src/std/env/env.zen:94`). An unsaved buffer is not on the disk. Two ways to interpose:

1. **A user-written `Fs` whose `read` consults an overlay first.** Wrong twice: `Fs`'s members have no bodies because they *are* the authority (`src/gen/gen_c/gen_c_cap.zen:1`), and a value of a bound type is a fat value the backend may not build yet (`:28`).
2. **A `Map<str, String>` field on `Build`, consulted by `Build.read` (`src/zen/zen_build.zen:260`) before `env.fs.read`.** One field, one branch, no new language feature, keyed on `Unit.path`.

**Take (2), and say what it costs.** This is the LSP reaching into the driver, and it is the one place the "thin server over compiler internals" thesis bends. The price is one field on `Build` and the honesty of writing in its comment that the overlay exists for the editor. The alternative — a private copy of `walk` in `src/lsp/` — is the second implementation this whole document exists to prevent.

#### "One field and one branch" was the wrong estimate — BUILT 2026-08-08

**The interposition really was one field and one branch**, exactly as specified: `Build.overlay` is a `Map<str, str>` keyed on `Unit.path`, and `Build.read` consults it before `env.fs.read`. Every other line below is code that made that branch reachable.

An earlier agent refused to land the field on its own and priced the rest. It named three costs, and all three were real:

1. **The LSP could not drive a `Build` at all.** `entry_of`, `walk` and `back_end` were private and the only public entry was `run_once`, returning an exit code. **Now `Build.whole(named, docs)`** — walk a root, check it, hand the `Checker` back. No emit.
2. **`check_tree` created the `Checker` locally and dropped it.** **Now `Build.checked`**, the one place a `Checker` comes from, called by `check_tree` and by `whole`. It **hands the value back rather than storing it in a field**, and the correction is worth recording: a `Checker`'s `Map`s are headers, so a copy retained on the `Build` mid-build would silently stop agreeing with the one `emit` goes on using. "`Build` has to retain it" was the wrong shape; "`Build` has to stop dropping it" was the requirement.
3. **`lsp_hover` had to stop being a single-module check**, and the server had to store `rootUri`. Both landed — `hover_in`, and `Server.workspace`.

**And four costs neither estimate had.** Each is the same shape as the original error — the code at the seam was priced and the code that makes the seam usable was not:

4. **`zen_build.zen` was AT its 800-line cap.** The overlay could not be added until the file was split, which is two moves: the entry probe (`entry_of` and its three helpers, plus `ENTRY`) to `zen_path.zen` as free functions, and `run_once` to `zen_run.zen`, whose subject it already was. Neither is optional and neither is part of the feature.
5. **The workspace root is not the compilation root.** An editor's `rootUri` is the repository — `root_markers = { "build.zen", ".git" }`, §6 — and this tree builds as `zen build src`. Resolving `lex.lex` against the repository finds nothing, which is indistinguishable from having no build at all, so hover would have answered `null` on every file in `src/` while looking like it worked. `zen_path.root_for` computes the root by climbing out of every directory that holds its own name, which is this file's own `<folder>/<folder>.zen` rule read upward.
6. **The driver PRINTS its lex and parse diagnostics, and a server must not.** `println` writes to stdout, which is where JSON-RPC frames go (§6), and **a buffer being edited has an unclosed brace in it most of the time** — so this is the common case for this reader, not a corner. `Build.speaking` is false under `whole`; the `Vec` still fills, which is what leaves `publishDiagnostics` something to publish.
7. **`Build.permute` is an exported field, and mutation of one goes through an exported method.** Moving `run_once` out of the module turned `b.permute = ..` into a diagnostic. One method, `walk_order`.

**And one that is not about this feature at all**: `bootstrap/gen_c.py`'s `MAX_INSTANCES` was 4096, and `corpus/cli/build_walks_a_root_it_is_given` — which stages the whole driver — already emitted 4086 functions. Ten of headroom. The `src/lsp` → `src/zen` import this section *ratifies* took it to 4099 and **eleven tests in two suites went red**, with a diagnostic naming an arbitrary `std` function rather than the size. A guard on divergence is unaffected by the number; a guard on a program's size is what 4096 had quietly become. It is 8192 now.

**The lesson generalises past this section, and it generalised twice.** The estimate counted the code at the seam and not the code that makes the seam reachable — and then the *revised* estimate did the same thing one level up, counting the seam's neighbours and not the file's line cap, the root discovery, the printing, or a constant in the other compiler. Any estimate in this document that names a line count should be read as "the edit", never "the change".

### What a build COSTS a session, which nothing above priced — BUILT

Every estimate in this section counted a build in *seconds*. The number that ended up mattering is megabytes, and it is the one failure mode a corpus test cannot see: a server that answers every request correctly and grows until the machine swaps.

A build of this tree is **~10 MB of arena pages** — the walk, the tree, the `Checker`'s memos. Before `src/lsp/lsp_built.zen` existed, every one of them — the settle's *and* each query's own — allocated from the **session** arena, which reclaims nothing before the process exits. So RSS grew by a whole-program build **per request**: a keystroke that also hovered is a settle, a hover and a completion, three builds, ~30 MB, permanent.

Two rules fix it, and `lsp_built.zen`'s header is where they are written because a caller has to obey the second one:

1. **A build's pages die with its replacement.** One arena per build, holding everything that build produced, dropped as a whole when the next build replaces it. The drop is EXPLICIT — a struct field carries no drop glue in this language — and forgetting the call leaks exactly as the session arena did.
2. **One build per document state, single-flight.** The settle and every query against the same state share one build, keyed on what a build READS: the root, the entry, and every open buffer's bytes. This is the stale-state stamp this section asks for, as a **content comparison rather than a version counter** — which is the same fact `lsp_serve.zen`'s unchanged-buffer skip already relies on, so there is one notion of "changed" in the server and not two.

**The constraint that falls out, and it binds every query in the folder:** nothing allocated from the slot may be kept past the next `ensure`, because eviction frees those pages. An answer is written into the *caller's* arena within the request; anything the server keeps across requests (the URIs currently showing errors) is copied into the session arena deliberately.

### Diagnostics have to escape the driver — **DONE**

`publishDiagnostics` needs `Diag` values, not printed lines. Sema was always fine (`diag_count`/`diag_at`, `src/sema/sema_check.zen:197,199`); **lex and parse were not** — the driver `println`'d them and dropped them.

**Landed 2026-08-08.** `Build` holds `diags: Vec<Diag>` and answers the same `diag_count`/`diag_at` pair `Checker` exports. No fourth struct was invented: `Diag` **is** `parse.parse_diag.Diag`, which that file's own header had already asked for. `report` prints *from* the `Vec` rather than from its argument, so the collection is load-bearing rather than a copy nobody reads — removing it silences the printing and takes all thirteen `must-fail/parse` tests red.

`Diag.note` also escapes now. It was being collected and never printed at all, so every note `diag_at` carried — including `expect_close`'s "the parser gave up here" — was thrown away.

**And they are published — 2026-08-08, `src/lsp/lsp_diag.zen`.** `Build.whole` hands back a `Checker` (whose `diag_count`/`diag_at` are sema's) and leaves `faults` and `diags` on the `Build` (which are lex's and parse's); the server reads both, because an editor showing type errors and silently not showing syntax errors teaches a user to distrust it. Four decisions were the whole of the work, and none of them was a missing query:

- **WHEN**: the settle point above.
- **WHICH FILE**: a build reports across the program, so a diagnostic is grouped by the URI its own `span.file` names — `<root>/<rel>` through `lsp_uri.uri_at`, which is `path_of` read backwards so the URI built for the open document is byte-identical to the one the client opened it with. One notification per file. Publishing another file's errors against the open document would be a wrong answer, and this folder's rule is that a wrong answer is worse than none.
- **CLEARING**: the protocol has no "remove" — a notification REPLACES a file's list — so an empty list is the only way to take an error back. The server keeps the set of URIs currently showing errors and publishes an empty list for every one this build found nothing in, plus always for the document that triggered it. **A server that publishes only what it finds leaves errors the user has already fixed on screen forever**, which is worse than publishing nothing.
- **SEVERITY**: 1, Error, for everything, and that is a fact about this compiler rather than a simplification — one tally, one exit code off it, and no phase produces anything a build survives. One constant changes on the day there is a warning.

**`Diag.note` becomes `relatedInformation`**, which is where the second half of the morning's work landed. A note is a sentence AND a span; folding it into the message throws the span away and leaves the reader told to look somewhere with no way to go there. Sema's second position stays inside its own sentence, because `write_detail` already writes a `PairFault`'s two declarations and lifting one out would be a second, divergent copy of how sema words a two-place diagnostic.

**Gates**: `tests/corpus/lsp/diagnostics_are_written_as_the_protocol_spells_them` is the writer over a table of hand-built spots — the empty list, two in one file, grouping across two, the note, a UTF-16 column past a two-byte character, and escaping. `tests/corpus/lsp/diagnostics_publish_and_clear` is a real session over framed JSON-RPC with a real build behind it: a parse fault in one buffer and a sema fault in another, published separately, then both taken back. Six mutations were run against the pair — dropping the parse diagnostics, dropping `take_back`, dropping the always-publish of the edited document, dropping the note, dropping the grouping, and dropping the unchanged-bytes skip — and every one of them went red.

**Known divergence, unreconciled:** the two compilers anchor the unclosed-delimiter note differently *and* word it differently — `./zen` says `3:24: the parser gave up here` (where the parser stopped), `bootstrap/` says `5:1: \`}\` here closes nothing` (the closer that arrived). A `.expected` asserts one substring plus positions that must all be reported, so **no shared expectation file can assert that note**. Neither anchor is obviously wrong.

---

## 6. Clients

**Both clients now exist, in `editors/`.** This section was written before they did, and what got built diverges from it in two places on purpose — both recorded below rather than quietly reconciled. `editors/README.md` is the user-facing half; this is the design half.

```
editors/
├── README.md                     what works, what does not, and how to install
├── nvim/zen.lua                  filetype + tree-sitter + vim.lsp.config
├── nvim/queries/zen/highlights.scm
└── vscode/                       TypeScript, vscode-languageclient, stdio
```

### What each client gets, per stage

The L1–L4 staging in §2 is about the SERVER. This is the same staging read from the editor, because that is what a user actually experiences — and the two are not the same shape: colour arrives in Neovim without the server at all, and in VS Code through it.

| | Neovim | VS Code |
|---|---|---|
| **colour** | **works**, tree-sitter, no server — and it does NOT come from `semanticTokens`, which changes nothing for Neovim | **works** — `semanticTokens`, from the compiler's own lexer and, on a clean build, its checker; the deviation below explains why it is not a TextMate grammar |
| brackets, comment toggling, word selection | tree-sitter | **works now**, `language-configuration.json` |
| **hover** | **works** — the transport landed, and so did the build behind it | **works** |
| go-to-definition | **works** — module-level names, call sites, members, written types; locals and pattern binders answer `null` (the L3 gap) | same |
| document symbols / outline | **works** — flat, top-level, off the buffer alone | same, plus the breadcrumb bar for free |
| **diagnostics as you type** | **works** — all three phases, grouped per file, cleared when fixed; §5 has the trigger policy | **works** |
| completion | **works** — members after a dot (via the backward scan and a dummy identifier), scope names and the three reserved words otherwise; no locals, no UFCS candidates | same |
| format on save | L3 — engine exists, request does not | same |
| references, rename, signature help | L4 | L4 |

**That sentence used to read "everything except colour is blocked on the same one thing" — the server could not read a pipe.** `Env.in` landed and hover landed behind it, so the remaining rows are each blocked on their own request and nothing shared. Neither client changed when the transport arrived, exactly as predicted: it is `zen.server.args` in VS Code and `M.cmd` in Neovim, one line each, and neither needed touching.

### Neovim

Filetype detection first — `.zen` is not a filetype Neovim knows:

```lua
vim.filetype.add({ extension = { zen = "zen" } })
```

Then the server, with no plugin and no `lspconfig` dependency:

```lua
vim.lsp.config("zen", {
  cmd = { "zen", "lsp" },
  filetypes = { "zen" },
  root_markers = { "build.zen", ".git" },
})
vim.lsp.enable("zen")
```

**DEVIATION 1, and it is just a version.** This document originally specified the `vim.lsp.start` autocmd below; `editors/nvim/zen.lua` uses `vim.lsp.config`/`vim.lsp.enable`, which is the current API from Neovim 0.11 and what the machine this was built on runs. The autocmd form still works and is kept here for 0.10 and earlier:

```lua
vim.api.nvim_create_autocmd("FileType", {
  pattern = "zen",
  callback = function(args)
    vim.lsp.start({
      name = "zen",
      cmd = { "zen", "lsp" },
      root_dir = vim.fs.root(args.buf, { "build.zen", ".git" }),
    }, { bufnr = args.buf })
  end,
})
```

`editors/nvim/zen.lua` splits `setup()` into `.filetype()`, `.treesitter()` and `.lsp()` for one reason worth stating: **the highlighting half works today and the LSP half does not**, so a user should be able to take the half that works without the half that exits 2.

`vim.fs.root` looking for `build.zen` is right for this language: `DESIGN.md` makes a build file a program and `PLAN.md`'s tree puts `build.zen` at the repository root, so it is the marker that means "this is a Zen project" — with `.git` as the fallback for a tree that has not got one yet.

Two Neovim-specific notes worth having written down. Neovim advertises `general.positionEncodings` including `utf-8`, so it is the client that can exercise the short-circuit in §3 — which makes it a **bad** default for testing the conversion and a good one for testing that negotiation works. Test the UTF-16 path against a client that only speaks UTF-16. And Neovim's `vim.lsp.start` reuses a client with the same `name` and `root_dir`, so a crashed server is silently not restarted; during L1 development, restart explicitly.

Syntax highlighting is separate and already exists: `grammar/` is a tree-sitter grammar, `DESIGN.md:30` says it "outlives the bootstrap as the editor and LSP grammar". Highlighting is tree-sitter's job in Neovim, and `semanticTokens` is a refinement over it, not a replacement — **so `lsp_colour.zen` landing changed nothing for Neovim**, which had colour before the server could read a pipe and has the same colour now. It is VS Code that had none, because it is VS Code that cannot load `grammar/`.

### VS Code, and this is a remote instance

**The constraint first, because it changes the answer.** This work is being done on a **remote VS Code instance** — the workspace, the source tree, and the compiler all live on the remote host; only the UI runs locally. An extension that gets this wrong appears to install correctly and then cannot find the server.

| piece | where it runs | why |
|---|---|---|
| the `zen` binary / `zen lsp` | **remote** | it reads the workspace off the remote filesystem, through `env.fs` |
| the extension host running `activate()` | **remote** | it must spawn a process next to the source |
| `LanguageClient` and the `ServerOptions` | **remote** | it spawns the server |
| the tree-sitter grammar for TextMate-style highlighting | **local (UI)** | declarative `contributes.grammars`, no process |
| settings UI, commands in the palette, the output channel | **local (UI), talking to remote** | VS Code bridges these |

So `package.json` must declare:

```json
{
  "extensionKind": ["workspace"],
  "activationEvents": ["onLanguage:zen"],
  "contributes": {
    "languages": [{ "id": "zen", "extensions": [".zen"], "configuration": "./language-configuration.json" }],
    "configuration": { "properties": { "zen.server.path": { "type": "string", "default": "./zen" } } }
  }
}
```

**DEVIATION 2, and this one is a real decision that should be ratified or overruled.** The sketch above originally contributed a `grammars` entry pointing at `./syntaxes/zen.tmLanguage.json`. **`editors/vscode/` ships no TextMate grammar, and the line is gone.**

- Hand-writing one is the second grammar `PLAN.md:137` names in those words as the failure the plan exists to prevent — and unlike the tree-sitter grammar, nothing would gate it, so it would drift the first time the language moved.
- Generating one from `grammar/` would be a third generated artifact, and `PLAN.md:127` says an ungated generated file is "a fork nobody is reading".
- VS Code has **no public API** for loading a tree-sitter grammar from an extension, so `grammar/` cannot simply be reused there the way Neovim reuses it.

**That cost has now been PAID, and it was the price this paragraph named.** It used to read "no colour at all until the server answers `semanticTokens`"; the server answers it. `src/lsp/lsp_colour.zen` is the whole of it, the colours come from the compiler's own lexer and therefore cannot disagree with the compiler, and no second grammar and no third generated artifact entered the tree. The colour section in §2 has the design; the refusal above is unchanged and was right.

The alternative — a second copy of the syntax rules, for colour sooner — is now moot, and the record of the choice is kept because the *reasoning* is what generalises: the query that already exists beats the artifact that would have to be maintained. **What VS Code still gets from `language-configuration.json` rather than from the server is brackets, comment toggling and word selection**, which are configuration and not colour.

**One thing about colour in VS Code that no server can control**, and it is worth knowing before someone reports a bug: semantic tokens are applied only when semantic highlighting is enabled. `editor.semanticHighlighting.enabled` defaults to `configuredByTheme` and every stock theme turns it on, but a user who has set it to `false` gets a perfectly correct token list that colours nothing, with nothing on screen to say why. `extension.ts` says so in the output channel at startup, because that is the same shape of silent failure as a server exiting 2 on an argument it did not recognise.

`"extensionKind": ["workspace"]` is the load-bearing line. Without it VS Code may install the extension on the UI side, where `activate()` runs on the local machine, `zen` is not on the PATH, the workspace is not on the disk, and the failure reads as "the server crashed".

Four more things this constrains:

- **The server path resolves on the remote.** `zen.server.path` must be read with the *remote* extension host's view of the filesystem, and a workspace-relative default (`./zen`, the binary `make build` produces) is more useful here than a global `zen`.
- **Document URIs are `vscode-remote://…`, not `file://`.** The server must convert a URI to a path and back, and it must do it for the scheme it is actually sent. This is a small function and it belongs beside `lsp_pos.zen` — same class of bug, same rule about living in one place.
- **VS Code does not offer `utf-8` position encoding.** So the UTF-16 conversion in §3 is not optional and VS Code is the client that proves it.
- **Debugging is remote.** `console.log` from `activate()` lands in the remote extension host log, and the server's own stderr lands wherever the extension host puts it — not in the local terminal. Route the server's diagnostics through an LSP `window/logMessage` and an output channel, and **never write anything to stdout that is not a JSON-RPC frame**: `println` (`src/std/env/env.zen:38`) writes to stdout, so a stray debug print corrupts the protocol stream and the failure looks like a parse error in the client. That is a real hazard in this tree specifically, because `println` needs no capability parameter to reach.

---

## 7. The stages, and a gate for each

`PLAN.md:135`: "Every stage ends at a gate that can fail. Not 'the code is written' — a command that exits non-zero when the stage is wrong. … Before trusting a new gate, break the thing it guards on purpose and watch it go red."

Every gate below is a `make` target or a suite under `tests/`, in the format `TESTING.md:27` fixes. **No gate below is "the editor feels right."**

### L0 — the two capabilities

Stdin, and byte-exact stdout. Before any protocol code.

**Gate, and it is green:** `tests/corpus/env/stdin_echoes_its_bytes_exactly` reads its own stdin and writes the bytes back with no newline added, byte-compared. The harness could not feed a program stdin at all; `.stdin` is the sidecar that was added for it, and `docs/TESTING.md` names it. And the existing gates stay green — `make test`, `make fixpoint` — because a new capability member is a change to `std` and to `gen_c`, and `TESTING.md:11` says what the fixpoint is worth. **Break it on purpose:** make the write append a newline and watch the byte comparison fail.

### L1 — transport, lifecycle, sync, diagnostics — **DONE**

JSON in and out. Framing. `initialize`/`initialized`/`shutdown`/`exit`. Full document sync into a `Build` overlay. `publishDiagnostics` from all three phases.

**Gates**, three of them:

1. **JSON round-trip**, a corpus test: a table of documents parsed and re-emitted, compared byte for byte, plus a table of malformed documents that must be rejected with a position. Both directions, per `TESTING.md:17` — "a rejection with the wrong span is a failure".
2. **A scripted session**: a recorded sequence of frames on stdin, the server's frames on stdout compared against a `.expected`. This is `tests/corpus/cli/cli_reads_an_explicit_entry.zen`'s shape one level up — a pure-ish function handed inputs no real client would produce.
3. **Diagnostic parity**: for every program in `tests/must-fail/`, the diagnostics `zen lsp` publishes name the same positions the `.expected` file already asserts. **This gate is free** — the expectations exist — and it is the one that catches the server inventing its own positions. Break it by shifting a column by one and watch every row go red.

Gates 1 and 2 are green (`json_round_trips_and_rejects`, `a_session_is_answered_frame_by_frame`, `frames_arrive_over_stdin`). **Gate 3 is still not written**, and it is the one that is left: `diagnostics_publish_and_clear` asserts a session and `diagnostics_are_written_as_the_protocol_spells_them` asserts the shape, but neither sweeps the 117 `must-fail` expectations, so nothing yet proves the wire positions and the compiler's positions are the same numbers over a corpus. It is still free and it is still the cheapest remaining L1 work.

**L1 is done when** an editor connected to `zen lsp` shows the same errors, at the same places, as `zen build`. The first half is true; the second half is exactly what gate 3 would measure.

### L2 — the queries that already exist — **DONE**

Hover, definition, documentSymbol, lexical semanticTokens. No new sema.

**All four are built.** Hover, and `semanticTokens/full` in its lexical form (`src/lsp/lsp_colour.zen`, §2's colour section), and now `definition` (`src/lsp/lsp_def.zen` — `call_memo`, `defs_of`, `Found.span`, exactly the queries the table above priced) and `documentSymbol` (`src/lsp/lsp_symbol.zen`, off the AST alone). The name finder hover introduced moved to `src/std/ast/ast_named.zen` on its second caller, as its own header had scheduled.

**Gate:** a query corpus. Each test is a source file with cursor positions and the expected answer — for hover the type name `Types.name_of` produces, for definition a `file:line:col`, for documentSymbol the list. Same `.expected` format, same byte comparison. The positions are asserted in **Zen** coordinates in the fixture and converted at the wire, so a failure separates "the query is wrong" from "the conversion is wrong". Break it by returning the enclosing node instead of the smallest and watch hover go red.

**Hover's half of that gate exists**: `tests/corpus/lsp/hover_answers_at_a_declaration`, an 18-row position table driven through framed JSON-RPC, asserting the value and the range together. It was mutation-verified against each of the three paths it guards — the name finder, the signature reprint and the poison refusal — and against the two `null` controls. See the hover section in §2.

**Colour's half exists too**: `tests/corpus/lsp/colour_comes_from_the_lexer`, which drives the server and then decodes the delta encoding back through `to_pos` so every row prints the bytes it colours. Ten mutations, nine red, and the tenth is an equivalent mutant §3 wrongly predicted would fire — both facts are in §2's colour section. **Break it on purpose:** make `deltaLine` absolute and watch the file's colour slide down the page.

**And the semantic half's gate is `tests/corpus/lsp/colour_comes_from_the_build`** (L4's row, landed early): a two-module build behind framed JSON-RPC, pinning that a type, a function and a parameter come back as three distinct indices, that the answer rides the diagnostics' build rather than running one of its own, and that a file with an undefined name is answered lexically — every identifier `variable` — until it compiles again. Mutation-verified on both new classifications.

Plus the §3 conversion gate, which lands here at the latest and preferably in L1.

### L3 — the queries that need sema work

References (a reverse index) and locals with spans. Formatting was priced here as waiting on `PLAN.md` stage 2 and landed with no sema work at all once stage 2 existed: `src/lsp/lsp_fmt.zen` is the buffer, `render`, and a `TextEdit` — the whole cost was deciding that a buffer which does not parse is answered `[]` rather than an error. Completion was priced here for its two gaps and landed with neither: the backward scan closed the incomplete-parse half, and collecting candidate strings for `defs_of` to judge stood in for the prefix form.

**Gate:** the same query corpus, extended. Plus, for references specifically, a property: **for every `Def` in `src/`, every reference the server reports must resolve back to that same `Def`.** Run it over the compiler's own tree — 90-odd modules is a better corpus than anything written by hand, and it is the corpus this tree already dogfoods.

### L4 — the expensive ones

~~Semantic tokens with RESOLUTION — the lexical form is L2 and done; what is L4 is telling a type from a function from a parameter, which no lexer can~~ — **the first of the three LANDED** (§2's colour section and table row): `type`, `function` and `parameter` joined the legend, the answers come off the diagnostics' build, and a file with errors keeps its lexical colours. What remains here is signature help and rename.

**Gate for rename, and it is the only interesting one:** a rename applied to a copy of `src/` must leave the tree **compiling and byte-identical at the fixpoint after the inverse rename**. That is `make fixpoint` used as a rename oracle, it costs almost nothing because the script exists (`scripts/fixpoint.sh`), and it is the only test that can catch the two hazards in §2 — a UFCS call site that never named the function, and a variant name that changed what an unrelated declaration means.

---

## 8. Open questions

Listed rather than guessed, per `PLAN.md:5`.

1. ~~**Does `Console.impl(Sink, ..)` compile today?**~~ **Moot for L1.** The `print` sugar already writes exact bytes, so L0 needed no new writer at all. The `Sink` impl remains worth doing and is no longer on anyone's critical path.
2. ~~**Where does JSON live?**~~ **Overruled by events, in the direction the stranger test pointed.** It lives in `std.json` (`src/std/json/`) as of the second-caller move; the env.zen "keep working forever" concern was answered by what the module always was — a streaming arena with zero allocations on the reply path, not a document model.
3. **Should `Pos` carry a byte offset?** `src/std/lex/lex_token.zen:26` has one and `src/std/ast/ast_span.zen:22` does not. Adding one to the AST's `Pos` makes the §3 conversion cheaper and slicing source off a span direct — and it is one more word on every position in the tree, which `src/AST_CONTRACT.md` was careful about for trivia. Not resolvable from the tree: it needs a measurement.
4. **What is the server's compilation root when `rootUri` is a directory with no entry?** `DESIGN.md:430` gives `zen build <root> --entry <file>` for exactly this, and `src/zen/zen_path.zen:249` probes `main`, then the root's basename, then `zen`. An editor opening a single file outside any root has none of those. Is that an error, a diagnostic, or a degraded mode that lexes and does not check?
5. **Is `zen lsp` allowed a second thread?** `Threads` exists (`src/std/env/env.zen:134`) but `PLAN.md` puts actors and threads at stage 5 and the compiler is written in the seed subset (`PLAN.md:222`), which excludes them. A single-threaded server cannot answer `shutdown` during a build. This document assumes single-threaded and says cancellation is honoured between requests; whether that is acceptable is a call nobody has made.
6. **Does `expr_memo` hold an answer for every expression after `check_all`?** Hover in L2 depends on it — the design is "run the check, then read the memo, and never reconstruct a `Ctx`". `compute_expr` writes a poison entry before computing, so *some* entry exists for anything walked. **The answer is no, and one instance is now closed and known:** a name in the base of a field access was typed by `sema_member.base_of` out of the scope, never reached `type_of`, and so was never recorded — `base_of` records it now. That is the shape of the question: not "does the walk reach it" but "does the path that types it go through the memo". Every path that does not is another such hole, and nothing enumerates them.
7. **`PLAN.md:363`'s memo-key note.** "`type_of`'s memo key is the node id alone, which is sound only while a generic body is checked once… that key is on the critical path for hover being *correct* inside a generic." `src/sema/sema.zen:26` argues monomorphisation did not force a re-key because an instantiation changes the answer at a **call site**, which `ExprId` already separates. Those two statements are not obviously the same statement. Hover inside a generic body is where the difference shows, and no test asserts it.
8. **Is trivia reachable from a position?** `Ast.trivia` is one list and a node names a run of it (`src/std/ast/ast_arena.zen:34`), but `node_at` deliberately answers `None` inside a comment (`src/std/ast/ast_find.zen:53`). Hover over a doc comment, and completion inside one, both need to know they are in trivia — and finding out costs a scan of a list nothing indexes by position.
