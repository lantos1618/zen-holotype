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
/* mirror std.text.str.starts_with / ends_with (prefix/suffix byte tests over a str). */
ZWEAK bool starts_with(const char* s, const char* prefix){ size_t pl = strlen(prefix); return strlen(s) >= pl && memcmp(s, prefix, pl) == 0; }
ZWEAK bool ends_with(const char* s, const char* suffix){ size_t sl = strlen(s), fl = strlen(suffix); return sl >= fl && memcmp(s + (sl - fl), suffix, fl) == 0; }
ZWEAK zslice bytes(String s){ zslice z; z.ptr = s.ptr; z.len = s.len; return z; }
ZWEAK void* heap(int64_t n){ return malloc(n); }
/* mirror the Zen bodies exactly:
 *   std.mem.raw.alloc(n)       = malloc(n)                                 (uninitialised n bytes)
 *   std.text.str.view(s)        = slice(s, strlen(s))                       ([u8] view over a str's bytes) */
ZWEAK uint8_t* alloc(int64_t n){ return (uint8_t*)malloc(n); }
ZWEAK zslice view(const char* s){ zslice z; z.ptr = (void*)s; z.len = (int64_t)strlen(s); return z; }

/* OS entry: the real main lives here, stashes argc/argv into globals that std.os reads, then calls
 * the Zen entry (emitted as `zen_main`). WEAK so that during the driver->Zen migration the zenc binary
 * — which still links bootstrap/driver.c and its own strong main — overrides this one (the weak body,
 * with its zen_main reference, is dropped at link). User programs (compiled with just <prog>.c +
 * zenrt.c, no driver.c) get this entry, which calls the program's own zen_main. */
int32_t __zen_argc = 0;
char**  __zen_argv = 0;
/* std.os reads argv through these (never touches the globals directly). Bounds-checked so an out-of-
 * range index is an empty string, not a crash. */
int32_t zen_argc(void){ return __zen_argc; }
const char* zen_argv_at(int32_t i){ return (i >= 0 && i < __zen_argc) ? __zen_argv[i] : ""; }
/* Weak stub so the zenc binary (whose weak main below is overridden by driver.c and never runs) still
 * links — a user program emits its own strong zen_main, which overrides this. */
ZWEAK int32_t zen_main(void){ return 0; }
ZWEAK int main(int argc, char** argv){
    __zen_argc = (int32_t)argc;
    __zen_argv = argv;
    return (int)zen_main();
}
