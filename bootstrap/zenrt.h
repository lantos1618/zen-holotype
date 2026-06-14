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

/* The compiler binary needs the `String` layout from here. A built program that imports
 * std.text.string emits its own `String` struct, so the build path defines ZEN_NO_STRING
 * before including this header to avoid the struct clash. Runtime builders are intentionally
 * not declared here; String allocation goes through explicit allocator APIs. */
#ifndef ZEN_NO_STRING
typedef struct { uint8_t* ptr; int64_t len; int64_t cap; } String;
zslice bytes(String s);
#endif
