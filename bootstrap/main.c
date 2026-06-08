#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
String genModule(zslice decls);
int32_t check_module(Malloc* a, zslice decls);       /* U1.2: error count over resolved decls */
int32_t check_module_kind(Malloc* a, zslice decls);  /* U1.2: first-error KIND (0 = ok, 1..13) */

/* ── normal mode: read one flat .zen (argv[1] or stdin), emit C to stdout ──────────────────────── */
static char* read_all(FILE* in, size_t* out_len){
    size_t cap = 1<<20, len = 0; char* buf = malloc(cap);
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = realloc(buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    if (out_len) *out_len = len;
    return buf;
}

static int compile_stdin_or_file(int argc, char** argv){
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "zenc: cannot open %s\n", argv[1]); return 1; } }
    char* buf = read_all(in, NULL);
    Malloc m = { 0 };
    String out = genModule(resolve_module(&m, parse_module(&m, buf)));
    fwrite(out.ptr, 1, out.len, stdout);
    return 0;
}

/* ── --build-self mode: Python-free regeneration of bootstrap/zenc.gen.c ─────────────────────────
 *
 * This reproduces, in C driver glue, exactly what bootstrap/generate.py.compiler_source() builds:
 *   compiler_source() = "\n".join(strip_imports(p) for p in SOURCES)
 *   strip_imports(p)  = "\n".join(l for l in TEXT.splitlines()
 *                                 if not (l.strip().startswith("{ ") and "= std." in l))
 * then feeds that flat source through the SAME parse_module->resolve_module->genModule path the
 * normal mode uses, and writes the emitted C to <out.c>. ZERO Python participates.
 *
 * The SOURCES list + order are HARDCODED below, identical to bootstrap/generate.py's SOURCES (paths
 * relative to the <srcroot> argument). check_validate.zen / alloc / io are intentionally NOT here —
 * the bootstrap binary only emits C; it does not type-check.
 */
static const char* const SOURCES[] = {
    "zen/std/genc.zen", "zen/std/genc_mono.zen", "zen/std/genc_emit.zen",
    "zen/std/lex.zen", "zen/std/parse_expr.zen", "zen/std/parse_type.zen",
    "zen/std/parse_stmt.zen", "zen/std/parse.zen", "zen/std/check.zen",
    /* U1.2: check_validate.zen is now compiled INTO the binary so `zenc build`/`check` can TYPE-CHECK
     * (check_module / check_module_kind). It depends only on genc/check/lex (above) + zenrt's
     * Malloc/eq/is_empty/malloc (its imports are stripped like every SOURCE), and shares zero top-level
     * names with the others. The emit-only path (compile_stdin_or_file) and --build-self do not call it. */
    "zen/std/check_validate.zen",
};
static const int N_SOURCES = (int)(sizeof(SOURCES) / sizeof(SOURCES[0]));

/* read an entire file into a malloc'd, NUL-terminated buffer; returns NULL (and prints) on error. */
static char* slurp(const char* path, size_t* out_len){
    FILE* f = fopen(path, "rb");
    if (!f){ fprintf(stderr, "zenc: cannot open %s\n", path); return NULL; }
    char* buf = read_all(f, out_len);
    fclose(f);
    return buf;
}

/* Python str.strip() whitespace set (ASCII): space, \t, \n, \r, \v, \f. */
static int py_isspace(unsigned char c){
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f';
}

/* the strip_imports predicate, applied to ONE physical line [p, e) of `src` (e is the index of the
 * line's '\n' or the terminating NUL). Returns 1 iff the line is an `{ … } = std.…` import to drop:
 *   l.strip().startswith("{ ")  AND  "= std." in l   (the membership test is over the WHOLE line). */
static int is_import_line(const char* src, size_t p, size_t e){
    /* l.strip(): advance over leading py-whitespace, then test startswith("{ "). */
    size_t s = p;
    while (s < e && py_isspace((unsigned char)src[s])) s++;
    if (!(s + 1 < e && src[s] == '{' && src[s+1] == ' ')) return 0;
    /* "= std." in l: substring search within [p, e). */
    static const char NEEDLE[] = "= std.";
    size_t nlen = sizeof(NEEDLE) - 1;
    if (e < p || e - p < nlen) return 0;
    for (size_t i = p; i + nlen <= e; i++){
        if (memcmp(src + i, NEEDLE, nlen) == 0) return 1;
    }
    return 0;
}

/* Build the flat compiler source: for each SOURCE (in order), append `\n` as a file separator iff
 * this is not the first file, then append that file's body with import lines dropped. Lines are split
 * on '\n' (Python splitlines: a trailing '\n' yields no extra empty line) and rejoined with '\n'. */
