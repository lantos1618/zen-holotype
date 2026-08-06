# Backend findings, and one ruling

Written by the orchestrator from a read-only audit of `src/gen/`, because two
agents converged on that folder and the one that stood down produced the more
useful artifact: a verification of the other's work against the reference.

---

## RULING: the `__builtin_*_overflow` fallback is required, not optional

`gen_c_runtime.zen` emits `#error "this backend needs __builtin_add_overflow
and friends"` under `#else`, in place of the reference's hand-written
pre-check. It is documented there as "COST ACCEPTED KNOWINGLY". **It is not
accepted. Write the fallback.**

The reason is not style, it is `PLAN.md`'s central promise. The seed exists so
that

> **`build`: what a newcomer runs. needs only a C compiler.**

`__builtin_add_overflow` is a GCC/Clang extension, not C99. A seed that
`#error`s without it is a seed that only two compilers can build, which
removes the reason the seed is committed at all. `DESIGN.md` says the backend
emits C99; an `#error` on a missing extension is that promise failing loudly
rather than being kept.

The cost of the fallback is real and small: a few more lines per `(op, int
type)` pair, emitted only for pairs a program actually uses. The cost of the
`#error` is that `cc -std=c99` on a conforming compiler cannot build Zen.

`bootstrap/gen_c.py:5596-5698` has the fallback already written and tested by
~34 corpus tests under `tests/corpus/traps/`. Port it.

---

## Confirmed bug in the bootstrapper

**A `.match` on a `str` scrutinee against string-literal patterns emits a
struct/pointer comparison.** The generated C reads

```c
if (zg_t2 == "i8")            /* zg_str struct vs char * */
```

which is invalid, and it is emitted silently — there is no diagnostic. This is
why `c_prim` is written as nested `pick` calls rather than the match it wants
to be. Reported here rather than worked around further; the workaround is
correct in the meantime.

---

## A claimed bug that is NOT real, and cost real code

`gen_c_runtime.zen:45-62` states that

> a Zen string literal containing a comment opener does not parse — the
> grammar reads it as a real comment and swallows the closing quote

and writes `comment()` a byte at a time to avoid it. **That bug was fixed** in
commit `e096260a`, "grammar: a string is one token, so nothing inside it is
syntax". `string_literal` was a `seq`, and a `seq` lets `extras` — whitespace
and both comment forms — match between its elements; it is now a single token
with no seam for an extra to enter, and `tests/corpus/lex/string_containing_comment_markers.zen`
gates it.

Verified against real `std`: all three of

```groovy
println("/* ---- types ---- */");
println("// a line comment inside a string");
println("a \"quote\" and a /* opener");
```

parse and emit correctly. **The byte-at-a-time `comment()` can collapse to one
`out.say`.**

The general lesson is worth more than the line count: a workaround outlives
the bug unless it names the bug, and re-testing is cheaper than assuming.

---

## Latent bug in `gen_name`, which will bite the moment anything spells a fixed array

`gen_name.comp` does not encode non-identifier bytes. The reference's `comp()`
hex-escapes anything failing `^[A-Za-z_][A-Za-z0-9_]*$`; this one writes the
bytes through raw. `sema_type.array_type` interns a fixed array as
`named(ARRAY_DECL, "[]", "[]", args)`, so `[u8, 4]` mangles to

```
zu_t1_2[]I1_b2u8
```

which is not a legal C identifier. Nothing in the corpus spells a fixed array
through the Zen backend yet, which is the only reason this is latent.

---

## Two files are over the hard cap

`gen_c_type.zen` (831 lines) and `gen_c_expr.zen` (973) both exceed
`STYLE.md`'s 800-line **build failure** threshold. Split by subject, never by
size — and note `STYLE.md` allows an exception only if the path is listed in
`build.zen` with a written reason.

---

## Sema's shape, for whoever finishes the backend

- `expr_kind` returns `Unknown` for `Call`, `Access`, `Lambda`, `Record`,
  `Index`, `FixedArray`, `Array`, `Scope`, `Meta`. **`Match` is handled** now,
  via `sema_match` / `sema_case`.
- The `block_type`-then-read-back protocol is mandatory, and stricter than it
  first appeared: after the walk, `type_of` on a memo **miss** re-reports
  `undefined name` into sema's diagnostics. A backend must read
  `Checker.expr_memo` directly and never call `type_of`.
