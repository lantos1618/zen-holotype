# Bootstrapper bugs found while writing `src/lex/`

> **The bootstrapper is deleted.** This document is a record, not a map:
> every `bootstrap/*.py` coordinate below resolves only in git history
> (`git show 4d05320a:bootstrap/gen_c.py`), and no gate can re-verify one.
> What is still worth reading is the Zen behaviour each entry describes.

Ten bugs, most-blocking first. Every reproducer is a complete program, run
the way `tests/run.py` runs one: a compilation root holding the program as
`main.zen` plus the whole of `src/` beside it.

---

## Where this ledger stands

**Re-measured 2026-08-08 against `39313c6a`**, every reproducer below re-run
through BOTH toolchains. Seven of the ten are closed and one is closed in the
self-hosted compiler only. §4 was recorded too narrowly and hid a worse defect
than the one it described; both halves are now closed and the language question
the second half raised is answered in DESIGN.md.

| § | what it claimed | bootstrap | `./zen` |
|---|---|---|---|
| 1 | `Ptr.to<U>()` no-op corrupts every `Vec` | **closed** | **closed** |
| 2 | match takes its type from arm one, drops a bare `Ok(x)` | **closed** | **closed** |
| 3 | void call in trailing-expression position discarded | **closed** | **closed** |
| 4 | a `::` field's default is ignored | **closed** | **closed, and the worse half too** |
| 5 | `==` on two enums passes sema, emits invalid C | **closed** | **closed** |
| 6 | grammar reads `//` inside a string literal as a comment | n/a | **closed** |
| 7 | method on an un-imported type resolves globally by name | **open** | open, different shape |
| 8 | `--root .` unusable — discovery walks `tests/` | **open** | not measured |
| 9 | same-named constructor loses to positional construction | **closed** | **closed** |
| 10 | `loop` with `h.break(value)` does not infer its result | **open** | **closed** |

A section marked closed keeps its reproducer, because a ledger that deletes
what it fixed cannot be re-run — and re-running is the only reason to keep it.

**§4 is the one to read.** It was filed as "a default on a `::` field is
ignored". That is true, and it was true of BOTH implementations, not just the
bootstrapper as filed. But the reproducer's other half was worse and was never
written down: **a `:` field that has a default is dropped from the emitted
struct entirely by the self-hosted compiler**, so any program that read one
failed to compile as C. Nothing caught either, because no test in the corpus
declared a field default — and the ones `src/` and `std` declare are all
already zero, which is exactly what the bug produced. DESIGN.md:117 and
DESIGN.md:1359 both specify the feature. `tests/corpus/codegen/field_defaults`
is the test that was missing; it declares only non-zero defaults, because a
zero default cannot tell the feature from its absence.

---

## 1. `Ptr.to<U>()` is a no-op, so `Arena.realloc` reads its header as one byte

**CLOSED.** The reproducer below now prints `100 101 ... 108` under both
toolchains. It was memory corruption in the standard library, silent, and it
hit every collection in the language once it was big enough.

### Symptom

A `Vec` loses every row written before a grow. Nine elements in, the first
eight come back zeroed:

```groovy
Kind = Ident | Int(u64) | Eof
Pos  = { offset*: usize, line*: usize, col*: usize }
Span = { start*: Pos, end*: Pos }
Token = { kind*: Kind, span*: Span }

main = (env: Env) Res<i32, AllocError> {
    alloc ::= env.mem.alloc();
    v ::= alloc.Vec<Token>();
    Range(0, 9).loop((h, i) {
        p = Pos(offset: i + 100, line: 1, col: 1);
        v.add(Token(kind: Kind.Ident, span: Span(start: p, end: p))).try();
    });
    Range(0, v.len).loop((h, i) {
        println("{}", v.get(i).match({ Ok(t) => t.span.start.offset, None => 999 }));
    });
    Ok(0);
}
```

```
0 0 0 0 0 0 0 0 108        <- 100 101 102 103 104 105 106 107 108 is correct
```

A `Vec<usize>` in the same program is fine, which is why nothing has caught
this: the bug is a function of the BUFFER's byte size, and `Vec<i32>`'s first
buffer is 32 bytes.

### Cause

`bootstrap/gen_c.py`, `FnCtx.ptr_method`:

