# `@meta` and comptime

Companion to `DESIGN.md`, `PLAN.md` and `TESTING.md`. Those say what the language is, what to build and how a gate fails; this says what `@meta` is, what of it exists, what has to be decided before code can be written, and in what order the rest lands.

`PLAN.md` stage 5 owns it. `STAGE` reads `4`.

`DESIGN.md:457` has already decided the thesis, and everything below is held to it:

> `@meta` **builds and reads**, and it does not get a parallel node type — it gets the compiler's own. `@meta(n)` hands back the same `Struct` / `Enum` / `Function` values from `std.ast` that `DumpAst` walks and `gen_c.zen` consumes. One AST, three consumers.

---

## 1. The scoping answer, first, because it bounds everything else

**`@meta` stays out of `bootstrap/`, and the reason is not politeness — it is that `src/` may not use it.**

| claim | evidence |
|---|---|
| `@meta` is not in the seed subset | `docs/PLAN.md:224`; `:228` — "`@meta` alone would roughly double it" |
| so the compiler adopts it only after self-hosting | `docs/PLAN.md:381` — "Only after this does the compiler start using `@meta` on itself"; `DESIGN.md:39` |
| and `src/` does not use it today — **zero real sites** | every `@meta` in `src/` is a comment or a string literal: `std/core/display.zen:33`, `std/core/hash.zen:31`, `std/core/eq.zen:10`, `std/env/env.zen:153`, `std/test/test.zen:37`, `std/build/build.zen:27`, `std/ast/ast.zen:2`, plus the lexer's own table entry and diagnostic text |
| `bootstrap/` is off the BUILD path | `make build` compiles `seed/zen.c`; nothing in the build calls Python |
| but it is **on the verification path for `src/`** | `scripts/fixpoint.sh:4` — stage 1 is `bootstrap src/ -> stage1.c -> zen-1`. `scripts/style.py:257` and `ufcs_collisions.py:94` also parse all of `src/` through `bootstrap/cst.py` |
| so the bootstrapper meets `@meta` only in a **test fixture** | which is the whole lever: a fixture the bootstrap toolchain never runs costs bootstrap nothing |

**The bill `PLAN.md:228` prices is the bill for putting `@meta` IN the seed subset.** It is not in it, so the bill is not owed — provided nobody writes `@meta` into `src/`. That single constraint is what makes this feature bounded, and it is the one thing a later lane must not quietly spend.

**And the constraint bites harder than the plan says.** `PLAN.md:228` frames `@meta` in `src/` as *work the bootstrapper would have to do*. It is worse than that: the bootstrapper compiles `src/` as **fixpoint's stage 1**, so the first `@meta` written into `src/` does not make the seed expensive — it makes `make fixpoint` red, and takes the project's strongest oracle off the board for every unrelated change at the same time. `src/sema/sema_meta.zen` implements `@meta` and, correctly, does not use it.

**What bootstrap already does, and it is more than "nothing":** `bootstrap/lex.py:73` (`AT_NAMES`) tokenizes `@meta`; `grammar/grammar.js:591` parses both forms; `bootstrap/cst.py:1182` lowers it to `A.MetaCall`; `bootstrap/sema.py:2786` types it as `ANY`; `bootstrap/gen_c.py:6263` refuses it by name. So the bootstrapper can *read* every `@meta` program and will *never* compile one. That is exactly the right shape and needs no further work.

**One divergence to know about:** in the typed form, `bootstrap/cst.py:1182` **drops the name** and keeps only the type, while `src`'s `ast.Meta` keeps `name` + `type` (`ast_node.zen:356`). The two ASTs already disagree about `@meta(self: @Self)`. Harmless while both refuse; a trap the day anything reads the name.

---

## 2. What exists — do not write it twice

