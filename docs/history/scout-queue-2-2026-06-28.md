# Scout round 2 — 2026-06-28 (regression-focused, main 7f3f2ba)

## REGRESSIONS (fix first)

Ranked within: soundness/accepts-invalid before diagnostics; shared-root items grouped.

### R1 — Read-only `Ptr<T>` silently coerces to `MutPtr<T>` through a call (guarantee laundered)
- dimension: checker soundness / pointer types · sev **high** · value **high** · **REGRESSION** · accepts-invalid
- lane: **compiler-core-serialized** (check.zen — same file as R2/R4/R-notcall; serialize)
- repro:
```
{ println } = std.text.fmt
Counter: { n: i32 }
do_bump = (c: MutPtr<Counter>) void { c.n = c.n + 1 }
main = () i32 {
    c := Counter(n: 0)
    p: Ptr<Counter> := c.addr()
    do_bump(p)
    println(c.n)
    0
}
./zenc run /tmp/s2-hole.zen  -> compiles, prints 1 (exit 0). Expected arg-type/ptr-write rejection.
Also reproduces via a MutPtr struct field (/tmp/s2-field.zen -> prints 42). Reverse (MutPtr->Ptr) correctly accepted.
```
- fix-sketch: In `tfits` (check.zen:3238), before the `g.ty_eq(w)` fall-through for two non-null pointers, reject when `g.is_readonly_ptr_ty()` and `w` is `k_mut_ptr`; equivalently make `ty_eq`'s `.Ptr` arm require `pa.kind` compatibility (MutPtr fits {Ptr,MutPtr}; Ptr fits only Ptr). Root: ty_eq's `.Ptr` arm (check.zen:3186-3189) compares only the pointee, never `pd.kind`.

### R2 — Nested field write `b.inner.v = 99` through read-only `Ptr<T>` accepted, mutates pointee
- dimension: checker soundness · sev **high** · value **high** · **REGRESSION** · accepts-invalid + miscompile
- lane: **compiler-core-serialized** (check_validate.zen — shares root with R3)
- repro:
```
Inner: { v: i64 }
Box: { inner: Inner }
poke = (b: Ptr<Box>) void { b.inner.v = 99 }
main = () i64 {
    i := Inner( v: 1 )
    x := Box( inner: i )
    poke(x.addr())
    x.inner.v
}
./zenc check s2-nest2.zen -> 'ok' (exit 0); ./zenc run -> exit 99.
Proof of inconsistency (/tmp/s2-cmp.zen): `b.inner = i` IS rejected ('cannot write through a read-only Ptr<T>') while `b.inner.v = 99` in the same file is accepted.
```
- fix-sketch: In `assign_ptr_write_err` (check_validate.zen:982-988), resolve the BASE of the target's member/index chain (follow `.Member`/`.Arrow`/`.Index` obj down to the root expr) and test whether that root infers to a readonly `Ptr<T>`, not just the immediate obj. Apply same to `store()` target analysis. **R3 below is the IndexSet half of the same fix — do them together.**

### R3 — Index-set `b.data[i] = v` through read-only `Ptr<T>` not readonly-checked
- dimension: checker soundness · sev **low** · value **medium** · **REGRESSION** · accepts-invalid · **shares root with R2**
- lane: **compiler-core-serialized** (check_validate.zen — fold into R2 PR)
- repro:
```
Buf: { data: [i64] }
poke = (b: Ptr<Buf>) void { b.data[0] = 99 }
main = () i64 { 0 }
./zenc check s2-idx.zen -> 'ok' (exit 0).
```
- fix-sketch: Apply R2's member-chain-root readonly analysis to IndexSet targets in `idxset_err` (check_validate.zen:989-993). Note: "shallow-const-debatable" since the element store goes through the slice's own backing pointer — see Needs-verification for the design call, but the inconsistency with R2's direct/store rejections justifies aligning.

