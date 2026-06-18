#include "zenrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
zslice parse_module(Malloc* a, const char* src);
zslice resolve_module(Malloc* a, zslice decls);
String genModule(zslice decls);
String genModuleIn(Malloc* a, zslice decls);
uint8_t* acquire(Malloc* a, int64_t n);
uint8_t* resize(Malloc* a, uint8_t* p, int64_t n);
int32_t check_module(Malloc* a, zslice decls);       /* U1.2: error count over resolved decls */
int32_t check_module_kind(Malloc* a, zslice decls);  /* U1.2: first-error KIND, U1.4: packed kind + pos*16 (0 = ok) */
int32_t check_module_ownership(Malloc* a, zslice decls);
int32_t check_module_ownership_kind(Malloc* a, zslice decls);
typedef struct CheckDiagnostic {
    int32_t code;
    const char* kind;
    int32_t source_offset;
    int32_t span_width;
    int32_t count;
    const char* message;
    const char* hint;
} CheckDiagnostic;
CheckDiagnostic check_module_diagnostic(Malloc* a, zslice decls);
CheckDiagnostic check_module_ownership_diagnostic(Malloc* a, zslice decls);
CheckDiagnostic check_module_diagnostic_from_source(Malloc* a, zslice decls, const char* src);
CheckDiagnostic check_module_ownership_diagnostic_from_source(Malloc* a, zslice decls, const char* src);
CheckDiagnostic check_module_escape_diagnostic_from_source(Malloc* a, zslice decls, const char* src);  /* M5: a scope ptr that outlives its scope */
typedef struct ModuleGraph {
    zslice imports;
    zslice symbols;
} ModuleGraph;
typedef struct ModuleEntry {
    const char* id;
    const char* path;
    const char* source;
    ModuleGraph graph;
} ModuleEntry;
typedef struct ModuleTable {
    zslice modules;
} ModuleTable;
typedef struct ResolvedProgram {
    ModuleTable table;
    const char* flat;
    int64_t body_start;
    int64_t body_end;
} ResolvedProgram;
/* U1.3: the Zen module loader (zen/std/internal/resolve.zen, now a SOURCE). Given the project root (the dir that
 * contains zen/std/ and zen/compiler/), the PROGRAM's own directory (for sibling `{ f } = b` imports;
 * "" when the source has no file), the input path (error-message prefix) + the program source, returns
 * the flat single-module source with the transitive import closure spliced in (per-module + per-name
 * dedup; N2b qualified `c.x` too). build/run/check call it BEFORE parse_module so a program that
 * imports the stdlib or a sibling file resolves from disk. ERROR CHANNEL: a loader error (unknown
 * module / unknown imported name / sibling duplicate / sibling-from-stdin) prints one
 * `zenc: <file>: error: …` line to stderr and exits 1 inside the loader — it never returns. */
const char* resolve_program(Malloc* a, const char* root, const char* progdir, const char* inpath, const char* src);
ResolvedProgram resolve_program_data(Malloc* a, const char* root, const char* progdir, const char* inpath, const char* src);
/* the first sibling-module name `src` imports ("" if none) — the stdin-mode guard below. */
const char* first_user_import(const char* src);
/* compiler.diagnostic (zen/compiler/diagnostic.zen): map a check error's flat-source byte
 * offset back to the user file's line:col (exact, alias-`__`-removal, and `__`==`.`
 * inverses). Replaces the hand-rolled C mapping below. line==0 => not located. */
typedef struct { int32_t line; int32_t col; int32_t end_col; } DiagSpan;
DiagSpan diag_user_span(const char* flat, const char* user, int32_t offset, int32_t span_width);
/* compiler.diagnostic: zen.toml manifest value span (start<0 = absent) — parser lives in Zen. */
typedef struct { int32_t start; int32_t len; } MfSpan;
MfSpan manifest_value_span(const char* src, int32_t len, const char* key, int32_t p);
const char* render_diagnostic(Malloc* a, const char* in_path, const char* user, int32_t line, int32_t col, int32_t end_col, const char* kind, const char* message, const char* hint, int32_t count);

static void* driver_alloc(Malloc* a, size_t n){
    return acquire(a, (int64_t)n);
}

static void* driver_resize(Malloc* a, void* p, size_t n){
    return resize(a, (uint8_t*)p, (int64_t)n);
}

static void driver_release(Malloc* a, void* p){
    (void)a;
    if (p) free(p);
}

static String driver_string_new_in(Malloc* a){
    String s;
    s.ptr = driver_alloc(a, 16);
    s.len = 0;
    s.cap = 16;
    return s;
}

static String driver_string_reserve_in(Malloc* a, String s, int64_t need){
    if (s.len + need > s.cap){
        int64_t nc = (s.cap + need) * 2;
        s.ptr = resize(a, s.ptr, nc);
        s.cap = nc;
    }
    return s;
}

