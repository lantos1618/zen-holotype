// zenrt.js — the JavaScript runtime floor for the js backend. The JS analog of bootstrap/zenrt.c:
// it provides the intrinsics (load/store/offset/slice/…) and the libc leaves (write/strlen/malloc/…)
// that emitted Zen programs bottom out on, over a single shared linear memory (a Uint8Array). All
// Zen pointers — str, RawPtr, MutPtr — are INTEGER offsets into `MEM`, exactly as they are addresses
// in C, so the whole memory model is uniform. Prepended to every emitted module by the driver.
//
// MINIMAL FLOOR (phase 1): enough for the str-print path (str literal → intern → view → write) plus
// the raw-memory intrinsics. Actors, i64-exact math, typed slice element reads, and the full libc/DOM
// surface are DEFERRED — the stubs below keep dead closure code loadable without pulling those in.
"use strict";
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

  const load = (p) => MEM[p];
  // a stored byte may arrive as a BigInt (a digit derived from a 64-bit value), so mask through `u8`.
  const store = (p, b) => { const v = u8(b); MEM[p] = v; return v; };
  const offset = (p, n) => p + Number(n);
  const load_i64 = (p) => norm(dv.getBigInt64(p, true));
  const store_i64 = (p, v) => { dv.setBigInt64(p, BigInt(v), true); return v; };
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
  const idx = (seq, i) => { const p = seq.ptr; return Array.isArray(p) ? p[i] : MEM[p + Number(i)]; };
  const setidx = (seq, i, v) => { const p = seq.ptr; if (Array.isArray(p)) { p[i] = v; } else { MEM[p + Number(i)] = u8(v); } return v; };
  const eq = (a, b) => a === b || decode(a, strlen(a)) === decode(b, strlen(b));
  const nn = (p) => { if (p === 0) panic("zen: panic: null pointer deref\n"); return p; };
  const addr = (x) => x;               // JS objects are references; scalar aliasing is DEFERRED (boxed refs)
  const sizeof = (_name) => 8;         // element sizes unused on the print path; DEFERRED for typed slices
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
  const panic = (m) => { const s = typeof m === "number" ? decode(m, strlen(m)) : String(m); process.stderr.write(s); throw new Error("zen panic"); };

  // fd 1 = stdout, 2 = stderr; ptr is a MEM offset (or, for a JS-array slice, ignored).
  const write = (fd, ptr, len) => {
    const s = decode(ptr, len);
    (fd === 2 ? process.stderr : process.stdout).write(s);
    return Number(len);
  };

  return { MEM, str, strlen, decode, jstr, malloc, load, store, offset, load_i64, store_i64,
           slice, u8lit, view, idx, setidx, eq, nn, addr, i32, i64, u8, big, wi64, wu64, u64,
           sizeof, div, mod, panic, write };
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
const abort = () => { throw new Error("abort"); };
// read(2): pull up to `n` bytes from fd into MEM at `ptr`; return the count (0 at EOF, -1 on error). The
// print path never calls it, but any stdin program (std.io.stdin → `read(STDIN, buf, 1)`) did before this
// → ReferenceError. Node's only synchronous stdin read is fs.readSync; on a pipe/file it blocks until data
// or EOF (the C contract). LIMITATION: a live TTY fd 0 can raise EAGAIN with no data ready; we retry (a
// blocking emulation), which busy-waits — fine for the piped-filter use case, not for interactive TTYs.
const fs = require("fs");
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