### R4 — Malformed binary/octal literals split into two tokens (wrong value, no error)
- dimension: parser/lexer robustness · sev **medium** · value **medium** · **REGRESSION** · accepts-invalid + miscompile
- lane: **compiler-core-serialized** (lex.zen + parse_expr.zen — own PR, parallel-safe vs check.zen/genc.zen)
- repro:
```
main = () i32 { 0o9 }  -> ./zenc run exits 9. emit: `{ 0; return 9; }` (0o = value-0 token, 9 a separate returned stmt).
0b2       -> exit 2
0b19      -> exit 9
1 + 0b2   -> exit 2; emits `{ (1 + 0); return 2; }` — addition silently dropped
0b2 + 1   -> exit 3
1 + 2 * 0o9 - 0b2 -> exit 2 (splits into 3 statements, last wins)
```
- fix-sketch: In lex.zen `num_end` (lex.zen:60-67), after a 0b/0o/0x prefix require >=1 valid base digit AND reject when the span is immediately followed by an alnum that is not a valid base digit (decimal digit out of range); call `lerr_set()` so the module is rejected. **R5 shares this exact fix point.**

### R5 — Lone `0b`/`0o`/`0x` prefix with no digits accepted as value 0
- dimension: parser/lexer robustness · sev **low** · value **low** · **REGRESSION** · accepts-invalid · **shares fix with R4**
- lane: **compiler-core-serialized** (lex.zen — fold into R4 PR)
- repro:
```
main = () i32 { 0b }  (also 0o, 0x) -> ./zenc run exits 0, no diagnostic. Expected 'empty <base> literal'.
(0b<EOF> surfaces a generic parse error; mid-expression it is silently 0.)
```
- fix-sketch: Same as R4 — require >=1 valid digit after the radix prefix in `num_end`; `lerr_set()` when none follows.

### R6 — Exhaustiveness error positionless for the dominant `x := e; x.match{}` shape
- dimension: diagnostics quality · sev **medium** · value **high** · **REGRESSION**
- lane: **compiler-core-serialized** (check_validate.zen — additive; low-conflict, serialize file-level)
- repro:
```
E: A | B | C
main = () i32 {
    e := E.A
    e.match({ .A => 1, .B => 2 })
    0
}
./zenc check -> `error[exhaustiveness]: match does not cover every variant` — NO line:col, NO snippet.
Inconsistency: param subject (`classify = (e: E) i32 {...}`) or inline call (`mk().match(...)`) DOES yield `:N:C:` with caret. Only a local :=/typed-local drops position (verified 3 variants).
```
- fix-sketch: `kv_match_kind` (check_validate.zen:1856) uses `.kv_at(load(m.subj).expr_pos())`; Var refs resolving to a local binding carry pos 0 (known `*_at`-ctor rebuild pitfall). Preserve the Var's source pos through resolution, or fall back to the enclosing match/Member token pos.

### R7 — Function falling off the end gives a positionless `return-fit`
- dimension: diagnostics quality · sev **medium** · value **high** · **REGRESSION**
- lane: **compiler-core-serialized** (check_validate.zen — same file as R6, serialize)
- repro:
```
main = () i32 {
    x := 5
}
./zenc check -> `error[return-fit]: returned value does not fit the declared return type` — NO line:col.
Contrast: `main = () i32 { "hello" }` IS positioned at 2:5 with a caret.
```
- fix-sketch: In the implicit-void-tail return-fit branch, attach the position of the function's last statement or closing brace, and special-case the message: `function body falls through with no value; add a trailing expression of type i32`.

### R8 — `assert_nonnull` accepts a non-pointer arg, yields a deref-able MutPtr
- dimension: checker soundness · sev **medium** · value **medium** · **REGRESSION** · accepts-invalid
- lane: **compiler-core-serialized** (check.zen — serialize with R1)
- repro:
```
main = () i64 {
    x := 5
    q := assert_nonnull(x)
    load(q)
}
./zenc check -> 'ok' (exit 0). Error only surfaces later from cc ('void value not ignored…').
```
- fix-sketch: In infer_call's assert_nonnull arm (check.zen:592), require `arg0_ty` to be a nullable pointer (`is_nullable_ptr_ty`); emit a fit/type error otherwise instead of calling `pointee_of()` on a scalar. **VETO (see below):** do NOT also reject the "already non-null Ptr/MutPtr" redundant case the finding suggests.

