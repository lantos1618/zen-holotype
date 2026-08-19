# Bootstrapper and `std` gaps found while writing `src/sema/`

> **The bootstrapper is deleted.** This document is a record, not a map:
> every `bootstrap/*.py` coordinate below resolves only in git history
> (`git show 4d05320a:bootstrap/gen_c.py`), and no gate can re-verify one.
> What is still worth reading is the Zen behaviour each entry describes.

Most-blocking first. Every reproducer is a complete program, run the way
`tests/run.py` runs one: a compilation root holding the program as
`main.zen` with `src/` beside it.

**Nothing here is fixed.** `bootstrap/` and `src/std/` belong to other
agents. Each entry says how `src/sema/` works around it and what the
workaround costs.

Read `docs/LEXER_BOOTSTRAP_FIXES.md` first — its §2 (a match takes its
type from its FIRST arm) bit this folder repeatedly and is worked around
throughout by putting the arm whose type is written down first. Its §3
(a void call in trailing position is discarded) is **fixed** and was
re-tested rather than worked around.

---

## 1. `ok_or` on a `Res<()>` reports `unresolved name value`

**Blocking: no — but it is a false diagnostic, so it fails a gate that
counts diagnostics while emitting correct code.**

`std.core.result.ok_or` is `<T, E>(r: Res<T>, reason: E) Res<T, E>`, and
its body binds the payload: `Ok(value) => Ok(value)`. Instantiated at
`T = ()`, the binder does not resolve.

```groovy
Alloc, AllocError = std.mem
Vec = std.collections

main = (env: Env) Res<i32, AllocError> {
    alloc ::= env.mem.alloc();
    v ::= alloc.Vec<i32>();
    v.add(7).try();
    // Vec.set returns Res<()> -- an absence. Naming its reason with
    // ok_or should make it a Res<(), AllocError>.
    v.set(0, 9).ok_or(AllocError.OutOfMemory).try();
    println("{}", v.get(0).match({ Ok(n) => n, None => 0 }));
    Ok(0);
}
```

```
src/std/core/result.zen:61:25: unresolved name `value`
bootstrap: 1 diagnostic(s)
```

The emitted C is nonetheless correct — the program prints `9`. So this
is a spurious diagnostic on a unit payload, not a miscompilation.

