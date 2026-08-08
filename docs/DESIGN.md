# Zen

**Performance is locked down, not hoped for.** Benches live next to tests (take a `Bencher` like tests take a `Tester`), budgets are code in build.zen, and a regression fails the build. That includes the build itself: a 20 minute build is a bug, and bugs fail CI. **Not implemented:** `Bencher` and `BenchStats` are declared in `std.test`, `Budget` in `std.build`, and the benches are written in `tests/bench/` — but the root `build.zen` that would run one against the other is stage 1 in `PLAN.md` and is not in the tree, so no budget gates anything.

**Pipeline:** `mod_resolver -> lexer -> parser -> sema -> codegen`

One stage per module, and modules are `<folder>/<folder>.zen` — a folder carries its root beside its children, so `src/gen/gen.zen` is module `gen` and `src/ast/ast.zen` is module `ast`.

```
build.zen              // this project's own build file. stage 1; not in the tree
src/zen/zen.zen        // thin cli: build / fmt / test / lsp
src/ast/ast.zen        // THE ast. the compiler, @meta and gen_c all consume these nodes
src/lex/lex.zen
src/parse/parse.zen
src/sema/sema.zen
src/gen/gen.zen        // backend-shared plumbing
src/gen/gen_c/gen_c.zen  // the c backend
src/zen/zen_build.zen  // the build driver behind `zen build`
src/std/...            // the stdlib specified below. ~34 modules.
```

`src/ast/ast.zen` is the keystone: one AST with three consumers, which is what makes `@meta` a view onto the compiler's own nodes rather than a parallel universe.

**The full tree — including the bootstrapper, the seed, the test corpora, and which stage each piece appears at — lives in `PLAN.md`.** It is the authority; this sketch shows only the shape.

---

# How the compiler gets built

The bootstrap is a throwaway: **Python + a tree-sitter grammar → the real compiler → `gen_c` → the generated C ships as stage 0.** From then on a user needs only a C compiler to build Zen. The bootstrapper is a developer dependency for regenerating the seed, never a shipped artifact — which is why it is written in Python and not in C. The tree-sitter grammar outlives the bootstrap as the editor and LSP grammar.

**The grammar is written first, not extracted later.** It is the stage-0 artifact anyway, and writing the rules rather than more examples is what surfaces the ambiguities — the first one already found is that `Alias = Shape` is indistinguishable from a one-variant enum unless the grammar says which.

Two properties designed in rather than discovered:

- **`gen_c` is deterministic.** Same input, byte-identical output. Otherwise every seed regeneration is a noisy diff nobody reviews, and the fixpoint test below is worthless.
- **Regenerate, then commit.** Commit-then-regenerate ships a seed one change stale, and nothing but a full feature test catches it.

**The seed subset is the real constraint.** The bootstrapper must implement every feature the compiler itself uses, so the compiler is written in a subset that avoids `@meta`. `@meta` is a feature user code gets from day one; the compiler adopts it only after self-hosting.

**The cheapest strong oracle:** because `gen_c` is deterministic, "the compiler compiles itself to byte-identical C" is a fixpoint test that catches an enormous class of bugs and costs one script. Pair it with a corpus of programs with expected output.

### The order

LSP, formatter, and race checker are the visible goals, and **two of those three are not tools.** The race checker is the type system (`self :: @Self`, `consume`, `iso`) — sound from the start or never sound. The formatter is the parser plus a printer, one grammar, not two. Only the LSP is a genuinely separate program, and even it is a thin server over compiler internals.

So four decisions, all made in week one, all brutal to retrofit:

1. **Every AST node carries a `file` plus a half-open `start..end` span,** each end a `line:col` with a 1-based byte column, from the lexer up. A point is not enough: without an end, the formatter cannot reprint a node and the LSP cannot select one.
2. **Trivia — comments and whitespace — is attached to nodes, not discarded.** Then the formatter is `parse |> print` and can never disagree with the compiler about what the language is.
3. **Sema is memoized queries, not monolithic passes.** `type_of(node)`, `defs_of(name)`. This is the *same machinery* as comptime memoization — build it once.
4. **The compiler is a library; the `zen` CLI is a thin `main`.** `zen build` / `zen fmt` / `zen lsp` are entry points into one artifact, so they cannot drift.

| stage | what | why here |
|---|---|---|
| 0 | Python bootstrapper, minimal subset | the grammar exists first |
| 1 | **self-host** | everything after this is cheaper; nothing before it matters |
| 2 | formatter + CI gate | do it *at* self-host, before the tree grows, or you get a flag day |
| 3 | ownership / sendability checker | `self :: @Self`, `consume`, `iso` |
| 4 | LSP | falls out of (1)–(4) above |
| 5 | actors + runtime | orthogonal; constrains nothing in the compiler |

**Ship the ownership *syntax* at stage 0** even though nothing checks it. `self :: @Self` and `consume` cost nothing to parse and ignore. Defer the syntax and every line of stdlib written before stage 3 has to be revised; defer only the enforcement and nothing is lost.

**So read the Ownership section below as law, and check the tree before reading it as behaviour.** Stage 2 is there in part: `zen fmt` is `parse |> print` over this parser and this trivia, and it prints the FILE — declarations in source order, comments where they were written, a run of blank lines collapsed to one, exactly one final newline — while every declaration's own text passes through verbatim. The rules this document states about match arms are therefore still owed, and a formatter that guessed at them would have reflowed the tree on its first run. What keeps that split honest is a guard rather than care: the output is re-lexed and its token stream compared to the input's, so a printing rule that changed the program cannot leave `src/fmt/`. Stage 3 is there in part — `sema_own.zen`, `sema_recv.zen`, `sema_drop.zen` and `sema_scope.zen` enforce the receiver rule, `consume` and use-after-move, the copy of a `Drop` value, the partial move that reaches a drop, and all three of `@scope`'s ways out. "Which closures escape" is read off the callee's signature and nothing else: a closure argument to a call that also takes an `Alloc` may be kept past the call, and every other one may not — so the reading is narrow where the signature is silent, and a free function taking an `Alloc` is not asked. One thing below is still law and not behaviour: `iso` at a behavior parameter is stage 5, along with actors. What is checked, refuses; what is not, still compiles.

**Not needed, and traps if attempted early:** an optimizer (C is the backend), a second backend, a package manager, incremental codegen.

**Compilation is whole-program.** One merged module graph; `gen_c` emits each generic instantiation exactly once. Separate compilation would have to decide which object file owns `Vec<Circle>` when `Vec` and `Circle` come from different modules, and every language that tries pays for that forever. The cost is that build time scales with the tree, which is exactly what `b.budget` exists to watch.

---

# The laws

Everything below follows from these. When two rules seem to conflict, the law wins.

1. **No ambient allocator.** Anything that needs memory takes an `Alloc`. No `Alloc` parameter, no allocation.
2. **No ambient authority.** All authority flows from the `Env` `main` receives — io, net, page allocation, threads, spawning.
3. **Satisfy requirements, never impl storage.** Layout is fixed at declaration and never depends on which impls are linked.
4. **Failure stays visible.** Only success lifts into `Res`. `Err` and `None` are always written. A reason is never invented.
5. **`Res` is for failure a caller can act on. A trap is for a bug.**
6. **`*` means this name crosses a module boundary** — and therefore its type is written, not inferred.
7. **The signature answers the question.** Does it allocate, does it mutate, can it fail, does it escape — read the signature.

---

# Lexical rules

A scanner cannot abstain. Every one of these was going to be decided by whoever wrote the first one, so they are decided here instead — that is the difference between a language and an implementation with a manual.

The shape of every rule below is the same: **reject rather than reinterpret.** A scanner that silently picks a reading is how a language ends up with a specification nobody can write down, and the readings it picks are always the ones that hide the bug (`010` meaning 8, `"\q"` meaning `q`). Rejecting costs the author one keystroke. Reinterpreting costs a reader an afternoon.

**Escapes.** The set is `\n \t \r \0 \\ \' \"` and nothing else. An unknown escape is an error, never a silent literal character: `"\q"` does not mean `q`.

**A string or character literal does not span lines.** The newline is the error, and the diagnostic points at the **opening quote** — pointing at end-of-file names no useful location, because end-of-file is not where the mistake is.

**A character literal holds exactly one byte.** `str` is bytes, so `''` and `'ab'` are both errors. `'é'` is two bytes and therefore not a character literal.

**Numbers are decimal, and a digit may not be followed by an identifier character.** `1abc` is an error, not a number beside a name. There are no type suffixes — a literal's type comes from its context, which is the same rule the rest of the language runs on.

- **A leading zero is rejected.** Zen has no octal, so `010` cannot quietly mean 8. Python 3 made this exact call for this exact reason.
- **`12.` is an error**; a float has digits on both sides of the point. The gain is that a number literal is never the base of a member access, so `1.max` needs no lookahead to disambiguate from a malformed float.
- Hex is therefore not in v1. `0xFF` is not "a number followed by an identifier character" but its own token shape, and adding a token shape later is compatible in a way that removing one is not. Cost to accept knowingly: bit masks are written in decimal until someone adds it.

**Identifiers are ASCII** — `[A-Za-z_][A-Za-z0-9_]*`. Widening a character set later is compatible; narrowing it is not, so v1 takes the narrow end.

**Block comments do not nest.** `/* a /* b */` is closed.

**A BOM is stripped only at offset 0.** Anywhere else it is an ordinary invalid byte sequence, and saying so beats a file that parses differently depending on where an editor left a marker.

**`@` is closed.** The namespace is exactly `@Self`, `@meta`, `@scope` — adding a fourth is a design change, not an implementation detail. So `@foo` is a lexical error at the `@`, and never an unresolved name later: one mistake, one diagnostic, anchored where the fix goes.

---

# Declarations

**Conventions settled:** fields mirror bindings: `name: T` is set at construction and never reassigned, `name :: T` is mutable, and `= default` makes a field optional at construction. `*` on a field means readable outside the module; mutation only ever goes through exported methods.

