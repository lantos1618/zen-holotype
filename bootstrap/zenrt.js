// zenrt.js — the JavaScript runtime floor for the js backend. The JS analog of bootstrap/zenrt.c:
// it provides the intrinsics (load/store/offset/slice/…) and the libc leaves (write/strlen/malloc/…)
// that emitted Zen programs bottom out on, over a single shared linear memory (a Uint8Array). All
// Zen pointers — str, RawPtr, MutPtr — are INTEGER offsets into `MEM`, exactly as they are addresses
// in C, so the whole memory model is uniform. Prepended to every emitted module by the driver.
//
// MINIMAL FLOOR (phase 1): enough for the str-print path (str literal → intern → view → write) plus
// the raw-memory intrinsics. Actors and the full libc/DOM surface are DEFERRED — the stubs below keep
// dead closure code loadable without pulling those in.
//
// NO STUB HERE MAY RETURN A PLAUSIBLE WRONG ANSWER. `sizeof` used to answer 8 for every type and
// `addr` used to be the identity for scalars; both let a program run to completion under node and
// print different numbers than the same program under C, with no diagnostic at either end. `sizeof`
// is now resolved to a literal by the emitter (compiler.backend.js.js_size) and never reaches this
// file; an address-taken scalar is boxed into a real cell (`box`/`ld`/`st`). What genuinely cannot be
// expressed on this target PANICS with a `js target:` message — silence is the one outcome ruled out.
"use strict";
// Every byte this floor writes goes out through fs.writeSync, NOT process.stdout.write: on a pipe the
// latter is ASYNCHRONOUS, so a program that prints and then panics (which exits immediately, below)
// would lose its output. Synchronous writes make stdout ordering identical to C's write(2).
const fs = require("fs");
const __zr = (() => {
  const CAP = 1 << 26;                 // 64 MiB linear memory
  const MEM = new Uint8Array(CAP);
  const dv = new DataView(MEM.buffer);
  const enc = new TextEncoder();
  const dec = new TextDecoder("utf-8");
  let HP = 8;                          // bump heap pointer (0 reserved for null)
  const interned = new Map();          // JS string -> interned MEM offset (NUL-terminated UTF-8)

  const malloc = (n) => { const p = HP; HP += (Number(n) + 7) & ~7; return p; };
  const str = (s) => {
    let p = interned.get(s);
    if (p !== undefined) return p;
    const b = enc.encode(s);
    p = malloc(b.length + 1);
    MEM.set(b, p);
    MEM[p + b.length] = 0;
    interned.set(s, p);
    return p;
  };
  const strlen = (p) => { let n = 0; while (MEM[p + n] !== 0) n++; return n; };
  const decode = (p, len) => dec.decode(MEM.subarray(p, p + Number(len)));
  const jstr = (p) => decode(p, strlen(p));  // a Zen `str` (MEM offset) -> a real JS string, for DOM/API boundaries

  // ── pointers ──────────────────────────────────────────────────────────────────────────────────
  // A pointer is a MEM offset (a number) EXCEPT for a pointer to a struct, which is the JS object
  // itself — objects are references, so `MutPtr<T>` needs no indirection and `load` on one is the
  // identity deref (`*p` in C). `isref` is that discriminator. A JS ARRAY is the backing of a non-byte
  // slice literal and is deliberately NOT a struct reference.
  const isref = (p) => p !== null && typeof p === "object" && !Array.isArray(p);
  // Byte arithmetic on an object-backed pointer has no meaning on this target. It used to write to a
  // Uint8Array under a non-index key — silently discarded — so say so instead of losing the write.
  const notbytes = (op) => panic("zen: panic: js target: " + op + " through an object-backed pointer\n");
  const load = (p) => isref(p) ? p : MEM[p];
  // a stored byte may arrive as a BigInt (a digit derived from a 64-bit value), so mask through `u8`.
  const store = (p, b) => { if (isref(p)) notbytes("store"); const v = u8(b); MEM[p] = v; return v; };
  const offset = (p, n) => { if (isref(p)) notbytes("offset"); return p + Number(n); };
  const load_i64 = (p) => { if (isref(p)) notbytes("load_i64"); return norm(dv.getBigInt64(p, true)); };
  const store_i64 = (p, v) => { if (isref(p)) notbytes("store_i64"); dv.setBigInt64(p, BigInt(v), true); return v; };
  // ── boxed (address-taken) scalar locals ───────────────────────────────────────────────────────
  // The js backend gives a scalar local whose address is taken a real one-value cell here, so that
  // `addr` yields a MEM offset and load/store/offset over it behave exactly as in C. `w` is the
  // emitter's width code (js_expr.js_cell_w): 1 u8, 2 u16, 3 u32, 4 i32, 5 i16, 6 i8, 7 u64, 8 i64,
  // 9 f64, 10 bool. The cell is exactly as wide as the C variable, so a BYTE store lands in its low
  // byte and a subsequent read of the variable sees it — which identity `addr` could never do.
  const CELLSZ = [0, 1, 2, 4, 4, 2, 1, 8, 8, 8, 1];
  const ld = (p, w) => {
    if (w === 1) return MEM[p];
    if (w === 2) return dv.getUint16(p, true);
    if (w === 3) return dv.getUint32(p, true);
    if (w === 4) return dv.getInt32(p, true);
    if (w === 5) return dv.getInt16(p, true);
    if (w === 6) return dv.getInt8(p);
    if (w === 7) return norm(dv.getBigUint64(p, true));
    if (w === 8) return norm(dv.getBigInt64(p, true));
    if (w === 9) return dv.getFloat64(p, true);
    return MEM[p] !== 0;
  };
  const st = (p, v, w) => {
    if (w === 1 || w === 6) { MEM[p] = u8(v); return v; }
    if (w === 2 || w === 5) { dv.setUint16(p, Number(v) & 0xffff, true); return v; }
    if (w === 3 || w === 4) { dv.setUint32(p, Number(v) >>> 0, true); return v; }
    if (w === 7 || w === 8) { dv.setBigInt64(p, BigInt.asIntN(64, tobig(v)), true); return v; }
    if (w === 9) { dv.setFloat64(p, Number(v), true); return v; }
    MEM[p] = v ? 1 : 0;
    return v;
  };
  const box = (v, w) => { const p = malloc(CELLSZ[w]); return st(p, v, w), p; };
  const slice = (ptr, len) => ({ ptr, len: Number(len) });
  // a [u8] SLICE LITERAL: copy the element values into linear memory and hand back the offset, so
  // the resulting `.ptr` is a real RawPtr (offset/store/load/write all work over MEM, as in C).
  // Fresh per evaluation — mirrors C's automatic-storage compound literal. Bump-allocated (never
  // freed), like every malloc on this minimal floor.
  const u8lit = (xs) => { const p = malloc(xs.length || 1); MEM.set(xs, p); return p; };
  const view = (s) => ({ ptr: s, len: strlen(s) });    // a str's byte view (matches std.text.str.view)
  // element read/write over a fat pointer, dispatching on how `.ptr` is backed: a SliceLit `[a,b,c]`
  // carries a JS ARRAY (index it directly), while a str/byte view carries a MEM OFFSET (an integer —
  // read the byte out of linear memory). Without this split, `sv.ptr[i]` on a byte view indexes an
  // integer and yields `undefined`, which silently broke every byte-scan (e.g. format's `{}` finder).
  // BOUNDS-CHECKED, like C's zen__idx (the genc preamble): an out-of-range slice index PANICS. This is
  // a language guarantee, not a debug aid — without the check `xs[5]` on a 3-element slice quietly read
  // MEM out of the slice (or `undefined` off a JS array) and the program exited 0 with a wrong answer.
  const bound = (seq, i) => {
    if (seq === null || typeof seq !== "object") panic("zen: panic: js target: index through a non-slice\n");
    const n = Number(i);
    if (n < 0 || n >= seq.len) panic("zen: panic: slice index out of bounds\n");
    return n;
  };
  // TYPED element access over a MEM-backed slice: `w` is the emitter's element-width code (js_expr's
  // js_elem_w — the cell codes plus 11 for an 8-byte pointer), the analog of C's `zen__idx(z, i,
  // sizeof(T))`. Without it the floor read ONE BYTE at `ptr + i` for every element type, so a
  // `[StringView]` or `[i64]` that came from an allocator decoded to garbage and kept running.
  // Code 0 = an element with no linear-memory form (a struct/enum/nested slice): MEM holds bytes and a
  // struct on this target is a JS object, so such a read is refused out loud, never guessed.
  const ELEMSZ = [0, 1, 2, 4, 4, 2, 1, 8, 8, 8, 1, 8];
  const elat = (p, n, w) => {
    if (!w) panic("zen: panic: js target: slice element of this type has no linear-memory representation\n");
    return p + n * ELEMSZ[w];
  };
  const rdel = (p, w) => w === 11 ? Number(dv.getBigUint64(p, true)) : ld(p, w);
  // An object-backed pointer (a `MutPtr<Struct>`, which IS the JS object) has no byte image, so a
  // `[MutPtr<T>]` living in linear memory is refused here rather than silently stored as something else.
  const wrel = (p, v, w) => {
    if (w === 11) { if (isref(v)) notbytes("slice element store of a pointer"); dv.setBigUint64(p, BigInt(v), true); return v; }
    return st(p, v, w);
  };
  const idx = (seq, i, w) => { const n = bound(seq, i); const p = seq.ptr; return Array.isArray(p) ? p[n] : rdel(elat(p, n, w), w); };
  const setidx = (seq, i, v, w) => { const n = bound(seq, i); const p = seq.ptr; if (Array.isArray(p)) { p[n] = v; return v; } return wrel(elat(p, n, w), v, w); };
  const eq = (a, b) => a === b || decode(a, strlen(a)) === decode(b, strlen(b));
  const nn = (p) => { if (p === 0) panic("zen: panic: null pointer deref\n"); return p; };
  // `addr` on an object-backed pointer (a struct) is the identity — the object IS the reference. An
  // address-taken SCALAR never reaches here: the emitter boxes it (see `box` above) and lowers its
  // `addr` to the variable itself, which already holds the cell offset.
  const addr = (x) => x;
  // ── struct VALUE semantics ────────────────────────────────────────────────────────────────────
  // A Zen struct is a value: `b = a` copies it in C, so a write through `b` is invisible through `a`.
  // A JS object is a reference, so the emitter copies at every sink C copies at. THIS is the one-level
  // half of that copy — a type whose every field is itself shared by a C copy (a scalar, a pointer, a
  // `zslice` header whose BUFFER stays shared). A type with a field that must be copied in turn gets a
  // generated `__zc_<Name>` walk instead (compiler.backend.js.js_copy); a deep clone can NOT live here,
  // because a `MutPtr<T>` on this target IS the object, and cloning one would fork an allocator.
  // Non-objects (a number, a BigInt, a MEM offset) are already values: pass them through — and so is
  // anything that is not a PLAIN object. Every Zen struct/enum/slice on this target is an object
  // literal, so `Object.prototype` is the exact discriminator; a real DOM node reaching a value sink
  // (the dom lowering hands back live objects) must pass through untouched, since `{...node}` would
  // keep its own fields and lose its prototype — the methods ARE the value. It also excludes arrays,
  // which back slice literals and are the shared BUFFER, never the copied header.
  const PLAIN = Object.prototype;
  const cp = (x) => (x !== null && typeof x === "object" && Object.getPrototypeOf(x) === PLAIN) ? { ...x } : x;
  // ── 64-bit integer model ───────────────────────────────────────────────────────────────────────
  // A JS `number` is a 32-bit-op / 53-bit-mantissa view, so i64/u64 are modeled as BigInt (arbitrary-
  // precision, EXACT). To keep ordinary/narrow arithmetic cheap, a 64-bit value is kept as a `number`
  // while it fits +/- 2^53 exactly and promoted to BigInt only past that (`norm`). The js backend coerces
  // both operands of a 64-bit operator to BigInt (`big`), so nothing mixes BigInt with number; the type's
  // boundary (let/param/assign/return) then wraps to width with `wi64`/`wu64` and norms the result back.
  const S53 = 9007199254740991n;                 // 2^53 - 1 — a BigInt within +/- this round-trips exactly
  const tobig = (x) => typeof x === "bigint" ? x : BigInt(Math.trunc(x));
  const norm = (b) => (b >= -S53 && b <= S53) ? Number(b) : b;
  const big = (x) => tobig(x);                    // operand coercion: force a value to BigInt for a 64-bit op
  const wi64 = (x) => norm(BigInt.asIntN(64, tobig(x)));   // wrap-to-i64 at a boundary
  const wu64 = (x) => norm(BigInt.asUintN(64, tobig(x)));  // wrap-to-u64 at a boundary
  const u64 = wu64;                               // (retained floor name)
  const u8 = (x) => typeof x === "bigint" ? Number(x & 255n) : x & 255;
  const i32 = (x) => typeof x === "bigint" ? Number(BigInt.asIntN(32, x)) : x | 0;
  const i64 = (x) => wi64(x);                     // to_i64: widen to a (norm) i64
  // div/mod stay integer-guarded (div-by-zero panics). A BigInt operand takes the BigInt path (signed,
  // truncating-toward-zero — matches C for i64; two non-negative u64 BigInts give unsigned division). The
  // float `/` is emitted natively by the js backend, never here.
  const div = (a, b) => { if (typeof a === "bigint" || typeof b === "bigint") { const bb = tobig(b); if (bb === 0n) panic("zen: panic: integer divide by zero\n"); return norm(tobig(a) / bb); } if (b === 0) panic("zen: panic: integer divide by zero\n"); return Math.trunc(a / b); };
  const mod = (a, b) => { if (typeof a === "bigint" || typeof b === "bigint") { const bb = tobig(b); if (bb === 0n) panic("zen: panic: integer modulo by zero\n"); return norm(tobig(a) % bb); } if (b === 0) panic("zen: panic: integer modulo by zero\n"); return a % b; };
  // A panic is FATAL, exactly as in C: the message goes to stderr and the process dies with C's abort
  // status (128 + SIGABRT). Exiting rather than throwing keeps the two backends' observable behaviour
  // identical — same stderr line, same non-zero status — instead of a JS stack trace at status 1. Safe
  // because `write` below is synchronous, so nothing buffered is lost.
  const ZEN_ABORT_STATUS = 134;
  const panic = (m) => {
    const s = typeof m === "number" ? decode(m, strlen(m)) : String(m);
    try { fs.writeSync(2, s); } catch (_e) { }
    process.exit(ZEN_ABORT_STATUS);
  };
  // ── seq-cst atomics over an i64 cell (the atomic_* intrinsics) ─────────────────────────
  // These are NOT stubs. Emitted JS runs on ONE thread with run-to-completion semantics: no other
  // agent can observe an intermediate state of a synchronous read-modify-write, and a fence has no
  // second thread to order against. So on this target the seq-cst contract is discharged EXACTLY by
  // plain cell ops — the same answers C's __atomic_* give, on a machine with one thread.
  // Real parallelism here would need Workers + SharedArrayBuffer, which nothing emits; a program that
  // tries to spawn a thread fails loudly on `pthread_create`, which no JS floor defines. So there is
  // no reachable state in which one of these is silently weaker than its C counterpart.
  const atomic_load = (p) => load_i64(p);
  const atomic_store = (p, v) => store_i64(p, v);
  // fetch-add returning the NEW value, wrapping at 64 bits — matches C's __atomic_add_fetch.
  const atomic_add = (p, d) => { const n = norm(BigInt.asIntN(64, tobig(load_i64(p)) + tobig(d))); store_i64(p, n); return n; };
  const atomic_cas = (p, exp, des) => { if (tobig(load_i64(p)) !== tobig(exp)) return false; store_i64(p, des); return true; };
  const atomic_fence = () => {};

  // fd 1 = stdout, 2 = stderr; ptr is a MEM offset (or, for a JS-array slice, ignored). SYNCHRONOUS
  // (fs.writeSync), so ordering against stderr and against a panic's exit matches C's write(2).
  const write = (fd, ptr, len) => {
    const s = decode(ptr, len);
    fs.writeSync(Number(fd), s);
    return Number(len);
  };

  // `main`'s return value is the process exit status, exactly as in C (`& 255`). Set as `exitCode`
  // rather than `process.exit` so anything still queued flushes on the normal exit path.
  const exit_main = (v) => { process.exitCode = Number(v || 0) & 255; };

  return { MEM, str, strlen, decode, jstr, malloc, load, store, offset, load_i64, store_i64, exit_main,
           slice, u8lit, view, idx, setidx, eq, nn, addr, cp, i32, i64, u8, big, wi64, wu64, u64,
           ld, st, box, div, mod, panic, write,
           atomic_load, atomic_store, atomic_add, atomic_cas, atomic_fence };
})();