static String driver_string_push_in(Malloc* a, String s, uint8_t b){
    String r = driver_string_reserve_in(a, s, 1);
    r.ptr[r.len] = b;
    r.len += 1;
    return r;
}

static const char* driver_string_finish_in(Malloc* a, String s){
    String r = driver_string_push_in(a, s, 0);
    return (const char*)r.ptr;
}

/* ── normal mode: read one flat .zen (argv[1] or stdin), emit C to stdout ──────────────────────── */
static char* read_all(Malloc* a, FILE* in, size_t* out_len){
    size_t cap = 1<<20, len = 0; char* buf = driver_alloc(a, cap);
    int c; while ((c = fgetc(in)) != EOF){ if (len + 1 >= cap){ cap *= 2; buf = driver_resize(a, buf, cap); } buf[len++] = (char)c; }
    buf[len] = 0;
    if (out_len) *out_len = len;
    return buf;
}

static int compile_stdin_or_file(int argc, char** argv){
    Malloc m = { 0 };
    FILE* in = stdin;
    if (argc > 1){ in = fopen(argv[1], "r"); if (!in){ fprintf(stderr, "zenc: cannot open %s\n", argv[1]); return 1; } }
    char* buf = read_all(&m, in, NULL);
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
    String out = genModuleIn(&m, resolve_module(&m, parse_module(&m, buf)));
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
 * then feeds that flat source through the SAME parse_module->resolve_module->genModuleIn path the
 * normal mode uses, and writes the emitted C to <out.c>. ZERO Python participates.
 *
 * The source list lives in bootstrap/sources.txt (paths relative to the <srcroot> argument).
 * alloc is intentionally NOT there — the bootstrap binary links runtime primitives from zenrt
 * rather than compiling the std allocator module into the seed.
 */
static const char SOURCE_MANIFEST[] = "bootstrap/sources.txt";

/* read an entire file into a malloc'd, NUL-terminated buffer; returns NULL (and prints) on error. */
static char* slurp(Malloc* a, const char* path, size_t* out_len){
    FILE* f = fopen(path, "rb");
    if (!f){ fprintf(stderr, "zenc: cannot open %s\n", path); return NULL; }
    char* buf = read_all(a, f, out_len);
    fclose(f);
    return buf;
}

static char* join_root_path(Malloc* a, const char* root, const char* rel){
    size_t rootlen = strlen(root);
    int need_trailing_slash = (rootlen > 0 && root[rootlen-1] != '/');
    size_t plen = rootlen + (need_trailing_slash ? 1 : 0) + strlen(rel) + 1;
    char* path = driver_alloc(a, plen);
    memcpy(path, root, rootlen);
    size_t pos = rootlen;
    if (need_trailing_slash) path[pos++] = '/';
    memcpy(path + pos, rel, strlen(rel) + 1);
    return path;
}

static char* dup_cstr(Malloc* a, const char* s){
    size_t n = strlen(s) + 1;
    char* out = driver_alloc(a, n);
    memcpy(out, s, n);
    return out;
}

static char* dup_range(Malloc* a, const char* s, size_t p, size_t e){
    char* out = driver_alloc(a, e - p + 1);
    memcpy(out, s + p, e - p);
    out[e - p] = 0;
    return out;
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

static int append_stripped_file(Malloc* a, String* out, const char* path){
    size_t len = 0;
    char* src = slurp(a, path, &len);
    if (!src) return 1;

    /* scan physical lines; emit each kept line, '\n'-separated within this file. */
    int first_kept = 1;
    size_t p = 0;
    while (p < len){
        size_t e = p;
        while (e < len && src[e] != '\n') e++;   /* [p, e) is the line body (no terminator) */
        if (!is_import_line(src, p, e)){
            if (!first_kept) *out = driver_string_push_in(a, *out, '\n');  /* "\n".join within file */
            first_kept = 0;
            for (size_t i = p; i < e; i++) *out = driver_string_push_in(a, *out, (uint8_t)src[i]);
        }
        if (e >= len) break;  /* no terminator -> last line (splitlines drops trailing) */
        p = e + 1;            /* skip the '\n'; if it was the final byte, loop ends (p==len) */
    }
    driver_release(a, src);
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
	 * Lines are split on '\n' (Python splitlines: a trailing '\n' produces no extra empty line) and rejoined
 * with '\n'. */
static String build_self_source(Malloc* a, const char* srcroot){
    String out = driver_string_new_in(a);
    char* manifest_path = join_root_path(a, srcroot, SOURCE_MANIFEST);
    size_t manifest_len = 0;
    char* manifest = slurp(a, manifest_path, &manifest_len);
    driver_release(a, manifest_path);
    if (!manifest){ out.ptr = NULL; return out; }

    int file_count = 0;
    size_t p = 0;
    while (p < manifest_len){
        size_t e = p;
        while (e < manifest_len && manifest[e] != '\n') e++;
        size_t s = 0, n = 0;
        if (manifest_entry(manifest, p, e, &s, &n)){
            char* rel = driver_alloc(a, n + 1);
            memcpy(rel, manifest + s, n);
            rel[n] = 0;
            char* path = join_root_path(a, srcroot, rel);
            driver_release(a, rel);
            if (file_count > 0) out = driver_string_push_in(a, out, '\n');  /* "\n".join across files */
            if (append_stripped_file(a, &out, path) != 0){
                driver_release(a, path);
                driver_release(a, manifest);
                out.ptr = NULL;
                return out;
            }
            driver_release(a, path);
            file_count++;
        }
        if (e >= manifest_len) break;
        p = e + 1;
    }
    driver_release(a, manifest);
    if (file_count == 0){
        fprintf(stderr, "zenc: no sources listed in %s\n", SOURCE_MANIFEST);
        out.ptr = NULL;
    }
    return out;
}

/* genModule emits this zslice typedef at the head of every module; bootstrap/zenc.gen.c provides it
 * via zenrt.h instead, so we swap the head for the include. */
static const char HEAD[] = "typedef struct { void* ptr; int64_t len; } zslice; ";
static const char HEAD_REPL[] = "#define ZEN_NO_MALLOC 1\n#include \"zenrt.h\"\n";
/* The build/run path uses this variant instead: a built program that imports std.text.string emits its OWN
 * String + builders (strong, they override zenrt.c's weak copies at link), so define ZEN_NO_STRING to
 * suppress zenrt.h's String and avoid the struct clash (#98). The compiler's own gen.c now also
 * suppresses zenrt's Malloc because std.mem.alloc is part of the bootstrap source manifest. */
static const char HEAD_REPL_PROG[] = "#define ZEN_NO_STRING 1\n#define ZEN_NO_MALLOC 1\n#include \"zenrt.h\"\n";

static void trim_trailing_ws(String* s){
    while (s->len > 0 && py_isspace(((uint8_t*)s->ptr)[s->len - 1])) s->len--;
}

static int build_self(const char* out_path, const char* srcroot){
    Malloc m = { 0 };
    String src = build_self_source(&m, srcroot);
    if (src.ptr == NULL){ return 1; }  /* a source file could not be read */
    const char* flat = driver_string_finish_in(&m, src);    /* NUL-terminate the flat source for the parser */
    String out = genModuleIn(&m, resolve_module(&m, parse_module(&m, flat)));
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
 * Emits the program's C (genModuleIn), swaps the leading HEAD typedef for #include "zenrt.h" (== the
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

typedef struct {
    int code;
    long source_offset;
    int span_width;
    int count;
    int line;
    int col;
    int end_line;
    int end_col;
    const char* kind;
    const char* message;
    const char* hint;
} Diagnostic;

static Diagnostic diagnostic_from_check(CheckDiagnostic cd){
    Diagnostic d;
    d.code = cd.code;
    d.source_offset = cd.source_offset;
    d.span_width = cd.span_width < 1 ? 1 : cd.span_width;
    d.count = cd.count < 1 ? 1 : cd.count;
    d.line = 0;
    d.col = 0;
    d.end_line = 0;
    d.end_col = 0;
    d.kind = cd.kind ? cd.kind : "type";
    d.message = cd.message ? cd.message : "type error";
    d.hint = cd.hint ? cd.hint : "";
    return d;
}

/* U1.2: type-check resolved decls. Prints a Zen-LEVEL error (a count + the first error's KIND) to stderr
 * and returns the error count (0 = ok) — so a user finally sees `zenc: foo.zen: 1 error (first: undefined-name)`
 * instead of cc errors on generated C they never wrote. (Real line:col + messages are U1 Step 4.) */
/* U2: a runnable program must define `main`. genModule emits the entry as `int32_t main(` (proto + def)
 * — the exact token cc links against — so scan the emitted C for that 13-byte substring. (A fn named
 * `mainframe` emits `int32_t mainframe(`, which this does NOT match because of the trailing `(`.) */
static int emits_main(String out){
    static const char NEEDLE[] = "int32_t zen_main(";
    size_t nlen = sizeof(NEEDLE) - 1;
    if ((size_t)out.len < nlen) return 0;
    for (size_t i = 0; i + nlen <= (size_t)out.len; i++)
        if (memcmp((const char*)out.ptr + i, NEEDLE, nlen) == 0) return 1;
    return 0;
}


static int diagnostic_attach_user_span(Malloc* a, Diagnostic* d, const char* flat, const char* user){
    (void)a;
    long pos = d->source_offset;
    if (pos <= 0 || !flat || !user) return 0;
    DiagSpan sp = diag_user_span(flat, user, (int32_t)pos, d->span_width);
    if (sp.line <= 0) return 0;
    d->line = sp.line;
    d->col = sp.col;
    d->end_line = sp.line;
    d->end_col = sp.end_col;
    return 1;
}

static void diagnostic_attach_resolved_span(
    Malloc* a,
    Diagnostic* d,
    const char* flat,
    const char* root_path,
    const char* root_src,
    const ResolvedProgram* resolved,
    const char** render_path,
    const char** render_src
){
    *render_path = root_path;
    *render_src = root_src;
    if (diagnostic_attach_user_span(a, d, flat, root_src)) return;
    if (!resolved || !resolved->table.modules.ptr) return;

    ModuleEntry* mods = (ModuleEntry*)resolved->table.modules.ptr;
    for (int64_t i = 0; i < resolved->table.modules.len; i++){
        if (!mods[i].source) continue;
        Diagnostic trial = *d;
        if (diagnostic_attach_user_span(a, &trial, flat, mods[i].source)){
            *d = trial;
            *render_path = mods[i].path ? mods[i].path : root_path;
            *render_src = mods[i].source;
            return;
        }
    }
}

static void diagnostic_render(Malloc* a, FILE* out, const char* in_path, const char* user, const Diagnostic* d){
    /* rendering (message line + source caret + hint) lives in compiler.diagnostic now */
    fputs(render_diagnostic(a, in_path, user, d->line, d->col, d->end_col, d->kind, d->message, d->hint, d->count), out);
}
static int type_check(Malloc* m, zslice raw, zslice decls, const char* in_path, const char* flat, const char* user, const ResolvedProgram* resolved){
    CheckDiagnostic cd = check_module_ownership_diagnostic_from_source(m, raw, flat);
    if (cd.code == 0) cd = check_module_escape_diagnostic_from_source(m, raw, flat);  /* M5: lexical scope-escape, on raw (pre-inline) decls */
    if (cd.code == 0) cd = check_module_diagnostic_from_source(m, decls, flat);
    if (cd.code == 0) return 0;
    Diagnostic diag = diagnostic_from_check(cd);
    const char* render_path = in_path;
    const char* render_src = user;
    diagnostic_attach_resolved_span(m, &diag, flat, in_path, user, resolved, &render_path, &render_src);
    diagnostic_render(m, stderr, render_path, render_src, &diag);
    return diag.count;
}

typedef struct {
    char* source;
    char* out;
    char* ccflags;
    char* links;   /* M6: `-l<lib>` flags built from the manifest's `link = "lib1 lib2"` directive */
} ProjectSpec;

static int path_is_dir(const char* path){
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

static char* manifest_value(Malloc* a, const char* src, size_t len, const char* key){
    MfSpan sp = manifest_value_span(src, (int32_t)len, key, 0);
    if (sp.start < 0) return NULL;
    return dup_range(a, src, (size_t)sp.start, (size_t)(sp.start + sp.len));
}

/* M6: turn a whitespace-separated library list ("m" or "m pthread") into cc `-l` flags
 * ("-lm " / "-lm -lpthread "). Returns NULL when there is nothing to link. */
static char* link_flags(Malloc* a, const char* libs){
    if (!libs) return NULL;
    size_t n = strlen(libs);
    char* out = driver_alloc(a, n * 4 + 1);  /* each char -> at most "-l", char, " " */
    size_t o = 0, i = 0;
    while (libs[i]){
        while (libs[i] == ' ' || libs[i] == '\t') i++;
        if (!libs[i]) break;
        out[o++] = '-'; out[o++] = 'l';
        while (libs[i] && libs[i] != ' ' && libs[i] != '\t') out[o++] = libs[i++];
        out[o++] = ' ';
    }
    out[o] = 0;
    if (o == 0){ driver_release(a, out); return NULL; }
    return out;
}

static ProjectSpec project_spec(Malloc* a, const char* project_dir){
    ProjectSpec spec = { 0 };
    char* manifest_path = join_root_path(a, project_dir, "zen.toml");
    size_t len = 0;
    char* src = slurp(a, manifest_path, &len);
    if (!src){ driver_release(a, manifest_path); return spec; }

    char* package = manifest_value(a, src, len, "package");
    char* root = manifest_value(a, src, len, "root");
    char* main = manifest_value(a, src, len, "main");
    char* out = manifest_value(a, src, len, "out");
    char* ccflags = manifest_value(a, src, len, "ccflags");
    char* link = manifest_value(a, src, len, "link");
    if (!package || !root || !main){
        fprintf(stderr, "zenc: %s: missing required package/root/main entries\n", manifest_path);
    } else {
        char* root_path = join_root_path(a, project_dir, root);
        spec.source = join_root_path(a, root_path, main);
        spec.out = out ? join_root_path(a, project_dir, out) : NULL;
        spec.ccflags = ccflags ? dup_cstr(a, ccflags) : NULL;
        spec.links = link_flags(a, link);
        driver_release(a, root_path);
    }

    driver_release(a, package);
    driver_release(a, root);
    driver_release(a, main);
    driver_release(a, out);
    driver_release(a, ccflags);
    driver_release(a, link);
    driver_release(a, src);
    driver_release(a, manifest_path);
    return spec;
}

static ProjectSpec input_spec(Malloc* a, const char* in_path){
    if (path_is_dir(in_path)) return project_spec(a, in_path);
    ProjectSpec spec = { 0 };
    spec.source = dup_cstr(a, in_path);
    return spec;
}

static int build_program(const char* argv0, const char* in_path, const char* out_path, const char* ccflags, const char* links, int run){
    Malloc m = { 0 };
    size_t len = 0;
    char* buf = slurp(&m, in_path, &len);
    if (!buf) return 1;
    /* U1.3: resolve `{ … } = std.X` / `compiler.X` / sibling `{ … } = b` imports from disk before
     * parsing, so a program that imports the stdlib or a neighboring file builds. root = dir of the
     * zenc binary (holds zen/std and zen/compiler); progdir = dir of the program (holds its siblings).
     * resolve_program returns the flat single-module source; on a program with no imports it is a pass-
     * through. The returned str is borrowed from the loader's arena — don't free it. */
    char dir[4096]; bin_dir(argv0, dir, sizeof dir);
    char pdir[4096]; prog_dir(in_path, pdir, sizeof pdir);
    ResolvedProgram resolved = resolve_program_data(&m, dir, pdir, in_path, buf);
    const char* flat = resolved.flat;
    zslice raw = parse_module(&m, flat);
    zslice decls = resolve_module(&m, raw);
    if (decls.len == 0){ fprintf(stderr, "zenc: %s: could not parse (no declarations)\n", in_path); driver_release(&m, buf); return 1; }  /* U2 */
    if (type_check(&m, raw, decls, in_path, flat, buf, &resolved) != 0){ driver_release(&m, buf); return 1; }  /* U1.2: don't build an ill-typed program */
    String out = genModuleIn(&m, decls);
    driver_release(&m, buf);
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
    snprintf(cmd, sizeof cmd, "cc -std=gnu11 -w -I%s/bootstrap %s %s %s/bootstrap/zenrt.c -o %s %s",
             dir, ccflags ? ccflags : "", cpath, dir, out_path, links ? links : "");
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

/* M6 (real build): if <dir>/build.zen exists, the build IS a Zen program. Append a `main` that runs
 * its `build(b)` and calls `.emit_spec()`, compile+run that, and read the five spec lines it prints
 * (name, root, main, out, link) back into the same ProjectSpec the zen.toml path produced. One module
 * (build.zen + appended main), so std imports resolve and there is no sibling-name collision. */
static ProjectSpec build_zen_spec(Malloc* a, const char* argv0, const char* project_dir){
    ProjectSpec spec = { 0 };
    char* build_path = join_root_path(a, project_dir, "build.zen");
    struct stat bst;
    if (stat(build_path, &bst) != 0){ driver_release(a, build_path); return spec; }  /* no build.zen -> zen.toml */
    size_t blen = 0;
    char* bsrc = slurp(a, build_path, &blen);
    if (!bsrc){ driver_release(a, build_path); return spec; }

    const char* tail = "\nmain = () i32 { build(Build(_: 0)).emit_spec()  0 }\n";
    size_t tlen = strlen(tail);
    char* entry = driver_alloc(a, blen + tlen + 1);
    memcpy(entry, bsrc, blen);
    memcpy(entry + blen, tail, tlen);
    entry[blen + tlen] = 0;
    driver_release(a, bsrc);

    char entry_path[4096];
    snprintf(entry_path, sizeof entry_path, "%s/.zenbuild_entry_%d.zen", project_dir, (int)getpid());
    FILE* ef = fopen(entry_path, "wb");
    if (!ef){ fprintf(stderr, "zenc: build.zen: cannot write build entry in %s\n", project_dir); driver_release(a, entry); driver_release(a, build_path); return spec; }
    fwrite(entry, 1, blen + tlen, ef);
    fclose(ef);
    driver_release(a, entry);

    char bin_path[4096];
    snprintf(bin_path, sizeof bin_path, "/tmp/zenbuild_spec_%d", (int)getpid());
    int brc = build_program(argv0, entry_path, bin_path, NULL, NULL, 0);
    unlink(entry_path);
    if (brc != 0){ fprintf(stderr, "zenc: build.zen: the build program did not compile\n"); driver_release(a, build_path); return spec; }

    char name[1024]={0}, root[1024]={0}, mainf[1024]={0}, outf[1024]={0}, link[1024]={0};
    char* fields[5] = { name, root, mainf, outf, link };
    int fi = 0;
    FILE* p = popen(bin_path, "r");
    if (p){
        char line[1024];
        while (fi < 5 && fgets(line, sizeof line, p)){
            size_t n = strlen(line);
            while (n && (line[n-1] == '\n' || line[n-1] == '\r')) line[--n] = 0;
            memcpy(fields[fi], line, n + 1);
            fi++;
        }
        pclose(p);
    }
    unlink(bin_path);

    if (!root[0] || !mainf[0]){
        fprintf(stderr, "zenc: build.zen: target is missing root/main (got %d field(s))\n", fi);
        driver_release(a, build_path);
        return spec;
    }
    char* root_path = join_root_path(a, project_dir, root);
    spec.source = join_root_path(a, root_path, mainf);
    const char* out_name = outf[0] ? outf : (name[0] ? name : NULL);
    spec.out = out_name ? join_root_path(a, project_dir, out_name) : NULL;
    spec.links = link[0] ? link_flags(a, link) : NULL;
    driver_release(a, root_path);
    driver_release(a, build_path);
    return spec;
}

static int build_input(const char* argv0, const char* in_path, const char* out_path, int run){
    Malloc m = { 0 };
    ProjectSpec spec = { 0 };
    if (path_is_dir(in_path)) spec = build_zen_spec(&m, argv0, in_path);  /* build.zen wins over zen.toml */
    if (!spec.source) spec = input_spec(&m, in_path);                     /* fallback: zen.toml or a single file */
    if (!spec.source) return 1;
    const char* final_out = out_path;
    if (!run && !final_out) final_out = spec.out ? spec.out : "a.out";
    int rc = build_program(argv0, spec.source, final_out, spec.ccflags, spec.links, run);
    driver_release(&m, spec.source);
    driver_release(&m, spec.out);
    driver_release(&m, spec.ccflags);
    driver_release(&m, spec.links);
    return rc;
}

static int check_program(const char* argv0, const char* in_path){
    Malloc m = { 0 };
    char* buf = slurp(&m, in_path, NULL);
    if (!buf) return 1;
    /* U1.3: resolve std.X / sibling imports from disk before checking, same as build_program. */
    char dir[4096]; bin_dir(argv0, dir, sizeof dir);
    char pdir[4096]; prog_dir(in_path, pdir, sizeof pdir);
    ResolvedProgram resolved = resolve_program_data(&m, dir, pdir, in_path, buf);
    const char* flat = resolved.flat;
    zslice raw = parse_module(&m, flat);
    zslice decls = resolve_module(&m, raw);
    /* U2: reject gross parse failure (zero decls). NOTE: a missing `main` is NOT enforced in `check`
     * — a library module (std.*) legitimately has no main; build/run enforce it instead. */
    if (decls.len == 0){ fprintf(stderr, "zenc: %s: could not parse (no declarations)\n", in_path); driver_release(&m, buf); return 1; }
    int n = type_check(&m, raw, decls, in_path, flat, buf, &resolved);
    driver_release(&m, buf);
    if (n == 0) fprintf(stderr, "zenc: %s: ok\n", in_path);
    return n == 0 ? 0 : 1;
}

static int check_input(const char* argv0, const char* in_path){
    Malloc m = { 0 };
    ProjectSpec spec = input_spec(&m, in_path);
    if (!spec.source) return 1;
    int rc = check_program(argv0, spec.source);
    driver_release(&m, spec.source);
    driver_release(&m, spec.out);
    driver_release(&m, spec.ccflags);
    driver_release(&m, spec.links);
    return rc;
}

static int emit_file(const char* argv0, const char* in_path){
    Malloc m = { 0 };
    char* buf = slurp(&m, in_path, NULL);
    if (!buf) return 1;
    char dir[4096]; bin_dir(argv0, dir, sizeof dir);
    char pdir[4096]; prog_dir(in_path, pdir, sizeof pdir);
    const char* flat = resolve_program(&m, dir, pdir, in_path, buf);
    String out = genModuleIn(&m, resolve_module(&m, parse_module(&m, flat)));
    fwrite(out.ptr, 1, out.len, stdout);
    driver_release(&m, buf);
    return 0;
}

static int fmt_line_space(unsigned char c){
    return c == ' ' || c == '\t' || c == '\r' || c == '\v' || c == '\f';
}

static void fmt_scan_depth(const char* src, size_t p, size_t e, int* depth, int* in_block){
    int in_str = 0, in_char = 0, esc = 0;
    for (size_t i = p; i < e; i++){
        unsigned char c = (unsigned char)src[i];
        if (*in_block){
            if (c == '*' && i + 1 < e && src[i + 1] == '/'){
                *in_block = 0;
                i++;
            }
            continue;
        }
        if (in_str){
            if (esc) esc = 0;
            else if (c == '\\') esc = 1;
            else if (c == '"') in_str = 0;
            continue;
        }
        if (in_char){
            if (esc) esc = 0;
            else if (c == '\\') esc = 1;
            else if (c == '\'') in_char = 0;
            continue;
        }
        if (c == '/' && i + 1 < e && src[i + 1] == '/') break;
        if (c == '/' && i + 1 < e && src[i + 1] == '*'){
            *in_block = 1;
            i++;
            continue;
        }
        if (c == '"'){ in_str = 1; continue; }
        if (c == '\''){ in_char = 1; continue; }
        if (c == '{') (*depth)++;
        else if (c == '}' && *depth > 0) (*depth)--;
    }
}

static String fmt_source(Malloc* a, const char* src, size_t len){
    String out = driver_string_new_in(a);
    int depth = 0;
    int in_block = 0;
    size_t p = 0;
    while (p < len){
        size_t e = p;
        while (e < len && src[e] != '\n' && src[e] != '\r') e++;

        size_t s = p;
        while (s < e && fmt_line_space((unsigned char)src[s])) s++;
        size_t t = e;
        while (t > s && fmt_line_space((unsigned char)src[t - 1])) t--;

        if (s == t){
            out = driver_string_push_in(a, out, '\n');
        } else {
            int indent = depth;
            int line_starts_in_block = in_block;
            if (!line_starts_in_block && src[s] == '}' && indent > 0) indent--;
            for (int i = 0; i < indent * 4; i++) out = driver_string_push_in(a, out, ' ');
            for (size_t i = s; i < t; i++) out = driver_string_push_in(a, out, (uint8_t)src[i]);
            out = driver_string_push_in(a, out, '\n');
            fmt_scan_depth(src, s, t, &depth, &in_block);
        }

        if (e >= len) break;
        if (src[e] == '\r' && e + 1 < len && src[e + 1] == '\n') p = e + 2;
        else p = e + 1;
    }
    return out;
}

static int write_file_bytes(const char* path, const char* data, size_t len){
    FILE* f = fopen(path, "wb");
    if (!f){ fprintf(stderr, "zenc: cannot write %s\n", path); return 1; }
    size_t n = fwrite(data, 1, len, f);
    int close_rc = fclose(f);
    if (n != len || close_rc != 0){ fprintf(stderr, "zenc: failed to write %s\n", path); return 1; }
    return 0;
}

static int fmt_file(const char* path, int check){
    Malloc m = { 0 };
    size_t len = 0;
    char* src = slurp(&m, path, &len);
    if (!src) return 1;
    String out = fmt_source(&m, src, len);
    size_t out_len = (size_t)out.len;
    int changed = (len != out_len) || memcmp(src, out.ptr, out_len) != 0;
    if (check){
        if (changed) fprintf(stderr, "zenc: %s: needs formatting\n", path);
        driver_release(&m, src);
        return changed ? 1 : 0;
    }
    int rc = changed ? write_file_bytes(path, out.ptr, out_len) : 0;
    driver_release(&m, src);
    return rc;
}

static int starts_with(const char* s, const char* prefix){
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

static char* std_module_path(Malloc* a, const char* root, const char* mod){
    const char* tail = mod + 4; /* after "std." */
    size_t n = strlen("zen/std/") + strlen(tail) + strlen(".zen") + 1;
    char* rel = driver_alloc(a, n);
    size_t pos = 0;
    memcpy(rel + pos, "zen/std/", strlen("zen/std/")); pos += strlen("zen/std/");
    for (size_t i = 0; tail[i]; i++) rel[pos++] = (tail[i] == '.') ? '/' : tail[i];
    memcpy(rel + pos, ".zen", strlen(".zen") + 1);
    char* path = join_root_path(a, root, rel);
    driver_release(a, rel);
    return path;
}

static void string_append_range(Malloc* a, String* s, const char* src, size_t p, size_t e){
    for (size_t i = p; i < e; i++) *s = driver_string_push_in(a, *s, (uint8_t)src[i]);
}

static int doc_is_blank(const char* src, size_t p, size_t e){
    for (size_t i = p; i < e; i++) if (!fmt_line_space((unsigned char)src[i])) return 0;
    return 1;
}

static int doc_is_comment(const char* src, size_t p, size_t e){
    return p + 1 < e && src[p] == '/' && src[p + 1] == '/';
}

static int doc_is_public_decl(const char* src, size_t p, size_t e){
    if (p >= e) return 0;
    unsigned char c = (unsigned char)src[p];
    if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || c == '_')) return 0;
    for (size_t i = p; i < e; i++){
        unsigned char b = (unsigned char)src[i];
        if (b == '*') return 1;
        if (b == '=' || b == ':') return 0;
    }
    return 0;
}

static int doc_source(const char* label, const char* src, size_t len){
    printf("# %s\n", label);
    Malloc m = { 0 };
    String docs = driver_string_new_in(&m);
    int found = 0;
    size_t p = 0;
    while (p < len){
        size_t e = p;
        while (e < len && src[e] != '\n' && src[e] != '\r') e++;

        size_t t = e;
        while (t > p && fmt_line_space((unsigned char)src[t - 1])) t--;

        if (doc_is_comment(src, p, t)){
            size_t s = p + 2;
            if (s < t && src[s] == ' ') s++;
            string_append_range(&m, &docs, src, s, t);
            docs = driver_string_push_in(&m, docs, '\n');
        } else if (doc_is_blank(src, p, t)){
            docs.len = 0;
        } else if (doc_is_public_decl(src, p, t)){
            if (docs.len > 0) fwrite(docs.ptr, 1, docs.len, stdout);
            fwrite(src + p, 1, t - p, stdout);
            fputc('\n', stdout);
            docs.len = 0;
            found = 1;
        } else {
            docs.len = 0;
        }

        if (e >= len) break;
        if (src[e] == '\r' && e + 1 < len && src[e + 1] == '\n') p = e + 2;
        else p = e + 1;
    }
    return found ? 0 : 0;
}

static int doc_arg(const char* argv0, const char* arg){
    Malloc m = { 0 };
    char root[4096]; bin_dir(argv0, root, sizeof root);
    char* path = starts_with(arg, "std.") ? std_module_path(&m, root, arg) : dup_cstr(&m, arg);
    size_t len = 0;
    char* src = slurp(&m, path, &len);
    if (!src){ driver_release(&m, path); return 1; }
    int rc = doc_source(arg, src, len);
    driver_release(&m, src);
    driver_release(&m, path);
    return rc;
}

static void usage(FILE* to){
    fprintf(to,
        "zenc — the Zen compiler (self-hosted)\n"
        "\n"
        "usage:\n"
        "  zenc run   <file.zen|dir>        type-check, build and run (exit = the program's exit code)\n"
        "  zenc build <file.zen|dir> [-o out] type-check and link a native binary\n"
        "  zenc check <file.zen|dir>        type-check only (libraries allowed: no main required)\n"
        "  zenc fmt   [--check] <file.zen>  format a Zen source file, or verify formatting\n"
        "  zenc doc   <std.mod|file.zen>    list public declarations and nearby docs\n"
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
        return emit_file(argv[0], argv[2]);
    }
    if (argc >= 2 && strcmp(argv[1], "--build-self") == 0){
        if (argc < 4){ fprintf(stderr, "usage: %s --build-self <out.c> <srcroot>\n", argv[0]); return 2; }
        return build_self(argv[2], argv[3]);
    }
    if (argc >= 2 && strcmp(argv[1], "build") == 0){
        const char* in = NULL; const char* out = NULL;
        for (int i = 2; i < argc; i++){
            if (strcmp(argv[i], "-o") == 0 && i + 1 < argc) out = argv[++i];
            else in = argv[i];
        }
        if (!in){ fprintf(stderr, "usage: %s build <file.zen|project-dir> [-o out]\n", argv[0]); return 2; }
        return build_input(argv[0], in, out, 0);
    }
    if (argc >= 2 && strcmp(argv[1], "run") == 0){
        if (argc < 3){ fprintf(stderr, "usage: %s run <file.zen|project-dir>\n", argv[0]); return 2; }
        return build_input(argv[0], argv[2], NULL, 1);
    }
    if (argc >= 2 && strcmp(argv[1], "fmt") == 0){
        int check = 0;
        const char* in = NULL;
        for (int i = 2; i < argc; i++){
            if (strcmp(argv[i], "--check") == 0) check = 1;
            else if (!in) in = argv[i];
            else { fprintf(stderr, "usage: %s fmt [--check] <in.zen>\n", argv[0]); return 2; }
        }
        if (!in){ fprintf(stderr, "usage: %s fmt [--check] <in.zen>\n", argv[0]); return 2; }
        return fmt_file(in, check);
    }
    if (argc >= 2 && strcmp(argv[1], "doc") == 0){
        if (argc < 3){ fprintf(stderr, "usage: %s doc <std.mod|file.zen>\n", argv[0]); return 2; }
        return doc_arg(argv[0], argv[2]);
    }
    if (argc >= 2 && strcmp(argv[1], "check") == 0){  /* U1.2: type-check only, no build */
        if (argc < 3){ fprintf(stderr, "usage: %s check <file.zen|project-dir>\n", argv[0]); return 2; }
        return check_input(argv[0], argv[2]);
    }
    return compile_stdin_or_file(argc, argv);
}