**Method rules**, everywhere. Export (`*`) and overridability (`=` / `::=`) are orthogonal: exported-but-final is `name* = sig {..}`, and on methods `::=` means impls may rebind, not runtime mutation.

| form | meaning |
|---|---|
| `name*` | exported from the module (same `*` as types) — **module level and struct members only** |
| `= sig` | required: impl must provide it |
| `= sig {..}` | sealed: provided, cannot be overridden |
| `::= sig {..}` | default: provided, impl may rebind it |
| `::= sig` | optional hook: impl may provide it |

**`*` is a module-level and struct-member marker, and nowhere else.** Law 6 says `*` means the name crosses a module boundary. A binding inside a function body cannot cross one — it does not outlive the call — so `*` on it means nothing, and a marker that means nothing is a marker someone will read as meaning something. `helper* = (a: i32) i32 {..}` inside a body is rejected by name, not by accident.

The corner this closes is sharp and was found by a parser: `*` is also multiplication, so a statement beginning `n *` has to be either an exported declaration or a product, and the parser cannot ask which until it has read further. Restricting `*` to the two places it has meaning removes the fork entirely at body level, which is the only place the ambiguity is reachable.

**Sum types are written with `|`, always.** A nominal enum and an error union are the same construct — the doc already says a union "is an anonymous enum of two variants" — so they get one syntax and not two:

```groovy
Shape = Circle(Circle) | Rect(Rect) | Unit      // nominal, with payloads
Error = AllocError | IoError | ArgError         // a union of existing types
AllocError* = | OutOfMemory                     // one variant: the bar leads
Alias = Shape                                   // no bar, so an alias. unambiguous.
```

**A variant name that is also a type in scope must be reported, not silently reinterpreted.** What separates `Error = AllocError | IoError` (a union of existing types) from `Signal = Start | Stop` (a nominal enum) is whether every variant name *is* a type. That rule is what lets one syntax serve both, and it has a sharp edge: the answer depends on what else is in scope, so **adding an import to an unrelated module can change what a declaration in this one means.** Found by writing `DefKind = Struct | Enum | ..` in a module that imports `ast`, where every one of those names is a type — the declaration silently became a union of `ast`'s types rather than the enum it was written as.

The rule stays, because the alternative is a second syntax for a distinction nobody wants to spell twice. The *silence* goes: when a variant name collides with a type in scope, the compiler says so and names both, exactly as it does for an impl collision. An author who meant the union renames nothing; an author who meant the enum renames the variant. Cost to accept knowingly: a nominal enum cannot use a name that is a type in scope without being told about it.

**Cost to accept knowingly:** a declaration does not terminate and nothing is newline-sensitive, so a trailing bar swallows the next declaration's name as a variant. `Shape = Circle | Square |` followed by `main = ..` reads as `Shape = Circle | Square | main` with a stray `=`, and the diagnostic lands on the `=` rather than on the bar. That is the parser being right. The alternative — ending a declaration with a token, or making a newline mean something — costs more everywhere than this costs here.

**An alias is the type, not a name that forwards to it.** `Alias = Shape` binds `Alias` to `Shape` itself, so `Alias.Circle` is `Shape.Circle` and a value of one is a value of the other — there is no conversion, because there are not two types. This is what makes the pair above observably different: under the alias reading `Alias.Circle` exists, and under the one-variant-enum reading it does not.

**Which of the two readings applies is not local to the file, and that is the sharp edge.** `A | B` is a union of existing types when *every* variant names a type in scope, and a nominal enum otherwise — so `DefKind = Struct | Enum | Alias` is nominal until someone imports types with those six names into the same module, at which point the declaration silently becomes a union of them. An import in one place changes what a declaration means in another. Two implementations have now been bitten by it and both worked around it by renaming variants.

The rule, so the surprise is a diagnostic rather than a silent reinterpretation: **when every variant of an enum names a type in scope, the declaration IS a union of those types.** If that is not what was meant, the variant names collide with types and one of them must be renamed — and the compiler must say so, naming the variant and the type it collided with, rather than quietly picking the other reading. The alternative — two spellings, one per reading — was rejected because a nominal enum and an error union really are the same construct, and paying for a second syntax to disambiguate a case this rare is the worse trade.

**A union is its members. Order and spelling are not part of its identity.** `WriteError = IoError | AllocError` and `Error = AllocError | IoError` are the same type, and so is the `IoError | AllocError` an inferred error set arrives at with no declaration behind it at all. This is not a new rule; it is the two above read together. The union reading says the declaration *is* a union of those types, not a fresh nominal type wrapping them — and the alias rule says a name does not create identity. A union of the same members, however it was spelled or in whatever order, is one type.

The consequence is a layout rule, and it is the reason to state this explicitly rather than leave it derivable: **a union's tags are numbered by a canonical order over its members, never by declaration order.** Number them by declaration and two spellings of one set get different tags, so `.try()` from one into the other needs a runtime map to renumber — a per-member switch at every widening site, for a difference that the type system says does not exist. Canonical numbering makes the widening a copy. The tag is internal either way: a program matches variants by name and can no more observe a tag's value than it can observe a struct's padding.

Nominal enums are unaffected. `Signal = Start | Stop` is not a union, its variants name no types, and there is no second spelling of it to agree with — so it is numbered by declaration order, which is the order its author wrote and the order its exhaustiveness diagnostics read best in.

The leading bar on a one-variant enum is the whole point: without it `AllocError = OutOfMemory` and `Alias = Shape` are the same three tokens, and `TestError = Failed(str)` and `Circle1 = AddFoo(Circle)` are the same five. With it, a parser needs no lookahead, no position rule, and no guess — and an enum may be declared anywhere, not only at module level.

**One declaration form:** there are no traits, only structs. A struct whose fields happen to be functions, used as a bound, is what other languages call a trait — nothing marks it special, because nothing needs to. `A.impl(B, {..})` supplies a value for every field `B` declares: an `f64` field takes an `f64`, a function-typed field takes a function. One rule, no second mechanism — which is why the method table above and the field rules are the same table.

**You satisfy requirements; you never impl storage.** A field a type declares for itself is storage. A field an impl supplies is computed, and is re-evaluated on read, so it can never go stale. Layout never depends on which impls are linked. When two impls declare the same name, the bound in scope selects which is in view; with no bound to disambiguate it is an error — never file order.

A computed field is **read-only and non-addressable**: there is no storage, so there is nothing to take the address of and nothing to assign into. Mutation goes through exported methods, as it always does.

```groovy fragment
c = Circle(radius: 1.0);
p = &c.width;     // ERROR: computed field, no address exists
c.width = 5.0;    // ERROR: nothing to assign to
```

The residue worth knowing: an impl may supply something expensive, and reading it in a loop hides real work behind a dot. The *simple* case is provable by a pair of budgets — if these two ever stop matching, uniform access is not free and we want to know. Both benches are written, in `tests/bench/bench_field.zen`; what fails the build on a divergence is the `build.zen` above, which is stage 1 and not in the tree:

```groovy fragment
budgets: [
    Budget(name: "stored_field_read",   ns_op: 2, allocs_op: 0, bytes_op: 0),
    Budget(name: "computed_field_read", ns_op: 2, allocs_op: 0, bytes_op: 0),
]
```

```groovy
Rect* = {
    width: f64,          // Rect's own fields: storage
    height: f64,

    area* ::= (self: @Self) f64 { self.width * self.height }
}

Circle* = { radius: f64 }

// width and height are f64, so the impl supplies f64 EXPRESSIONS —
// the same `name: value` form used at construction. Circle stays
// one f64 wide; these are computed on read, never stored. area
// comes along free, it only ever needed a width and a height
Circle.impl(Rect, {
    width: self.radius * 2.0,
    height: self.radius * 2.0,
})

// a bound is just "which struct's shape do I need"
scale* = <T: Rect>(shape: T, k: f64) f64 { shape.area() * k }
```

**An impl lives with the type, not with the trait.** `A.impl(B, {..})` belongs in the module that declares `A`, which imports `B`. `str.impl(Eq, ..)` is in `std.text`, not `std.core.eq`; `Vec.impl(Display, ..)` is in `std.collections`, not `std.core.display`.

This is not a taste rule, it is what keeps dependencies pointing down. A trait sits below the types that satisfy it — `Eq` cannot know about `str` — so putting the impl with the trait forces the lower layer to import the upper one, and the module graph inverts. The reading test is the one in `STYLE.md`: write the impl's one-line summary, and whichever type it names is the module it belongs to.

The consequence worth stating: **there are no orphan impls.** A module may not impl a trait it does not own for a type it does not own, because there is no third module for that impl to live in.

**A trait value is a fat value.** Since a "trait" is an ordinary struct, a trait *value* is an ordinary record: a receiver pointer plus one function pointer per method, copied by value. `shape.as(Display)` builds that record on the stack; storing it in a `Vec<Display>` copies it inline. No `dyn`, no vtable concept, no boxing, **no allocation** — so the Alloc law is satisfied rather than side-stepped. This is the same shape as `Alloc` itself. The one thing it costs: the record points at the receiver, so the receiver must outlive it — the ordinary rule for any pointer stored in a collection.

```groovy fragment
printers ::= alloc.Vec<Display>();
printers.add(circle.as(Display)).try();   // 2 words copied in, no alloc
```

**`Display.toString` writes into a `Sink`, not into a `String`.** This is forced, and it was found by trying to implement the obvious thing. `println("{}", shape)` has to route through `toString`; if `toString` writes into a `String`, then printing needs a `String`, a `String` needs an `Alloc` to grow, and `println` has no `Alloc` parameter — so printing a value would either allocate behind the caller's back, breaking law 1, or `println` would grow an allocator parameter and hello-world would need an arena.

