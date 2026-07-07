// zenrt.js — the JavaScript runtime floor for the genjs backend. The JS analog of bootstrap/zenrt.c:
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

  const load = (p) => MEM[p];
  const store = (p, b) => { MEM[p] = b & 255; return b & 255; };
  const offset = (p, n) => p + Number(n);
  const load_i64 = (p) => Number(dv.getBigInt64(p, true));
  const store_i64 = (p, v) => { dv.setBigInt64(p, BigInt(v), true); return v; };
  const slice = (ptr, len) => ({ ptr, len: Number(len) });
  const view = (s) => ({ ptr: s, len: strlen(s) });    // a str's byte view (matches std.text.str.view)
  const eq = (a, b) => a === b || decode(a, strlen(a)) === decode(b, strlen(b));
  const nn = (p) => { if (p === 0) panic("zen: panic: null pointer deref\n"); return p; };
  const addr = (x) => x;               // JS objects are references; scalar aliasing is DEFERRED (boxed refs)
  const i32 = (x) => x | 0;
  const i64 = (x) => Math.trunc(x);
  const sizeof = (_name) => 8;         // element sizes unused on the print path; DEFERRED for typed slices
  const div = (a, b) => { if (b === 0) panic("zen: panic: integer divide by zero\n"); return Math.trunc(a / b); };
  const mod = (a, b) => { if (b === 0) panic("zen: panic: integer modulo by zero\n"); return a % b; };
  const panic = (m) => { const s = typeof m === "number" ? decode(m, strlen(m)) : String(m); process.stderr.write(s); throw new Error("zen panic"); };

  // fd 1 = stdout, 2 = stderr; ptr is a MEM offset (or, for a JS-array slice, ignored).
  const write = (fd, ptr, len) => {
    const s = decode(ptr, len);
    (fd === 2 ? process.stderr : process.stdout).write(s);
    return Number(len);
  };

  return { MEM, str, strlen, decode, malloc, load, store, offset, load_i64, store_i64,
           slice, view, eq, nn, addr, i32, i64, sizeof, div, mod, panic, write };
})();

// ── libc leaves referenced by name from emitted code. The print path needs only write/strlen; the
//    rest are stubs so dead closure code (file I/O, threads) stays loadable. DEFERRED: real impls. ──
const write = (fd, ptr, len) => __zr.write(fd, ptr, len);
const strlen = (p) => __zr.strlen(p);
const malloc = (n) => __zr.malloc(n);
const memcpy = (dst, src, n) => { for (let i = 0; i < Number(n); i++) __zr.MEM[dst + i] = __zr.MEM[src + i]; return dst; };
const realloc = (p, n) => { const q = __zr.malloc(n); return q; };
const free = (_p) => {};
const abort = () => { throw new Error("abort"); };