```python
if name == "to" and len(argnodes) == 0:
    return (rcode, rty)          # rty is the RECEIVER's Ptr<T>, not Ptr<U>
```

`to<U>` returns the receiver's own element type, so every later `read`,
`write`, `bytes` and `copy_from` keeps scaling by `T`. `Arena.realloc` reads
its allocation header through exactly that:

```groovy
old = src.back(HEADER_BYTES).to<usize>().read(0)
```

`src` is a `Ptr<u8>`, so the read stays `uint8_t` and the emitted C is

```c
uint8_t zg_t1;
zg_t1 = (zu_l3src - zg_t3)[((size_t)0ULL)];   /* ONE BYTE of an 8-byte header */
uint8_t zu_l3old = zg_t1;
```

So `old` is the **low byte** of the previous allocation's size. A `Vec<Token>`
first allocates `8 * 64 = 512` bytes; `512 & 0xFF == 0`, so `keep` is 0 and
`copy_from` copies nothing. At 56-byte elements it is `448 & 0xFF == 192`, and
exactly 192 bytes survive — which is three and a half tokens, and is what the
symptom above looks like before you know why.

`Arena.bump` writes the header through the same expression, so the header only
ever held its own low byte in the first place; both sides truncate, which is
why nothing errors.

### The fix

`ptr_method` now takes the call's type arguments and returns `("ptr", U)`, so
`to<U>` changes the element type that `read`, `write`, `bytes` and `copy_from`
scale by. `corpus/lex_zen/token_kinds` and `corpus/lex_zen/big_input` — the two
lexer tests that scan more than eight tokens — are the ones that flipped, and
they are the standing guard: both are in the corpus and both are green.

**If you see a regression in `corpus/std/res_try_error_sets_merge` while
touching `bootstrap/`, it is a stale `bootstrap/__pycache__`.** It cost the
original author twenty minutes; `rm -rf bootstrap/__pycache__` and it passes.

### Why there was no workaround

`Vec` grows geometrically, so the buffer passes 256 bytes for any element type
at some doubling — element size under 32 bytes only postpones it. There is no
`reserve`, and the header round-trip is inside `std.mem`. No `Token` layout
avoids it.

---

## 2. A match takes its type from its FIRST arm, and a bare `Ok(x)` there is dropped

**CLOSED.** The reproducer prints `true` under both toolchains. It was the
costliest of the ten, because the program compiled and returned a zeroed `Res`
whose tag happened to read as `Ok(false)`.

### Symptom

```groovy
Fault = | Bad

report = (n: usize) Res<(), Fault> { Err(Fault.Bad) }

// the `Ok(())` arm comes first
first_ok = (n: usize) Res<bool, Fault> {
    (n > 0).match({
        true  => Ok(()),
        false => report(n),
    }).try();
    Ok(true);
}
```

`gen_c` types the match from arm one — `Res<()>`, with no error — then cannot
assign the second arm's `Res<(), Fault>` to it. Depending on the shape it
either emits a C type error:

```
error: incompatible types when assigning to type 'ResI1_z' from type
       'ResI2_zt...AllocError'
```

or, when the match is the function's trailing statement, **silently discards
the value**:

```c
(void)(((ResI1_b4bool){ .zg_tag = Ok, .zg_data = { .zu_m2Ok = true } }));
...
return (ResI2_b4boolt...AllocError){0};      /* a zeroed Res */
```

In `src/lex/lex_literal.zen` that made `1.5` lex as an integer literal: the
`Ok(true)` saying "this is a float" was thrown away and the zeroed return read
as `Ok(false)`.

### What the workaround left behind

While it was open, `src/lex/` put the arm whose type was known — the call
returning `Res<T, E>` — **first**, so the match took its type from that. Four
matches in `src/lex/` were ordered `false` before `true` for that reason and no
other, each at a point where a reader would expect the other order. **Now that
the bug is closed those four are load-bearing for nothing**, and anyone
touching `src/lex/` should put them back in the natural order rather than
preserve a shape whose only justification has gone.

---

## 3. A void call in trailing-expression position is silently discarded

**CLOSED.** The reproducer prints `1` and `1` under both toolchains — the
trailing-expression form now runs its effect. While it was open there was no
diagnostic and no C error; the program simply did not do the thing.