A `Sink` dissolves it. A console is a sink, a `String` is a sink, and `println` hands `toString` the console it already holds — so **printing does not allocate at all**, and nesting still writes into the one buffer that is already open. It is the same move as `Alloc`: name the capability, pass it as a fat value, and let the caller decide what is behind it.

**`Sink` has two members, not one.** `write_byte` looks redundant beside `write` and is not. The integer writers build a number a digit at a time, and a digit has no `str` to point at — `str` borrows bytes, and the only way to obtain something to borrow is a `Ptr` from an `Alloc`. So a sink that accepts bytes but not *a* byte makes printing an integer allocate, which is the one thing this whole design exists to prevent. The alternatives are worse: formatting digits in the C runtime moves the format rules out of `text_fmt.zen` and splits the single implementation in two, and a static digit table needs a `u64`→`usize` conversion the numeric surface does not have.

`Sink.write` returns `WriteError`, the union, and that is the part worth arguing about. Writing to a console fails with `IoError` and writing to a growable `String` fails with `AllocError`; there is no `From`, so a single sink type cannot pretend those are one error. The union is the honest type — which is exactly the reason `WriteError` was introduced. **Cost to accept knowingly:** a caller writing into a `String` must handle an `IoError` that a `String` can never produce, and a caller writing to a console must handle an `AllocError` it can never produce. `.try()` merges either into the caller's set for free, so the cost is paid only where someone actually matches on the error.

---

# Control flow

**Control flow is one thing:** `.match`, a method — exactly as `loop` is a function. No `if`, no ternary, no `?` operator. Arms are `pattern => expr`, comma-separated, no leading `|`; `=>` already separates, so the bar is noise. Payloads bind in the pattern: `Ok(n) => n`. **Match is always exhaustive**, in every position: cover every case or write `_`. There is no partial form, so a missing arm is never ambiguous between "deliberate" and "forgot". When you really do want one side only, `bool.then` says so out loud — and being a different word, it cannot be a typo. Guards inside loops are usually a missing loop word (`find`, `filter`), not a conditional at all.

**A statement ends with `;`. A declaration does not.** That is the whole rule, and it holds without a lexer that counts newlines:

**A function type may not be written where a value is expected.** `f = (a: i32) () i32` and "returns unit, and the next member is named `i32`" are the same tokens — a signature always writes its return type, so `()` in return position and `()` as an empty parameter list cannot be told apart by looking left. The tree-sitter grammar dodges it with a declared GLR conflict; a recursive-descent parser has no such move, so the rule is: after a `)`, a `(` or a `<` never begins a return type in **expression** position. A zero-parameter function type is therefore written only in *parameter* position — `cond: () bool`, `body: () Res<T, E>` — where the following token is a `,` or a `)` and nothing is ambiguous. Every one in the standard library already sits there, so this costs nothing today; it is written down because it is a restriction the parser enforces and no reader could derive.

```groovy fragment
Vec*<T> = { .. }                 // declaration: struct. no semicolon.
Shape = Circle(Circle) | Unit    // declaration: enum. no semicolon.
area* = (c: Circle) f64 { .. }   // declaration: function with a body. no semicolon.

v ::= alloc.Vec<i32>();          // statement. semicolon.
Circle1 = AddFoo(Circle);        // a binding inside a body is a statement. semicolon.
println("done");                 // statement. semicolon.
```

**A binding or assignment is a statement, so it can never be a block's trailing value** — there is no assignment *expression* to produce one from. `() { x = 1; }`, never `() { x = 1 }`. The compiler used to answer the second form with "expected expression", which names a thing the author did not want; it now names the rule that was broken.

Optional semicolons were the alternative and they carry a real hazard, not an aesthetic one: a statement ending in an expression, followed by a line beginning `(` or `[`, silently becomes a call or an index of the previous line. Newline sensitivity was the other alternative, and it breaks the leading-dot continuation this doc already uses in `build.zen`.

**Non-local exit** is one mechanism, not two special cases:

> A non-escaping closure may return through its caller. `.try()` and `h.break()` are both this. Escaping closures may not — they have no caller frame to return through.

`.try()` unwraps `Ok` or returns the `Err` from the enclosing function; that is a jump out through a frame boundary, exactly what `h.break(v)` does. There is no coherent position where one is fine and the other is exotic. So `loop` stays a genuinely ordinary function — `break` is a general language feature that `loop` merely uses, not a privilege the compiler grants it.

**A block is a value too.** `@scope` stands for the enclosing block, exactly as `h: LoopHandle` stands for the enclosing loop — the same idea, one level down. It nests, and each block gets its own:

```groovy fragment
{
    outer = @scope;
    {
        inner = @scope;                              // the inner block
        inner.defer(() { println("inner cleanup") });
    }                                                // inner's defers run, inner dies
    outer.defer(() { println("outer cleanup") });
}                                                    // outer's defers run
```

This is where `defer` lives, and it is why `defer` needs no keyword and no ambient authority: the block owns its own stack of closures. It is also why `Env` does not — `Env` outlives every block inside `main`, so a defer stack on `Env` would be storage in the wrong place.

**`@scope` is non-escaping.** It may be passed *inward*, so a helper can register cleanup on its caller's block, but it can never be stored in a struct, returned, or captured by an escaping closure. Same escaping/non-escaping distinction as above, now doing a third job.

**A closure registered on a scope keeps its captures in that scope's own storage**, and this is what non-escaping buys. A deferred closure outlives the frame that wrote it — `register(@scope, env)` returns long before its cleanup runs — so its captures cannot live in the caller's frame, and a general escaping closure would need a heap record, which law 1 forbids without an `Alloc`. But the block it is registered on outlives it by construction, so the block's own defer stack is exactly the right storage: correctly sized, freed at block exit, no allocator. `defer` therefore needs no escaping-closure machinery at all — it needs the one guarantee `@scope` already makes. That is why the restriction is a feature and not a limitation.

---

# Errors

**Error sets.** The error type of a `Res` is a union, and propagation merges sets. `A | B` is an anonymous enum of two variants — a structural enum, not a new kind of type — so `Res<T, E>` never changes shape and a single error type is a set of one.

```groovy
read_cfg  = (p: Path) Res<Cfg, _>                       // internal: inferred from the body
read_cfg* = (p: Path) Res<Cfg, IoError | ParseError>    // exported: written out

Error = AllocError | IoError | ArgError
main  = (env: Env) Res<i32, Error>
```

Inference inside a module, explicit at the boundary — law 6. A private refactor never ripples through signatures; a public one always lands in review.

**There is no `From`, and no implicit error conversion.** An error does not change identity because the compiler found a conversion somewhere. That is the same principle as law 4, one level up.

**A `None` never becomes an `Err`.** You name the reason:

```groovy fragment
row = table.get("ada").try();                        // ERROR: Res<User> is not Res<User, E>
row = table.get("ada").ok_or(Error.NotFound).try();  // required form
```

---

# The failure model

`Res` is for failure a caller can do something about — a file is missing, input is malformed. A bug is not that, and routing bugs through `Res` would put `.try()` on every arithmetic expression in the compiler and destroy the signal that makes `.try()` readable. So:

- `+ - *` **trap** on overflow. `+% -% *%` wrap, for when wrapping is the intent.
- `/ %` **trap** on a zero divisor, and on `i32.MIN / -1` — which is an overflow wearing division's clothes, and faults identically on x86.
- `buf[i]` on a fixed array is **bounds-checked and traps**. **The count is part of the type** — `[u8, 64]` and `[u8, 65]` are different types — which is what makes the check possible with no length stored beside the bytes, and what lets a literal index past a known length be the compile error below rather than a runtime trap. `Vec.get` still returns `Res<T>` — a lookup that can legitimately miss is not a bug.
- A trap **aborts the process**: it prints `file:line:col: trap: <what>` to stderr and exits `134`. The three whats are `integer overflow`, `divide by zero`, `index out of bounds`, and the position is the **operator** token. Column is a 1-based byte offset.
- Overflow traps for **unsigned** types too. "A trap is for a bug" does not have a signedness exception, and a `u8` reaching 256 is the same bug a `i8` reaching 128 is.
- A trap the compiler can **prove** will fire — `i32.MAX + 1`, a constant zero divisor, a literal index past a known length — is a **compile error**, not a runtime trap. It is a bug, and it is a bug that was visible without running the program.

One constraint this puts on the backend, stated here because it is a correctness requirement and not an implementation detail: **signed overflow is undefined behaviour in C**, so `gen_c` may not emit `a + b` and inspect the result afterwards — the optimizer is entitled to delete that check, and will. The test happens before the operation, or through `__builtin_add_overflow` and friends.

Killing only the offending actor is the Pony-shaped alternative, and it needs a supervision story that does not exist yet. It can be added later without changing any of the above.

---

# Ownership

Three questions, one checker: *what is this binding allowed to do?*

**There is no implicit receiver.** A method is a UFCS function whose first parameter happens to be named `self`, and that parameter is written out like every other one — a name and a type, never bare.

This is a rule about **declarations**, not about every parameter list. A closure passed to a function whose signature is already known infers its parameter types from that signature, so `items.loop((h, v) { .. })` needs no annotations — `h` and `v` each have exactly one possible type. Annotate a closure parameter only to disambiguate, as the fold body does with `acc: i32`. A declaration states types because someone reads it without context; a closure does not, because the context is the call.

`@Self` is the type being declared, supplied by the compiler inside a struct or impl body. The `@` says exactly that: like `@meta`, it is not a name you could have written yourself.

```groovy fragment
add* = (self :: @Self, value: T) Res<(), AllocError> { ... }   // mutates
get* = (self: @Self, i: usize) Res<T> { ... }                  // does not

v = alloc.Vec<i32>();    v.add(1);   // ERROR: add needs a mutable receiver
w ::= alloc.Vec<i32>();  w.add(1);   // ok
```

`@Self` is spelled `Vec<T>` when you write the same function outside the body — the two forms are the same function, and the second is what the first means:

