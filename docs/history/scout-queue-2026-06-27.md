# Scout fix-queue — 2026-06-27 (5-dimension fan-out on main e0f8317)

This is a triage task producing a markdown work plan. No code investigation needed—I'm synthesizing the 30 findings into a ranked queue. Let me produce the output directly.

## Next fix-queue (ranked)

### 1. Partial struct literal zero-fills a non-null `Ptr<T>` field → null-deref segfault (checker says ok)
**dim:** correctness/checker soundness (accepts-invalid) · **sev/value:** high/high · **lane:** compiler-core (check_validate.zen)
**Repro:**
```
Inner*: { n: i32 }
Outer*: { p: Ptr<Inner>, tag: i32 }
main = () i32 { o := Outer(tag: 7)  println(o.p.n)  0 }
$ ./zenc run /tmp/scout-28.zen  ->  Segmentation fault (core dumped)
  EXPECTED: checker error (missing field `p`, or non-null Ptr field cannot be default-zeroed).
Also: /tmp/scout-14.zen Box*:{v,w} with Box(v:5) -> x.w reads 0, checker 'ok'.
```
**Fix-sketch:** Require all fields in a struct literal (minimum: any non-null `Ptr`/`MutPtr` field left uninitialized is a checker error). This is the root of which scout-ergo finding #29 "partial literals zero-fill" is the soft twin — fixing it satisfies both. **Veto note:** full all-fields-required may annoy users who want zero-defaults; mitigate with an explicit `..default`/zero marker opt-in. Hard-error only the pointer case if you want to stay conservative.

### 2. Nullable `RawPtr<T>` coerces to non-null `Ptr<T>` param, bypassing assert_nonnull → segfault
**dim:** correctness/checker soundness (accepts-invalid) · **sev/value:** high/medium · **lane:** compiler-core (check.zen:3226 `fits()`)
**Repro:**
```
Box*: { v: i32 }
deref = (p: Ptr<Box>) i32 { p.v }
main = () i32 { r: RawPtr<Box> := null_ptr()  println(deref(r))  0 }
$ ./zenc run /tmp/scout-10.zen  ->  Segmentation fault (core dumped)
  EXPECTED: checker rejects passing nullable RawPtr where non-null Ptr is required.
```
**Fix-sketch:** In `fits()`, drop the `g.is_raw_ptr_ty() && w.is_ptr_ty_g() => true` rule for the nullable RawPtr kind (not the RawPtr<u8> floor); require explicit `assert_nonnull`, matching the deref rule.

### 3. Field-write through a read-only `Ptr<T>` is accepted (S2 mutability guarantee defeated)
**dim:** correctness/checker soundness (accepts-invalid) · **sev/value:** medium/medium · **lane:** compiler-core (check_validate.zen:242-244, check.zen:3219)
**Repro:**
```
Box*: { v: i32 }
write_through_ro = (p: Ptr<Box>) void { p.v = 99 }
main = () i32 { 0 }
$ ./zenc check /tmp/scout-9.zen  ->  'ok'  (EXPECTED: error[ptr-write])
And it mutates: bump=(b: Ptr<Box>) void { b.v = b.v+1 } over Box(v:5) -> run prints 6.
```
**Fix-sketch:** Apply the existing `store`-intrinsic read-only check to Assign/MemberAssign targets whose base infers to a k_ptr (read-only) pointer kind; reject with error[ptr-write]. Same file/area as #1–#3 → these three are one serialized checker-soundness lane.