| what | where |
|---|---|
| `@` is a closed namespace of three, enforced in one place | `src/std/lex/lex_scan.zen:181` (`at_kind`), fault at `lex_diag.zen:68` |
| `@meta` is a token | `src/std/lex/lex_token.zen:73` (`AtMeta`), `:123` |
| both forms parse | `src/std/parse/parse_expr.zen:544` (`meta_expr`), `:562` (`typed_meta`), `:571` (`value_meta`) |
| the node | `src/std/ast/ast_node.zen:356` (`Meta`), variant at `:193`, contract row `src/AST_CONTRACT.md:273` |
| the grammar's twin | `grammar/grammar.js:591` — so `make parse` and `make grammar-test` cover the syntax |
| the formatter needs nothing | `src/fmt/fmt.zen` passes declarations through verbatim, guarded by `faithful` — `@meta` formats by construction |
| the editor paints it | `src/lsp/lsp_colour.zen:185` |
| **one AST, and it is already the target** | `src/std/ast/ast_arena.zen:56` — `Ast.add_expr` is exported and appends; a comptime-built node has an arena to live in |
| **hygienic inlining of a lambda at a call site** | `src/gen/gen_c/gen_c_inline.zen` — `Closure` records both scope depths and `run_closure` rewinds to them. This is the field-walk's unroll, already written |
| **one body per instantiation** | `src/gen/gen_c/gen_c_mono.zen`, reading `sema_inst.zen`'s answer back |
| a step-budgeted expression folder, with the argument for the budget | `src/sema/sema_trap.zen:392` (`FOLD_DEPTH`), `:396` (`const_int`) |
| the refusal | `src/sema/sema_meta.zen` — §3, M0 |

`sema_trap.zen:386` is worth quoting because it draws the line this document has to cross:

> A budget is right here (elsewhere a bound must REPORT) because this is a **prover**: declining to prove is already what this file does for values reached through a binding.

The comptime evaluator is not a prover. Declining is not an available answer, so its budget must report — which is why "step-budgeted" is in M2's definition and not in a hardening pass after it.

## 2.1 Must NOT be built

- **A parallel node type.** `DESIGN.md:457`. `@meta` hands back `std.ast`'s own `Struct` / `Enum` / `Function`. A convenience view with friendlier field names is that mistake wearing a new hat, and §4 is where the temptation actually arrives.
- **A second evaluator.** If the C backend can compute a comptime value that sema cannot, the two disagree and only the fixpoint will notice — and the fixpoint is blind here (§6).
- **A macro system.** There is no quotation syntax, no hygiene annotation, no `@meta` in a pattern. `@meta` is a function call whose argument is a value or a type.
- **File reads at comptime.** `DESIGN.md:472`: "the fastest route to a build that is not reproducible."
- **A fourth `@` entry.** `DESIGN.md:111`. If a milestone below seems to need one, it is the milestone that is wrong.
- **`@meta` anywhere in `src/`.** §1 is the whole reason this feature is affordable.

---

## 3. M0 — the wall. LANDED

`src/sema/sema_meta.zen`: `@meta` is refused in sema, by name, once.

Before: `expr_kind` had no `Meta` arm, so the node fell to `Ty.Unknown`; `Unknown` agrees with everything, so `@meta(p).name` drew nothing at all, and the only sentence came from the backend — "codegen does not lower this yet: `this expression form`" — plus a **second** one when the poison reached `println`. Two diagnostics, one mistake, neither naming the feature, both from the one phase that has no business holding a language rule.

After: one diagnostic at the `@meta` token, naming `@meta` and pointing here. A sema fault stops the pipeline before `emit` (`zen/zen_build.zen:547`), so the cascade closes for free.

**Gated by three must-fail tests, and they pass on BOTH toolchains** — `meta_value_form_refused`, `meta_typed_form_refused` (the two parse branches), `meta_refusal_does_not_cascade` (carrying `.count 1`). `bootstrap/gen_c.py:6264` was reworded so the two implementations share one substring, `` `@meta` is not implemented yet ``, because a must-fail expectation is read by both and a sentence only one writes is a red board (`STAGE`).

**Mutation-checked, not assumed:** all three go red against the pre-change binary built from `seed/zen.c`, and `meta_value_form_refused` shows the old cascade there as two diagnostics.

**This refusal is the only part of `@meta` the differential oracle will ever see.** §6.

---

## 4. The surface is under-specified, and that is M1