```groovy fragment
Vec*<T> = { add* = (self :: @Self, value: T) Res<(), AllocError> { ... } }
add*    = (v :: Vec<T>, value: T) Res<(), AllocError> { ... }   // identical
```

So `::` on a receiver means the method mutates it, and it is not a receiver rule at all — it is the ordinary binding marker doing its ordinary job on the ordinary first parameter. One function form, one binding rule, nothing added.

This is **shallow**: `::` means the method writes the receiver's *own bytes*, and nothing more. So **a handle's methods are `:`, even when they change the world.** `Alloc.raw` is `self: @Self` — allocating changes the arena behind the handle, not the two words of the handle. Same for `@scope.defer` (the closure stack lives in the block), `Ref` behavior calls (the mailbox is behind the address), and `Env.spawn`.

That is not a nicety, it is what makes the system consistent. `Vec.alloc` is a `:` field, and `Vec.grow` calls `self.alloc.realloc(..)` through it. If `realloc` demanded `:: Alloc`, that call would be illegal and every collection would need a mutable allocator field — the shallowness would buy nothing. It compiles precisely because `realloc` writes the arena, not the handle. Same reason `foo.receive_msg(..)` is legal on a `foo = env.spawn(..)`.

The test, when a signature is unclear: **would a bitwise copy of the receiver see the change?** If yes, the change was to its own bytes and the method is `::`. If the copy sees it too — because both point at the same thing — the method is `:`.

It is not inferred from the body. An inferred receiver requirement changes when the body changes, so adding one `self.x = ..` would silently break callers in other modules. Explicit keeps it a promise instead of a consequence.

**`consume` moves.** The compiler calls `drop` exactly once, so `g = f` on a `Drop` type cannot copy — both would drop. There is no `Clone` trait: want a second one, construct a second one.

Three consequences worth stating, because each one is a place the rule looks like it bites and does not:

- **A handle is not a `Drop` value.** `Alloc` is an interface, so an `Alloc` value is a fat value pointing at an arena. The *arena* is `Drop`; the handle is two words and copies freely. That is why `Vec` can store `alloc: Alloc` by value and why `fill(alloc, v)` is not an illegal copy.
- **Passing a `Drop` value to a parameter is a borrow, not a move.** `v.add(1)` does not consume `v`, and a receiver is just the first parameter — so nothing else could be true. A move is spelled `consume` at the call site, and only there.
- **The compiler-inserted `drop` is exempt from the receiver rule.** `drop` is declared `(self :: @Self)`, but scope exit runs it on `:` bindings too. Destroying a value is not mutating it through a binding.

```groovy fragment
f = alloc.File("x.txt").try();
g = consume f;                  // move, stated at the use site. f is dead after
f.read();                       // ERROR: f was consumed
g = alloc.File(f.path).try();   // want another? construct it
```

**Reference capabilities**, the lite set. The problem they solve: two actors run at once and both hold the same `Vec`; one writes while the other reads. Locks solve it at runtime, types solve it at compile time.

| | can you write? | how many refs exist? | can you send it? |
|---|---|---|---|
| `ref` | yes | many, all inside one actor | **no** |
| `val` | never, ever | many, anywhere | yes |
| `iso` | yes | exactly one, program-wide | yes — and you lose it |

`val` is deeply immutable *forever* — not "you may not write it" but "no writer exists", so any number of actors may read at once. Literals are `val`. `iso` is unique: you may write through it precisely *because* you hold the only reference in the program. So **only `val` and `iso` cross actors** means *share what nobody can change, or hand over what only you have*. Both make races impossible by construction, and there are no locks anywhere in the language.

**None of `ref`, `val`, `iso` is ever written.** There is no capability syntax, and that is deliberate: a behavior's parameters are sendable *by definition* — it is a behavior — so marking them would restate what the declaration already says. The constraint lives on the **argument**, and it is checked where the argument is passed. The checker proves one of two things at every send: the value is deeply immutable (`val`), or it is uniquely owned and handed over (`iso`), which you spell `consume`. The only thing you write is the `consume`.

Sending an `iso` is the same `consume`, tracked the same way:

```groovy fragment
buf ::= alloc.Vec<u8>();
worker.process(consume buf);
buf.add(2).try();              // ERROR: buf was consumed
```

**Data races are compile errors** — not deep copies at runtime.

---

# Modules

**Module paths are `<folder>/<folder>.zen`.** A bare `src/ast.zen` is module `ast`; a folder carries its root beside its children, so `src/gen/gen.zen` is module `gen`. Deliberately not Rust's `mod.rs` (twenty editor tabs all reading `mod.rs` is a real cost) and not Zig's raw path imports (no module concept at all).

Names are qualified by path, imports bind locally, and two modules may define the same top-level name without colliding.

**A name that is not imported is not visible, and the prelude is the only exception.** That exception is what "auto-imported" means: `std.core` is imported into every module, so `Res`, `Ok`, `Vec`, `Map`, `str`, `Env` and the rest are in scope everywhere without a line. Everything else needs its import, and this is not a formality — a compiler that resolves any exported top-level name program-wide makes "two modules may define the same top-level name" impossible, which is the property the flat namespace exists to provide. A whole-program name table also hides missing imports until the day two modules disagree, which is the worst day to find out.

**That rule is about BARE names. A UFCS function is reached through a value, so it travels with the value's type.** `x.f(..)` never names `f`, so it cannot collide with anything and needs no import: the candidates are the members of `x`'s type, its impls' and its bounds' methods, and every exported free function whose **first parameter type** is `x`'s type. Two modules may both declare `size` as long as they take different first parameters — and if they take the same one, that is a real collision and is reported. This is what "importing a type pulls its world along" means, said as a rule rather than as a comment in an example: the world travels with the *type*, and you are holding one.

The two halves fit together because they answer different questions. A bare name asks "what is `Vec` here", which two modules can disagree about, so it needs an import. `x.get(0)` asks "what can this value do", which only `x`'s type can answer.

**Three gaps a `time` module makes unavoidable, named here so they are decided rather than worked around.**

*There is no operator overloading.* `==` through `Eq` is the only operator that dispatches to an impl, so `a + b` on a `Duration` is not writable and a module that wants it writes `add`. Whether arithmetic operators should dispatch is a real question — it is the difference between a `Duration` reading like a number and reading like a record — but it is a language decision, and until it is made, a comment promising `+ - * /` on a struct is describing a language this is not.

*There is no `Ord`.* `std.core` has `Eq` and `Hash` and nothing that orders. Adding one is not a fifth trait beside them: **`Ord` and `Eq` must agree**, exactly as `Eq` and `Hash` must, and a type where `eq` says equal while `compare` says less is a sorted container that loses rows. Whichever is sealed in terms of the other, the relationship is the design.

*A clock is authority and a duration is not.* `Duration`, `Instant`, `Timestamp` and a broken-down civil time are values — no `Env`, constructible in a test, no capability. A `Clock` that reads one, and the timers it schedules, need `Ref` and `Context` and therefore the actor runtime. They do not belong in the same module: `std.core` sits below everything, and a `Clock` declared there would make the prelude's core depend on stage 5. It is also what makes "comptime has no clock" true by construction rather than by convention — comptime has no `Env`, and now no import path to one.

**`zen build` takes an explicit entry, and `Fs` gets no directory listing.** The driver finds the entry by probing `main.zen` and the root's own name, which cannot find a single-file program named anything else — and the obvious fix, listing the directory, is the wrong one. `std.env.Fs` has four members and its header says why: "There is no open handle, no seek, no listing and no permission surface… Every member added here is a member the self-hosted compiler has to keep working forever." A listing is also authority to enumerate, which is a bigger capability than reading a path you were given.

The information already exists at the call site: whoever invokes the compiler knows which file is the entry. So `zen build <root> --entry <file>` is the answer, and the capability surface does not grow. A build is still a root — the entry names where to start inside it, and everything else follows imports as it always did.

**A constructor does not travel with the type it constructs, and that is the hole associated functions fill.** `seconds(n: u64) Duration` takes a `u64`, so by the rule above it travels with `u64` — which means `Duration = std.core.time` gives you every method and no way to make one. The two obvious answers are both wrong: listing the constructors in every import is the noise this rule exists to remove, and letting them travel with `u64` puts `.seconds()`, `.minutes()` and every other module's `u64`-taking function on every integer in every program, because `u64` is in the prelude.

The answer is that a struct body may bind a **function**, read as `Type.name(..)` — `Duration.seconds(60)`. This is the existing "a struct body may bind a name to a value, read as `Type.NAME`" rule plus the fact that a function *is* a value here, and it puts the constructor in the one namespace that is already exactly right: the type it constructs. A name that is neither a variant nor a receiverless member is still refused rather than guessed at — `src/gen/gen_c/gen_c_member.zen` raises a positioned `codegen does not lower this yet`, because a backend that emits C for a form it does not understand turns one diagnostic into a C compiler's.

**A prelude declaration of a primitive's name IS that primitive.** `str` and `i32` are declared as ordinary structs in the prelude — `str` in `std.text.text_str` carrying `len`, `get`, `index` and `slice`; `i32` in `std.core.num` carrying `MIN`, `MAX` and `BITS` — and the members they declare belong to the primitive the compiler already knows. They are not a second nominal type that shadows it. Getting this wrong is not a small error: it mints a `str` beside the `str` every literal has, and then every literal, every trap check and every standard-library signature disagrees about which one they meant.

**Re-export is an import whose bindings are starred.** No `export`, no `from` — `*` doing the same job it does everywhere else, and `=` being the binding it already is:

```groovy fragment
// src/std/core/core.zen
Res, Ok, None = std.core.result     // imported, local to this module
Res*, Ok*, None* = std.core.result  // imported AND re-exported
str*, String* = std.text.string     // types travel with their methods and impls
```

A folder root is then just a file of starred bindings, which is why re-export is what makes folders work — and why the prelude can span several files instead of being one enormous one.

---

# Comptime and `@meta`

