# Bootstrapper bugs found while writing `src/lex/`

Ten bugs, most-blocking first. Every reproducer is a complete program, run
the way `tests/run.py` runs one: a compilation root holding the program as
`main.zen` plus the whole of `src/` beside it.

**One of them I fixed**, because it could not be worked around — §1. It is a
fifteen-line change to `bootstrap/gen_c.py` and the diff is below. Everything
else is recorded and worked around in `src/lex/`.

---

## First: what is in this worktree that is not mine

The orchestrator's note reported 308 insertions in `bootstrap/gen_c.py` and 77
in `bootstrap/sema.py` here. Those were real and none of them were mine.

**This worktree was created from the wrong base commit** — `3800ad29`, a
`main`-era tree with `src/compiler/` and no `docs/` at all. I detached onto
`zen/reset` to get the tree the brief describes. At `bf58f405` that tree did
not build: `src/std/std.zen` re-exported from `std.build` and `src/std/build/`
was not in the commit (the `.gitignore` bug, since fixed), so every compile
died and the baseline was 98 passed / 201 failed. I copied `bootstrap/*.py`
and `src/std/` wholesale from `/home/ubuntu/zenc` to get a usable baseline.
Seven of the eight bootstrap files were byte-identical to the shared checkout;
the eighth differed only because it had been written to 29 seconds after I
copied it.

That copy is now gone. The worktree has since been brought onto current
`zen/reset` with `git restore --source=zen/reset`, and **the whole difference
between this worktree and `zen/reset` is now**:

```
$ git diff --stat zen/reset -- bootstrap
 bootstrap/gen_c.py | 15 ++++-
```

That fifteen lines is §1 below and nothing else.

---

## 1. `Ptr.to<U>()` is a no-op, so `Arena.realloc` reads its header as one byte

**Blocking: absolutely, and not workaroundable.** This is memory corruption in
the standard library, it is silent, and it hits every collection in the
language once it is big enough.

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

### The fix, as applied

```diff
@@ class FnCtx:
         if rty is not None and rty[0] == "ptr":
-            got = self.ptr_method(rcode, rty, name, argnodes, node)
+            got = self.ptr_method(rcode, rty, name, argnodes, node, targs)
             if got is not None:
                 return got

-    def ptr_method(self, rcode, rty, name, argnodes, node):
+    def ptr_method(self, rcode, rty, name, argnodes, node, targs=()):

         if name == "to" and len(argnodes) == 0:
+            # `to<U>` must change the ELEMENT type: read, write, bytes and
+            # copy_from all scale by it, so returning the receiver's own type
+            # leaves them scaling by T.  Arena.realloc reads its usize header
+            # through `.to<usize>()`, so as a no-op that read is ONE BYTE, and
+            # every Vec whose buffer reaches 256 bytes silently loses the rows
+            # written before each grow.
+            if targs:
+                u = self.e.resolve_type(targs[0], self.subst, self.parts, self.self_ty)
+                if u not in (None, UNKNOWN):
+                    return ("((%s *)%s)" % (self.e.ctype(u).strip(), paren(rcode)),
+                            ("ptr", u))
             return (rcode, rty)
```

### Evidence it is right and costs nothing

Same tree, same tests, only this diff differing:

| | passed | failed |
|---|---|---|
| `zen/reset` `gen_c.py` | 299 | 8 |
| with this fix | **301** | **6** |

The two that flip are `corpus/lex_zen/token_kinds` and
`corpus/lex_zen/big_input` — the two lexer tests that scan more than eight
tokens. The six that remain failing are pre-existing and untouched
(`own/defer_runs_before_drop`, `own/scope_passed_inward`, and the four
`std/display_*`).

**If you see a regression in `corpus/std/res_try_error_sets_merge` while
integrating this, it is a stale `bootstrap/__pycache__`.** It cost me twenty
minutes; `rm -rf bootstrap/__pycache__` and it passes.

### Why there is no workaround

`Vec` grows geometrically, so the buffer passes 256 bytes for any element type
at some doubling — element size under 32 bytes only postpones it. There is no
`reserve`, and the header round-trip is inside `std.mem`. No `Token` layout
avoids it.