It matters because `ok_or` is **the only** sanctioned route from a
`Res<T>` to a `Res<T, E>` ("this is the ONLY way a `Res<T>` becomes a
`Res<T, E>`: there is no From"), and `Vec.set`, `Vec.take` and `Map.get`
all return bare `Res`. Any of them at `T = ()` hits this.

**Workaround in `src/sema/`:** `sema_ty.zen`'s `put` matches instead of
naming the reason:

```groovy
put* = (out :: Vec<TyId>, i: usize, v: TyId) Res<(), AllocError> {
    out.set(i, v).match({
        None  => Err(AllocError.OutOfMemory),
        Ok(_) => Ok(()),
    })
}
```

Five lines where one was specified, and the `_` throws away a binding
the language says is there.

---

## 2. A bar-form declaration silently becomes a union of existing types

**Not a bootstrapper bug — a `DESIGN.md` hole. The diagnostic was
correct and it still cost an hour.**

`sema_def.zen` wanted an enum of the declaration forms:

```groovy
DefKind* = Struct | Enum | Alias | Function | Const
```

Those five names are `ast`'s node types. DESIGN.md gives the bar form
two readings — "`Shape = Circle(Circle) | Rect(Rect) | Unit` // nominal,
with payloads" and "`Error = AllocError | IoError | ArgError` // a union
of existing types" — and which one applies is decided by **what the
names mean**, not by how the declaration is written. So this is a union
of five struct types, and every use site fails:

```
sema_def.zen:284:49: `DefKind.Struct` carries a value of type `Struct`
                     -- write `DefKind.Struct(e)`
```

The trap is that the reading depends on names that are in scope
**somewhere else**, so adding an import to an unrelated module can
change what a declaration in this one means. `ast_node.zen` already
dodged it by hand — "`Equal` and not `Eq` because `Eq` is a prelude type
and a variant that shadows one is a trap laid for the next reader" — but
that is a convention, not a rule the compiler enforces.

**Workaround:** every `DefKind` variant carries a `Def` suffix
(`StructDef`, `EnumDef`, …). Uglier, and unique tree-wide, which is what
`STYLE.md`'s grep test asks for anyway.

**What DESIGN.md should say:** either a nominal enum's variants may not
shadow a type in scope (an error at the declaration, naming both), or
the two readings get two spellings. Right now the language has a
declaration form whose meaning is not local to its own file.

---

## 3. `std.core.num` has no narrowing conversion, so an index cannot
   become a `u32`

**A `std` gap, not a bug, and the design reason for it is sound.**

`ast_id.zen` states it: "`std.core.num` carries only LOSSLESS
conversions — a narrowing one can fail, so it belongs in a
`Res`-returning function someone writes on purpose". Correct. But no
such function exists, and every id in this compiler is a `u32` while
every `Vec` index is a `usize`.

`Ast` solved it by keeping a parallel `u32` counter beside each arena.
`sema_def.zen` cannot: it is handed `Vec` positions by `Range`, so it
counts:

```groovy
index_u32* = (v: usize) u32 {
    n ::= 0;
    Range(0, v).loop((h, i) { n = n + 1; });
    n
}
```

That is O(n) per declaration indexed, which is O(n²) over a module. It
is correct and it is embarrassing.

**What is wanted:** `to_u32* = (self: usize) Res<u32>` in
`std.core.num`, absence meaning "does not fit". One function, and both
`Ast`'s counters and this loop delete.

---

## 4. `std.text` has no ordering on `str`

`str` impls `Eq` and `Hash` and nothing else. Canonicalising an error
set means sorting its members, and sorting means comparing.

`sema_ty.zen` declares `key_before(a: str, b: str) bool` locally with a
header saying it does not belong there. By the stranger test —
"orders two byte strings lexicographically" names no module — it belongs
beside `str.eq` in `std.text.text_str`.

**What is wanted:** `before*` or an `Ord` bound in `std.text`. The
moment it exists, `key_before` deletes and an import replaces it.

---

## 5. `String.add` speaks `WriteError`, so no single-error-set function
   can format a number

**The language working exactly as specified, with a cost worth naming.**

`String.add(fmt, args)` returns `Res<(), WriteError>`, and `WriteError`
is `AllocError | IoError`. `src/sema/` returns `Res<_, AllocError>`
everywhere, because the seed subset is "one nominal error enum per
function". There is no From, so `.add("{}", n).try()` cannot propagate:

```
sema_ty.zen:219:51: no implicit error conversion: AllocError | IoError
                    is not part of AllocError
```

This is law 4 doing its job. But it means **any** function that both
formats a number and keeps one error set has to spell the digits itself.
`sema_diag.zen` carries `write_usize`, which writes a decimal a digit at
a time by recursion, purely to render `line:col`.

**What is wanted:** an `AllocError`-only integer writer in
`std.text.text_fmt` — the digits already exist there, since `Sink`'s
`write_byte` was introduced precisely so "printing an integer" need not
allocate. Exposing it would delete `write_usize` and stop the next
compiler component from writing a third copy.

---

## 6. `LoopHandle` carries no iteration counter

`h.index()` does not exist; the counter comes from the three-parameter
overload `loop((h, i, v) { .. })`. That is the documented design and the
diagnostic is clear (`LoopHandle has no index`). Recorded only because
it is the first thing anyone coming from the two-parameter form tries,
and the fix is to change the closure's arity rather than to look for a
method.

---

## Not bugs, recorded because I expected them to be

**A `Map` keyed on a user struct works.** `Map<ExprId, TyId>` and
`Map<TypeId, TyId>` are the memo tables the whole design rests on, and
they work exactly as `ast_id.zen` promised — `Eq` + `Hash` impls on a
`{ index: u32 }` struct are enough. The `*%` in `sema_id.zen`'s mixer is
required, though: `*` traps on overflow and a hash constant overflows
`u64` by design, so wrapping has to be written.

**Recursion through a struct method works to real depth.** `write_name`,
`flatten_into` and `resolve_type` all recurse, including mutual
recursion between a method and a free function, with no depth trouble.

**`Map.get` is a linear scan.** `index_of` is a `find` over every entry,
so every memo lookup is O(n) in the number of memoised nodes and the
engine is O(n²) overall. Correct, and it will not survive a real
compilation. `sema_def.zen` uses a plain `Vec` scan for module tables on
exactly this reasoning — a `Map` would have bought a nested generic and
a second allocation for the same complexity. The fix belongs in
`std.collections`, which is why it is here and not worked around.

---

## 7. `LEXER_BOOTSTRAP_FIXES.md` §2 reaches `cc`, not just sema

The preamble above says §2 is worked around throughout. What it does not
say is that in sema's shape the bug produces **no Zen diagnostic at
all** — it emits C that `cc` rejects, so the failure surfaces two tools
downstream of the mistake.

The shape is not a literal `Ok(x)` first arm. It is an arm calling
something that returns `Res<T>` — an *absence* — beside an arm calling
something that returns `Res<T, E>`:

```groovy
Alloc, AllocError = std.mem
Vec = std.collections

grow = (v :: Vec<usize>, x: usize) Res<(), AllocError> { v.add(x) }

fill = (v :: Vec<usize>, x: usize, skip: bool) Res<(), AllocError> {
    skip.match({
        true  => Ok(()),          // types the match as Res<()>
        false => grow(v, x),      // ...and this arm no longer fits
    }).try();
    Ok(());
}

main = (env: Env) Res<i32, AllocError> {
    alloc ::= env.mem.alloc();
    v ::= alloc.Vec<usize>();
    fill(v, 1, false).try();
    println("{}", v.len);
    Ok(0);
}
```

```
error: incompatible types when assigning to type 'ResI1_z' from type
       'ResI2_zt4_3std3mem9mem_alloc10AllocError'
error: 'ResI1_z' has no member named 'zg_data'
```

This matters more than the literal-`Ok` form because **every `Res<T>` in
this stdlib is an absence** — `Vec.get`, `Vec.set`, `Map.get`,
`Ast.module_at`, `find` — so the natural spelling of a fallible walk is
the broken one:

```groovy
self.tables.get(mi).match({
    None  => Ok(()),                    // reads correctly
    Ok(t) => self.walk(t, name, out),   // and is wrong
})
```

**Nine matches in `src/sema/` are written with the arm a reader expects
second placed first**, for this reason and no other. Where both arms are
bare `Ok(..)`, the `Ok` is lifted outside the match instead so the arms
yield plain values.

The diagnostic that would cost nothing: sema knows both arm types and
could take their **join** rather than the first — or, failing that, say
`arm 2 has type Res<(), AllocError>, arm 1 has type Res<()>` instead of
letting `cc` describe it in mangled names.

---

## 8. A node type that is not imported turns every pattern into a binder

**Blocking: no. Silent: worse than silent — it produces a cascade of
confidently wrong diagnostics that name the wrong thing.**

```groovy
// Unary is NOT imported; UnOp is
UnOp = ast

flip = (u: Unary) bool {
    u.op.match({
        Not  => true,
        Neg  => false,
        Addr => false,
    })
}
```

```
unreachable match arm: every value it could match is already covered above
unreachable match arm: every value it could match is already covered above
```

The chain: `Unary` is unknown, so `u` is unknown, so `u.op` is unknown,
so the enum has no case list — and with no case list, `Not` is not a
variant but a **binder**, which covers everything and makes every arm
after it unreachable.

One compile of `sema_check.zen` produced **twenty-three** of these from
**four** missing names on one import line. Every one of them pointed at a
correct, exhaustive match and none of them pointed at the import.

This is `LEXER_BOOTSTRAP_FIXES.md` §7 — global by-name resolution
papering over a missing import — surfacing in pattern position, and it is
worse there because the wrong answer is not "no method `bump`" but a
plausible claim about control flow.

**The fix belongs where the scrutinee is unknown.** `bootstrap/sema.py`
already skips the *exhaustiveness* check for an `any`/`error`/`var`
scrutinee (`_t_Match`, the `sty.kind not in (...)` guard) and it disables
the *unreachable* check when a pattern is `opaque`. It needs the same
guard for an unknown scrutinee type: with no case list there is no
usefulness question to ask, and "never invent a diagnostic out of missing
information" is already this file's stated rule one function up.

---

## 9. §9 of the lexer's list, re-confirmed unchanged

A same-named constructor still loses to positional struct construction:

```
sema/sema_check.zen:728:22: expected Vec<ModuleTable>, found Alloc
sema/sema_check.zen:728:25: expected Alloc, found Ast
sema/sema_check.zen:728:31: `.try()` needs a Res, found World
```

from `World(a, tree).try()`, where `World* = (a: Alloc, tree: Ast)
Res<World, AllocError>` is declared beside `World* = { tables, alloc }` —
the same pairing `std.collections` uses for `Vec` and this folder uses
for `Types`, `Checker` and `World`.

**Workaround:** the ufcs spelling `a.World(tree)`, exactly as the lexer
uses `alloc.Lexer(source)`. Recorded again because three of the four
constructors in `src/sema/` are declared this way, so the next component
will meet it three more times.

---

## 10. A loop binding read inside a nested closure does not resolve

**CLOSED as written, 2026-08-08 — and a narrower shape survives. Read this
before citing §10.** Both forms below were re-run against both toolchains and
**both are accepted by both**: form (a) compiles clean, form (b) emits C that
`cc` takes and that prints the right answer. Whatever fixed it is not recorded
here; what matters is that the reproducer no longer reproduces, so a source
comment citing §10 to justify a workaround is citing a gap that is not there.

**What DOES still fail is a different capture, and only in the bootstrapper:**

```groovy
Fault = { name*: str }
show = (f: Fault, out :: String) Res<(), AllocError> {
    (f.name.len > 0).then(() { out.add_bytes(f.name).try() });   // bootstrap:
    Ok(());                                    // `no member `name` on this value`
}
```

A PARAMETER, not a loop binding, and no loop in sight. The self-hosted compiler
accepts it. So the family is not "a loop binding in a nested closure" but "a
struct reaching a `.then` body across a lambda boundary", and the loop case is
the half that got fixed. An agent hit this independently the same day and worked
around it by binding `text = f.name` before the closure.

**The seven workaround sites named below are therefore no longer required**, and
removing them is a real cleanup — but it is a cleanup, not a fix, and each site
should be re-tested rather than assumed, since the surviving shape is close.

---

**Original entry, kept because the workarounds still exist and cite it:**

**Blocking: yes for one shape, and one of the two forms is silent.**

`x.loop((h, v) { <cond>.then(() { .. v .. }) })` — a `.then` closure
nested inside a `.loop` closure — loses `v`. There are two symptoms and
they depend on whether the inner use is `v` itself or a field of it:

```groovy
Row = { name*: str, ty*: usize }

// (a) a FIELD of the loop binding: a Zen diagnostic, pointing at the field
each = (rows: Vec<Row>, want: str, out :: Vec<usize>) Res<(), AllocError> {
    rows.loop((h, r) {
        r.name.eq(want).then(() { out.add(r.ty).try() });   // `no member `ty``
    });
    Ok(());
}

// (b) the loop binding ITSELF, when the `.then` receiver is a CALL:
//     no Zen diagnostic at all, and the emitted C says `r` undeclared
keep = (c: Checker, rows: Vec<Row>, kept :: Vec<Row>) Res<(), AllocError> {
    rows.loop((h, r) {
        c.wanted(r.ty).then(() { kept.add(r).try() });      // C: `r` undeclared
    });
    Ok(());
}
```

Form (b) reaches `cc`, which is two tools downstream of the mistake.
`sema_def.zen`'s `keep_exported` — `d.exported.then(() { out.add(d).try() })`
— does NOT trip it, which is what made this hard to see: the receiver
there is a plain field read, and the capture survives.

**Workaround in `src/sema/`:** every such site is a named helper taking
the loop binding as a written parameter, with the `.then` replaced by a
`.match`. Seven sites in `sema_member.zen`, `sema_call.zen`,
`sema_match.zen`, `sema_decl.zen` and `sema_check.zen` are written that
way for this reason and no other. It reads better, which is the only
consolation.

---

## 11. `Vec.get` on a locally-bound Vec resolves to `Map.get` at unknown
   type arguments

**Blocking: yes, and it fails in `cc` with no Zen diagnostic naming the
line that caused it.**

```groovy
Found = { computed*: bool }

// `found` is bound with `::=` from a generic call, and `.get` is read
// inside an expression that has an expectation (`Ok(..)` around it)
computed_member = (c :: Checker, ac: Access, ctx: Ctx) Res<bool, AllocError> {
    found ::= c.alloc.Vec<Found>();
    Ok(found.get(0).match({ Ok(f) => f.computed, None => false }));
}
```

```
std/collections/collections_map.zen:93:9: cannot infer the type of `Ok` here
std/collections/collections_vec.zen:39:22: cannot infer the type of `Ok` here
std/collections/collections_vec.zen:40:22: cannot infer the type of `None` here
bootstrap: 3 diagnostic(s)
```

and then, from `cc`, on code nothing calls:

```
error: incompatible type for argument 1 of 'zu_f5_3ast6ast_id7BlockId4Hash4hash'
       expected 'zu_t3_3ast6ast_id7BlockId' but argument is of type 'int'
```

The chain: `get` is resolved by name across the whole program rather than
on the receiver, `Map.get` is a candidate, and it is instantiated at
`K = ?`, `V = ?`. `Map.get` then calls `key.hash(..)` on an unknown type,
which picks whatever `Hash` impl the tree happens to end with —
`ast_id.zen`'s `BlockId` — and passes it the `int` literal `0`. The three
diagnostics all point INSIDE `std/collections`, at correct code, and none
of them names the file that caused it.

This is `LEXER_BOOTSTRAP_FIXES.md` §7 again — global by-name method
resolution — now producing a monomorphisation rather than a wrong
diagnostic. The `Ok(..)` around the expression matters: the same `.get`
as a trailing expression (`found.get(0).match({ .. })` returning `Res`)
does not trip it, which is why `sema_type.zen`'s `lookup_named` has
always been fine.

**Workaround:** a one-line helper whose parameter type is WRITTEN.

```groovy
first_found = (found: Vec<Found>) Res<Found> { found.get(0) }
```

Three sites in `src/sema/` are written that way.

---

## 12. `Checker` holds the `Ast` by value, so the tree must be finished
   first

**Not a bug — a constraint worth writing down, because it costs an
afternoon and the symptom is a trap two files away.**

`Checker* = (a: Alloc, tree: Ast) Res<Checker, AllocError>` copies the
`Ast`, and an `Ast` is six `Vec`s: pointer, length, capacity. A node
added to the caller's `tree` after `alloc.Checker(tree)` is invisible to
the checker, and asking about its id traps in `ast_arena.zen`'s `expr_at`
— which is correct behaviour for an id the arena never handed out, and
says nothing about where the mistake was.

```
ast/ast_arena.zen:108:28: trap: integer overflow
```

There is no reference type to hold it by instead, and taking one would
not help: `Vec` grows by reallocating, so any copy taken before a growth
points at freed pages. **The engine is a query over a FINISHED tree**,
and every test in `tests/corpus/sema_zen/` builds the whole AST before
constructing the checker for exactly this reason.

Worth a sentence in `AST_CONTRACT.md`: "an `Ast` is a value, and a copy
of it is a snapshot."

---

## 13. The driver names a module by the IMPORT that reached it, so one
   file is two modules — and a program can lose its prelude

**Blocking: it was, for whole-program checking. Worked around inside
`sema_def.zen`; the defect is in `src/zen/zen_build.zen`.**

`Build.enqueue` keys a `Unit` on `dotted(im.module)` — the spelling of
the import that discovered the file — and `Build.file_of` maps that
spelling back to a path. A folder root has two spellings for one file:
`std/core/core.zen` is `std.core` when a module writes `Range =
std.core` and `std.core.core` when it writes `Eq = std.core.core`. Both
occur in `src/`, so that file is parsed TWICE and lands in the `Ast` as
two modules with two names and one set of declarations.

Two consequences, in order of how much they cost:

1. **A program that never spells the short form has no prelude.**
   `defs_of` reaches the prelude by asking `index_of("std.core")`, which
   is DESIGN.md's name for it and `bootstrap/modules.py`'s `PRELUDE`.
   A root whose modules all write `std.core.range`, `std.core.result`,
   `std.core.core` gets `None` and every ambient name — `Vec`, `str`,
   `Res` — becomes an undefined name, in `std` itself:

   ```groovy
   // main.zen, with src/std/ beside it
   str = std.text
   hello = (s: str) usize { s.len }
   ```

   ```
   std/text/text_str.zen:72:21: no such field or method on this type `len`
   ...18 diagnostics, none of them about main.zen
   ```

   `World.prelude_index` now tries `PRELUDE_FILE` (`std.core.core`)
   when `PRELUDE` misses, which is correct on its own terms — both
   spellings name one module — but it is covering for the driver.

2. **Every declaration in a doubly-named module exists twice.** Nothing
   depends on it today because the two tables are asked separately, but
   any rule that counts declarations program-wide (a redeclaration
   check, `impls_named`) will see doubles.

The fix belongs in the driver: name a `Unit` by its resolved PATH, not
by the import's spelling, and let two spellings find the one unit.

---

## Differential findings — the self-hosted frontend vs the bootstrapper

TESTING.md's second-strongest oracle, run for the first time:
`tests/run.py --toolchain zen --zen <zen-1>`. Two independent
implementations of Zen exist only during stage 1, and any disagreement is
a bug in one of them with a *program* attached.

**Result: 14 of 17 `corpus/modules/` directory tests pass through zen-1.**
The self-hosted compiler builds and runs real multi-module programs. Three
disagree, and each is a real gap in `src/sema/`:

**D1. A variant re-exported as a bare name is not bound.**
`corpus/modules/enum_variants_survive_a_root` — `Two`, `Three` and
`Single` are variants re-exported from a folder root by name, and zen-1
reports `undefined name` for each. The bootstrapper binds them.

**D2. A module alias does not carry the module's types.**
`corpus/modules/module_alias_qualified` — `sh = shape.shape` then
`sh.Bag` gives `no such field or method on this type 'Bag': expected
<unknown>, found sh`, i.e. the alias is being read as a VALUE and its
members looked up on its type. A module alias is not a value; qualifying
through it is a module path, not a field access. `type_survives_two_roots`
fails the same way.

**Single-file corpus tests cannot run through zen-1 at all**, and this is
an entry-point rule, not a compiler bug. `run.py` stages a single-file
test as `<name>.zen` — it cannot rename it to `main.zen` without breaking
every `must-fail` position assertion, which names the file. `entry_of`
probes `main`, `<root basename>`, then `zen`, so it finds none of them and
says `<root>/zen.zen: nothing is at that path`. The rule that closes it:
**a root holding exactly one top-level `.zen` file uses that file as the
entry.** One file is a program and there is nothing to disambiguate.