`DESIGN.md`'s three `@meta` examples do not type-check against `src/std/ast/ast_node.zen`. This is not pedantry: "it gets the compiler's own nodes" is the entire thesis, and three of the names in the worked examples are not the compiler's.

| written in `DESIGN.md` | what `src/std/ast/` actually has | the collision |
|---|---|---|
| `@meta(self: @Self).fields` (`:565`) | `Struct.members*: Vec<Member>`, `MemberKind = Field \| Const \| Function` | there is no `fields`. A field-wise walk is `members` filtered to `MemberKind.Field` |
| `field.value` (`:566`), meaning *this instance's value* | `Field.value*: Res<ExprId>` — the **default expression** | the name is taken, and by something with a different meaning. Two readings of one member is exactly the field-default trap `STAGE` records |
| `@meta(n).type` (`:1324`) | `Decl.kind*: DeclKind` | `type` is not a member of any node; and the example's `Other(o)` arm is not one of `DeclKind`'s seven variants, so as written it is also not exhaustive (`SemaFault.NotExhaustive`) |
| `Field(name: "foo", value: 1)` (`:1338`) | `Field.name*: Ident`, `Field.value*: Res<ExprId>` | a `str` where an `Ident` goes and an `i64` where an id goes. Building a node needs a **builder** over an `Ast`, which exists (`ast_arena.zen:56`) but is not what the example writes |

There is a further ambiguity `tests/parse/constructs.md` already flags as **A-META-ARG** and does not settle: in `@meta(self: @Self)`, is `self: @Self` a labelled argument, a type ascription, or `@meta`-specific syntax? The parser has answered structurally — `Meta` carries `name` + `type` as its own fields — but the *meaning* is unrecorded, and the bootstrapper has already answered differently (§1).

**So M1 is a decision, not code**, and it is the user's: `DESIGN.md` is the constitution and three of its sentences have to move. The cheapest resolution that keeps the thesis intact:

- `.fields` becomes a **method on `ast.Struct`** returning its `Field` members. A helper on the real node is not a parallel node type; a struct with friendlier copies of the same data is.
- `field.value` cannot mean two things. The instance projection needs its own spelling — `self.at(field)` or `field.read(self)` — and the default keeps `value`. Naming is a judgement; the collision is not.
- `.type` becomes `.kind`, and the example gains a `_` arm or names all seven variants.
- the build example is rewritten against a builder.

**Gate:** `make design` — every complete example in `DESIGN.md` must parse — plus the table above going to zero rows. **Risk:** ratifying the wrong names here is the one mistake in this whole plan that is expensive to undo, because `Display.dump`'s body is quoted verbatim in `src/std/core/display.zen` and in `DESIGN.md`, and every later milestone is written against it.

---

## 5. What `@meta` actually requires: staging, not evaluation

Read `DESIGN.md:564` closely:

```groovy
out.add("{} {", @meta(self: @Self).name);
@meta(self: @Self).fields.loop((h, field) {
    out.add(" {}: {},", field.name, field.value);
});
```

`field.name` is known at compile time. `field.value` is a **runtime** value, of a **different type at each iteration**. And `out` is a runtime sink. So this loop is not evaluated at comptime and it is not compiled as a loop either: it is **unrolled**, once per field, and each copy of the body is ordinary runtime code with one comptime-known name substituted.

That is partial evaluation over two stages, and it means the evaluator's output is not a value — it is **program text**. Anyone who builds "an interpreter that returns a comptime value" will get `.name` working and discover that the canonical example of the feature does not fit through it.

Consequences, and they are the load-bearing paragraphs of this document:

