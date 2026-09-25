#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

/* Must match the generated C representation of `str`. */
typedef struct zg_str {
    unsigned char *data;
    size_t len;
} zg_str;

extern char **environ;

static char *
strndup_zg(zg_str s)
{
    char *p;
    if (s.len == 0) {
        p = malloc(1);
        if (!p) return NULL;
        p[0] = '\0';
        return p;
    }
    p = malloc(s.len + 1);
    if (!p) return NULL;
    memcpy(p, s.data, s.len);
    p[s.len] = '\0';
    return p;
}

static int
invalid_string(zg_str s)
{
    return s.len > 0 && (!s.data || memchr(s.data, '\0', s.len) != NULL);
}

static void
argv_free(char **argv, size_t argc)
{
    size_t i;
    if (!argv) return;
    for (i = 0; i < argc; i++) free(argv[i]);
    free(argv);
}

/* Copy Zen strings into the NUL-terminated shape posix_spawnp requires.
   Empty argv and embedded NUL bytes are invalid rather than silently changed. */
static char **
argv_copy(zg_str *args, size_t argc)
{
    char **argv;
    size_t i;

    if (!args || argc == 0 || argc == SIZE_MAX || args[0].len == 0) return NULL;

    argv = calloc(argc + 1, sizeof(*argv));
    if (!argv) return NULL;

    for (i = 0; i < argc; i++) {
        if (invalid_string(args[i])) {
            argv_free(argv, argc);
            return NULL;
        }
        argv[i] = strndup_zg(args[i]);
        if (!argv[i]) {
            argv_free(argv, argc);
            return NULL;
        }
    }
    return argv;
}

struct capture {
    uint8_t *data;
    size_t len;
    size_t cap;
};

static void
capture_free(struct capture *c)
{
    free(c->data);
    c->data = NULL;
    c->len = 0;
    c->cap = 0;
}

static int
capture_append(struct capture *c, const uint8_t *buf, size_t n)
{
    size_t want = c->len + n;
    if (want > c->cap) {
        size_t new_cap = c->cap ? c->cap * 2 : 4096;
        while (new_cap < want) new_cap *= 2;
        uint8_t *p = realloc(c->data, new_cap);
        if (!p) return -1;
        c->data = p;
        c->cap = new_cap;
    }
    memcpy(c->data + c->len, buf, n);
    c->len = want;
    return 0;
}

/* Reap the child, retrying when a signal interrupts the wait. */
static int
wait_for(pid_t pid, int *status)
{
    pid_t r;
    do {
        r = waitpid(pid, status, 0);
    } while (r < 0 && errno == EINTR);
    return r < 0 ? -1 : 0;
}

static int32_t
exit_code(int status)
{
    if (WIFEXITED(status)) return (int32_t)WEXITSTATUS(status);
    if (WIFSIGNALED(status)) return 128 + (int32_t)WTERMSIG(status);
    return 127;
}

struct proc_stream {
    pid_t pid;
    int out_fd;
    int err_fd;
    int next;
};

static struct proc_stream *
stream_start(const char *cwd, const char *file, char *const argv[])
{
    int pipes[2][2] = {{-1, -1}, {-1, -1}};
    posix_spawn_file_actions_t fa;
    int initialized = 0;
    struct proc_stream *s = calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->pid = -1; s->out_fd = -1; s->err_fd = -1;
    if (pipe2(pipes[0], O_CLOEXEC) || pipe2(pipes[1], O_CLOEXEC)) goto fail;
    if (posix_spawn_file_actions_init(&fa)) goto fail;
    initialized = 1;
    if (cwd && posix_spawn_file_actions_addchdir_np(&fa, cwd)) goto fail;
    for (int i = 0; i < 2; i++) {
        if (posix_spawn_file_actions_adddup2(&fa, pipes[i][1], i + 1) ||
            posix_spawn_file_actions_addclose(&fa, pipes[i][0]) ||
            posix_spawn_file_actions_addclose(&fa, pipes[i][1])) goto fail;
    }
    if (posix_spawnp(&s->pid, file, &fa, NULL, argv, environ)) goto fail;
    posix_spawn_file_actions_destroy(&fa);
    close(pipes[0][1]); close(pipes[1][1]);
    s->out_fd = pipes[0][0]; s->err_fd = pipes[1][0];
    return s;
fail:
    if (initialized) posix_spawn_file_actions_destroy(&fa);
    for (int i = 0; i < 2; i++)
        for (int j = 0; j < 2; j++) if (pipes[i][j] >= 0) close(pipes[i][j]);
    free(s);
    return NULL;
}

/* The caller owns this handle until close. Bytes are copied into caller storage. */
void *
zg_proc_stream_start(zg_str cwd, zg_str *args, size_t argc)
{
    char *cwd_c = NULL;
    char **argv = NULL;
    struct proc_stream *s = NULL;
    if (invalid_string(cwd)) return NULL;
    if (cwd.len) {
        cwd_c = strndup_zg(cwd);
        if (!cwd_c) return NULL;
    }
    argv = argv_copy(args, argc);
    if (argv) s = stream_start(cwd_c, argv[0], argv);
    free(cwd_c); argv_free(argv, argc);
    return s;
}

