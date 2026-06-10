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
int32_t check_module_kind(Malloc* a, zslice decls);  /* U1.2: first-error KIND, U1.4: packed kind + pos*16 (0 = ok) */
/* U1.3: the Zen module loader (zen/std/resolve.zen, now a SOURCE). Given the project root (the dir that
 * contains zen/std/ and zen/compiler/), the PROGRAM's own directory (for sibling `{ f } = b` imports;
 * "" when the source has no file), the input path (error-message prefix) + the program source, returns
 * the flat single-module source with the transitive import closure spliced in (per-module + per-name
 * dedup; N2b qualified `c.x` too). build/run/check call it BEFORE parse_module so a program that
 * imports the stdlib or a sibling file resolves from disk. ERROR CHANNEL: a loader error (unknown
 * module / unknown imported name / sibling duplicate / sibling-from-stdin) prints one
 * `zenc: <file>: error: …` line to stderr and exits 1 inside the loader — it never returns. */
const char* resolve_program(Malloc* a, const char* root, const char* progdir, const char* inpath, const char* src);
/* the first sibling-module name `src` imports ("" if none) — the stdin-mode guard below. */
const char* first_user_import(const char* src);

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
    /* piped stdin has no directory: a sibling import `{ f } = b` cannot resolve, so error cleanly
     * instead of emitting C that references names no one defines (std imports stay as-is — the raw
     * filter mode never resolved them either, and the oracle depends on that). */
    if (in == stdin){
        const char* sib = first_user_import(buf);
        if (sib && sib[0]){
            fprintf(stderr, "zenc: <stdin>: error: sibling import '%s' needs a source file on disk "
                            "(stdin has no directory); use `zenc build <file.zen>`\n", sib);
            return 1;
        }
    }
    Malloc m = { 0 };
    String out = genModule(resolve_module(&m, parse_module(&m, buf)));
    fwrite(out.ptr, 1, out.len, stdout);
    return 0;
}

/* ── --build-self mode: Python-free regeneration of bootstrap/zenc.gen.c ─────────────────────────
 *
 * This reproduces, in C driver glue, the flat compiler source shape used for the committed seed:
 *   compiler_source() = "\n".join(strip_imports(p) for p in bootstrap/sources.txt)
 *   strip_imports(p)  = "\n".join(l for l in TEXT.splitlines()
 *                                 if not (l.strip().startswith("{ ")
 *                                         and ("= std." in l or "= compiler." in l)))
 * then feeds that flat source through the SAME parse_module->resolve_module->genModule path the
 * normal mode uses, and writes the emitted C to <out.c>. ZERO Python participates.
 *
 * The source list lives in bootstrap/sources.txt (paths relative to the <srcroot> argument).
 * alloc is intentionally NOT there — the bootstrap binary links runtime primitives from zenrt
 * rather than compiling the std allocator module into the seed.
 */
static const char SOURCE_MANIFEST[] = "bootstrap/sources.txt";

/* read an entire file into a malloc'd, NUL-terminated buffer; returns NULL (and prints) on error. */
static char* slurp(const char* path, size_t* out_len){
    FILE* f = fopen(path, "rb");
    if (!f){ fprintf(stderr, "zenc: cannot open %s\n", path); return NULL; }
    char* buf = read_all(f, out_len);
    fclose(f);
    return buf;
}

static char* join_root_path(const char* root, const char* rel){
    size_t rootlen = strlen(root);
    int need_trailing_slash = (rootlen > 0 && root[rootlen-1] != '/');
    size_t plen = rootlen + (need_trailing_slash ? 1 : 0) + strlen(rel) + 1;
    char* path = malloc(plen);
    memcpy(path, root, rootlen);
    size_t pos = rootlen;
    if (need_trailing_slash) path[pos++] = '/';
    memcpy(path + pos, rel, strlen(rel) + 1);
    return path;
}

/* Python str.strip() whitespace set (ASCII): space, \t, \n, \r, \v, \f. */
static int py_isspace(unsigned char c){
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\v' || c == '\f';
}