```groovy
Alpha = {
    n* :: usize,
    up* = (self :: @Self) () { self.n = self.n + 1; }
}

once      = (a :: Alpha) () { a.up() }      // trailing EXPRESSION
once_semi = (a :: Alpha) () { a.up(); }     // trailing STATEMENT

main = (env: Env) Res<i32, AllocError> {
    a ::= Alpha(n: 0);  a.once();       println("{}", a.n);   // 0  <- wrong
    b ::= Alpha(n: 0);  b.once_semi();  println("{}", b.n);   // 1  <- right
    Ok(0);
}
```

`gen_c` emitted an empty C function body for `once`. Worth pairing with §2: a
value in trailing position must NOT be semicolon-terminated, and an effect
MUST be. That is exactly "a statement ends with `;`", so while both were open
they punished every departure from the specified style in one direction or the
other, and never said so.

---

## 4. Field defaults do not work, in two different ways

**CLOSED, both halves, and the question 4b asked has an answer in DESIGN.md.**
The entry stands as written because the reasoning is what settled it; what each
half turned out to be is recorded at the end of it.

The original entry said "a default on a `::` field is ignored" and blamed the
bootstrapper. Re-measuring found two defects, one of them worse and unrecorded.

```groovy
Konst = { a: usize = 7, b :: usize = 9 }

main = (env: Env) Res<i32, AllocError> {
    k = Konst();
    println("{} {}", k.a, k.b);      // `7 9` is correct
    Ok(0);
}
```

### 4a. A `::` field's default is ignored — in BOTH implementations

```groovy
C = { a :: usize = 9, b :: bool = true }
// both toolchains print `0 false`; `9 true` is correct
```

The field is zero-initialised and the default is dropped. **This is not a
bootstrapper bug**, as filed — the self-hosted compiler does exactly the same
thing, which is why no differential test can see it: the two implementations
agree, and they are both wrong. Only a corpus test asserting the printed value
can catch it, and none exists.

### 4b. A `:` field that HAS a default is dropped from the struct entirely

This is the one nobody wrote down, and it is worse:

```groovy
A = { a: usize = 7 }
main = (env: Env) Res<i32, AllocError> { println("{}", A().a); Ok(0); }
```

The bootstrapper prints `7`. The self-hosted compiler emits C that will not
compile, because the field does not exist in the emitted struct:

```
error: 'zu_t2_4main1A' has no member named 'zu_m1a'
    zg_print_u64((uint64_t)((zu_t2_4main1A){0}.zu_m1a));
```

`{ a: usize }` with no default is fine, and `{ a: usize = 7, b: usize }` keeps
`b` and drops `a` — so the trigger is precisely **immutable field, with a
default**. The storage was elided without teaching the reader, which reads like
a half-landed "an immutable field with a default is a constant, not storage"
decision. If that IS the intent, DESIGN.md does not say it and the member
access has to fold to the constant; if it is not, the field must be emitted.

### Why neither is caught

