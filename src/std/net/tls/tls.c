// src/std/net/tls/tls.c
// C runtime floor for std.net.tls. Linked into programs that use
// std.net.tls.connect. Built on OpenSSL.

#define _POSIX_C_SOURCE 200809L

#include <limits.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <openssl/ssl.h>
#include <openssl/x509v3.h>

#ifndef _WIN32
#include <signal.h>
#endif

/* Matches the Zen runtime's string spelling. */
typedef struct zg_str {
    unsigned char *data;
    size_t len;
} zg_str;

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

/* Shared connect path. alpn/alpn_len: protocol list in ALPN wire form
   (length-prefixed), or NULL/0 to offer none. */
static uint8_t *
tls_wrap_alpn(size_t raw, zg_str host,
              const unsigned char *alpn, unsigned int alpn_len)
{
    char *host_c = strndup_zg(host);
    SSL_CTX *ctx = NULL;
    SSL *ssl = NULL;
    uint8_t *answer = NULL;

    if (!host_c) goto done;

#ifndef _WIN32
    /* OpenSSL has no per-write MSG_NOSIGNAL; a closed peer must come
       back as an error, never as a signal. */
    signal(SIGPIPE, SIG_IGN);
#endif

    ctx = SSL_CTX_new(TLS_client_method());
    if (!ctx) goto done;

    SSL_CTX_set_default_verify_paths(ctx);
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);

    if (alpn && SSL_CTX_set_alpn_protos(ctx, alpn, alpn_len) != 0) goto done;

    ssl = SSL_new(ctx);
    if (!ssl) goto done;

    if (SSL_set_fd(ssl, (int)raw) != 1) goto done;

    SSL_set_tlsext_host_name(ssl, host_c);

    /* Verify the peer cert chains to a trusted root (SSL_VERIFY_PEER
       above) and that it names the host we dialed. No partial wildcard
       match ("*.com" must not cover "example.com"). */
    SSL_set_hostflags(ssl, X509_CHECK_FLAG_NO_PARTIAL_WILDCARDS);
    if (SSL_set1_host(ssl, host_c) != 1) goto done;

    if (SSL_connect(ssl) != 1) goto done;

    /* Handshake-level failure already reports verification errors; check
       the result explicitly so a silently-ignored verify is never ok. */
    if (SSL_get_verify_result(ssl) != X509_V_OK) goto done;

    answer = (uint8_t *)ssl;

done:
    if (!answer) {
        if (ssl) SSL_free(ssl);
        if (ctx) SSL_CTX_free(ctx);
    }
    free(host_c);
    return answer;
}

uint8_t *
zg_tls_wrap(size_t raw, zg_str host)
{
    return tls_wrap_alpn(raw, host, NULL, 0);
}

/* Same wrap, but offers ALPN "h2" only: the HTTP/2 floor. */
uint8_t *
zg_tls_wrap_h2(size_t raw, zg_str host)
{
    static const unsigned char alpn_h2[] = { 2, 'h', '2' };
    return tls_wrap_alpn(raw, host, alpn_h2, sizeof(alpn_h2));
}

/* Length on success, SIZE_MAX when the caller's buffer is too small. */
size_t
zg_tls_alpn(uint8_t *ctx, uint8_t *buf, size_t cap)
{
    SSL *ssl = (SSL *)ctx;
    const unsigned char *proto = NULL;
    unsigned int len = 0;
    SSL_get0_alpn_selected(ssl, &proto, &len);
    if (!proto || len == 0) return 0;
    if (len > cap) return SIZE_MAX;
    memcpy(buf, proto, len);
    return (size_t)len;
}

int32_t
zg_tls_write(uint8_t *ctx, zg_str bytes)
{
    SSL *ssl = (SSL *)ctx;
    size_t sent = 0;
    while (sent < bytes.len) {
        size_t left = bytes.len - sent;
        int chunk = left > (size_t)INT_MAX ? INT_MAX : (int)left;
        int n = SSL_write(ssl, bytes.data + sent, chunk);
        if (n <= 0) {
            int err = SSL_get_error(ssl, n);
            if (err == SSL_ERROR_WANT_READ || err == SSL_ERROR_WANT_WRITE) continue;
            return 3; /* WriteFailed */
        }
        sent += (size_t)n;
    }
    return 0;
}

size_t
zg_tls_read(uint8_t *ctx, uint8_t *buf, size_t n)
{
    SSL *ssl = (SSL *)ctx;
    int chunk = n > (size_t)INT_MAX ? INT_MAX : (int)n;
    int rc;

    if (n == 0) return 0;
    for (;;) {
        rc = SSL_read(ssl, buf, chunk);
        if (rc > 0) return (size_t)rc;
        int err = SSL_get_error(ssl, rc);
        if (err == SSL_ERROR_ZERO_RETURN) return SIZE_MAX - 1;
        if (err != SSL_ERROR_WANT_READ && err != SSL_ERROR_WANT_WRITE)
            return SIZE_MAX;
    }
}

void
zg_tls_close(uint8_t *ctx)
{
    SSL *ssl = (SSL *)ctx;
    SSL_CTX *ssl_ctx = SSL_get_SSL_CTX(ssl);
    SSL_free(ssl);
    SSL_CTX_free(ssl_ctx);
}