### 4. Checker accepts generic type-arg mismatches (`Box<i32>` where `Box<u8>` expected) → cryptic cc error + 58KB C dump
**dim:** correctness/codegen · **sev/value:** medium/medium · **lane:** compiler-core (check.zen fits/ty_eq ~3132-3227; manifests in genc)
**Repro:**
```
Box<T>: { v: T }
mk<T> = (x: T) Box<T> { Box<T>(v: x) }
unbox<T> = (b: Box<T>) T { b.v }
main = () i32 { bu: Box<u8> := mk(255)  println(to_i64(unbox(bu)))  0 }
$ ./zenc check /tmp/scout-14.zen  -> ok
$ ./zenc run   /tmp/scout-14.zen  -> error: unknown type name 'Box_u8'
fn arg (scout-39): useu8(mk(7)) -> check ok, cc: incompatible type for argument 1
fn return (scout-40): getu8 = () Box<u8> { mk(7) } -> check ok, cc: incompatible types returning 'Box_i32' but 'Box_u8'
```
**Fix-sketch:** Generic CALL result type is treated as unknown at call site, so the unknown_ty guard skips assign-fit/arg-type/return-fit. Resolve the monomorphized return type (or compare mangled names) before the fit check so the mismatch is a Zen `assign-fit`/`arg-type` diagnostic, not a cc leak.

### 5. Mixed-width integer arithmetic takes the LEFT operand's type → silent truncation + order-dependent acceptance
**dim:** correctness/checker soundness (accepts-invalid) · **sev/value:** medium/medium · **lane:** compiler-core (check.zen:481 `bin_ty(b.op, infer_expr(b.lhs))`)
**Repro:**
```
f = () i32 { a: i32 := 0  b: i64 := 4294967297  a + b }
main = () i32 { println(f())  0 }
$ ./zenc run  ->  prints 1   (4294967297 silently truncated; EXPECTED: type error)
Asymmetry: `a + b` (i32,i64) returned from i32 fn -> ok; `b + a` (swapped) -> error[return-fit].
```
**Fix-sketch:** Type a numeric binary op as the wider (max-rank) of the two operands, not the LHS. Then `i32 + i64` is i64 and consistently fails to fit i32 regardless of order, killing the silent truncation.

### 6. UFCS/trait method on the wrong receiver type checks OK → link error (no impl verification)
**dim:** correctness/checker soundness (accepts-invalid) · **sev/value:** medium/high · **lane:** compiler-core (check_validate.zen method resolution)
**Repro:**
```
Area*: { area: (Ptr<Self>) i32 }
Circle*: { r: i32 }
Box*: { w: i32 }
Circle.impl(Area, { area = (c: Ptr<Circle>) i32 { c.r*c.r } })
main = () i32 { b := Box(w:3)  println(b.addr().area())  0 }
$ ./zenc run /tmp/scout-25.zen
  /usr/bin/ld: undefined reference to `area'   (EXPECTED: Box has no method/impl `area`)