**`@` is the compiler's namespace.** A leading `@` marks something the compiler supplies that no user code could have written — `@Self` (the type being declared), `@meta` (the ast node for a value or type), `@scope` (the enclosing block). It is not a sigil with meaning of its own and it is not a macro marker; it is one flat namespace, deliberately small, and everything in it is documented here. Anything without an `@` is an ordinary binding you could have written yourself.

`@meta` **builds and reads**, and it does not get a parallel node type — it gets the compiler's own. `@meta(n)` hands back the same `Struct` / `Enum` / `Function` values from `src/ast.zen` that `DumpAst` walks and `gen_c.zen` consumes. One AST, three consumers. Building a type is constructing those nodes and returning them.

**Identity: type-returning comptime calls are memoized on their arguments.**

| question | answer |
|---|---|
| does `Circle` itself change? | no — nodes are values; `AddFoo` returns a new one |
| two calls to `AddFoo(Circle)` — one type or two? | one, memoized on (function, args) |
| identity across module boundaries? | the generating call, which is module-independent |
| can it nest? | yes — `AddFoo(AddFoo(Circle))` is just another call to memoize |
| what does the C backend see? | one emitted struct per distinct call, same as a generic |
| what if it escapes its block? | nothing special; identity is the call, not the scope |

Declared types stay **nominal** — `Circle = {radius: f64}` and `Sphere = {radius: f64}` are different types, and an impl on one is not an impl on the other. Only *generated* types are identified by their generating call.

**What runs at comptime:** the language minus io and actors. Comptime code **may allocate** (`@meta`-driven serialization has to build strings) and may loop, but the evaluator counts steps and fails the build rather than hanging. **No file reads in v1** — that is the fastest route to a build that is not reproducible.

---

# Constants on a type

A struct body may bind a name to a **value** rather than a field, and it is read as `Type.NAME`. That access form already exists — `Shape.Unit`, `Os.Macos` — so this adds a spelling, not a concept:

```groovy
i32* = {
    MAX*: i32 = 2147483647,     // starred: a constant crossing a module
    MIN*: i32 = -2147483648,    // boundary obeys law 6 like everything else
    BITS*: usize = 32,
}
```

and read back, in a body:

```groovy fragment
x = i32.MAX;              // a constant, resolved at comptime
buf: [u8, i32.BITS]       // usable wherever a comptime value is
```

The distinction from a field: a field declares storage per value, a constant declares one value per type. `MAX: i32 = 2147483647` inside `i32` is the second, because `i32` has no instances to give it storage in. Every primitive numeric type carries `MIN`, `MAX`, and `BITS` from the prelude.

---

# Overloading

Resolution is on **declared parameter types and arity**, and a closure's type is its full signature. There is no carve-out: `loop` overloads on `(h: LoopHandle, value: T)` versus `(h: LoopHandle, index: usize, value: T)` for exactly the reason `toString` overloads on a buffer versus an allocator.

**Parameter names are documentation, not identity.** `(a: i32, b: i32) i32` and `(x: i32, y: i32) i32` are the same type, and overload resolution never sees names. Two candidates that differ only in parameter names are the same signature, and declaring both is an error at the declaration site — named for both declarations, when the generic is instantiated.

Function types must name their parameters: `(i32, i32) i32` says nothing about which `i32` is which. `() ()` has nothing to name and stays as it is.

One consequence worth stating: a generic parameter swallows a concrete one, so `fold`'s `(init: A, body: ..)` and a hypothetical `(alloc: Alloc, body: ..)` cannot be overloads. The allocating variant gets its own name, `map` — which is honest anyway, since it is the one that allocates.

---

```groovy // just using this for highlighting
// std.text.string

// borrowed view of text: pointer + length, no alloc, no growth,
// no allocator. string literals are str, living in static memory.
// (* is reserved for exports, so raw pointers are Ptr<T>)
//
// str is BYTES. len is a byte count, indexing yields u8, == is
// bytewise. utf-8 is functions over bytes — s.codepoints(),
// s.validate_utf8() — paid for only where the guarantee is wanted
str* = {
    data: Ptr<u8>,
    len*: usize,      // * so a byte count is readable outside std.text
}

// owned, growable text. Vec already carries len, capacity, and
// the Alloc it grows with, so String adds nothing on top: it IS
// the buffer. there is no separate StringBuffer type
String* = {
    data :: Vec<u8>,

    add* = (self :: @Self, fmt: str, args: ...) Res<(), WriteError>
    view* = (self: @Self) str
}

// anything bytes can be written to. a String is one and a console
// is one, which is what lets `{}` format into either without the
// format machinery knowing which it has
Sink* = {
    write* = (self :: @Self, bytes: str) Res<(), WriteError>

    // a sink that takes bytes but not A byte forces every integer
    // writer to allocate, which is the exact cost this design
    // exists to avoid: digits are produced one at a time, `str`
    // BORROWS bytes, and the only way to get a `str` to borrow is
    // a `Ptr` from an Alloc. so one byte is its own member
    write_byte* = (self :: @Self, byte: u8) Res<(), WriteError>
}

String.impl(Sink, {
    write      = (self :: @Self, bytes: str) Res<(), WriteError> { .. }
    write_byte = (self :: @Self, byte: u8) Res<(), WriteError> { .. }
})

Display* = {
    // sealed (=): the mechanical debug dump. @meta walk over
    // the fields, "Name { field: value, .. }". always there,
    // for every type, never overridden
    dump* = (self: @Self, out :: Sink) Res<(), WriteError> {
        out.add("{} {", @meta(self: @Self).name);
        @meta(self: @Self).fields.loop((h, field) {
            out.add(" {}: {},", field.name, field.value);
        });
        out.add(" }");
        Ok(());
    }

    // outlined only (::=, no body): the pretty representation,
    // impls define THIS one. format machinery routes {} through
    // it, falling back to dump when a type hasn't defined one.
    // writes into a sink the CALLER owns, so nesting never
    // allocates and printing never allocates at all
    toString* ::= (self: @Self, out :: Sink) Res<(), WriteError>

    // sealed overload (=): the allocating form, derived from
    // the sink form, so the two can never diverge. overload
    // resolution picks by what you pass: a sink or an allocator
    toString* = (self: @Self, a: Alloc) Res<String, WriteError> {
        sb ::= a.String().try();
        self.toString(sb).try();
        Ok(sb);
    }
}


// std.core (prelude, auto-imported)

Res*<T> = Ok(T) | None

Res*<T, E> = Ok(T) | Err(E)

// hoisting: a bare T lifts into Res<T> wherever a Res is
// expected, so the obvious thing just works:
//   Foo = { bar: Res<i32> }
//   foo = Foo(bar: 32)       // lifted to Ok(32)
//   foo = Foo(bar: Ok(32))   // identical, explicit
// same in returns: `0;` closes a Res<i32, E> function like
// `Ok(0);` does. hoisting only fires when exactly ONE variant
// carries the type; ambiguous cases require the explicit form.
// only success lifts: Err and None are always written, failure
// stays visible, and a None never becomes an Err

// error propagation: .try() unwraps Ok, or returns the Err /
// None from the ENCLOSING function. it is the non-local-exit
// intrinsic, not a method on Res — same mechanism as h.break:
//   sb ::= alloc.String().try();
//   self.toString(sb).try();

// the one-sided conditional. match is ALWAYS exhaustive, so there is
// no partial form to hide a dropped case in: when you genuinely want
// nothing on the false side, you write .then and it is visible in the
// source. lands in Res, so it composes with .try() and match like
// anything else — Ok(v) when true, None when false.
// a plain ufcs function: first param is bool, so it calls as a method
then* = <T>(b: bool, f: () T) Res<T>

// RAII: the compiler calls drop when a binding leaves scope,
// reverse declaration order, exactly once. exactly-once is why
// `consume` exists: a Drop value cannot be copied. Allocators
// are the flagship user: mem.alloc() returns an arena, and
// dropping the arena frees everything ever allocated from it
Drop* = {
    drop = (self :: @Self) ()
}

// @scope is the enclosing block, as a value — what LoopHandle is
// to a loop, one level down. non-escaping: it may be passed
// INWARD so a helper can register cleanup on its caller's block,
// but never stored, returned, or captured by an escaping closure
Scope* = {
    // runtime cleanup, for the ad-hoc cases Drop doesn't cover.
    // registers a closure on THIS block; they run LIFO at block
    // exit, BEFORE drops. a stack of closures, not a map: order
    // matters, and the stack lives with the block that owns it
    defer* = (self: @Self, f: () ()) ()
}


// the capability root. main receives one, and ALL authority
// flows from it, pony-style: no ambient io, net, threads, or
// page allocation.
//
// println(...) is sugar for `<the Env in scope>.out.println(...)`,
// resolved BY TYPE, not by the name of the binding. no Env in
// scope is a compile error, so printing exists exactly where the
// capability does and the law is not bent to make hello-world short
ArgError* = Missing(str)   // required field absent; names the field
          | Parse(str)     // value present but not the field's type

// the disk. Three members, and each earns its place: a compiler
// reads a whole file at once, never streams and never seeks, so
// there is no handle and no `open`. A module tree is
// <folder>/<folder>.zen and is COMPUTED rather than discovered, so
// nothing needs a listing -- but a walk still has to tell a folder
// from a file before opening it, and ruling a candidate path out
// should cost a stat rather than reading a megabyte to learn
// nothing. Hence exactly is_dir and exists beside read.
//
// `read` takes an Alloc because it allocates, returns Res because a
// missing file is a caller's problem and not a bug, and is `:`
// because a handle's methods are `:` -- a bitwise copy of an Fs sees
// the same filesystem.
FsError* = NotFound | Denied | IsDir | Failed | OutOfMemory

Fs* = {
    read*   = (self: @Self, a: Alloc, path: str) Res<String, FsError>
    write*  = (self: @Self, path: str, bytes: str) Res<(), FsError>
    exists* = (self: @Self, path: str) bool
    is_dir* = (self: @Self, path: str) bool
}

// OutOfMemory is a member of FsError only because the seed subset has
// no error unions and no From, and `read` allocates. When unions
// arrive the signature becomes Res<String, FsError | AllocError> and
// the variant goes.
//
// `write` arrived the moment it had a caller and not before: `zen build
// src -o stage2.c` cannot honour its own `-o` without one, so the
// fixpoint could not complete. No append, no mode, no handle — the
// compiler writes one file once. It takes no Alloc because it allocates
// nothing: the bytes are the caller's and stay the caller's.

