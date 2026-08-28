// src/std/proc/proc.c
// Process execution and capture floor for std.proc.

#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

/* Matches the Zen runtime's string spelling. */
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

static int
capture_read_some(struct capture *c, int fd, int *open)
{
    uint8_t buf[4096];
    ssize_t n = read(fd, buf, sizeof(buf));
    if (n < 0) {
        if (errno == EINTR) return 0;
        return -1;
    }
    if (n == 0) {
        *open = 0;
        return 0;
    }
    return capture_append(c, buf, (size_t)n);
}

/* Drain both pipes concurrently. Reading one stream to EOF before starting
   the other deadlocks once the child fills the unread pipe's buffer. */
static int
capture_read_both(struct capture *out, int out_fd,
                  struct capture *err, int err_fd)
{
    struct pollfd pfds[2];
    int out_open = 1;
    int err_open = 1;

    pfds[0].fd = out_fd;
    pfds[0].events = POLLIN;
    pfds[1].fd = err_fd;
    pfds[1].events = POLLIN;

    while (out_open || err_open) {
        int nready;
        pfds[0].revents = 0;
        pfds[1].revents = 0;
        do {
            nready = poll(pfds, 2, -1);
        } while (nready < 0 && errno == EINTR);
        if (nready < 0) return -1;

        if (out_open && (pfds[0].revents & (POLLIN | POLLHUP | POLLERR))) {
            if (capture_read_some(out, out_fd, &out_open) != 0) return -1;
        }
        if (err_open && (pfds[1].revents & (POLLIN | POLLHUP | POLLERR))) {
            if (capture_read_some(err, err_fd, &err_open) != 0) return -1;
        }
    }
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

/* 0 = ok, 1 = SpawnFailed, 2 = WaitFailed, 3 = ReadFailed */
int32_t
zg_proc_run(zg_str cwd, zg_str cmd,
            int32_t *code_out,
            uint8_t **out_buf, size_t *out_len,
            uint8_t **err_buf, size_t *err_len)
{
    char *cwd_c = strndup_zg(cwd);
    char *cmd_c = strndup_zg(cmd);
    int out_pipe[2] = {-1, -1};
    int err_pipe[2] = {-1, -1};
    posix_spawn_file_actions_t fa;
    int fa_init = 0;
    pid_t pid = -1;
    int status;
    struct capture out = {0};
    struct capture err = {0};
    int32_t ret = 1; /* SpawnFailed */

    if (!cmd_c) goto done;

    if (pipe(out_pipe) != 0 || pipe(err_pipe) != 0) goto done;

    if (posix_spawn_file_actions_init(&fa) != 0) goto done;
    fa_init = 1;

    if (cwd.len > 0 && cwd_c) {
        if (posix_spawn_file_actions_addchdir_np(&fa, cwd_c) != 0) goto done;
    }

    if (posix_spawn_file_actions_adddup2(&fa, out_pipe[1], STDOUT_FILENO) != 0) goto done;
    if (posix_spawn_file_actions_adddup2(&fa, err_pipe[1], STDERR_FILENO) != 0) goto done;
    if (posix_spawn_file_actions_addclose(&fa, out_pipe[0]) != 0) goto done;
    if (posix_spawn_file_actions_addclose(&fa, out_pipe[1]) != 0) goto done;
    if (posix_spawn_file_actions_addclose(&fa, err_pipe[0]) != 0) goto done;
    if (posix_spawn_file_actions_addclose(&fa, err_pipe[1]) != 0) goto done;

    char *argv[] = {"sh", "-c", cmd_c, NULL};
    if (posix_spawnp(&pid, "/bin/sh", &fa, NULL, argv, environ) != 0) goto done;

    /* Parent: close write ends and read. */
    close(out_pipe[1]); out_pipe[1] = -1;
    close(err_pipe[1]); err_pipe[1] = -1;

    if (capture_read_both(&out, out_pipe[0], &err, err_pipe[0]) != 0) {
        ret = 3;
        goto done;
    }

    close(out_pipe[0]); out_pipe[0] = -1;
    close(err_pipe[0]); err_pipe[0] = -1;

    if (wait_for(pid, &status) != 0) { ret = 2; goto done; }
    pid = -1; /* reaped */

    if (WIFEXITED(status)) {
        *code_out = (int32_t)WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        *code_out = 128 + (int32_t)WTERMSIG(status);
    } else {
        *code_out = 127;
    }

    *out_buf = out.data;
    *out_len = out.len;
    *err_buf = err.data;
    *err_len = err.len;
    out.data = NULL;
    err.data = NULL;
    ret = 0;

done:
    if (fa_init) posix_spawn_file_actions_destroy(&fa);
    if (out_pipe[0] >= 0) close(out_pipe[0]);
    if (out_pipe[1] >= 0) close(out_pipe[1]);
    if (err_pipe[0] >= 0) close(err_pipe[0]);
    if (err_pipe[1] >= 0) close(err_pipe[1]);
    if (pid >= 0) {
        /* A read failed after the spawn: the child may be blocked writing
           to a pipe nobody drains. Kill it and reap so no zombie is left. */
        kill(pid, SIGKILL);
        wait_for(pid, &status);
    }
    free(cwd_c);
    free(cmd_c);
    if (ret != 0) {
        capture_free(&out);
        capture_free(&err);
    }
    return ret;
}