`src/` declares **zero** fields with defaults — the grep over the whole tree
returns nothing — and no corpus test declares one either. The compiler does not
use the feature, so the compiler cannot notice it is broken. DESIGN.md:117
("`= default` makes a field optional at construction") and DESIGN.md:1359 ("a
field with a default is optional; no default and no `Res` means required")
both specify it, and DESIGN.md's own `Opts` example uses `verbose :: bool =
false` — a default of `false`, which is indistinguishable from the zeroing.
That coincidence runs through `std` as well: `Vec`'s `len* :: usize = 0` and
`data :: Ptr<T> = null_ptr<T>()` are both already zero.

**Fixing this needs a corpus test with a NON-ZERO default first** — a test
whose expected output is `7 9`, which is red today. That test is the gate; the
fix is downstream of it.

**Workaround, while open:** `Cursor` has no field defaults; `cursor_at`
supplies all four explicitly. `line: 1` is exactly the non-zero default that
would have been lost.

### How both were closed

`tests/corpus/codegen/field_defaults` is the test this entry asked for, written
first and watched go red in both toolchains before a line of compiler moved. It
declares only non-zero defaults, supplies `0` and `false` as *arguments* so a
zeroing back end fails on the defaults and an argument-dropping one fails on
those, and covers a default that is a construction (`Pos(line: 1, col: 1)`) and
not a literal.

**4a was one defect in two places, and the cause was the same sentence of code
in each: the initialiser list was built out of the ARGUMENTS and never out of
the DECLARATION.** A field nobody supplied got no initialiser and fell to C's
`{0}`. `gen_c_build.zen` now appends a designator for every storage member the
call omitted that declares a value, and `bootstrap/gen_c.py` fills the same
holes as it walks the declared fields. A default is written in the DECLARING
module's context, because the expression names what that module can see.

Both back ends hold a default to the same purity gate a constant read is held
to — a literal, an operator over literals, or a construction of them. A default
that is not one is left to the zeroing it already got; `Vec`'s `data :: Ptr<T>
= null_ptr<T>()` is the only shape in the tree that reaches the gate, and a
null pointer is what zeroing gives. **That gate is a remaining hole, not a
decision**: a `::` field defaulted to a call gets zero and no diagnostic.

**4b was a different defect, self-hosted only, and the answer to its question
is the CONSTANT reading — the field really is not storage.** Grammar R4,
`grammar/grammar.js`, `src/AST_CONTRACT.md` and `src/parse/parse_member.zen` all
already say so: inside a struct body `name: T = value` is a constant and
`name :: T = value` is a field with a default. The deciding argument is that a
constant has no other spelling — `i32.MAX` is declared `MAX*: i32 = 2147483647`
and DESIGN.md's "Constants on a type" section gives it no alternative — while a
field with a default has `::`. Reading `:` + a value as storage would leave the
constant unwritable; reading it as a constant leaves the immutable-field-with-a-
default unwritable, and `::` covers that shape. So the loss is one-sided.

DESIGN.md now says it, which is what 4b required and what `AST_CONTRACT.md`'s
open question 2 asked for: the "Declarations" section states R4 and prices it,
and "Constants on a type" adds that the spelling decides everywhere and that a
constant folds wherever it is read.

The self-hosted bug was the second half of that: `Limits.WIDTH` folded and
`j.WIDTH` did not. It fell through to the field path and emitted `.zu_m5WIDTH`
on a struct declaring no such member, so the diagnostic came from `cc` and named
a symbol the author never wrote. The bootstrapper already folded it, so this was
also the two implementations disagreeing. `gen_c_read.zen` now asks the
RECEIVER's declaration for a constant of that name before falling to the field
path.

**Still owed, and sema's, not codegen's:** supplying a constant at construction
— `Limits(WIDTH: 8)` — is silently dropped by both back ends. It should be a
diagnostic naming the member.

---

## 5. `==` on two enum values passes sema and emits invalid C

**CLOSED, the way this entry asked for.** Both toolchains now refuse it in
sema, and the must-fail test the entry said "does not exist" now does —
`tests/must-fail/sema/eq_needs_an_impl`:

```
main.zen:6:19: `==` needs an `Eq`: equality dispatches to the impl, so write
               one or compare the parts — `Res<u8>` has none
```

The record of what it used to do follows.

```groovy
main = (env: Env) Res<i32, AllocError> {
    r: Res<u8> = Ok('a');
    println("{}", r == Ok('a'));
    Ok(0);
}
```

No Zen diagnostic. `cc` then says

```
error: invalid operands to binary == (have 'zu_t4_3std4core6result3ResI1_b2u8'
       and 'zu_t4_3std4core6result3ResI1_b2u8')
```

`DESIGN.md` gives `Eq` as an ordinary struct with an `eq` method and never says
`==` desugars to it, so the right fix was a sema rejection rather than a
codegen change. That is what landed.

**Workaround, no longer needed but still the clearer code:** `Cursor.at_byte`
compares after unwrapping.

---

## 6. The grammar reads a comment opener inside a string literal as a comment

**CLOSED.** `npx tree-sitter parse` accepts all four lines below, and both
toolchains compile and run the program. It was not a bootstrapper bug —
`grammar/grammar.js` — and it stopped a valid program from parsing at all.

```groovy
main = (env: Env) Res<i32, AllocError> {
    a = " // x";        // does not parse
    b = "a\n/* x */";   // does not parse
    c = "x// y";        // fine
    d = "https://example.com";   // fine
    Ok(0);
}
```

```
main.zen:2:14: expected expression
main.zen:6:1: expected `"`
```

The `//` was lexed as a real line comment and swallowed the closing quote. It
fired when the opener followed whitespace or an escape sequence, and not when
it followed ordinary content — `token.immediate` on the string's content regex
was not keeping `extras` out at those positions.

`tests/corpus/lex_zen/comments` still builds every comment input a byte at a
time through a `String` rather than writing it down. That was the workaround;
with the grammar fixed it is now just a slower way to say the same thing, and a
test that writes the literals down directly would guard the grammar instead of
routing around it.

---

## 7. A method call on a type whose module was not imported resolves by name, globally

**OPEN, in both, in different shapes.** The bootstrapper still names an
unrelated module; the self-hosted compiler no longer does, but answers a
resolution question with a codegen diagnostic and names neither the type nor
the missing import:

```
bootstrap   main.zen:12:7: bump is not exported by module mem_arena
./zen       main.zen:12:5: codegen cannot resolve `bump`
```

Neither is the `no method bump on Cursor` this entry asks for. The original
report follows.

```
lex/lex_literal.zen:34:12: bump is not exported by module mem_arena
```

`lex_literal.zen` called `lx.cur.bump()`, where `cur` is a `Cursor`. It had not
imported `Cursor`, so resolution fell through to a global by-name search and
found the **private** `Arena.bump` in `std.mem.mem_arena` — a module nothing in
the file mentions.

Importing `Cursor` fixes it, and per `DESIGN.md` ("importing a type pulls its
world along") that is the correct requirement. The bug is the diagnostic:
twenty-two of them, each naming an unrelated module, for one missing import
line. It should say `no method bump on Cursor` and name the import.

---

## 8. `--root .` is unusable, because discovery walks `tests/` and `example/`

**OPEN, and grown.** Re-run today it is **158** diagnostics, not the 125
recorded — the noise scales with `tests/parse/errors/`, so it gets worse every
time someone adds a test that exists in order not to parse.

```
$ python3 -m bootstrap.bootstrap --root . src/lex/lex.zen
tests/parse/errors/while_loop.zen:6:11: syntax error near `n`
tests/parse/errors/tuple_struct_fields.zen:10:2: unexpected end of file
... bootstrap: 158 diagnostic(s)
```

`zmodules.build(root)` walks the whole root before `prune` runs, and
`tests/parse/errors/` holds twenty-five files that exist **in order not to
parse**. A real diagnostic from `src/lex/` is invisible in the noise. Either
prune before reporting parse diagnostics, or exclude `tests/` from discovery
the way dot-directories already are.

---

## 9. A same-named constructor loses to positional struct construction

**CLOSED.** `Lexer(source)` against a `Lexer* = (source: Source) Lexer`
declared beside the struct now picks the function under both toolchains. The
original report follows.

```
lex/lex_scan.zen:44:18: expected Source, found Alloc
lex/lex_scan.zen:44:25: expected Cursor, found Source
```

`Lexer(alloc, source)` — with `Lexer* = (alloc: Alloc, source: Source) Lexer`
declared beside the struct, exactly as `std.collections` declares
`Vec* = <T>(a: Alloc) Vec<T>` — was matched against the STRUCT's fields
positionally instead of against the function. `std` never trips over this
because `alloc.Vec<i32>()` is written as a UFCS method call, where a struct
literal is not a candidate.

**Workaround, no longer needed:** `alloc.Lexer(source)` for the one whose first
parameter is an `Alloc`, and the name `cursor_at` for the one whose first
parameter is a `str` — following `std.text`'s own `str_at`. `cursor_at` is a
good name on its own merits and should stay; the UFCS spelling is now a free
choice rather than a workaround.

---

## 10. `loop` with `h.break(value)` does not infer its result type

**Closed in the self-hosted compiler, OPEN in the bootstrapper.** This is now a
differential: `./zen` compiles the reproducer and prints `true`, and
`bootstrap/` still says `unresolved name done` and then emits C that will not
compile (`'Ok' undeclared`). The self-hosted compiler is the one that is right.

> MEASURED STALE, 2026-08-25 (worktree fix779-break-type, #779 lane): the
> self-hosted compiler no longer takes this side. On today's tree the exact
> reproducer below is REFUSED twice over --
>
>     main.zen:6:9:  h.break(v) is not free to choose its type: the loop's
>                    own T is usize, broken with bool
>     main.zen:11:26 printing a value of this type
>
> -- because gen_c_shape.zen `loop_element()` settles a NO-RANGE loop's T to
> usize before anything looks at the break. The annotated form
> (`w: Res<i64> = loop((h){ h.break(5000001234) })`) still reaches cc and dies
> there (`ResI1_b3i64` from `ResI1_b5usize`) -- see
> tests/corpus/loop-break/LANE.md, "Compiler bug". What DOES work today:
> writing the type at the loop call (`loop<i64>((h){ ... })`), and ranged /
> fold / array-walk shapes. Until break-driven settlement lands,
> `loop<T>(..)` is the supported spelling for a bare loop broken with a value;
> corpus/ownership-consume/consume_breaks_with_its_value carries the worked
> example.

Because the shipped compiler is correct, the pressure to fix `bootstrap/` is
only that `make test` runs the corpus through it — so a corpus test using the
inferred-break shape cannot be written until it is fixed. The original report
follows.

```
lex/lex_scan.zen:127:21: unresolved name `done`
```

from

```groovy
closed = loop((h) { ... h.break(true); ... }).match({
    Ok(done) => done,
    None     => false,
});
```

The `Res<T>` the loop family returns has no `T` inferred from the `break`, so
the payload binding does not resolve.

**Workaround:** `block_comment` threads a `closed ::= false` local and breaks
without a value.

---

## What this ledger asks for next

In the order the work would pay off:

1. ~~**A corpus test with a non-zero field default** (§4)~~ — done:
   `tests/corpus/codegen/field_defaults`, written red first under both
   toolchains, and both halves of §4 fixed under it.
2. ~~**Decide what a `:` field with a default MEANS** (§4b)~~ — decided: it is a
   constant, DESIGN.md says so, and the read folds in both toolchains.
3. **Refuse a construction that supplies a constant** (§4). `Limits(WIDTH: 8)`
   is silently dropped by both back ends; it should name the member. Sema's,
   not codegen's.
4. **A `::` field defaulted to a call still gets zero** (§4). Both back ends
   gate a default on the same purity test a constant read gets, so
   `Ptr<T> = null_ptr<T>()` falls through to zeroing — which is the right value
   by luck. Something that is not is silently wrong and undiagnosed.
5. **`--root .`** (§8), now 158 diagnostics and growing with every must-fail
   parse test added. Prune before reporting, or exclude `tests/`.
6. **Name the type in the unresolved-method diagnostic** (§7). Neither
   toolchain says which type has no such method, and neither names the import
   that would fix it.
7. **`h.break(value)` in `bootstrap/`** (§10) — the only thing it blocks is
   writing a corpus test in the shape the shipped compiler already handles.

## Not bugs, recorded because I expected them to be

**Mutual module imports are accepted.** `alpha/alpha.zen` importing a function
from `alpha/beta.zen` while `beta` imports a type back from `alpha` resolves
and runs. `must-fail/modules/import_cycle` rejects a cycle between *value
initialisers*, which is a different thing — `modules.py` solves export tables
to a fixpoint precisely so `std.core.display` ↔ `std.text` works. `src/lex/` is
acyclic anyway, but the constraint I designed around does not exist.

**A trailing statement IS a block's value** — `Vec.get`'s
`(i < self.len).match({..});` returns what the match evaluates to. It is only
the two shapes in §2 and §3 that lose it.

---

## One thing I want from `std` rather than writing it here

`src/lex/lex_byte.zen` declares `BOM_FIRST`, `BOM_SECOND`, `BOM_THIRD` — the
three bytes of a UTF-8 byte-order mark, `239 187 191`. They cannot be written
as char literals (not ASCII, and Zen's escape set is closed), so they have to
be named somewhere.

By the stranger test they name **UTF-8**, not the lexer, so they belong beside
`UTF8_LEAD_2_MIN` and friends in `std.text.text_utf8`. They are in `src/lex/`
only because that module does not declare them yet. Say the word and they move.

**Still true as of 2026-08-08** — all three are still declared in
`src/lex/lex_byte.zen:40-42` and re-exported from `lex.zen:47`, and
`std.text.text_utf8` still does not have them. Nobody has said the word.