---

## 2. A match takes its type from its FIRST arm, and a bare `Ok(x)` there is dropped

**Blocking: yes, and silent.** This one cost the most time, because the
program compiles and returns a zeroed `Res` whose tag happens to read as
`Ok(false)`.

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

### Workaround in `src/lex/`

Put the arm whose type is known — the call returning `Res<T, E>` — **first**,
so the match takes its type from that. Four matches in `src/lex/` are ordered
`false` before `true` for this reason and no other; each is at the point where
a reader would expect the other order.

The related shape, `{ effect(); Ok(x) }` as a block arm, also loses its value.
`DESIGN.md`'s own `Vec.set` writes `true => { self.data.write(i, value); Ok(()) }`,
so the specified form is the one that breaks.

---

## 3. A void call in trailing-expression position is silently discarded

**Blocking: no — the discipline that avoids it is `DESIGN.md`'s own rule.** But
there is no diagnostic and no C error; the program just does not do the thing.

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

`gen_c` emits an empty C function body for `once`. Worth pairing with §2: a
value in trailing position must NOT be semicolon-terminated, and an effect
MUST be. That is exactly "a statement ends with `;`", so the two bugs together
punish every departure from the specified style in one direction or the other,
and never say so.

---

## 4. A default on a `::` field is ignored at construction

```groovy
Konst = { a: usize = 7, b :: usize = 9 }

main = (env: Env) Res<i32, AllocError> {
    k = Konst();
    println("{} {}", k.a, k.b);      // prints `7 0`; `7 9` is correct
    Ok(0);
}
```

The `:` field's default is applied; the `::` field's is not — it is
zero-initialised. Nothing in `std` notices because every `::` default there is
`0` or a null pointer (`Vec`'s `len* :: usize = 0`, `data :: Ptr<T> =
null_ptr<T>()`), so a zeroed struct is indistinguishable from the intent.
`DESIGN.md`'s own `Opts` has `verbose :: bool = false` — same coincidence.

**Workaround:** `Cursor` has no field defaults; `cursor_at` supplies all four
explicitly. `line: 1` is exactly the non-zero default that would have been
lost.

---

## 5. `==` on two enum values passes sema and emits invalid C

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
`==` desugars to it, so the right fix is probably a sema rejection rather than
a codegen change — which makes this a `must-fail/sema` test that does not
exist.

**Workaround:** `Cursor.at_byte` compares after unwrapping, which is clearer
anyway.

---

## 6. The grammar reads a comment opener inside a string literal as a comment

**Not the bootstrapper — `grammar/grammar.js`.** It stops a valid program from
parsing at all.

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

The `//` is lexed as a real line comment and swallows the closing quote. It
fires when the opener follows whitespace or an escape sequence, and not when
it follows ordinary content — so `token.immediate` on the string's content
regex is not keeping `extras` out at those positions.

`bootstrap/lex.py` accepts all four, so the two implementations disagree, and
the stricter one is the one that is right.

**Workaround:** `tests/corpus/lex_zen/comments` builds every comment input a
byte at a time through a `String` rather than writing it down.

---

## 7. A method call on a type whose module was not imported resolves by name, globally

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

The brief's own gate:

```
$ python3 -m bootstrap.bootstrap --root . src/lex/lex.zen
tests/parse/errors/ternary.zen:6:22: unexpected character `?`
example/src/main.zen:6:8: module pkg.json not found
... 125 diagnostics
```

`zmodules.build(root)` walks the whole root before `prune` runs, and
`tests/parse/errors/` holds twenty-five files that exist **in order not to
parse**. A real diagnostic from `src/lex/` is invisible in the noise. Either
prune before reporting parse diagnostics, or exclude `tests/` from discovery
the way dot-directories already are.

---

## 9. A same-named constructor loses to positional struct construction

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

**Workaround:** `alloc.Lexer(source)` for the one whose first parameter is an
`Alloc`, and the name `cursor_at` for the one whose first parameter is a `str`
— following `std.text`'s own `str_at`, which exists for the same reason.

---

## 10. `loop` with `h.break(value)` does not infer its result type

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
