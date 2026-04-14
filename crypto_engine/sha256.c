/**
 * sha256.c — Pure C SHA-256 Implementation (FIPS 180-4)
 *
 * Implements the full SHA-256 compression function, streaming update/final
 * API, and a dedicated benchmarking entry point sha256_bench_hash().
 *
 * SECURITY NOTE: Not hardened against side-channel attacks.
 *                Use a vetted library for production cryptography.
 */

#include "sha256.h"
#include <string.h>

/* =========================================================================
 * SHA-256 Constants — first 32 bits of fractional parts of cube roots
 * of the first 64 prime numbers (FIPS 180-4, Section 4.2.2)
 * ====================================================================== */
static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

/* =========================================================================
 * Initial Hash Values — first 32 bits of fractional parts of square roots
 * of the first 8 prime numbers (FIPS 180-4, Section 5.3.3)
 * ====================================================================== */
static const uint32_t H0[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
};

/* =========================================================================
 * Bit-rotation and logical functions (FIPS 180-4, Section 4.1.2)
 * ====================================================================== */
#define ROTR(x, n)  (((x) >> (n)) | ((x) << (32 - (n))))
#define SHR(x,  n)  ((x) >> (n))

/* Σ (capital sigma) functions */
#define SIGMA0(x)   (ROTR(x,  2) ^ ROTR(x, 13) ^ ROTR(x, 22))
#define SIGMA1(x)   (ROTR(x,  6) ^ ROTR(x, 11) ^ ROTR(x, 25))

/* σ (lower-case sigma) functions */
#define sigma0(x)   (ROTR(x,  7) ^ ROTR(x, 18) ^ SHR(x,   3))
#define sigma1(x)   (ROTR(x, 17) ^ ROTR(x, 19) ^ SHR(x,  10))

/* Choice and majority functions */
#define Ch(x, y, z)  (((x) & (y)) ^ (~(x) & (z)))
#define Maj(x, y, z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))

/* =========================================================================
 * Big-endian helpers
 * ====================================================================== */
static inline uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] <<  8) | ((uint32_t)p[3]);
}

static inline void put_be32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >>  8); p[3] = (uint8_t)(v);
}

static inline void put_be64(uint8_t *p, uint64_t v) {
    p[0] = (uint8_t)(v >> 56); p[1] = (uint8_t)(v >> 48);
    p[2] = (uint8_t)(v >> 40); p[3] = (uint8_t)(v >> 32);
    p[4] = (uint8_t)(v >> 24); p[5] = (uint8_t)(v >> 16);
    p[6] = (uint8_t)(v >>  8); p[7] = (uint8_t)(v);
}

/* =========================================================================
 * SHA-256 Block Compression (FIPS 180-4, Section 6.2.2)
 *
 * Processes a single 64-byte (512-bit) message block and updates the
 * 8-word (256-bit) hash state in-place.
 * ====================================================================== */
