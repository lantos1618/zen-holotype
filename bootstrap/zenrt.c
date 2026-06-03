#include "zenrt.h"
#include <stdlib.h>
#include <string.h>
String new(void){ String s; s.ptr = malloc(16); s.len = 0; s.cap = 16; return s; }
static String reserve(String s, int64_t need){
    if (s.len + need > s.cap){ int64_t nc = (s.cap + need) * 2; s.ptr = realloc(s.ptr, nc); s.cap = nc; }
    return s;
}
String push(String s, uint8_t b){ String r = reserve(s, 1); r.ptr[r.len] = b; r.len += 1; return r; }
String append(String s, const char* t){ int64_t n = strlen(t); String r = reserve(s, n); memcpy(r.ptr + r.len, t, n); r.len += n; return r; }
zslice bytes(String s){ zslice z; z.ptr = s.ptr; z.len = s.len; return z; }
const char* finish(String s){ String r = push(s, 0); return (const char*)r.ptr; }   // NUL-terminate -> str
bool eq(const char* a, const char* b){ return strcmp(a, b) == 0; }
bool is_empty(const char* s){ return s[0] == 0; }
void* heap(int64_t n){ return malloc(n); }