static String build_self_source(const char* srcroot){
    String out = new();
    size_t rootlen = strlen(srcroot);
    int need_trailing_slash = (rootlen > 0 && srcroot[rootlen-1] != '/');
    for (int fi = 0; fi < N_SOURCES; fi++){
        /* join the absolute path: <srcroot>[/]<SOURCES[fi]>. */
        const char* rel = SOURCES[fi];
        size_t plen = rootlen + (need_trailing_slash ? 1 : 0) + strlen(rel) + 1;
        char* path = malloc(plen);
        memcpy(path, srcroot, rootlen);
        size_t pos = rootlen;
        if (need_trailing_slash) path[pos++] = '/';
        memcpy(path + pos, rel, strlen(rel) + 1);

        size_t len = 0;
        char* src = slurp(path, &len);
        free(path);
        if (!src){ out.ptr = NULL; return out; }  /* signal error to caller via NULL ptr */

        if (fi > 0) out = push(out, '\n');  /* "\n".join across files */

        /* scan physical lines; emit each kept line, '\n'-separated within this file. */
        int first_kept = 1;
        size_t p = 0;
        while (p < len){
            size_t e = p;
            while (e < len && src[e] != '\n') e++;   /* [p, e) is the line body (no terminator) */
            if (!is_import_line(src, p, e)){
                if (!first_kept) out = push(out, '\n');  /* "\n".join within file */
                first_kept = 0;
                for (size_t i = p; i < e; i++) out = push(out, (uint8_t)src[i]);
            }
            if (e >= len) break;  /* no terminator -> last line (splitlines drops trailing) */
            p = e + 1;            /* skip the '\n'; if it was the final byte, loop ends (p==len) */
        }
        free(src);
    }
    return out;
}

/* genModule emits this zslice typedef at the head of every module; bootstrap/zenc.gen.c provides it
 * via zenrt.h instead, so we swap the head for the include (== generate.py.gen_c_file()). */
static const char HEAD[] = "typedef struct { void* ptr; int64_t len; } zslice; ";
static const char HEAD_REPL[] = "#include \"zenrt.h\"\n";

static int build_self(const char* out_path, const char* srcroot){
    String src = build_self_source(srcroot);
    if (src.ptr == NULL){ return 1; }  /* a source file could not be read */
    const char* flat = finish(src);    /* NUL-terminate the flat source for the parser */
    Malloc m = { 0 };
    String out = genModule(resolve_module(&m, parse_module(&m, flat)));

    size_t hlen = sizeof(HEAD) - 1;
    if ((size_t)out.len < hlen || memcmp(out.ptr, HEAD, hlen) != 0){
        fprintf(stderr, "zenc: --build-self: emitted C did not start with the expected head\n");
        return 1;
    }
    FILE* f = fopen(out_path, "wb");
    if (!f){ fprintf(stderr, "zenc: cannot write %s\n", out_path); return 1; }
    /* write gen_c_file(out): replace the leading HEAD typedef with the zenrt.h include. */
    fwrite(HEAD_REPL, 1, sizeof(HEAD_REPL) - 1, f);
    fwrite((const char*)out.ptr + hlen, 1, out.len - hlen, f);
    fclose(f);
    return 0;
}

/* ── build/run mode (Goal U / U1 Step 1): compile a .zen to a runnable native binary ───────────────
 * Emits the program's C (genModule), swaps the leading HEAD typedef for #include "zenrt.h" (== the
 * gen_c_file form), writes it to a temp .c, and links it with bootstrap/zenrt.c into `-o <out>` via cc.
 * A Zen `main = () i32 { … }` emits as C `int32_t main()` — the program's entry, no separate runner.
 * NOTE: the binary does NOT yet resolve `{ } = std.X` imports (U1 Step 3), so the program must be
 * self-contained for now. zenrt.{c,h} are found relative to the zenc binary: <dir(argv0)>/bootstrap. */

/* directory of argv[0]: everything up to the last '/', or "." if none. zenc lives at <root>/zenc, so
 * this is <root>, and <root>/bootstrap holds zenrt.{c,h}. */
static void bin_dir(const char* argv0, char* out, size_t n){
    const char* slash = strrchr(argv0, '/');
    if (!slash){ snprintf(out, n, "."); return; }
    size_t len = (size_t)(slash - argv0);
    if (len >= n) len = n - 1;
    memcpy(out, argv0, len); out[len] = 0;
}

/* the 13 validator error KINDs (check_module_kind's 1..13 return) → human-readable names. */
static const char* const KIND_NAME[] = {
    "ok", "arity", "arg-type", "undefined-name", "struct-field", "exhaustiveness",
    "dup-variant", "operand-type", "index", "return-fit", "assign-fit",
    "conformance", "dup-fn", "value-pos-return",
};

