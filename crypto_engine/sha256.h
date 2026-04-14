/**
 * sha256.h — Pure C SHA-256 Implementation
 *
 * Full SHA-256 compression function per FIPS 180-4.
 * Provides a benchmarking entry point sha256_bench_hash().
 *
 * SECURITY NOTE: This implementation is for benchmarking/educational use only.
 *                For production use, use a vetted library (e.g., OpenSSL).
 */

#ifndef SHA256_H
#define SHA256_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -------------------------------------------------------------------------
 * Constants
 * ---------------------------------------------------------------------- */
#define SHA256_DIGEST_SIZE   32  /* 256 bits */
#define SHA256_BLOCK_SIZE    64  /* 512-bit message block */

/* -------------------------------------------------------------------------
 * SHA-256 Context
 * ---------------------------------------------------------------------- */
typedef struct {
    uint32_t state[8];          /* Current hash state (H0..H7) */
    uint64_t bit_count;         /* Total number of bits processed */
    uint8_t  buffer[SHA256_BLOCK_SIZE]; /* Partial block buffer */
    size_t   buf_len;           /* Bytes currently in buffer */
} SHA256Ctx;

/* -------------------------------------------------------------------------
 * SHA-256 API
 * ---------------------------------------------------------------------- */

/**
 * sha256_init - Initialize a SHA-256 context with FIPS 180-4 initial values.
 * @ctx: Context to initialize.
 */
void sha256_init(SHA256Ctx *ctx);

/**
 * sha256_update - Feed data into the running hash computation.
 *
 * @ctx:  SHA-256 context (must have been sha256_init'd).
 * @data: Input bytes.
 * @len:  Number of bytes in @data.
 */
void sha256_update(SHA256Ctx *ctx, const uint8_t *data, size_t len);

/**
 * sha256_final - Finalize the hash and write the 32-byte digest.
 *
 * Applies the SHA-256 length encoding / padding and produces the digest.
 * The context is unusable after this call.
 *
 * @ctx:    SHA-256 context.
 * @digest: 32-byte output buffer.
 */
void sha256_final(SHA256Ctx *ctx, uint8_t digest[SHA256_DIGEST_SIZE]);

/* -------------------------------------------------------------------------
 * Convenience: hash a single buffer
 * ---------------------------------------------------------------------- */

/**
 * sha256_hash - Compute SHA-256 of a complete buffer.
 *
 * @data:   Input bytes.
 * @len:    Input length.
 * @digest: 32-byte output buffer.
 */
void sha256_hash(const uint8_t *data, size_t len,
                 uint8_t digest[SHA256_DIGEST_SIZE]);

/* -------------------------------------------------------------------------
 * Benchmarking Entry Point
 * ---------------------------------------------------------------------- */

/**
 * sha256_bench_hash - Benchmarking-oriented SHA-256 hash.
 *
 * Computes SHA-256 over @data of length @len and writes the 32-byte
 * digest to @digest.  Designed to be called in a tight timing loop with
 * no persistent state across calls.
 *
 * @data:   Input byte buffer.
 * @len:    Number of bytes.
 * @digest: 32-byte output buffer.
 */
void sha256_bench_hash(const uint8_t *data, size_t len,
                       uint8_t digest[SHA256_DIGEST_SIZE]);

#ifdef __cplusplus
}
#endif

#endif /* SHA256_H */
