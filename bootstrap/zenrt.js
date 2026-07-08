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
  const jstr = (p) => decode(p, strlen(p));  // a Zen `str` (MEM offset) -> a real JS string, for DOM/API boundaries

  const load = (p) => MEM[p];
  const store = (p, b) => { MEM[p] = b & 255; return b & 255; };
  const offset = (p, n) => p + Number(n);
  const load_i64 = (p) => Number(dv.getBigInt64(p, true));
  const store_i64 = (p, v) => { dv.setBigInt64(p, BigInt(v), true); return v; };
  const slice = (ptr, len) => ({ ptr, len: Number(len) });
  const view = (s) => ({ ptr: s, len: strlen(s) });    // a str's byte view (matches std.text.str.view)
  // element read/write over a fat pointer, dispatching on how `.ptr` is backed: a SliceLit `[a,b,c]`
  // carries a JS ARRAY (index it directly), while a str/byte view carries a MEM OFFSET (an integer —
  // read the byte out of linear memory). Without this split, `sv.ptr[i]` on a byte view indexes an
  // integer and yields `undefined`, which silently broke every byte-scan (e.g. format's `{}` finder).
  const idx = (seq, i) => { const p = seq.ptr; return Array.isArray(p) ? p[i] : MEM[p + Number(i)]; };
  const setidx = (seq, i, v) => { const p = seq.ptr; if (Array.isArray(p)) { p[i] = v; } else { MEM[p + Number(i)] = v & 255; } return v; };
  const eq = (a, b) => a === b || decode(a, strlen(a)) === decode(b, strlen(b));
  const nn = (p) => { if (p === 0) panic("zen: panic: null pointer deref\n"); return p; };
  const addr = (x) => x;               // JS objects are references; scalar aliasing is DEFERRED (boxed refs)
  const i32 = (x) => typeof x === "bigint" ? Number(BigInt.asIntN(32, x)) : x | 0;
  const i64 = (x) => typeof x === "bigint" ? Number(BigInt.asIntN(64, x)) : Math.trunc(x);
  const sizeof = (_name) => 8;         // element sizes unused on the print path; DEFERRED for typed slices
  // u64 reinterpretation: a JS `number` can't hold the top of the u64 range (values >= 2^63 wrapped to
  // a NEGATIVE i64 in the AST, and anything > 2^53 loses precision), so reinterpret the 64-bit pattern
  // as UNSIGNED and promote to BigInt only when it no longer fits exactly in a `number`. Small u64s stay
  // `number` (so ordinary arithmetic with number literals keeps working); huge ones become BigInt so
  // they print exactly. u64 values enter through the type-driven param normalization genjs emits.
  const U64_SAFE = 9007199254740991n;  // 2^53 - 1
  const u64 = (x) => { const b = BigInt.asUintN(64, typeof x === "bigint" ? x : BigInt(Math.trunc(x))); return b <= U64_SAFE ? Number(b) : b; };
  // div/mod stay integer-guarded (div-by-zero panics), but tolerate a BigInt operand (a wide u64): the
  // BigInt path never truncates or guards floats — float `/` is emitted natively by genjs, not here.
  const div = (a, b) => { if (typeof a === "bigint" || typeof b === "bigint") { const bb = BigInt(b); if (bb === 0n) panic("zen: panic: integer divide by zero\n"); return u64(BigInt(a) / bb); } if (b === 0) panic("zen: panic: integer divide by zero\n"); return Math.trunc(a / b); };
  const mod = (a, b) => { if (typeof a === "bigint" || typeof b === "bigint") { const bb = BigInt(b); if (bb === 0n) panic("zen: panic: integer modulo by zero\n"); return u64(BigInt(a) % bb); } if (b === 0) panic("zen: panic: integer modulo by zero\n"); return a % b; };
  const panic = (m) => { const s = typeof m === "number" ? decode(m, strlen(m)) : String(m); process.stderr.write(s); throw new Error("zen panic"); };

  // fd 1 = stdout, 2 = stderr; ptr is a MEM offset (or, for a JS-array slice, ignored).
  const write = (fd, ptr, len) => {
    const s = decode(ptr, len);
    (fd === 2 ? process.stderr : process.stdout).write(s);
    return Number(len);
  };

  return { MEM, str, strlen, decode, jstr, malloc, load, store, offset, load_i64, store_i64,
           slice, view, idx, setidx, eq, nn, addr, i32, i64, u64, sizeof, div, mod, panic, write };
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