// ── libc leaves referenced by name from emitted code. The print path needs only write/strlen; the
//    rest are stubs so dead closure code (file I/O, threads) stays loadable. DEFERRED: real impls. ──
const write = (fd, ptr, len) => __zr.write(fd, ptr, len);
const strlen = (p) => __zr.strlen(p);
const malloc = (n) => __zr.malloc(n);
const memcpy = (dst, src, n) => { for (let i = 0; i < Number(n); i++) __zr.MEM[dst + i] = __zr.MEM[src + i]; return dst; };
// A bump allocator never frees, so the OLD block at `p` is still live: copy `n` bytes forward into the
// fresh, larger block (the tail past the old length is spare capacity the caller overwrites). Without the
// copy, growing a container — vec.push past cap → try_resize → realloc — silently dropped every existing
// element (the Vec growth regression produced 4 instead of 10). C realloc preserves contents; so must this.
const realloc = (p, n) => { const q = __zr.malloc(n); n = Number(n); for (let i = 0; i < n; i++) __zr.MEM[q + i] = __zr.MEM[p + i]; return q; };
const free = (_p) => {};
const abort = () => { process.exit(134); };
// std.core.result's `panic` writes its own `zen: panic: …` line, calls this, then aborts. The genc
// preamble ships a WEAK no-op for the C target (c_emit.zen); without the JS counterpart every panic on
// this backend died with `ReferenceError: __zen_panic_unwind is not defined` after the message. There
// is no actor supervisor on this target to siglongjmp into, so — as in the weak C stub — it returns,
// which is what makes the `abort()` that follows it unconditional.
const __zen_panic_unwind = () => {};
// read(2): pull up to `n` bytes from fd into MEM at `ptr`; return the count (0 at EOF, -1 on error). The
// print path never calls it, but any stdin program (std.io.stdin → `read(STDIN, buf, 1)`) did before this
// → ReferenceError. Node's only synchronous stdin read is fs.readSync; on a pipe/file it blocks until data
// or EOF (the C contract). LIMITATION: a live TTY fd 0 can raise EAGAIN with no data ready; we retry (a
// blocking emulation), which busy-waits — fine for the piped-filter use case, not for interactive TTYs.
const read = (fd, ptr, n) => {
  fd = Number(fd); n = Number(n);
  const buf = Buffer.allocUnsafe(n);
  for (;;) {
    let got;
    try { got = fs.readSync(fd, buf, 0, n, null); }
    catch (e) { if (e.code === "EAGAIN") { continue; } if (e.code === "EOF") { return 0; } return -1; }
    // the destination backing mirrors __zr.idx/setidx: a slice-literal target (`cell := [0]`) carries a
    // JS ARRAY, a malloc'd/str target a MEM offset. std.io.stdin's 1-byte `cell` is the array case.
    if (Array.isArray(ptr)) { for (let i = 0; i < got; i++) ptr[i] = buf[i]; }
    else { const p = Number(ptr); for (let i = 0; i < got; i++) __zr.MEM[p + i] = buf[i]; }
    return got;
  }
};