/* U1.2: type-check resolved decls. Prints a Zen-LEVEL error (a count + the first error's KIND) to stderr
 * and returns the error count (0 = ok) — so a user finally sees `zenc: foo.zen: 1 error (undefined-name)`
 * instead of cc errors on generated C they never wrote. (Real line:col + messages are U1 Step 4.) */
static int type_check(Malloc* m, zslice decls, const char* in_path){
    int kind = check_module_kind(m, decls);
    if (kind == 0) return 0;
    int count = check_module(m, decls);
    if (count < 1) count = 1;
    const char* kn = (kind >= 1 && kind <= 13) ? KIND_NAME[kind] : "error";
    fprintf(stderr, "zenc: %s: %d error%s (first: %s)\n", in_path, count, count == 1 ? "" : "s", kn);
    return count;
}

static int build_program(const char* argv0, const char* in_path, const char* out_path, int run){
    size_t len = 0;
    char* buf = slurp(in_path, &len);
    if (!buf) return 1;
    Malloc m = { 0 };
    zslice decls = resolve_module(&m, parse_module(&m, buf));
    if (type_check(&m, decls, in_path) != 0){ free(buf); return 1; }  /* U1.2: don't build an ill-typed program */
    String out = genModule(decls);
    free(buf);

    size_t hlen = sizeof(HEAD) - 1;
    if ((size_t)out.len < hlen || memcmp(out.ptr, HEAD, hlen) != 0){
        fprintf(stderr, "zenc: emitted C did not start with the expected head\n");
        return 1;
    }
    /* wrapped C to a temp file: #include "zenrt.h" + the emitted body (HEAD stripped). */
    char cpath[256];
    snprintf(cpath, sizeof cpath, "/tmp/zenc_build_%d.c", (int)getpid());
    FILE* f = fopen(cpath, "wb");
    if (!f){ fprintf(stderr, "zenc: cannot write %s\n", cpath); return 1; }
    fwrite(HEAD_REPL, 1, sizeof(HEAD_REPL) - 1, f);
    fwrite((const char*)out.ptr + hlen, 1, out.len - hlen, f);
    fclose(f);

    char dir[4096]; bin_dir(argv0, dir, sizeof dir);
    char binpath[256];
    if (run){ snprintf(binpath, sizeof binpath, "/tmp/zenc_run_%d", (int)getpid()); out_path = binpath; }

    char cmd[8192];
    snprintf(cmd, sizeof cmd, "cc -std=gnu11 -w -I%s/bootstrap %s %s/bootstrap/zenrt.c -o %s",
             dir, cpath, dir, out_path);
    int rc = system(cmd);
    unlink(cpath);
    if (rc != 0){ fprintf(stderr, "zenc: cc failed to link %s\n", in_path); return 1; }
    if (run){
        int prc = system(out_path);
        unlink(out_path);
        return (prc >= 0 && WIFEXITED(prc)) ? WEXITSTATUS(prc) : 1;
    }
    return 0;
}

int main(int argc, char** argv){
    if (argc >= 2 && strcmp(argv[1], "--build-self") == 0){
        if (argc < 4){ fprintf(stderr, "usage: %s --build-self <out.c> <srcroot>\n", argv[0]); return 2; }
        return build_self(argv[2], argv[3]);
    }
    if (argc >= 2 && strcmp(argv[1], "build") == 0){
        const char* in = NULL; const char* out = "a.out";
        for (int i = 2; i < argc; i++){
            if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) out = argv[++i];
            else in = argv[i];
        }
        if (!in){ fprintf(stderr, "usage: %s build <in.zen> [-o out]\n", argv[0]); return 2; }
        return build_program(argv[0], in, out, 0);
    }
    if (argc >= 2 && strcmp(argv[1], "run") == 0){
        if (argc < 3){ fprintf(stderr, "usage: %s run <in.zen>\n", argv[0]); return 2; }
        return build_program(argv[0], argv[2], NULL, 1);
    }
    if (argc >= 2 && strcmp(argv[1], "check") == 0){  /* U1.2: type-check only, no build */
        if (argc < 3){ fprintf(stderr, "usage: %s check <in.zen>\n", argv[0]); return 2; }
        char* buf = slurp(argv[2], NULL);
        if (!buf) return 1;
        Malloc m = { 0 };
        zslice decls = resolve_module(&m, parse_module(&m, buf));
        free(buf);
        int n = type_check(&m, decls, argv[2]);
        if (n == 0) fprintf(stderr, "zenc: %s: ok\n", argv[2]);
        return n == 0 ? 0 : 1;
    }
    return compile_stdin_or_file(argc, argv);
}