Env* = {
    argv: Vec<str>,       // raw argv; argv.get(0) is the program path
    vars: Map<str, str>,  // raw environment variables
    out: Console,         // stdout / stderr
    mem: Mem,             // page authority: env.mem.alloc() makes an arena
    fs: Fs,               // the disk. `read` is the whole file at once
    net: Net,             // named and empty until something needs it
    threads: Threads,     // the thread escape hatch, no longer ambient

    // typed args: declare a schema struct, @meta walks its
    // fields and fills them. each field maps to --flag and its
    // SCREAMING env var, flag wins. Res<T> fields may be absent
    // (None), fields with defaults are optional, everything
    // else is required and errors by name. this IS the cli story
    args* = <T>(self: @Self) Res<T, ArgError>

    spawn* = <A: Actor>(self: @Self, actor: A) Ref<A>
}

// equality and hashing, same shape as Display: one overridable
// core with an @meta default, sealed laws around it
Eq* = {
    // default (::=): field-wise comparison via @meta walk;
    // override for custom equality
    eq* ::= (self: @Self, other: @Self) bool { /* @meta field-wise */ }

    // sealed law: ne is always !eq, they can never diverge
    ne* = (self: @Self, other: @Self) bool { !self.eq(other) }
}

Hash* = {
    // default (::=): feeds every field through the hasher
    hash* ::= (self: @Self, hasher :: Hasher) u64 { /* @meta field-wise */ }
}


// std.mem.zen
// the law: there is NO ambient allocator. anything that needs
// memory takes an Alloc, so "does this allocate?" is answered
// by reading the signature. no Alloc parameter, no allocation

AllocError* = | OutOfMemory

// the allocator interface. everything that allocates takes one.
// implementations: arena (mem.alloc()), fixed buffer, c malloc.
// only raw is required; the typed conveniences are defaults.
// Alloc is itself the fat-value shape every trait value has:
// a receiver plus function pointers, passed by value
Alloc* = {
    raw* = (self: @Self, size: usize, align: usize) Res<Ptr<u8>, AllocError>
    realloc* = <T>(self: @Self, p: Ptr<T>, count: usize) Res<Ptr<T>, AllocError>
    free* ::= <T>(self: @Self, p: Ptr<T>) ()    // arenas no-op this

    // one typed convenience, a default built on raw:
    create* ::= <T>(self: @Self) Res<Ptr<T>, AllocError>
}

// Vec, Map and String are NOT members of Alloc. each is a ufcs
// function declared beside its OWN type, taking an Alloc first:
//
//     Vec*    = <T>(a: Alloc) Vec<T>                 // std.collections
//     Map*    = <K, V>(a: Alloc) Map<K, V>           // std.collections
//     String* = (a: Alloc, fmt: str, args: ...) Res<String, AllocError>
//
// the call surface is identical — `alloc.Vec<i32>()` either way,
// because a free function whose first parameter is the type is
// callable as a method. what changes is the direction of the
// dependency. as members they would put Vec-shaped defaults inside
// std.mem, which cannot see Vec's unexported fields, and mem and
// collections would have to import each other.
//
// Vec and Map return a bare value: an empty one owns no pages yet, so
// construction cannot fail. the first add allocates, and THAT returns
// Res. String takes a format and must hold the result, so it allocates
// at once and says so.

// Alloc is an INTERFACE, so an Alloc value is a fat value: a receiver
// pointer plus function pointers. It is a handle, it is freely copied,
// and it is NOT Drop. Copying it copies two words, never ownership.
//
// the concrete allocator behind it owns the memory and is what Drop
// applies to. env.mem.alloc() hands back an Arena; the Arena impls
// both, and passing it where an Alloc is wanted builds the handle
Arena* = {
    // pages, free lists, whatever the arena needs. owns them.
}

Arena.impl(Alloc, { ... })

Arena.impl(Drop, {
    drop = (self :: @Self) () { /* release every page at once */ }
})


// std.collections.zen
// everything here is sealed (=): collections are not extension
// points, and sealed methods compile to direct, inlinable calls

// fixed-size arrays are [type, count]: comptime length, lives
// on the stack, no alloc. [0, 1, 2] literals infer [i32, 3].
// indexing is bounds-checked and TRAPS: a fixed array has no
// Res escape hatch, and an out-of-range index is a bug
//   buf: [u8, 64]
//   primes = [i32, 4](2, 3, 5, 7)

Vec*<T> = {
    data :: Ptr<T>,
    len* :: usize,      // * is readable outside; mutation still only via methods
    capacity :: usize,
    alloc: Alloc,       // : set once at construction

    // `self :: @Self` — mutates the receiver. @Self is Vec<T> here.
    // the handle
    // in self.alloc stays usable: `:` is shallow, it protects
    // the field's own bytes, not what it points at
    add* = (self :: @Self, value: T) Res<(), AllocError> {
        (self.len == self.capacity).then(() { self.grow().try() });
        self.data.write(self.len, value);
        self.len = self.len + 1;
        Ok(());
    }

    // moves an element OUT, leaving the vec one shorter. without this a
    // Vec<T> of Drop values can be filled and never emptied
    take* = (self :: @Self, i: usize) Res<T>

    get* = (self: @Self, i: usize) Res<T> {
        (i < self.len).match({
            true => Ok(self.data.read(i)),
            false => None,
        });
    }

    grow = (self :: @Self) Res<(), AllocError> {
        cap = (self.capacity == 0).match({
            true => 8,
            false => self.capacity * 2,
        });
        self.data = self.alloc.realloc(self.data, cap).try();
        self.capacity = cap;
        Ok(());
    }
}

// internal: no *, not visible outside std.collections
Entry<K, V> = {
    hash: u64,
    key: K,
    value: V,
}

// bounds: K must be Eq + Hash. the hash finds the bucket fast,
// eq confirms the key: comparing hashes alone returns wrong
// values on collision
Map*<K: Eq + Hash, V> = {
    entries :: Vec<Entry<K, V>>,

    set* = (self :: @Self, key: K, value: V) Res<(), AllocError> {
        h = key.hash(Hasher());
        // probe: overwrite where hash matches AND key.eq, else:
        self.entries.add(Entry(hash: h, key: key, value: value)).try();
        Ok(());
    }

    get* = (self: @Self, key: K) Res<V> {
        h = key.hash(Hasher());
        self.entries.loop((hd, e) {
            ((e.hash == h) && e.key.eq(key)).then(() { hd.break(e.value) });
        });
    }
}


// std.test.zen
// no test keyword, and no discovery baked into the compiler:
// build.zen walks the module tree itself (b.module) and
// registers Tester-taking functions as the test target. the
// function name IS the test name. `zen test` just runs it

TestError* = | Failed(str)

Tester* = {
    env: Env,
    alloc: Alloc,   // per-test arena: dropped after each test,
                    // so leaks are contained and reported

    expect* = (self: @Self, cond: bool) Res<(), TestError>

    // dumps both sides via Display.dump on failure
    expect_eq* = <T: Eq>(self: @Self, a: T, b: T) Res<(), TestError>
}

// benchmarking: same discovery shape, take a Bencher instead.
// because ALL allocation goes through Alloc (the law), the
// bencher counts allocs and bytes per op for free, with zero
// instrumentation
Bencher* = {
    env: Env,
    alloc: Alloc,

    // runs f until timing stabilizes
    iter* = (self: @Self, f: () ()) BenchStats
}

BenchStats* = {
    ns_op: u64,
    allocs_op: u64,
    bytes_op: u64,
}


// std.build.zen

BuildError* = NotFound | FetchFailed | VersionConflict | HashMismatch

// a dependency, hash-locked: the url and version say what you
// asked for, the hash pins what you actually got
Package* = {
    url: str,
    version: str,
    hash: str,
}

// build.zen runs in the middle of a three-phase build:
//   parse every module  ->  run build.zen  ->  compile
// so b.module can READ any module's declarations (that is how
// test discovery works) but build.zen may never CALL code from
// the tree it configures — that would need the tree compiled
// before the thing that says how to compile it
Builder* = {
    os: Os,        // Macos, Linux, Windows
    arch: Arch,    // X86_64, Arm64
    env: Env,
    alloc: Alloc,  // build-time arena
    exe: Exe,
    lib: Lib,

    // the parsed module graph, as the same ast.zen nodes DumpAst
    // walks. build programs can inspect their own project: this
    // is how test discovery is WRITTEN in build.zen instead of
    // baked into the compiler
    module* = (self: @Self, path: Path) Module

    // packages are declared in build.zen itself (build files
    // are programs, no separate manifest format). fetched into
    // a content-addressed cache, verified against hash
    add* ::= (self :: @Self, name: str, pkg: Package) Res<Dep, BuildError>
    remove* ::= (self :: @Self, name: str) Res<(), BuildError>

    // build-time budget: total and per-target compile times are
    // tracked against a rolling median
    budget* = (self :: @Self, d: Duration) ()
}