1. **The evaluator's answer domain has two kinds of thing**: known values, and *residual* expressions standing for something only the running program will know. `self` is residual from the start. `@meta(self: @Self)` is known. `field.value` is residual, derived from a known field name and a residual receiver.
2. **Expansion happens per instantiation, not once.** `Display.dump` means something different for every implementing type. `sema_inst.zen:10` says a generic body is deliberately checked exactly **once**, generically — and `sema.zen` already records that `type_of`'s memo key must become `(ExprId, instantiation)` before hover is correct inside a generic. **A body containing `@meta` is the first body for which "check once" is wrong, and it is wrong for a reason the memo comment does not cover:** the objection there is that re-checking would *duplicate* the diagnostics a body owes, and an `@meta` body's diagnostics are not duplicates — they are different sentences about different instantiations.
3. **The residue must be type-checked.** This tree's worst bugs are unchecked plausible answers: match arms that were never typed, a join that answered `int` at 28 sites, field defaults that silently produced zeros. Code the compiler *generated* is the last place to relax that.

### The fork: where expansion lives

**(a) In the backend, beside `gen_c_mono` and `gen_c_inline`.** Tempting, and cheaper than it looks: the backend already emits one body per instantiation and already inlines a lambda hygienically at a call site (`gen_c_inline.zen`), which is the unroll. The new part is only "a name bound to a compile-time-known value".

Rejected. The residue would never be type-checked; `genJs` would need a second copy of the expander, which is a second definition of the language; and `@meta`'s diagnostics would come from the phase that `sema_meta.zen`'s own header argues is the wrong one.

**(b) In sema, as an AST → AST rewrite at instantiation time.** The expander is a *fourth consumer* of `std.ast` that also **produces** it: `@meta` disappears, and what is left is `out.add(" x: {},", self.x)` — ordinary nodes the backend already lowers, with no backend change at all and nothing for a second backend to duplicate. The residue goes through the type checker like any other code. It is also the honest reading of "one AST, three consumers": the fourth one writes.

**Recommended: (b).** Its two prerequisites are real and should be measured before M2 starts:

- **`Checker.tree` is immutable** (`sema_check.zen:97`, `tree*: Ast`), and an expander appends. Making it `::` has a blast radius nobody has measured, and `Ast` is held **by value**, which is a question about shallow copies of its `Vec`s before it is a question about mutability.
- **Nothing may see the expansion but sema and the backend.** `zen fmt` reprints what the parser produced and `make fmt` asserts the token stream is unchanged (`fmt.zen:45`, `faithful`); expanded nodes must never reach it.

---

## 6. Testing, when the two strongest oracles are blind

`TESTING.md` ranks them: fixpoint, differential, corpus, must-fail, mutation. **The top two cannot see `@meta`.**

- **Fixpoint** compares `zen-1`'s and `zen-2`'s C for `src/` — and `src/` may not contain `@meta`, because fixpoint's own stage 1 is the bootstrapper compiling `src/` (§1). So the strongest oracle is not merely blind to `@meta`: it is the reason `@meta` can never appear where it could see it. It proves the *expander code* compiles deterministically and never once runs it.
- **Differential** compares two implementations, and the second one refuses the feature by design. Its whole coverage of `@meta` is M0's refusal, which is why M0 was worth landing on its own.

So `@meta` is tested by the two oracles that remain — must-fail and mutation — plus two mechanisms that do not exist yet and have to be built with the milestone that first needs them:

1. **must-fail, on both toolchains** — the refusal (M0, done), and later the budget: a `@meta` that does not terminate must fail the build with a diagnostic naming the budget, and *that* test is differential only until the day `src`'s message stops being a refusal. Write the budget test the same day the budget lands, never after.
2. **corpus, zen-only** — which needs a mechanism that does not exist. `tests/run.py` has `.stage` (`:56`, `:893`), and it is stage-keyed, not toolchain-keyed: the day `STAGE` reads `5`, a `.stage 5` `@meta` test becomes **required to pass under `make test`**, which the bootstrapper cannot do. **M3 must add a toolchain sidecar with `.stage`'s exact shape** — a deferred test is RUN, never skipped; if bootstrap *passes* a zen-only test, that is a failure and the sidecar is deleted. Anything else (a suite outside `make test`, a lowered `STAGE`) is a gate that cannot fail, which is this repository's recurring disease and the Makefile diagnoses it three times in its own comments.
   This need is already measured, not predicted: M0 wanted `.count 1` on `meta_value_form_refused` and could not have it, because the bootstrapper still cascades three sentences there. The assertion had to move to a third fixture written in the one shape both toolchains agree about.
