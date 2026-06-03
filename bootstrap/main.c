#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
String genModule(zslice decls);
int main(int argc, char** argv){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    FILE* in = (argc > 1) ? fopen(argv[1], "r") : stdin;
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    Malloc m = { 0 };
    String out = genModule(resolve_module(&m, parse_module(&m, buf)));
    fwrite(out.ptr, 1, out.len, stdout);
    return 0;
}