/* the strip_imports predicate, applied to ONE physical line [p, e) of `src` (e is the index of the
 * line's '\n' or the terminating NUL). Returns 1 iff the line is an import to drop:
 *   l.strip().startswith("{ ")  AND  ("= std." in l OR "= compiler." in l)
 * (the membership test is over the WHOLE line). */
static int is_import_line(const char* src, size_t p, size_t e){
    /* l.strip(): advance over leading py-whitespace, then test startswith("{ "). */
    size_t s = p;
    while (s < e && py_isspace((unsigned char)src[s])) s++;
    if (!(s + 1 < e && src[s] == '{' && src[s+1] == ' ')) return 0;
    /* import marker in l: substring search within [p, e). */
    static const char STD_NEEDLE[] = "= std.";
    static const char COMPILER_NEEDLE[] = "= compiler.";
    size_t std_len = sizeof(STD_NEEDLE) - 1;
    size_t compiler_len = sizeof(COMPILER_NEEDLE) - 1;
    for (size_t i = p; i <= e; i++){
        if (i + std_len <= e && memcmp(src + i, STD_NEEDLE, std_len) == 0) return 1;
        if (i + compiler_len <= e && memcmp(src + i, COMPILER_NEEDLE, compiler_len) == 0) return 1;
    }
    return 0;
}

static int append_stripped_file(String* out, const char* path){
    size_t len = 0;
    char* src = slurp(path, &len);
    if (!src) return 1;

    /* scan physical lines; emit each kept line, '\n'-separated within this file. */
    int first_kept = 1;
    size_t p = 0;
    while (p < len){
        size_t e = p;
        while (e < len && src[e] != '\n') e++;   /* [p, e) is the line body (no terminator) */
        if (!is_import_line(src, p, e)){
            if (!first_kept) *out = push(*out, '\n');  /* "\n".join within file */
            first_kept = 0;
            for (size_t i = p; i < e; i++) *out = push(*out, (uint8_t)src[i]);
        }
        if (e >= len) break;  /* no terminator -> last line (splitlines drops trailing) */
        p = e + 1;            /* skip the '\n'; if it was the final byte, loop ends (p==len) */
    }
    free(src);
    return 0;
}

static int manifest_entry(const char* src, size_t p, size_t e, size_t* s_out, size_t* n_out){
    size_t s = p;
    while (s < e && py_isspace((unsigned char)src[s])) s++;
    size_t t = e;
    while (t > s && py_isspace((unsigned char)src[t-1])) t--;
    if (s == t || src[s] == '#') return 0;
    *s_out = s;
    *n_out = t - s;
    return 1;
}

/* Build the flat compiler source: for each path in bootstrap/sources.txt, append `\n` as a file
 * separator iff this is not the first file, then append that file's body with import lines dropped.
 * Lines are split on '\n' (Python splitlines: a trailing '\n' yields no extra empty line) and rejoined
 * with '\n'. */
static String build_self_source(const char* srcroot){
    String out = new();
    char* manifest_path = join_root_path(srcroot, SOURCE_MANIFEST);
    size_t manifest_len = 0;
    char* manifest = slurp(manifest_path, &manifest_len);
    free(manifest_path);
    if (!manifest){ out.ptr = NULL; return out; }

    int file_count = 0;
    size_t p = 0;
    while (p < manifest_len){
        size_t e = p;
        while (e < manifest_len && manifest[e] != '\n') e++;
        size_t s = 0, n = 0;
        if (manifest_entry(manifest, p, e, &s, &n)){
            char* rel = malloc(n + 1);
            memcpy(rel, manifest + s, n);
            rel[n] = 0;
            char* path = join_root_path(srcroot, rel);
            free(rel);
            if (file_count > 0) out = push(out, '\n');  /* "\n".join across files */
            if (append_stripped_file(&out, path) != 0){
                free(path);
                free(manifest);
                out.ptr = NULL;
                return out;
            }
            free(path);
            file_count++;
        }
        if (e >= manifest_len) break;
        p = e + 1;
    }
    free(manifest);
    if (file_count == 0){
        fprintf(stderr, "zenc: no sources listed in %s\n", SOURCE_MANIFEST);
        out.ptr = NULL;
    }
    return out;
}