3. **A hand-written twin — the substitute for the differential oracle, and the strongest thing available.** Every `@meta` consumer is a *derivation of code somebody could have written by hand*. So each corpus test comes in pairs sharing one byte-identical `.expected`: `x_via_meta` (zen-only) and `x_by_hand` (both toolchains, no `@meta` anywhere). The hand-written twin is the oracle, it is checked by the bootstrapper, and the pair failing to agree is exactly the differential signal `@meta` otherwise cannot get. A gate asserting the pairing exists belongs with the sidecar.
4. **Mutation, and it is not optional here.** `STAGE`'s standing question is "what does this feature's failure look like, and would anyone notice?" For `@meta` the answer is the worst one available: **a walk that silently skips a field prints something plausible.** So every milestone's expectation must contain values no default could produce — distinct non-zero numbers, distinct strings, and a field count asserted out loud — and each new rule gets mutated red on purpose before its zero is believed.

---

## 7. The milestones

M0 is landed. Each of the rest names what it unblocks, its gate, and its risk. The numbering differs from the sketch this lane was handed, and §7.1 says why.

### M1 — the surface, ratified
§4. A decision and a `DESIGN.md` edit; no compiler code. **Unblocks:** every milestone below, all of which are written against these names. **Gate:** `make design`, plus §4's table at zero rows. **Risk:** it is a constitutional change and the wrong names are expensive to withdraw.

### M2 — the comptime evaluator
The language minus io and actors (`DESIGN.md:472`), may allocate, may loop, **step-budgeted from the first commit, and the budget REPORTS** — `sema_trap.zen:386` explains why a prover may decline and an evaluator may not. Two value kinds, known and residual (§5). **Unblocks:** M3 onward. **Gate:** none of its own — see §7.2. **Risks:** (i) a hanging build is the failure mode that makes the feature unusable, so the budget is not deferrable; (ii) recursion in the evaluator over deeply-nested input is a segfault, not a diagnostic — `sema_trap.zen:382` records that this tree has already been bitten there; (iii) allocation at comptime needs an `Alloc`, and whose it is (the `Checker`'s? the `Ast`'s?) is a design question, not a lookup.

### M3 — READ, one member deep
`@meta(self: @Self).name` becomes a `str` in the residue. **The first green line of the feature**, and the whole point of making it a milestone is that it is the smallest thing that exercises the entire path: sema types `Meta`, the evaluator answers, the residue is an ordinary literal, the backend lowers it having learned nothing new. **Also lands the zen-only sidecar and the hand-written-twin pairing (§6).** **Gate:** a `corpus/meta/` pair — `type_name_via_meta` (zen-only) and `type_name_by_hand` — with one shared `.expected`. **Risk:** the temptation to special-case this in the backend and call the feature started. A `.name` that works with no evaluator behind it is a demo and a lie in the tree; `sema_meta.zen` is where it goes instead.

### M4 — STAGING: the field walk
`.fields.loop((h, field) { .. })` unrolled once per field, `field.name` known, the instance projection residual (§4, §5). **Unblocks all five waiting consumers**, one lane each: `Display.dump` (`std/core/display.zen:33`), the `Eq` default (`std/core/eq.zen:10`), the `Hash` default (`std/core/hash.zen:31`), `Tester.expect_eq` (`std/test/test.zen:37`), `Env.args`' schema fill (`std/env/env.zen:153`). **Gate:** hand-written twins, plus an expectation that names every field with a distinct non-default value and asserts the count (§6.4). **Risk:** this is the keystone and the largest single piece. A skipped field prints plausibly; a nested struct recurses into `dump` and is where a step budget first earns its keep; and hygiene — `gen_c_inline.zen`'s header is the record of how a captured `h` goes silently wrong rather than loudly.

### M5 — comptime dispatch on a node's kind
`@meta(n).kind.match({ .. })` — `DumpAst`'s shape (`DESIGN.md:1329`), and what lets `std/build/build.zen`'s `Module` and `Function` stand-ins (`:38`) be deleted in favour of the real nodes. **Gate:** `corpus/std/build_api_resolves` extended to walk a real `Function`. **Risk:** it is a *type* switch, which touches the same ground as the type-sets feature; keep it to matching on `DeclKind` and do not let a general type-switch in through this door.