// a locked expectation for one bench.
//
// allocs_op and bytes_op are DETERMINISTIC — identical on every
// machine — so exceeding them FAILS THE BUILD. ns_op and the
// build-time budget are wall clock, which varies 2-5x on shared
// ci, so they are tracked against a rolling median and fail only
// on a sustained shift. a flaky gate gets switched off, and it
// would take the honest gates down with it
Budget* = {
    name: str,
    ns_op: u64,
    allocs_op: u64,
    bytes_op: u64,
}
```

```groovy
// ~/zen/src/loop.zen
// one construct. the compiler picks the variant by signature —
// the ordinary overload rule, with a closure's type being its
// full parameter list. no carve-out for closures
//
// loops NEVER allocate: bodies are stack closures inlined at
// the call site, index and acc thread by value, and a fold
// compiles to a plain C for-loop. the one variant that can
// allocate is map, and it is a different NAME rather than an
// overload — a generic `init: A` would swallow `alloc: Alloc`,
// so they could not be told apart. the rule holds std-wide:
// no Alloc parameter, no allocation

// while true
loop*<T> = (body: (h: LoopHandle) ()) Res<T>

// while true, with iteration counter
loop*<T> = (body: (h: LoopHandle, index: usize) ()) Res<T>

// while cond
loop*<T> = (cond: () bool, body: (h: LoopHandle) ()) Res<T>

// ranged / collection iteration, with and without index
loop*<T> = (range: Range, body: (h: LoopHandle, index: usize, value: T) ()) Res<T>
loop*<T> = (range: Range, body: (h: LoopHandle, value: T) ()) Res<T>

// fold: init seeds acc, acc threads through iterations,
// the loop evaluates to the final acc (or h.break(value))
loop*<T, A> = (range: Range, init: A, body: (h: LoopHandle, index: usize, value: T, acc: A) A) Res<A>

// map: body returns a value per element, collected into a Vec.
// allocation is explicit as always, and so is the name
map*<T, U> = (range: Range, alloc: Alloc, body: (h: LoopHandle, index: usize, value: T) U) Res<Vec<U>>

// the loop words that delete guards: a `.then` inside a loop is
// usually one of these
find*<T> = (range: Range, pred: (value: T) bool) Res<T>
filter*<T> = (range: Range, alloc: Alloc, pred: (value: T) bool) Res<Vec<T>>

// key/value containers
loop*<K, V> = (map: Map<K, V>, body: (h: LoopHandle, key: K, value: V) ()) Res<()>

// LoopHandle controls flow, via the same non-local-exit
// mechanism as .try():
//   h.next()        continue
//   h.break()       break, loop evaluates to None
//   h.break(value)  break with value, loop is an expression
```

```groovy
// ~/zen/src/std/actor.zen
// the pony model: actors are the ONLY concurrency primitive.
// no async/await, no locks, no user-facing threads.
//
// a behavior is any method in an Actor impl (lifecycle hooks
// aside). calling a behavior on a Ref enqueues a message and
// returns immediately: calling IS sending. the message enum
// behind the behaviors is derived from their signatures at
// comptime (@meta), the same way AddFoo manufactures a field.
//
// three guarantees replace every lock:
//   one message at a time per actor -> actor state is single-threaded
//   causal ordering                 -> A's messages to B arrive in send order
//   only val / iso cross actors     -> data races are compile errors
//
// sendability is checked, not bought with deep copies: an iso
// is handed over with `consume`, and using it afterward is an
// error. same checker as `self :: @Self` and Drop-moves
//
// the program exits by quiescence: when every mailbox is empty
// and no io is pending. main RETURNING is not the program
// exiting — main's drops run when main's scope ends, and the
// runtime outlives it. nothing to join, nothing to wait on

ActorError* = Closed | Full

// the address of an actor. freely sendable. behavior calls on
// a Ref are messages. every Ref also carries:
//   stop* ::= (self: @Self) ()  // delivers stopped after the mailbox drains
Ref*<A> = {
    id: u64,
}

Context* = {
    env: Env,      // authority flows from Env, no ambient globals

    // per-actor arena (pony's per-actor heap, minus the GC),
    // rooted in the RUNTIME, not in main's arena: an actor
    // draining its mailbox after main returns still has memory.
    // drops when the actor stops, freeing everything it made
    alloc: Alloc,
}

Actor* = {
    // optional lifecycle hooks (::= with no body = optional):
    // started runs on spawn, stopped after stop() drains the box
    started* ::= (self :: @Self, ctx: Context) ()
    stopped* ::= (self :: @Self, ctx: Context) ()
}

// on Env, the capability root:
// spawn* = <A: Actor>(self: @Self, actor: A) Ref<A>
```

```groovy
// ~/zen/src/std/thread.zen
// what the scheduler runs actors on. an escape hatch for ffi
// and batch work only; NEVER block inside a behavior, it parks
// a scheduler thread and starves every actor queued on it.
//
// a thread is authority — the one kind that can outlive its
// creator — so it hangs off Env like io and pages do. there is
// no ambient thread.spawn

ThreadError* = SpawnFailed | Panicked

Thread* = {
    id: u64,

    // block until the body finishes, yields its result
    join* = <T>(self: @Self) Res<T, ThreadError>
}

Threads* = {
    // body is a closure; it captures its scope. an escaping
    // closure needs memory, so it says so: the Alloc law does
    // not stop at collections
    spawn* = <T>(self: @Self, a: Alloc, body: () Res<T, ThreadError>) Res<Thread, ThreadError>

    sleep* = (self: @Self, ms: u64) ()
}
```

# Example Zen Code

```gitignore
# ~/example_zen/.gitignore

*.exe
*.dll
*.so
*.dylib
*.lib
*.obj
*.pdb
*.exp
*.def
build/
```

```c
// ~/example_zen/src/extern_add.c

int add(int a, int b) {
    return a + b;
}

// ~/example_zen/src/extern_add.h

int add(int a, int b);
```

```groovy
// ~/example_zen/build.zen
// build files are zen programs; b is the Builder from std.build.
// b is `::` because b.add / b.exe / b.test mutate the graph

// package declarations are plain data at module level, build()
// wires them into the graph. hash-locked, and the cli edits
// these lines for you: `zen add json` / `zen remove json`
json_pkg = Package(
    url: "https://github.com/zen-pkgs/json",
    version: "0.3.1",
    hash: "sha256:9f2a...",
)

build = (b :: Builder) Res<(), BuildError> {

    // and build programs can branch on the target, match on
    // b.os right here, no cfg annotations, no ifdef
    lib_paths = b.os.match({
        Macos => ["/opt/homebrew/lib"],
        Linux => ["/usr/local/lib"],
        Windows => ["C:/sodium/lib"],
    });

    json = b.add("json", json_pkg);

    libsodium = b.lib("libsodium", {
        src: Path("src/extern.c"),
        libs: ["sodium"],
        paths: lib_paths,
    });

    extern_add = b.extern("extern_add", {
        src: Path("src/extern_add.c"),
        libs: ["add"],
        paths: lib_paths,
    });

    // per-os executable suffix
    ext = b.os.match({
        Windows => ".exe",
        _ => "",
    });

    // deps are wired per target, swift-style: main.zen may only
    // import from pkg what this list declares. out defaults to
    // build/{os}-{arch}/{name} if omitted; gitignore covers build/
    b.exe("example_zen", {
        src: Path("src/main.zen"),
        deps: [json, libsodium, extern_add],
        out: Path("build/{}-{}/example_zen{}", b.os, b.arch, ext),
    });

    // test discovery is just code, not compiler magic: walk the
    // PARSED module tree, keep every function whose single
    // parameter is a Tester. `zen test` merely runs the target
    // this registers. change the filter, change what a test is
    tests ::= b.alloc.Vec<Function>();
    b.module(Path("src")).functions.loop((h, f) {
        (f.params.len == 1 && f.params.get(0).try().type == Tester)
            .then(() { tests.add(f).try() });
    });

    b.test("example_zen_tests", {
        tests: tests,
        deps: [json, libsodium, extern_add],
    });

    // benches: same walk, different filter. this is the "change
    // the filter, change what a test is" promise, kept
    benches ::= b.alloc.Vec<Function>();
    b.module(Path("src")).functions.loop((h, f) {
        (f.params.len == 1 && f.params.get(0).try().type == Bencher)
            .then(() { benches.add(f).try() });
    });

    // budgets live HERE, in code, reviewed like code. allocs_op
    // and bytes_op are deterministic, so over budget FAILS the
    // build. ns_op is wall clock, tracked against a rolling median
    b.bench("example_zen_bench", {
        benches: benches,
        budgets: [
            Budget(name: "vec_add", ns_op: 40, allocs_op: 1, bytes_op: 64),
        ],
    });

    // and the build budgets itself: per-target compile times are
    // tracked, so a build never quietly grows to 20 minutes
    b.budget(Duration.seconds(60));

    Ok(());
}
```

```groovy
// ~/example_zen/src/main_test.zen
// tests live next to code. no annotations: build.zen's walk
// finds these because their single parameter is a Tester

vec_grows* = (t: Tester) Res<(), TestError> {
    v ::= t.alloc.Vec<i32>();
    v.add(1).try();
    v.add(2).try();
    t.expect_eq(v.len, 2).try();
    Ok(());
}

shape_prints* = (t: Tester) Res<(), TestError> {
    s = Shape.Unit;
    out = t.alloc.String("{}", s).try();
    t.expect_eq(out.view(), "unit").try();
    Ok(());
}

// a bench: found by the Bencher filter in build.zen
vec_add* = (bn: Bencher) Res<(), TestError> {
    bn.iter(() {
        v ::= bn.alloc.Vec<i32>();
        v.add(1);
    });
    Ok(());
}
```

```groovy
// ~/example_zen/src/main.zen

// imports are just bindings; std and pkg are namespaces.
// pkg contains exactly what build.zen declared for THIS target,
// importing anything else is a compile error.
//
// importing a type pulls its world along: its methods, its
// trait impls, and exported ufcs functions (a free function
// whose first param is the type is callable as a method).
// * is the one gate — it means "this name crosses a module
// boundary" — so Vec travels with add/get but never grow or Entry
json = pkg.json
sodium = pkg.libsodium

Circle = {
    radius: f64,
}

// ufcs: a free function whose first param is Circle, so it
// travels with Circle when imported and calls like a method.
// this IS the method form — a method is a ufcs function whose
// first parameter is named self and whose type is inferred
area* = (c: Circle) f64 {
    c.radius * c.radius * 3.14159
}