static void sha256_compress(uint32_t state[8], const uint8_t block[SHA256_BLOCK_SIZE]) {
    uint32_t W[64];  /* Message schedule */
    uint32_t a, b, c, d, e, f, g, h;
    uint32_t T1, T2;

    /* Prepare message schedule — first 16 words from block data */
    for (int t = 0; t < 16; t++)
        W[t] = be32(block + t * 4);

    /* Extend message schedule to 64 words */
    for (int t = 16; t < 64; t++)
        W[t] = sigma1(W[t - 2]) + W[t - 7] + sigma0(W[t - 15]) + W[t - 16];

    /* Initialize working variables from current hash state */
    a = state[0]; b = state[1]; c = state[2]; d = state[3];
    e = state[4]; f = state[5]; g = state[6]; h = state[7];

    /* 64 rounds of the SHA-256 compression */
    for (int t = 0; t < 64; t++) {
        T1 = h + SIGMA1(e) + Ch(e, f, g) + K[t] + W[t];
        T2 = SIGMA0(a) + Maj(a, b, c);
        h = g; g = f; f = e; e = d + T1;
        d = c; c = b; b = a; a = T1 + T2;
    }

    /* Add the compressed chunk to the current hash value */
    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

/* =========================================================================
 * Public API
 * ====================================================================== */

void sha256_init(SHA256Ctx *ctx) {
    memcpy(ctx->state, H0, sizeof(H0));
    ctx->bit_count = 0;
    ctx->buf_len = 0;
    memset(ctx->buffer, 0, SHA256_BLOCK_SIZE);
}

void sha256_update(SHA256Ctx *ctx, const uint8_t *data, size_t len) {
    size_t remaining = len;
    const uint8_t *ptr = data;

    /* Update bit count */
    ctx->bit_count += (uint64_t)len * 8;

    /* If there is data in the buffer, try to fill it first */
    if (ctx->buf_len > 0) {
        size_t space = SHA256_BLOCK_SIZE - ctx->buf_len;
        size_t copy  = (remaining < space) ? remaining : space;
        memcpy(ctx->buffer + ctx->buf_len, ptr, copy);
        ctx->buf_len += copy;
        ptr += copy;
        remaining -= copy;

        if (ctx->buf_len == SHA256_BLOCK_SIZE) {
            sha256_compress(ctx->state, ctx->buffer);
            ctx->buf_len = 0;
        }
    }

    /* Process full blocks directly from the input */
    while (remaining >= SHA256_BLOCK_SIZE) {
        sha256_compress(ctx->state, ptr);
        ptr += SHA256_BLOCK_SIZE;
        remaining -= SHA256_BLOCK_SIZE;
    }

    /* Buffer any remaining bytes */
    if (remaining > 0) {
        memcpy(ctx->buffer, ptr, remaining);
        ctx->buf_len = remaining;
    }
}

void sha256_final(SHA256Ctx *ctx, uint8_t digest[SHA256_DIGEST_SIZE]) {
    /*
     * SHA-256 padding (FIPS 180-4, Section 5.1.1):
     *   1. Append bit '1' (0x80 byte).
     *   2. Append zero bytes until message length ≡ 56 (mod 64).
     *   3. Append original message length as big-endian 64-bit integer.
     */
    uint64_t total_bits = ctx->bit_count;
    size_t   pad_start  = ctx->buf_len;

    /* Append 0x80 */
    ctx->buffer[pad_start++] = 0x80;
    ctx->buf_len = pad_start;

    /* If we can't fit the 8-byte length in this block, flush first */
    if (pad_start > 56) {
        memset(ctx->buffer + pad_start, 0, SHA256_BLOCK_SIZE - pad_start);
        sha256_compress(ctx->state, ctx->buffer);
        memset(ctx->buffer, 0, SHA256_BLOCK_SIZE);
    } else {
        memset(ctx->buffer + pad_start, 0, 56 - pad_start);
    }

    /* Append bit length as 64-bit big-endian */
    put_be64(ctx->buffer + 56, total_bits);
    sha256_compress(ctx->state, ctx->buffer);

    /* Write the digest in big-endian order */
    for (int i = 0; i < 8; i++)
        put_be32(digest + i * 4, ctx->state[i]);
}

void sha256_hash(const uint8_t *data, size_t len,
                 uint8_t digest[SHA256_DIGEST_SIZE]) {
    SHA256Ctx ctx;
    sha256_init(&ctx);
    sha256_update(&ctx, data, len);
    sha256_final(&ctx, digest);
}

/* =========================================================================
 * Benchmarking Entry Point
 *
 * Stateless wrapper: each call creates a fresh context, digests the input,
 * and writes the 32-byte digest.  This is the function called in tight
 * timing loops by the C bench API.
 * ====================================================================== */
void sha256_bench_hash(const uint8_t *data, size_t len,
                       uint8_t digest[SHA256_DIGEST_SIZE]) {
    sha256_hash(data, len, digest);
}