### M6 — BUILD
Returning new nodes; two calls with the same arguments are one type, memoized on (function, arguments) (`DESIGN.md:459`); declared types stay nominal. **Deliberately last: no consumer in the tree needs it.** All six waiting sites read. Once M2 and M4 exist it is also the cheap one — the arena is already there (`ast_arena.zen:56`) and what is missing is a builder surface (§4) and the memo. **Risk:** identity. "One emitted struct per distinct call" is a `gen_name`/mangling question, and getting it wrong collides two types into one symbol, which is `gen_c_mono.zen`'s already-recorded failure mode.

### 7.1 Why this is not the M0–M3 in the brief

The sketch was: evaluator, then `@meta` READ, then `@meta` BUILD, then the consumers. Three corrections, each from something in the tree:

- **BUILD moves from third to last.** Not one of the six waiting consumers needs it; all six read. Putting it third spends the feature's hardest identity question before anything it unblocks.
- **STAGING becomes its own milestone between READ and the consumers.** `Display.dump` does not need "@meta returns a value" — it needs a comptime loop with runtime residue (§5). Fold it into READ and READ stops being small; fold it into the consumers and five lanes each discover it separately.
- **The evaluator cannot be a standalone gated milestone.** §7.2.

### 7.2 Why M2 cannot be gated on its own

An evaluator with no caller is a gate that cannot fail, so the instinct is to give it a caller that is not `@meta`. The obvious candidate looks perfect and is a trap.

`DESIGN.md:313` makes an array's count part of its type, and `sema_type.zen:151` says what that costs: "The count is an EXPRESSION because it's comptime, not literal: `[u8, i32.BITS]` folds like `i32.MAX + 1`." So the language already has a position that promises comptime evaluation and is not `@meta`. It is also genuinely broken today, in this tree's favourite way — **silently**:

```groovy
SIZE: usize = 4
b: [u8, SIZE] = [1, 2, 3, 4];   // reports: expected [u8, 0], found [int, 4]
```

`const_count` (`sema_trap.zen:356`) declines on a named constant and the count becomes **0**, so the type is `[u8, 0]`, every index into it is out of range, and the diagnostic blames the literal instead of saying the count did not fold. The bootstrapper declines too and answers `None` rather than `0` (`bootstrap/sema.py:1501`) — the two implementations already disagree here, and no test asks.

**But the array-count position is INSIDE the seed subset.** A corpus test for it must pass under `make test`, so fixing it properly means teaching the bootstrapper to evaluate too — which is `PLAN.md:228`'s bill, arriving through a side door, for a feature that was supposed to cost bootstrap nothing.

So: **the comptime evaluator's only legitimate entry point is `@meta`.** M2 lands under M3's gate, in one lane with it, and the array-count defect is a separate, smaller, seed-subset bug that should be fixed in both implementations on its own ticket — not smuggled in as the evaluator's test harness.

---

## 8. What this document does not answer

Named rather than left to be discovered:

- **Whose allocator does comptime code use**, and what happens to what it allocated once expansion is over (M2).
- **What the step budget's number is**, and whether it is per `@meta` call or per compilation. `FOLD_DEPTH: usize = 256` is a depth, not a step count, and it is a prover's budget (§2).
- **Whether `@meta(v)` on an ordinary value reflects the value's TYPE or its expression.** `DESIGN.md:455` says "the ast node for a value or a type"; `:1324` reads it as the type. `@meta(p)` on a `Point` has no settled meaning today, which is why M0's fixtures assert only that it is refused.
- **What `@meta` does inside a generic body with an unbound `T`.** `gen_c_mono.zen` refuses an open type at the backend; the expander needs the same rule earlier, and the diagnostic is easier to write than to place.
- **Whether `@meta` may appear in a type position.** Nothing in `DESIGN.md` writes it there; `M6` returning a type implies something does.