Rect = {
    width: f64,
    height: f64,
}

// variants carry payload types; a default payload and a
// discriminant are different things and are written apart
Shape = Circle(Circle) | Rect(Rect) | Unit

Shape.impl(Display, {
    // defining the outlined toString: pretty output for {}.
    // dump stays available for free alongside it
    toString ::= (self: @Self, out :: Sink) Res<(), WriteError> {
        self.match({
            Circle(circle) => out.add("circle: {}", circle.radius),
            Rect(rect) => out.add("rect: {} {}", rect.width, rect.height),
            Unit => out.add("unit"),
        });
    }
})

DumpAst = (sb :: String, n: Enum) Res<(), IoError> {
    sb.add("Enum {}", n.name);
    n.fields.loop((h, field) {
        sb.add("{}: {}", field.name, field.value);
    });
}

DumpAst = (sb :: String, n: Struct) Res<(), IoError> {
    sb.add("Struct {}", n.name);
    n.fields.loop((h, field) {
        sb.add("{}: {}", field.name, field.value);
    });
}

DumpAst = (sb :: String, n: Function) Res<(), IoError> {
    sb.add("Function {}", n.name);
    n.params.loop((h, param) {
        sb.add("{}: {}", param.name, param.value);
    });
}

DumpAst = (sb :: String, n: Other) Res<(), IoError> {
    sb.add("Other {}", n.name);
}

// generic entry: comptime match on the node kind. the kind is
// an ordinary enum carrying the node as payload, so the arm
// BINDS the typed node and overload resolution just works,
// no casts, no as_* anything. these are ast.zen's own nodes —
// the same ones gen_c consumes
DumpAst<T> = (sb :: String, n: T) Res<(), IoError> {
    @meta(n).type.match({
        Enum(e) => DumpAst(sb, e),
        Struct(s) => DumpAst(sb, s),
        Function(f) => DumpAst(sb, f),
        Other(o) => DumpAst(sb, o),
    });
}

// @meta BUILDS as well as reads: this returns a new ast node.
// two calls to AddFoo(Circle) are ONE type, memoized on the
// call and its arguments
AddFoo<T> = (n: T) Res<T, Error> {
    @meta(n).type.match({
        Struct(s) => {
            s.fields.add(Field(name: "foo", value: 1));
        },
        _ => Err(Error("Invalid node type")),
    });
    Ok(n);
}


// actor example, pony-style: behaviors are async methods
Foo = {}

Foo.impl(Actor, {
    // optional lifecycle hooks. println resolves through
    // ctx.env — a Context carries an Env, so one is in scope
    started ::= (self :: @Self, ctx: Context) () { println("actor started") }
    stopped ::= (self :: @Self, ctx: Context) () { println("actor stopped") }

    // behaviors: calling one on a Ref<Foo> enqueues a message
    // and returns immediately. params must be sendable (val or
    // iso). the message enum is derived at comptime via @meta
    receive_msg = (self :: @Self, ctx: Context, data: str) () {
        println("actor has received {}", data)
    }

    // request/response the pony way: the request carries the
    // reply ADDRESS, and the response is just another behavior
    // call. no promise, no await, no second concept
    compute = (self :: @Self, ctx: Context, n: i32, reply: Ref<Collector>) () {
        reply.result(n + 1);
    }
})

Collector = {}

Collector.impl(Actor, {
    result = (self :: @Self, ctx: Context, v: i32) () {
        println("got {}", v)
    }
})


// what this program expects: a schema, not string fishing.
// fields are bindings, so defaults use the same syntax as any
// typed binding. a field with a default is optional; no
// default and no Res means required
Opts = {
    name: Res<str>,          // --name or NAME, optional, may be absent
    verbose :: bool = false, // --verbose or VERBOSE, defaults false
}

Error = AllocError | IoError | ArgError | ThreadError

// main receives the capability root. it is not named `self`:
// main is not a method on Env. println finds the Env by TYPE
main = (env: Env) Res<i32, Error> {

    // Env fills the schema via @meta; missing required fields
    // error by name before your logic ever runs
    opts = env.args<Opts>().try();

    name = opts.name.match({
        Ok(n) => n,
        None  => "world",
    });

    opts.verbose.then(() { println("hello, {}", name) });

    Circle1 = AddFoo(Circle); // memoized on the call: one type
    c1 = Circle1(radius: 1.0, foo: 1);
    a = c1.area();           // ufcs: free function, method syntax

    // arena allocator: page authority comes from Env, nothing
    // ambient. implements Drop, so everything allocated from it
    // frees in one shot when alloc leaves scope at end of main
    alloc ::= env.mem.alloc();

    // functions are just bindings of lambdas, so they're values.
    // function types name their parameters — names are
    // documentation, not identity, and resolution never sees them
    add_i32 = (a: i32, b: i32) i32 { a + b }
    apply = (f: (a: i32, b: i32) i32, a: i32, b: i32) i32 { f(a, b) }
    nine = apply(add_i32, 4, 5);

    // ::= makes the function itself rebindable
    op ::= add_i32;
    op = (a: i32, b: i32) i32 { a * b }

    // closures capture their scope. this one does not escape,
    // so it needs no Alloc
    base = 10;
    add_base = (x: i32) i32 { x + base }

    // actors, pony-style: foo IS the address, calling a
    // behavior IS sending a message. async is visible right
    // here: each call below returns IMMEDIATELY, the prints
    // happen later, on foo's turn, in send order (causal)
    foo = env.spawn(Foo());
    Range(0, 5).loop((h, v) {
        foo.receive_msg("hello world!");
    });
    println("sent all five");   // may print BEFORE any receive

    // request/response without promises: send our collector's
    // address, the reply lands in its mailbox as a message
    bar = env.spawn(Collector());
    foo.compute(41, bar);       // returns immediately
                                // "got 42" prints when bar runs

    foo.stop();   // stopped runs after foo's mailbox drains
    // nothing to join or wait on: the program exits by
    // quiescence once every mailbox is empty. main returning
    // is NOT the program exiting

    // threads, the escape hatch: authority from Env, never
    // ambient. legal in plain code like main, banned inside
    // behaviors (blocking parks a scheduler thread). the body
    // escapes, so it takes an Alloc — the law does not bend
    t = env.threads.spawn(alloc, () Res<i32, ThreadError> {
        Ok(21 * 2);   // imagine ffi or heavy batch work here
    }).try();
    t.join().match({
        Ok(v)  => println("thread says {}", v),
        Err(e) => println("thread failed: {}", e),
    });

    // fixed arrays: [type, count], comptime size, stack, no alloc.
    // indexing is bounds-checked and traps — no Res here
    primes = [i32, 4](2, 3, 5, 7);

    // collections come from the arena; .try() propagates errors,
    // and the error sets merge into main's Error union
    names ::= alloc.Vec<str>();
    names.add("ada").try();

    ages ::= alloc.Map<str, i32>();
    ages.set("ada", 36).try();

    // ad-hoc cleanup: registered on THIS block, runs LIFO at
    // block exit, before drops. @scope is the block itself
    @scope.defer(() { println("goodbye") });

    // fold variant: 0 seeds acc, loop evaluates to the final
    // acc. stack array, by-value acc, capture-free body: this
    // compiles to a plain for-loop, zero allocations
    sum = [0, 1, 2].loop(0, (h, i, v, acc: i32) {
        acc + v
    });

    // {} routes through toString, or dump if a type has none;
    // sum.toString(alloc) is the same thing via the sealed overload
    alloc.String("{}", sum).match({
        Ok(s)  => println(s),
        Err(e) => println("error: {}", e),
    });


    const_val_implicit = 1;
    const_val_explicit : i32 = 1;
    mutable_val_implicit ::= 1;
    mutable_val_explicit : i32 ::= 1;

    // arithmetic traps on overflow. want wrapping? say so
    wrapped = const_val_implicit +% 255;


    // one conditional form: .match, a method, exactly like loop is a
    // function. no if, no ternary, no ? operator. every case covered,
    // always — in statement position too
    label = (const_val_implicit == 0).match({
        true => "zero",
        false => "nonzero",
    });

    // want one side only? say it. .then cannot be mistaken for a
    // forgotten arm, because it is a different word
    (const_val_implicit == 0).then(() { println("const_val_implicit is 0") });


    some_static_string = "hello";                        // str: borrowed bytes
    some_dynamic_string = alloc.String("{}!", "hello");  // String: owned, arena-backed

    Ok(0);
    // scope ends: defers run first, then drops in reverse order,
    // alloc last, freeing every String this arena handed out
}
```

---

# Still open

- **`println` and `Env`.** Resolving `println` to the in-scope binding *of type* `Env` gives `Env` a slightly privileged position in name resolution. That is the cost of keeping both the no-ambient-authority law and a two-line hello-world. The alternative is no sugar at all: `env.out.println(..)` everywhere.
- **Operator overloading.** `==` through `Eq` is the only operator that dispatches to an impl, so `a + b` on a `Duration` is not writable and a module that wants it writes `add`. Whether arithmetic should dispatch is the difference between a `Duration` reading like a number and one reading like a record, and it is a language decision nobody has made.
- **`Ord`.** `std.core` has `Eq` and `Hash` and nothing that orders. The open question is not whether to add a trait: `Ord` and `Eq` must agree exactly as `Eq` and `Hash` must, so which of the two is sealed in terms of the other is the design.
- **Supervision.** A trap aborts the process. Killing only the offending actor is the Pony answer and needs a supervision story that does not exist yet.
- **`env.threads.spawn` vs `env.blocking.run`.** If the only legitimate use of a thread is running blocking work off the scheduler, the honest capability is `blocking.run` — it makes the misuse unrepresentable rather than merely discouraged.
- **Comptime file reads.** Excluded from v1 for reproducibility. `@embed_file` is the feature people will ask for.
