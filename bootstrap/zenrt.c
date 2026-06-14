#include "zenrt.h"
#include <stdlib.h>
#include <string.h>
/* U1.3: the runtime primitives below are also defined in Zen by resolvable std modules.
 * Built programs emit their own strong definitions when they import those modules; these weak
 * fallbacks keep the bootstrap compiler and import-free programs linkable. String allocation is
 * intentionally not provided here; String builders must go through an explicit allocator. */
#define ZWEAK __attribute__((weak))
ZWEAK bool eq(const char* a, const char* b){ return strcmp(a, b) == 0; }
ZWEAK bool is_empty(const char* s){ return s[0] == 0; }
ZWEAK zslice bytes(String s){ zslice z; z.ptr = s.ptr; z.len = s.len; return z; }
ZWEAK void* heap(int64_t n){ return malloc(n); }
/* mirror the Zen bodies exactly:
 *   std.mem.raw.alloc(n)       = malloc(n)                                 (uninitialised n bytes)
 *   std.text.str.view(s)        = slice(s, strlen(s))                       ([u8] view over a str's bytes) */
ZWEAK uint8_t* alloc(int64_t n){ return (uint8_t*)malloc(n); }
ZWEAK zslice view(const char* s){ zslice z; z.ptr = (void*)s; z.len = (int64_t)strlen(s); return z; }
