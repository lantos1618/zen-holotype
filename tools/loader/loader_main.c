/* C entry for the std.resolve loader driver. zenc emits tools/loader/loader_driver.zen (+ its whole
 * transitive std closure, flattened by the bootstrap step) into loader_body.c (found via -I); this TU
 * prepends the C stdint/stdbool types the emitted code uses and the libc-string head that std.string's
 * `cstr`/`str` lowering expects, then calls resolve_to(argv[1]=in, argv[2]=out, argv[3]=root).
 *
 *   loader <in.zen> <out_flat.zen> <root>
 *
 * Prints the byte count written and returns 0 on success. Pure libc — the loader's std closure (resolve
 * + io + string + str + mem + lex + alloc) is all Zen, compiled into loader_body.c. No zenrt.c. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>

/* std.io names its lseek `whence` constants SEEK_SET / SEEK_END (the POSIX names) and emits them as
 * `static int32_t SEEK_SET = 0;` — but <stdio.h> already #defines those as object-like macros, so the
 * emitted definition would expand to `static int32_t 0 = 0;`. Undefine the macros before the body so the
 * Zen constants stand. (Their values match the POSIX ones, so nothing changes semantically.) */
#undef SEEK_SET
#undef SEEK_END

/* The emitted Zen uses `str` == `const char*` and the builtins slice/cstr/load/offset/store. The
 * flattened body defines everything else (String, resolve_program, …). */
int64_t resolve_to(const char* in_path, const char* out_path, const char* root);

#include "loader_body.c"

int main(int argc, char** argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: %s <in.zen> <out_flat.zen> <root>\n", argv[0]);
        return 2;
    }
    int64_t n = resolve_to(argv[1], argv[2], argv[3]);
    fprintf(stderr, "loader: wrote %lld bytes to %s\n", (long long)n, argv[2]);
    return n > 0 ? 0 : 1;
}
