#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef struct { void* ptr; int64_t len; } zslice;
typedef struct { uint8_t* ptr; int64_t len; int64_t cap; } String;
typedef struct { int32_t _; } Malloc;
String new(void);
String push(String s, uint8_t b);
String append(String s, const char* t);
zslice bytes(String s);
const char* finish(String s);
bool eq(const char* a, const char* b);
bool is_empty(const char* s);
void* heap(int64_t n);