- Sema has no pointer type kind — `Ptr<T>` arrives as an ordinary `Named` — so
  a declarator never binds an asterisk in this subset.

---

## Housekeeping

`src/gen/gen.zen:51` currently reads

```groovy
// CBackend*, emit_program*, ctype*         = gen.gen_c
```

commented out to unblock module resolution while the backend is written.
**It must be restored when the folder root lands**, or the `gen` module
exports no backend and `src/zen.zen` has nothing to call.

The reference `BANNER` / `INCLUDES` text is not reproduced byte-for-byte, so
line 1 of the Zen backend's output will differ from `bootstrap/gen_c.py`'s.
That is fine for the fixpoint, which compares stage2 against stage3 — both
from the Zen backend — but it means the two backends' output cannot be
diffed directly during the differential-oracle stage.

---
---

# Part two: findings from writing `src/gen/`

Everything above was an audit. What follows was found by building the backend
and running it end to end, and each entry is either **acted on** or **recorded
with a reproducer**. Reproducers run the way `tests/run.py` runs one: a
compilation root holding the program as `main.zen` with the top-level modules
of `src/` beside it, compiled as a **directory**.

## What was acted on

- **The `#error` ruling is carried out.** Every checked helper is now emitted
  twice: `__builtin_*_overflow` under `#ifdef ZG_HAS_OVERFLOW_BUILTINS`, and
  the reference's hand-written pre-operation range test under `#else` —
  two-sided for signed add and subtract, four-quadrant for signed multiply,
  one-sided for unsigned. `cc -std=c99` on a conforming compiler builds the
  output. `gen_c_runtime.zen`'s header states it as a promise rather than a
  cost.
- **`comment()` collapsed to one `out.say`**, and the workaround's comment now
  records that the grammar bug it dodged was fixed rather than repeating the
  claim. Re-tested, not assumed.
- **`comp` hex-escapes a non-identifier component.** `[]` — the name
  `sema_type.array_type` interns a fixed array under — now mangles to
  `x5b5d` rather than producing `zu_t1_2[]I1_b2u8`.
- **Both files over the hard cap were split by subject**, and the folder root
  is restored and lists the backend.

## Confirmed bootstrapper bugs, most-blocking first

### 1. `Vec.get` at `T = str` cannot infer its own `Ok`

**Blocking: yes.** It is two diagnostics pointing at `std`, from a program that
never mentions `std.collections`, and it takes the whole compilation down.

```groovy
Alloc, AllocError = std.mem
str, String = std.text
Vec = std.collections

pick = (a: Alloc, i: usize) Res<str, AllocError> {
    v ::= a.Vec<str>();
    v.add("hello").try();
    Ok(v.get(i).match({ Ok(s) => s, None => "" }));
}

main = (env: Env) Res<i32, AllocError> {
    alloc ::= env.mem.alloc();
    println("{}", pick(alloc, 0).try());
    Ok(0);
}
```

```
std/collections/collections_vec.zen:39:22: cannot infer the type of `Ok` here
std/collections/collections_vec.zen:40:22: cannot infer the type of `None` here
```

`Vec<bool>` fails the same way. `Vec<Def>`, `Vec<TyId>`, `Vec<String>`,
`Vec<Member>`, `Vec<Variant>` and `Map<ExprId, TyId>` are all fine, so it is
not "a generic in a Vec" — it is `Res<T>` at particular `T`s, and `str` is the
one a backend reaches for constantly.

**Workaround:** `gen_c_call.storage_name` counts to the i-th storage member
with two mutable locals rather than collecting names into a `Vec<str>`.

### 2. A local `Vec<T>` read back in the same function can lose its type arguments

**Blocking: yes, and the diagnostic names `std`.** The same shape as §1 from a
different direction: the emitted C contains `Map.get` instantiated at
`Map<q, q>` — `q` is the mangler's *unresolved* tag — called with a `BlockId`
key that no program has.

The version that failed:

```groovy
storage_type = (be :: CBackend, s: Struct, name: str, dctx: Ctx)
               Res<TyId, AllocError> {
    found ::= be.alloc.Vec<TyId>();
    s.members.loop((h, m) { collect_named_field(be, m, name, dctx, found).try() });
    Ok(found.get(0).match({ Ok(t) => t, None => TyId(index: 0) }));
}
```