## Next fix-queue (ranked)

### Q1 — Untyped integer-literal arithmetic computed at i32 width — silent wrong values  ⚠ MISCOMPILE (co-top priority)
- dimension: codegen & runtime · sev **high** · value **high** · not a regression, but **silent miscompile → treat as top-tier**
- lane: **compiler-core-serialized** (genc.zen / genc_emit.zen — separate files, parallel-safe vs all checker/lexer lanes)
- repro:
```
{ println } = std.text.fmt
sz = (n: i64) i64 { n }
big = () i64 { 100000 * 100000 }
main = () i32 {
    g: i64 := 100000 * 100000          // observed 1410065408, expected 10000000000
    println(g)
    f: i64 := 1024 * 1024 * 1024 * 1024 // observed 0, expected 1099511627776
    println(f)
    println(sz(65536 * 65536))          // observed 0, expected 4294967296
    k: u64 := 1 << 40                    // observed 0, expected 1099511627776
    println(k)
    z: i64 := 0xFF * 0x1000000           // observed -16777216, expected 4278190080
    println(z)
    println(big())                       // observed 1410065408, expected 10000000000
    println((100000 * 100000) > 5000000000) // observed false, expected true
    0
}
./zenc run /tmp/s2-w.zen — every line silently wrong, no diagnostic.
emit shows: `int64_t f = (((1024 * 1024) * 1024) * 1024);` and `int64_t d = (1 << 40);` — bare 32-bit int operands overflow before the i64 assignment.
Workaround confirms root cause: `1 * 3000000000` and `c*c` with `c: i64` are correct. Literals individually > i32 (e.g. 6022000000000000000, 0xFFFFFFFFFFFFFFFF) print correctly — only products/shifts of small literals whose RESULT exceeds i32 miscompile.
```
- fix-sketch: When a binary integer expression's operands are untyped literals, infer the literal type from the expected/target/declared type (i64/u64) BEFORE folding, or emit operands with a width suffix/cast (`(int64_t)1024`, `1LL`). Pairs conceptually with the lexer literal work (R4/R5) but is a distinct codegen file — schedule in parallel.

### Q2 — Top-level fn named like a runtime/libc symbol leaks 130KB of raw cc error
- dimension: diagnostics / namespacing · sev **medium** · value **medium** · not a regression
- lane: **parallel-safe** (genc preamble + driver cc invocation — independent of checker/lexer/codegen-int lanes)
- repro:
```
read = (x: i32) i32 { x + 1 }  + call read(5)  -> error[arity] pointing at the user's own correct call (user def silently shadowed by builtin read). Same for write, open.
alloc = (x: i32) i32 { x + 1 } -> NO Zen diagnostic; gcc error leaks: `/tmp/zenc_zd_2680582.c:4:1618: error: conflicting types for 'alloc'...` + ~130KB of generated C dumped to stderr.
Contrast: print/len give a clean error[dup-fn].
```
- fix-sketch: At check time emit a clean `error[dup-fn]`/`name reserved by runtime` for these names; at minimum **always** suppress dumping the full generated C to stderr on cc failure. **PARTIAL VETO** on blanket-reserving `read`/`write`/`open` (see vetoes) — but the 130KB-dump suppression is unconditional.

### Q3 — Calling a non-function local reports `undefined-name` (the name IS defined)
- dimension: diagnostics quality · sev **medium** · value **medium** · not a regression
- lane: **compiler-core-serialized** (check.zen call resolution — serialize with R1/R8)
- repro:
```
main = () i32 {
    x := 5
    x(3)
    0
}
./zenc check -> `:3:5: error[undefined-name]: undefined name` with hint to declare/import.
Expected: error[not-callable]: value of type i32 is not a function.
```
- fix-sketch: When a call target resolves to a value of non-function type, emit a distinct not-callable diagnostic instead of routing through undefined-name.