/* 1=stdout, 2=stderr, 0=EOF, -1=read failure. Closed fds leave the poll set. */
int32_t
zg_proc_stream_next(void *handle, uint8_t *buf, size_t cap, size_t *count)
{
    struct proc_stream *s = handle;
    *count = 0;
    if (!s || !buf || cap == 0) return -1;
    while (s->out_fd >= 0 || s->err_fd >= 0) {
        struct pollfd fds[2] = {{s->out_fd, POLLIN, 0}, {s->err_fd, POLLIN, 0}};
        int ready;
        do { ready = poll(fds, 2, -1); } while (ready < 0 && errno == EINTR);
        if (ready < 0) return -1;
        for (int turn = 0; turn < 2; turn++) {
            int i = (s->next + turn) % 2;
            if (fds[i].fd < 0 || !fds[i].revents) continue;
            if (fds[i].revents & POLLNVAL) return -1;
            ssize_t n;
            do { n = read(fds[i].fd, buf, cap); } while (n < 0 && errno == EINTR);
            if (n < 0) return -1;
            if (n > 0) { s->next = 1 - i; *count = (size_t)n; return i + 1; }
            close(fds[i].fd);
            if (i == 0) s->out_fd = -1; else s->err_fd = -1;
        }
    }
    return 0;
}

int32_t
zg_proc_stream_wait(void *handle, int32_t *code)
{
    struct proc_stream *s = handle;
    int status;
    if (!s || s->pid < 0 || wait_for(s->pid, &status)) return 2;
    s->pid = -1;
    *code = exit_code(status);
    return 0;
}

void
zg_proc_stream_close(void *handle)
{
    struct proc_stream *s = handle;
    int status;
    if (!s) return;
    if (s->out_fd >= 0) close(s->out_fd);
    if (s->err_fd >= 0) close(s->err_fd);
    if (s->pid >= 0) { kill(s->pid, SIGKILL); wait_for(s->pid, &status); }
    free(s);
}

/* Buffered callers use the same incremental drainage and cleanup path. */
static int32_t
run_captured(const char *cwd, const char *file, char *const argv[],
             int32_t *code_out,
             uint8_t **out_buf, size_t *out_len,
             uint8_t **err_buf, size_t *err_len)
{
    struct proc_stream *s = stream_start(cwd, file, argv);
    struct capture out = {0}, err = {0};
    uint8_t buf[4096];
    size_t n;
    int32_t channel, rc = 3;
    if (!s) return 1;
    while ((channel = zg_proc_stream_next(s, buf, sizeof(buf), &n)) > 0) {
        if (capture_append(channel == 1 ? &out : &err, buf, n)) goto done;
    }
    if (channel < 0) goto done;
    rc = zg_proc_stream_wait(s, code_out);
    if (rc) goto done;
    *out_buf = out.data; *out_len = out.len;
    *err_buf = err.data; *err_len = err.len;
    out.data = NULL; err.data = NULL;
done:
    zg_proc_stream_close(s);
    capture_free(&out); capture_free(&err);
    return rc;
}

/* Return ordinals match ProcError in src/std/proc/proc.zen. */
int32_t
zg_proc_run(zg_str cwd, zg_str cmd,
            int32_t *code_out,
            uint8_t **out_buf, size_t *out_len,
            uint8_t **err_buf, size_t *err_len)
{
    char *cwd_c = strndup_zg(cwd);
    char *cmd_c = strndup_zg(cmd);
    char *argv[] = {"sh", "-c", cmd_c, NULL};
    int32_t ret = 1;

    if (cmd_c) {
        ret = run_captured(cwd.len > 0 ? cwd_c : NULL, "/bin/sh", argv,
                           code_out, out_buf, out_len, err_buf, err_len);
    }
    free(cwd_c);
    free(cmd_c);
    return ret;
}

int32_t
zg_proc_run_argv(zg_str cwd, zg_str *args, size_t argc,
                 int32_t *code_out,
                 uint8_t **out_buf, size_t *out_len,
                 uint8_t **err_buf, size_t *err_len)
{
    char *cwd_c = NULL;
    char **argv = NULL;
    int32_t ret = 1; /* SpawnFailed */

    if (invalid_string(cwd)) goto done;
    if (cwd.len > 0) {
        cwd_c = strndup_zg(cwd);
        if (!cwd_c) goto done;
    }
    argv = argv_copy(args, argc);
    if (!argv) goto done;

    ret = run_captured(cwd_c, argv[0], argv,
                       code_out, out_buf, out_len, err_buf, err_len);

done:
    free(cwd_c);
    argv_free(argv, argc);
    return ret;
}

int32_t
zg_proc_run_argv_inherit(zg_str cwd, zg_str *args, size_t argc,
                         int32_t *code_out)
{
    char *cwd_c = NULL;
    char **argv = NULL;
    posix_spawn_file_actions_t fa;
    int fa_init = 0;
    pid_t pid = -1;
    int status;
    int32_t ret = 1; /* SpawnFailed */

    if (invalid_string(cwd)) goto done;
    if (cwd.len > 0) {
        cwd_c = strndup_zg(cwd);
        if (!cwd_c) goto done;
    }
    argv = argv_copy(args, argc);
    if (!argv) goto done;

    if (posix_spawn_file_actions_init(&fa) != 0) goto done;
    fa_init = 1;
    if (cwd_c && posix_spawn_file_actions_addchdir_np(&fa, cwd_c) != 0) goto done;

    if (posix_spawnp(&pid, argv[0], &fa, NULL, argv, environ) != 0) goto done;
    if (wait_for(pid, &status) != 0) { ret = 2; goto done; }
    pid = -1;
    *code_out = exit_code(status);
    ret = 0;

done:
    if (fa_init) posix_spawn_file_actions_destroy(&fa);
    if (pid >= 0) {
        kill(pid, SIGKILL);
        wait_for(pid, &status);
    }
    free(cwd_c);
    argv_free(argv, argc);
    return ret;
}