/* genModule emits this zslice typedef at the head of every module; bootstrap/zenc.gen.c provides it
 * via zenrt.h instead, so we swap the head for the include. */
static const char HEAD[] = "typedef struct { void* ptr; int64_t len; } zslice; ";
static const char HEAD_REPL[] = "#include \"zenrt.h\"\n";
/* The build/run path uses this variant instead: a built program that imports std.string emits its OWN
 * String + builders (strong, they override zenrt.c's weak copies at link), so define ZEN_NO_STRING to
 * suppress zenrt.h's String and avoid the struct clash (#98). NOTE the compiler's own gen.c (build_self,
 * above) uses the plain HEAD_REPL — it relies on zenrt's String (its gen.c strips std imports, emits
 * none of its own). A built program that doesn't use String is unaffected (zenrt's String fns unreferenced). */
static const char HEAD_REPL_PROG[] = "#define ZEN_NO_STRING 1\n#define ZEN_NO_MALLOC 1\n#include \"zenrt.h\"\n";

static void trim_trailing_ws(String* s){
    while (s->len > 0 && py_isspace(((uint8_t*)s->ptr)[s->len - 1])) s->len--;
}

static int build_self(const char* out_path, const char* srcroot){
    String src = build_self_source(srcroot);
    if (src.ptr == NULL){ return 1; }  /* a source file could not be read */
    const char* flat = finish(src);    /* NUL-terminate the flat source for the parser */
    Malloc m = { 0 };
    String out = genModule(resolve_module(&m, parse_module(&m, flat)));
    trim_trailing_ws(&out);

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
 * zenrt.{c,h} are found relative to the zenc binary: <dir(argv0)>/bootstrap. */

/* the project ROOT: $ZEN_ROOT if set (a relocated/installed zenc points it at a checkout containing
 * zen/std + bootstrap/zenrt.{c,h}), else the directory of argv[0] (zenc lives at <root>/zenc). Without
 * this a copied binary failed with raw cc/loader errors (census #34). */
static void bin_dir(const char* argv0, char* out, size_t n){
    const char* env = getenv("ZEN_ROOT");
    if (env && env[0]){ snprintf(out, n, "%s", env); return; }
    const char* slash = strrchr(argv0, '/');
    if (!slash){ snprintf(out, n, "."); return; }
    size_t len = (size_t)(slash - argv0);
    if (len >= n) len = n - 1;
    memcpy(out, argv0, len); out[len] = 0;
}

/* the PROGRAM's directory (sibling `{ f } = b` imports resolve to <progdir>/b.zen): the bytes of
 * in_path before its last '/', "." if it has none, "/" if it IS the root. */
static void prog_dir(const char* in_path, char* out, size_t n){
    const char* slash = strrchr(in_path, '/');
    if (!slash){ snprintf(out, n, "."); return; }
    size_t len = (size_t)(slash - in_path);
    if (len == 0) len = 1;                      /* "/p.zen" -> "/" */
    if (len >= n) len = n - 1;
    memcpy(out, in_path, len); out[len] = 0;
}

/* the 13 validator error KINDs (check_module_kind's 1..13 return) → human-readable names. */
static const char* const KIND_NAME[] = {
    "ok", "arity", "arg-type", "undefined-name", "struct-field", "exhaustiveness",
    "dup-variant", "operand-type", "index", "return-fit", "assign-fit",
    "conformance", "dup-fn", "value-pos-return", "parse",
};
/* U1.4 Phase 1A: a human-readable MESSAGE per kind (index-aligned to KIND_NAME / the K* codes). The bare
 * kind name was developer shorthand; this is what an outsider reads. (Phase 1B will splice in the offending
 * name/types; Phase 2 the file:line:col.) */
static const char* const KIND_MSG[] = {
    "ok",
    "wrong number of arguments",
    "argument type does not fit the parameter",
    "undefined name",
    "unknown struct field",
    "non-exhaustive match (add the missing variants or a `_` arm)",
    "duplicate match variant",
    "operator applied to the wrong operand type",
    "invalid index",
    "returned value does not fit the declared return type",
    "assigned value does not fit the variable's type",
    "impl does not satisfy the trait",
    "duplicate top-level definition",
    "early `return` in a value-position match arm",
    "syntax error: unparseable top-level input",
};

/* U1.2: type-check resolved decls. Prints a Zen-LEVEL error (a count + the first error's KIND) to stderr
 * and returns the error count (0 = ok) — so a user finally sees `zenc: foo.zen: 1 error (first: undefined-name)`
 * instead of cc errors on generated C they never wrote. (Real line:col + messages are U1 Step 4.) */
/* U2: a runnable program must define `main`. genModule emits the entry as `int32_t main(` (proto + def)
 * — the exact token cc links against — so scan the emitted C for that 13-byte substring. (A fn named
 * `mainframe` emits `int32_t mainframe(`, which this does NOT match because of the trailing `(`.) */
static int emits_main(String out){
    static const char NEEDLE[] = "int32_t main(";
    size_t nlen = sizeof(NEEDLE) - 1;
    if ((size_t)out.len < nlen) return 0;
    for (size_t i = 0; i + nlen <= (size_t)out.len; i++)
        if (memcmp((const char*)out.ptr + i, NEEDLE, nlen) == 0) return 1;
    return 0;
}

/* U1.4 Phase 2: check_module_kind packs the first error's source BYTE OFFSET alongside its kind
 * (kind + pos*16; pos 0 = unknown/synthesized). The offset is into the import-FLATTENED source, not
 * the user's file — resolve_program strips import lines and can rewrite `ns.name` quals — so map back
 * by the error LINE's text: take the flat line holding pos, find that exact line in the user's buffer,
 * and report its 1-based line + the column within it. A no-import program is a pass-through (exact);
 * a rewritten line or an error inside an imported std module doesn't match and falls back to the
 * position-less format. */
static int user_line_of(const char* user, const char* ls, size_t llen){
    int line = 1;
    const char* p = user;
    for (;;){
        const char* e = strchr(p, '\n');
        size_t n = e ? (size_t)(e - p) : strlen(p);
        if (n == llen && memcmp(p, ls, llen) == 0) return line;
        if (!e) return 0;
        p = e + 1; line++;
    }
}
static int type_check(Malloc* m, zslice decls, const char* in_path, const char* flat, const char* user){
    int packed = check_module_kind(m, decls);
    if (packed == 0) return 0;
    int kind = packed & 15;
    long pos = packed >> 4;
    int count = check_module(m, decls);
    if (count < 1) count = 1;
    const char* msg = (kind >= 1 && kind <= 14) ? KIND_MSG[kind] : "type error";
    char where[64] = "";
    if (pos > 0 && flat && user && (size_t)pos < strlen(flat)){
        const char* ls = flat + pos; while (ls > flat && ls[-1] != '\n') ls--;
        const char* le = flat + pos; while (*le && *le != '\n') le++;
        int uline = user_line_of(user, ls, (size_t)(le - ls));
        if (uline > 0) snprintf(where, sizeof where, ":%d:%d", uline, (int)(flat + pos - ls) + 1);
    }
    if (count == 1)
        fprintf(stderr, "zenc: %s%s: error: %s\n", in_path, where, msg);
    else
        fprintf(stderr, "zenc: %s%s: error: %s (+%d more error%s)\n", in_path, where, msg, count - 1, count - 1 == 1 ? "" : "s");
    return count;
}

static int build_program(const char* argv0, const char* in_path, const char* out_path, int run){
    size_t len = 0;
    char* buf = slurp(in_path, &len);
    if (!buf) return 1;
    Malloc m = { 0 };
    /* U1.3: resolve `{ … } = std.X` / `compiler.X` / sibling `{ … } = b` imports from disk before
     * parsing, so a program that imports the stdlib or a neighboring file builds. root = dir of the
     * zenc binary (holds zen/std and zen/compiler); progdir = dir of the program (holds its siblings).
     * resolve_program returns the flat single-module source; on a program with no imports it is a pass-
     * through. The returned str is borrowed from the loader's arena — don't free it. */
    char dir[4096]; bin_dir(argv0, dir, sizeof dir);
    char pdir[4096]; prog_dir(in_path, pdir, sizeof pdir);
    const char* flat = resolve_program(&m, dir, pdir, in_path, buf);
    zslice decls = resolve_module(&m, parse_module(&m, flat));
    if (decls.len == 0){ fprintf(stderr, "zenc: %s: could not parse (no declarations)\n", in_path); free(buf); return 1; }  /* U2 */
    if (type_check(&m, decls, in_path, flat, buf) != 0){ free(buf); return 1; }  /* U1.2: don't build an ill-typed program */
    String out = genModule(decls);
    free(buf);
    if (!emits_main(out)){ fprintf(stderr, "zenc: %s: no `main` entry point (need `main = () i32 { … }`)\n", in_path); return 1; }  /* U2 */

    size_t hlen = sizeof(HEAD) - 1;
    if ((size_t)out.len < hlen || memcmp(out.ptr, HEAD, hlen) != 0){
        fprintf(stderr, "zenc: emitted C did not start with the expected head\n");
        return 1;
    }
    /* wrapped C to a temp file: ZEN_NO_STRING + #include "zenrt.h" + the emitted body (HEAD stripped). */
    char cpath[256];
    snprintf(cpath, sizeof cpath, "/tmp/zenc_build_%d.c", (int)getpid());
    FILE* f = fopen(cpath, "wb");
    if (!f){ fprintf(stderr, "zenc: cannot write %s\n", cpath); return 1; }
    fwrite(HEAD_REPL_PROG, 1, sizeof(HEAD_REPL_PROG) - 1, f);
    fwrite((const char*)out.ptr + hlen, 1, out.len - hlen, f);
    fclose(f);

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

static void usage(FILE* to){
    fprintf(to,
        "zenc — the Zen compiler (self-hosted)\n"
        "\n"
        "usage:\n"
        "  zenc run   <file.zen>            type-check, build and run (exit = the program's exit code)\n"
        "  zenc build <file.zen> [-o out]   type-check and link a native binary (default a.out)\n"
        "  zenc check <file.zen>            type-check only (libraries allowed: no main required)\n"
        "  zenc emit  <file.zen>            emit the generated C to stdout\n"
        "  zenc --version | --help\n"
        "\n"
        "ZEN_ROOT: a relocated zenc finds zen/std + bootstrap/ at $ZEN_ROOT (default: the binary's directory).\n");
}
int main(int argc, char** argv){
    if (argc >= 2 && (strcmp(argv[1], "--help") == 0 || strcmp(argv[1], "-h") == 0)){ usage(stdout); return 0; }
    if (argc >= 2 && strcmp(argv[1], "--version") == 0){ printf("zenc 0.1.0-dev (self-hosted; C backend)\n"); return 0; }
    /* bare `zenc` on a TTY prints usage; with PIPED stdin it stays the classic filter (read source on
     * stdin, emit C on stdout) — the oracle and scripts depend on that mode. */
    if (argc < 2 && isatty(0)){ usage(stderr); return 2; }
    if (argc >= 2 && strcmp(argv[1], "emit") == 0){
        if (argc < 3){ fprintf(stderr, "usage: %s emit <in.zen>\n", argv[0]); return 2; }
        char* shifted[2] = { argv[0], argv[2] };
        return compile_stdin_or_file(2, shifted);
    }
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
        /* U1.3: resolve std.X / sibling imports from disk before checking, same as build_program. */
        char dir[4096]; bin_dir(argv[0], dir, sizeof dir);
        char pdir[4096]; prog_dir(argv[2], pdir, sizeof pdir);
        const char* flat = resolve_program(&m, dir, pdir, argv[2], buf);
        zslice decls = resolve_module(&m, parse_module(&m, flat));
        /* U2: reject gross parse failure (zero decls). NOTE: a missing `main` is NOT enforced in `check`
         * — a library module (std.*) legitimately has no main; build/run enforce it instead. */
        if (decls.len == 0){ fprintf(stderr, "zenc: %s: could not parse (no declarations)\n", argv[2]); free(buf); return 1; }
        int n = type_check(&m, decls, argv[2], flat, buf);
        free(buf);
        if (n == 0) fprintf(stderr, "zenc: %s: ok\n", argv[2]);
        return n == 0 ? 0 : 1;
    }
    return compile_stdin_or_file(argc, argv);
}