### Q4 — Unterminated `/* */` comment produces a positionless parse error
- dimension: diagnostics quality · sev **medium** · value **medium** · not a regression
- lane: **compiler-core-serialized** (lex.zen — fold with R4/R5 lexer PR)
- repro:
```
{ println } = std.text.fmt
main = () i32 {
    println("hi")
    /* unterminated here
    0
}
./zenc check -> `error[parse]: syntax error: unparseable top-level input (+1 more error)` — NO line:col.
Unterminated string literals DO get a caret (s2-unterm.zen:2:10), so block comments are the gap.
```
- fix-sketch: Record the `/*` start position in the lexer; emit a positioned unterminated-comment diagnostic at EOF instead of the generic top-level sentinel.

## Lower priority

### L1 — Index of a non-slice value (`x[0]`) is positionless
- diagnostics quality · sev **low** · value **medium** · not a regression · lane **compiler-core-serialized** (check_validate.zen)
- repro:
```
main = () i32 {
    x := 5
    x[0]
    0
}
./zenc check -> `error[index]: invalid index operation` — NO line:col, doesn't say x is i32 (non-indexable).
```
- fix-sketch: `kv_index_kind` (check_validate.zen:1859) is the only `kv_*_kind` builder missing `.kv_at(...)`; add `.kv_at(ix.pos.pos_or(load(ix.base).expr_pos()))`, mirroring `kv_operand_kind`. Cheap; batch with R6/R7 in the same check_validate.zen diagnostics pass.

### L2 — `dup-fn` is positionless and never names the duplicated symbol
- diagnostics quality · sev **low** · value **medium** · not a regression · lane **compiler-core-serialized** (check_validate.zen)
- repro:
```
f = () i32 { 1 }
f = () i32 { 2 }
main = () i32 { 0 }
./zenc check -> `error[dup-fn]: duplicate top-level definition` — NO line:col, NO symbol name.
```
- fix-sketch: Attach the second decl's source position and interpolate the offending name (`:2:1: error[dup-fn]: 'f' is already defined`). Batch with L1/R6/R7.

## Ergonomics vetoes

- **R8 (assert_nonnull):** Implement ONLY the "reject non-pointer arg" part. Do NOT adopt the finding's secondary suggestion to also reject `assert_nonnull` on an already-non-null `Ptr`/`MutPtr` — that case is a legitimate no-op and rejecting it would break generic code that asserts nullness it can't prove statically. Veto the redundant-pointer rejection.
- **Q2 (libc-name reservation):** Veto *blanket* reservation of common identifiers (`read`, `write`, `open`) as reserved keywords — that bans reasonable user function names and harms ergonomics. Prefer proper shadowing/namespacing so a user `read` wins (or, if collision is genuinely unavoidable, a precise dup-fn only when it actually conflicts). The unconditional, non-vetoed part is: never dump generated C to stderr and never surface a temp-file cc path to the user.

## Needs verification

All 14 findings are marked `confidence: verified` with reproducible commands — none are speculative. Two open *design* questions (not correctness gaps) to resolve before coding:

- **R3 shallow-const semantics:** the finding itself flags this as "shallow-const-debatable" — writing an element through a slice's own backing pointer is arguably allowed even when the containing struct is reached via a read-only `Ptr`. Decide the intended depth of `Ptr<T>` read-only-ness (shallow vs deep/transitive) before locking R3's behavior; ship R2 (direct nested field write, unambiguous) regardless.
- **Q2 collision policy:** which libc/intrinsic names are genuinely always-in-scope vs. shadowable needs an enumerated list confirmed against the genc preamble before choosing reserve-vs-shadow.