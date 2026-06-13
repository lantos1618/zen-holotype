#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct { void* ptr; int64_t len; } zslice;
/* Like String below: a built program that imports std.mem.alloc emits its own `Malloc` (+ Allocator impls),
 * so the build path defines ZEN_NO_MALLOC to suppress zenrt's. The compiler binary (no macro) keeps it —
 * main.c's `Malloc m = {0}` + gen.c's `Malloc*` params need it, and gen.c emits none of its own (#98). */
#ifndef ZEN_NO_MALLOC
typedef struct { int32_t _; } Malloc;
#endif
bool eq(const char* a, const char* b);
bool is_empty(const char* s);
void* heap(int64_t n);
/* U1.3: loader primitives (mirror std.mem.raw.alloc / std.text.str.view). */
uint8_t* alloc(int64_t n);
zslice view(const char* s);

/* The `String` runtime type + builders. A `zenc build` PROGRAM that imports std.text.string emits its OWN
 * String struct + strong new/push/append/etc. (which override zenrt.c's weak copies at link), so the
 * build path defines ZEN_NO_STRING before including this header to suppress zenrt's String — otherwise
 * the program's `struct String {…}` would clash with the typedef here (task #98). The COMPILER binary
 * (main.c / zenc.gen.c / zenrt.c, compiled WITHOUT the macro) still gets String from here, since its
 * gen.c strips std imports and emits no String of its own. */
#ifndef ZEN_NO_STRING
typedef struct { uint8_t* ptr; int64_t len; int64_t cap; } String;
String new(void);
String push(String s, uint8_t b);
String append(String s, const char* t);
zslice bytes(String s);
const char* finish(String s);
String with_cap(int64_t cap);
#endif