```
std/collections/collections_map.zen:93:9: cannot infer the type of `Ok` here
```

The version that works is the same function with no collection at all — a
mutable local assigned inside the loop. What makes this worse than §1 is that
the failure is a **`Map`** the program does not use: resolution fell through to
a global by-name search for `get` and found `Map.get`, which is
`LEXER_BOOTSTRAP_FIXES.md` §7 surfacing in a new place.

### 3. Two modules declaring `Diag` collide on a method name, and `cc` reports it

**Blocking: yes for any program that imports both.** It reddened
`corpus/cli/*`, which stages `sema` and `gen` together.

`sema.sema_diag` declares `Diag` with a free `render(self: Diag, types, out)`.
`gen.gen_diag` declared `Diag` with a method `render(self: @Self, out)`. A call
`d.render(out)` on the *gen* value resolved to *sema's* function:

```
error: too many arguments to function 'zu_f4_3gen8gen_diag4Diag6render'
note:  expected 'zu_t3_3gen8gen_diag4Diag' but argument is of type
       'zu_t3_4sema9sema_diag4Diag'
```

DESIGN.md says "two modules may define the same top-level name without
colliding", and four modules in this tree declare a `Diag`. The bootstrapper's
member resolution does not honour that.

**Workaround:** the type is `GenDiag` and the renderer is a free function
`render_gen`. Uglier, unique tree-wide, and what STYLE.md's grep test asks for
anyway.

### 4. A struct field whose name matches a field of an unrelated type is read-only

```
gen_c_decl.zen:187:8: body is not writable outside module ast_node
```

from `be.body = be.alloc.Emit().try();`, where `body` is a `::` field of the
backend's own struct. `ast.Function` declares `body*` — immutable, in another
module — and the assignment was checked against *that*. Renaming the field to
`buf` fixed it; the field is now unexported with six forwarding methods, which
is what DESIGN.md asks for anyway ("mutation only ever goes through exported
methods").

### 5. A `.then` closure capturing several enclosing parameters is inlined wrong

```groovy
traps(b.op).then(() { write_trap_args(be, node, b, out).try() });
```

emitted

```c
write_trap_args(&be, node, traps(b.op), &out)
```

— the receiver of `.then` substituted into the third argument slot. `cc`
catches it; there is no Zen diagnostic. A `.then` capturing one parameter is
fine and is used throughout `std`.

**Workaround:** `.match` with an explicit `false => Ok(())`, which reads better
anyway.

### 6. Binding an enum arm's payload to a local types the match as `()`

```groovy
what = fault.match({
    Unsupported(w) => w,
    Unresolved(w)  => w,
    ...
});
out.add_bytes(what).try();
```

emits `void zu_l4what = 0;`. Every arm is `str` and the first one is too, so
this is not `LEXER_BOOTSTRAP_FIXES.md` §2's first-arm rule — it is a payload
binder reaching a local. **Workaround:** write the payload into the sink inside
each arm.

### 7. A `str` scrutinee against string-literal patterns — confirmed again

Already recorded above; confirmed independently while writing `c_prim`, and
`gen_c_runtime.signed_guard` / `unsigned_guard` are written as `.eq` chains for
the same reason.

## A parser finding

**`x * 2` in statement position is parsed as a declaration.** A block whose
value is a multiplication loses it:

```groovy
main = (env: i32) i32 { x = 6; x * 2 }
```

emits `return;`, and the backend reports `a declaration inside a body` at the
`x`. `x + 2` in the same position is fine, and `(x * 2)` is fine. The `*` is
being read as the export marker. It belongs in `src/parse/`, not here.

## A design gap, not a bug

**An unannotated integer binding is a literal type, and nothing settles it.**
`x = 6` gives `x` sema's `int`, which this backend spells `int64_t`; a use of
`x` in an `i32` context is then narrowed at the call to the checked helper. The
value is right for anything that fits and silently truncates for anything that
does not. Settling a literal's type from its context is bidirectional inference
and it is sema's, not the backend's — recorded here because TESTING.md's "a
literal at the exact type boundary" test will find it.
