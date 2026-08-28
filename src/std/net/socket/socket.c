// src/std/net/socket/socket.c
// Normalises the incompatible POSIX fd and Windows SOCKET ABIs to size_t.

#define _POSIX_C_SOURCE 200809L

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <errno.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

typedef struct zg_str {
    unsigned char *data;
    size_t len;
} zg_str;

static char *
zg_socket_cstr(zg_str s)
{
    char *p = (char *)malloc(s.len + 1);
    if (!p) return NULL;
    if (s.len != 0) memcpy(p, s.data, s.len);
    p[s.len] = '\0';
    return p;
}

#ifdef _WIN32
typedef SOCKET zg_native_socket;
#define ZG_INVALID_SOCKET INVALID_SOCKET

static int
zg_socket_start(void)
{
    WSADATA data;
    return WSAStartup(MAKEWORD(2, 2), &data) == 0;
}

static void
zg_socket_stop(void)
{
    WSACleanup();
}

static void
zg_socket_discard(zg_native_socket s)
{
    if (s != ZG_INVALID_SOCKET) closesocket(s);
}
#else
typedef int zg_native_socket;
#define ZG_INVALID_SOCKET (-1)

static int
zg_socket_start(void)
{
    return 1;
}

static void
zg_socket_stop(void)
{
}

static void
zg_socket_discard(zg_native_socket s)
{
    if (s != ZG_INVALID_SOCKET) close(s);
}
#endif

size_t
zg_socket_tcp_connect(zg_str host, uint16_t port)
{
    char *host_c = NULL;
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    struct addrinfo *ai;
    char port_c[6];
    zg_native_socket socket_fd = ZG_INVALID_SOCKET;
    size_t answer = SIZE_MAX;

    if (!zg_socket_start()) return SIZE_MAX;
    host_c = zg_socket_cstr(host);
    if (!host_c) goto done;

    memset(&hints, 0, sizeof(hints));
    snprintf(port_c, sizeof(port_c), "%u", (unsigned)port);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;
    if (getaddrinfo(host_c, port_c, &hints, &res) != 0) goto done;

    for (ai = res; ai != NULL; ai = ai->ai_next) {
        socket_fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (socket_fd == ZG_INVALID_SOCKET) continue;
#if !defined(_WIN32) && defined(SO_NOSIGPIPE)
        {
            int one = 1;
            (void)setsockopt(socket_fd, SOL_SOCKET, SO_NOSIGPIPE,
                             &one, sizeof(one));
        }
#endif
        if (connect(socket_fd, ai->ai_addr, ai->ai_addrlen) == 0) {
            answer = (size_t)socket_fd;
            socket_fd = ZG_INVALID_SOCKET;
            break;
        }
        zg_socket_discard(socket_fd);
        socket_fd = ZG_INVALID_SOCKET;
    }

done:
    zg_socket_discard(socket_fd);
    if (res) freeaddrinfo(res);
    free(host_c);
    if (answer == SIZE_MAX) zg_socket_stop();
    return answer;
}

int32_t
zg_socket_write(size_t raw, zg_str bytes)
{
    size_t sent = 0;
    zg_native_socket socket_fd = (zg_native_socket)raw;
    while (sent < bytes.len) {
#ifdef _WIN32
        size_t left = bytes.len - sent;
        int chunk = left > (size_t)INT_MAX ? INT_MAX : (int)left;
        int n = send(socket_fd, (const char *)bytes.data + sent, chunk, 0);
        if (n == SOCKET_ERROR) {
            if (WSAGetLastError() == WSAEINTR) continue;
            return 2;
        }
#else
#ifdef MSG_NOSIGNAL
        const int flags = MSG_NOSIGNAL;
#else
        const int flags = 0;
#endif
        ssize_t n = send(socket_fd, bytes.data + sent, bytes.len - sent, flags);
        if (n < 0) {
            if (errno == EINTR) continue;
            return 2;
        }
#endif
        if (n == 0) return 4;
        sent += (size_t)n;
    }
    return 0;
}

size_t
zg_socket_read(size_t raw, uint8_t *buf, size_t cap)
{
    zg_native_socket socket_fd = (zg_native_socket)raw;
    if (cap == 0) return 0;
    for (;;) {
#ifdef _WIN32
        int chunk = cap > (size_t)INT_MAX ? INT_MAX : (int)cap;
        int n = recv(socket_fd, (char *)buf, chunk, 0);
        if (n == SOCKET_ERROR) {
            if (WSAGetLastError() == WSAEINTR) continue;
            return SIZE_MAX;
        }
#else
        ssize_t n = recv(socket_fd, buf, cap, 0);
        if (n < 0) {
            if (errno == EINTR) continue;
            return SIZE_MAX;
        }
#endif
        if (n == 0) return SIZE_MAX - 1;
        return (size_t)n;
    }
}

void
zg_socket_close(size_t raw)
{
    zg_socket_discard((zg_native_socket)raw);
    zg_socket_stop();
}

/* DNS stays here because addrinfo/sockaddr are platform-owned layouts. */
int32_t
zg_dns_resolve(zg_str host, uint8_t **ip_out, size_t *ip_len,
               int32_t *is_v6_out)
{
    char *host_c = NULL;
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    void *addr = NULL;
    char *buf = NULL;
    size_t cap = 0;
    int family = 0;
    int started = 0;
    int32_t answer = 2;

    if (!zg_socket_start()) goto done;
    started = 1;
    host_c = zg_socket_cstr(host);
    if (!host_c) goto done;

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host_c, NULL, &hints, &res) != 0 || !res) {
        answer = 1;
        goto done;
    }

    family = res->ai_family;
    if (family == AF_INET) {
        struct sockaddr_in *sin = (struct sockaddr_in *)res->ai_addr;
        addr = &sin->sin_addr;
        cap = INET_ADDRSTRLEN;
    } else if (family == AF_INET6) {
        struct sockaddr_in6 *sin6 = (struct sockaddr_in6 *)res->ai_addr;
        addr = &sin6->sin6_addr;
        cap = INET6_ADDRSTRLEN;
    } else {
        answer = 1;
        goto done;
    }

    buf = (char *)malloc(cap);
    if (!buf) goto done;
#ifdef _WIN32
    if (!InetNtopA(family, addr, buf, (DWORD)cap)) goto done;
#else
    if (!inet_ntop(family, addr, buf, cap)) goto done;
#endif

    *ip_out = (uint8_t *)buf;
    *ip_len = strlen(buf);
    *is_v6_out = family == AF_INET6 ? 1 : 0;
    buf = NULL;
    answer = 0;

done:
    free(buf);
    if (res) freeaddrinfo(res);
    free(host_c);
    if (started) zg_socket_stop();
    return answer;
}