(check-only also reports 'ok': /tmp/scout-23.zen.)
```
**Fix-sketch:** On UFCS method resolution, verify the receiver type implements the trait / the resolved fn's receiver param type matches; reject with method-not-found / receiver-mismatch instead of deferring to the C linker.

### 7. `println("x={}", v)` — no format-string interpolation / variadic print
**dim:** build gap + ergonomics · **sev/value:** high/high · **lane:** parallel-safe (zen/std/text/fmt.zen)
**Repro:**
```
{ println, print } = std.text.fmt
main = () i32 { name := "Zen"  n := 42  println("name={} n={}", name, n)  0 }
$ ./zenc run -> error[arity]: wrong number of arguments (println takes exactly one value)
EXPECTED: prints 'name=Zen n=42'.
```
**Fix-sketch:** Add a `{}`-template `format`/variadic `println(fmt, args...)`; the Printer builder already has per-type writers (.i/.f/.s) to back it. **Note:** stdlib comment says true cross-module generic+struct-param dispatch is the deep blocker; a `fmt2/fmt3` family or `{}` special-case unblocks the common path now. Merges scout-ergo #25 (same root).

### 8. Type errors during generic monomorphization carry no source position; stdlib errors blame the library, not the call site
**dim:** build gap + ergonomics · **sev/value:** medium/high · **lane:** compiler-core (checker monomorphization path)
**Repro:**
```
wrap<T> = (xs: [T]) i64 { xs.len }
main = () i32 { println(wrap(42))  0 }
$ ./zenc run -> 'zenc: scout-diag.zen: error[struct-field]: unknown struct field or invalid field access'  (NO line:col)
Stdlib case: vec.of(m, [1,2,3]) with wrong arg -> 'zen/std/collections/vec.zen:99:16: error[arg-type] ... a.acquire(...)' (points INTO the library, not the user's call).
```
**Fix-sketch:** Thread the instantiation/call-site span through monomorphization; report the user call position and attach a "required from here" note when the failure is inside library code. Merges scout-ergo #27 (identical root).

### 9. No scientific/e-notation float literals — `6.022e23`, `1e10`, `1.5e-3` rejected as undefined-name
**dim:** build gap · **sev/value:** high/high · **lane:** parallel-safe (lexer numeric scan)
**Repro:**
```
main* = () i64 { x := 6.022e23  0 }
$ ./zenc run -> error[undefined-name], caret under 'e23'
Also failing: 1e10, 1.5e-3, 1.0E5.
```
**Fix-sketch:** Extend the float-literal rule to consume an optional `[eE][+-]?digits` exponent (allow exponent without a fractional part). Same lexer file as #14/#15 → one lexer lane.

### 10. No compound-assignment operators (`+=`, `-=`, ...); failure misdiagnosed as a top-level parse error
**dim:** ergonomics · **sev/value:** medium/high · **lane:** compiler-core (parser)
**Repro:**
```
main = () i32 { x := 0  x += 5  println(x)  0 }
$ ./zenc run -> zenc: f.zen:4:8: error[parse]: syntax error: unparseable top-level input
EXPECTED: += supported, or a clear in-body 'unknown operator +=' message.
```
**Fix-sketch:** Desugar `lhs OP= rhs` to `lhs = lhs OP rhs` in the parser for existing binary ops; at minimum `+=`/`-=`. Independently, stop labeling in-body parse failures as "top-level" (shared root with #16). **Veto note:** Zen is match-only/expression-oriented; adding mutation sugar is fine since `x = x + 1` already exists, but keep it pure desugar—no new semantics.

## Lower priority

### L1. Inconsistent diagnostics: struct-field / operand-type errors carry no file:line:col and never name the symbol
**dim:** ergonomics · sev/value medium/medium · parallel-ish (checker emit paths, distinct from #8)
**Repro:** `println(p.z)` → `error[struct-field]: unknown struct field or invalid field access` (NO line:col, doesn't say `z`/list x,y); `println("foo"+"bar")` → `error[operand-type]: operator cannot be applied` (NO line:col, doesn't name str/str or `+`). Contrast: undefined-name/assign-fit DO emit caret.
**Fix-sketch:** Thread the existing Var/Call node position into struct-field and operand-type emitters; include symbol + valid fields.

### L2. Parser recovery emits positionless "unparseable top-level input" for in-body errors + misattributes dangling-operator errors
**dim:** ergonomics · sev/value medium/medium · compiler-core (parser) — pairs with #10
**Repro:** Unterminated `println("hi"` → `error[parse]: unparseable top-level input` (no line:col, "top-level" wrong). Dangling `x := 5 +` then `println(x)` → `error[undefined-name]` caret under `x` (real defect is `5 +`; parser consumed `println` as the operand).
**Fix-sketch:** Give top-level recovery a real position, reword for in-body context, stop the binary-op parser greedily crossing a newline/statement boundary.

### L3. Lambdas not first-class — cannot be returned/stored, only passed directly
**dim:** build gap · sev/value medium/medium · compiler-core (lambda lowering)
**Repro:** `make_adder = (base: i64) (i64) i64 { (x: i64) i64 { x + base } }` → `error[lambda-value]: a lambda can only be used directly as a call argument`. (Capturing closures DO work passed directly.)
**Fix-sketch:** Closure conversion (env struct + fn pointer) so a lambda value can escape its frame.

### L4. Hash map supports only `str` keys — no `Map<i64,V>`
**dim:** build gap · sev/value medium/medium · parallel-safe (zen/std/collections/map.zen)
**Repro:** `m: map.Map<i64> := map.empty(a.addr()); m.put(a.addr(),42,7)` → `error[arg-type] (+6 more)`; put/get take `k: str` only.
**Fix-sketch:** Generalize to `Map<K,V>` with Hash/Eq bound on K (str impl exists), or ship IntMap.

### L5. Explicit call-site type args `f<T>(x)` unsupported, misleading error
**dim:** build gap · sev/value medium/medium · compiler-core (parser/checker)
**Repro:** `id<T> = (x: T) T { x }; id<i64>(42)` → `error[undefined-name]` caret under `i64` (`<` parsed as less-than).
**Fix-sketch:** Support turbofish, or detect `<TypeName>` after callee and emit a targeted "call-site type args not supported; rely on inference" diagnostic.

### L6. No binary literals (`0b1010`) and no digit separators (`1_000_000`); only hex works
**dim:** build gap · sev/value medium/medium · parallel-safe (lexer) — bundle with #9
**Repro:** `0xFF` OK; `0b1010` → error[undefined-name] col 11; `1_000_000` → error[undefined-name] col 11.
**Fix-sketch:** Add `0b`/`0o` prefixes and allow `_` between digits (strip before parse).

### L7. String building has no `+` and no concise builder; positionless `operand-type` error gives no hint
**dim:** ergonomics · sev/value low/medium · parallel-safe (zen/std/text/str.zen)
**Repro:** `println("foo" + "bar")` → `error[operand-type]` (positionless). Concatenation forces `a.join([...], "")` or a Printer chain.
**Fix-sketch:** Allow `str + str` via an allocator-backed UFCS `a.cat(x,y)` returning owned String, or document join as THE idiom. **Veto note:** must stay explicit-allocator (no-hidden-heap rule) — do NOT add implicit heap `+`. Positionless error overlaps L1.

### L8. genjs.zen (272 lines) fully dead — not in manifest, not in seed, no CLI path
**dim:** dead code · sev/value medium/low · parallel-safe
**Repro:** `./zenc --help` lists no `js`; genjs.zen absent from bootstrap/sources.txt; `grep -c genModuleJs bootstrap/zenc.gen.c` → 0. Only live refs: tests/oracle_misc.zen corpus + tests/test_genjs.py.
**Fix-sketch:** Delete genjs.zen + test_genjs.py, drop from oracle_misc.zen corpus lists. If JS is a real goal, move to a branch.

### L9. Int-format/string-escape/byte-fetch helper families copy-pasted across genc_emit/pretty/genjs/diagnostic
**dim:** redundancy · sev/value medium/low · compiler-core (multiple gen files)
**Repro:** `byte = (v,i) { load(offset(v,i)) }` verbatim 4× (sbyte/dsbyte/ffbyte/jsbyte); `digit` 4×; gen_int/gen_int_neg/gen_int_nat byte-identical to ff_int* except prefix+append-method; pretty's ff_append/ff_push are pass-through wrappers over genc's gstr_append/gstr_push on the SAME String type.
**Fix-sketch:** Promote sbyte/digit/gen_int*/gen_strlit/gen_escape* to public in genc; pretty imports them, delete ff_* copies; diagnostic reuses too. (genjs copies vanish with L8.) Do AFTER L8.

### L10. `zenc run` prints the entire generated C source (~58KB one line) to stderr on any cc error
**dim:** codegen · sev/value low/medium · parallel-safe (driver.zen)
**Repro:** `./zenc run /tmp/scout-14.zen 2>&1 | head` → 58KB of generated C as a single line before the real `error:`.
**Fix-sketch:** Surface only cc's own stderr (has file:line) + a short "internal: generated C failed to compile" note; don't echo source. Ideally caught in checker (#4) so cc never fails.

### L11. Top-level globals cannot carry a type annotation: `g: i32 := 42` is a parse error
**dim:** codegen/parser · sev/value low/low · compiler-core (parser top-level grammar)
**Repro:** `g: i32 := 42` → `error[parse]: unparseable top-level input` at `:`; yet `g := 42` (top) and `x: i32 := 0` (in-fn) both work.
**Fix-sketch:** Allow `name: Type := expr` in top-level decl grammar, matching in-function let.

### L12. Float printing fixed at ~6 fractional digits, silently lossy
**dim:** codegen · sev/value low/low · parallel-safe (zen/std float fmt)
**Repro:** `println(0.123456789)` → `0.123457`; `println(1.0/7.0)` → `0.142857`; `println(0.1+0.2)` → `0.3`. f64 arithmetic itself is correct.
**Fix-sketch:** Shortest-round-trip float formatter, or expose precision control.

### L13. Stale python test files remain despite Zero-Python goal
**dim:** dead code · sev/value low/low · parallel-safe — bundle with L8
**Repro:** `ls tests/*.py` → 7 files (test_genjs.py, test_resolver_oracle.py, test_user_imports.py, _oracle.py, _oracle_corpus.py, _resolver.py, conftest.py); 14 total .py. sources.txt + driver.zen still cite tests/_resolver.py for manifest regen.
**Fix-sketch:** Delete test_genjs.py with L8; finish the zen-native-oracle port, remove .py corpus, update the sources.txt regen note to point at the Zen tool.

### L14. `is_upper_b` and `is_upper_byte` are two names for the identical predicate; bytes.zen lacks `is_upper`
**dim:** synonym sprawl · sev/value low/low · parallel-safe
**Repro:** parse.zen:681 `is_upper_b` and parse_expr.zen:339 `is_upper_byte` are character-identical `b >= 'A' && b <= 'Z'`; std.text.bytes has is_digit/is_hex/... but no is_upper.
**Fix-sketch:** Add `is_upper*` to zen/std/text/bytes.zen, import in both parsers, delete the two private copies.

### L15. Two public `at*` on `str` (bytes.at i32-unchecked vs str.at i64-bounds-checked) — name collision in a no-overload language
**dim:** synonym sprawl · sev/value low/low · parallel-safe
**Repro:** bytes.zen:6 `at* = (s: str, i: i32) u8 { s.offset(i).load() }` (unchecked) vs str.zen:126 `at* = (s: str, i: i64) u8 {... bounds-checked ...}`. Which binds depends on which module a file imports — silently swaps checked for unchecked.
**Fix-sketch:** Rename the unchecked variant `byte_at*`/`at_unchecked*`, widen its index to i64, so `at` always means bounds-checked.

### L16. Duplicate field in struct literal accepted silently
**dim:** checker soundness (minor) · sev/value low/low · compiler-core — fold into #1's struct-literal pass
**Repro:** `Box(v: 5, v: 9)` → check `ok` (last wins in codegen).
**Fix-sketch:** Track seen field names while checking a struct literal; reject a second initializer for the same field. Cheap add-on while in the literal-check path for #1.

### L17. Bitwise `&`/`|` bind tighter than comparison `==`/`<` (opposite of C) — footgun, not a miscompile
**dim:** codegen/parser precedence · sev/value low/low · doc-or-parser
**Repro:** `(1 | 2 == 2)` → parses `(1|2)==2` → false (prints 0); C would give `1|(2==2)` → true. Parser and genc AGREE (no miscompile), but differs from C.
**Fix-sketch:** Document the precedence prominently, or align bitwise/comparison precedence with the expected convention. **Veto note:** changing precedence risks silently re-meaning existing code — prefer documentation over a precedence change.

## Needs verification
*(All 30 findings were tagged `confidence: verified` by the scouts; none are speculative or unverified, so this list is empty.)* The only forward-looking/unproven claims embedded in otherwise-verified findings, flagged for confirmation before acting:
- **#7 / scout-ergo #25 deep fix:** the stdlib comment's claim that true variadic `{}` interpolation is blocked on cross-module generic+struct-param dispatch — verify whether a `{}` special-case can ship without that compiler work (the interim `fmt2/fmt3` path needs no verification).
- **L9 redundancy collapse:** verify pretty's ff_append/ff_push truly share genc's exact `String` type at link time (scout asserts they do) before deleting the ff_* triad — a one-shot `make` + fixpoint check gates this.