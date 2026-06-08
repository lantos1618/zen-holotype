#include "zenrt.h"
#include <stdlib.h>
#include <string.h>
/* U1.3: the runtime primitives below are ALSO defined in Zen by resolvable std modules
 * (std.string's new/push/append/bytes/finish/with_cap, std.str's eq/is_empty/view, std.mem's
 * alloc). When `zenc build/run` RESOLVES a program that imports those modules, the program's
 * emitted C carries its OWN (strong) definitions — so zenrt.c's copies are WEAK fallbacks: the
 * program's win when present, and zenrt.c supplies them otherwise (incl. for the compiler binary
 * itself, whose gen.c strips std imports and thus defines none of these). `heap` stays weak too
 * for symmetry though no std module emits it. `reserve` is file-local (static), never resolved. */
#define ZWEAK __attribute__((weak))
ZWEAK String new(void){ String s; s.ptr = malloc(16); s.len = 0; s.cap = 16; return s; }
static String reserve(String s, int64_t need){
    if (s.len + need > s.cap){ int64_t nc = (s.cap + need) * 2; s.ptr = realloc(s.ptr, nc); s.cap = nc; }
    return s;
}
ZWEAK String push(String s, uint8_t b){ String r = reserve(s, 1); r.ptr[r.len] = b; r.len += 1; return r; }
ZWEAK String append(String s, const char* t){ int64_t n = strlen(t); String r = reserve(s, n); memcpy(r.ptr + r.len, t, n); r.len += n; return r; }
ZWEAK zslice bytes(String s){ zslice z; z.ptr = s.ptr; z.len = s.len; return z; }
ZWEAK const char* finish(String s){ String r = push(s, 0); return (const char*)r.ptr; }   // NUL-terminate -> str
ZWEAK bool eq(const char* a, const char* b){ return strcmp(a, b) == 0; }
ZWEAK bool is_empty(const char* s){ return s[0] == 0; }
ZWEAK void* heap(int64_t n){ return malloc(n); }
/* mirror the Zen bodies exactly:
 *   std.mem.alloc(n)       = malloc(n)                                 (uninitialised n bytes)
 *   std.str.view(s)        = slice(s, strlen(s))                       ([u8] view over a str's bytes)
 *   std.string.with_cap(c) = String( ptr: alloc(c), len: 0, cap: c )  (an empty String with cap c) */
ZWEAK uint8_t* alloc(int64_t n){ return (uint8_t*)malloc(n); }
ZWEAK zslice view(const char* s){ zslice z; z.ptr = (void*)s; z.len = (int64_t)strlen(s); return z; }
ZWEAK String with_cap(int64_t cap){ String s; s.ptr = (uint8_t*)malloc(cap); s.len = 0; s.cap = cap; return s; }
