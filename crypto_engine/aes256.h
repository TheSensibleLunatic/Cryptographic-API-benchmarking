/**
 * aes256.h — Pure C AES-256-CBC Implementation
 *
 * Full 14-round AES-256 key schedule, CBC mode encryption/decryption,
 * PKCS#7 padding, and a dedicated benchmarking entry point.
 *
 * NOTE: This implementation is for benchmarking and educational use ONLY.
 *       It is NOT hardened against side-channel attacks (timing, cache).
 *       For production cryptography, use a vetted library (e.g., OpenSSL).
 */

#ifndef AES256_H
#define AES256_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -------------------------------------------------------------------------
 * Constants
 * ---------------------------------------------------------------------- */
#define AES256_KEY_SIZE     32  /* 256 bits */
#define AES256_BLOCK_SIZE   16  /* 128 bits */
#define AES256_IV_SIZE      16  /* 128 bits */
#define AES256_NUM_ROUNDS   14
#define AES256_KEY_SCHEDULE_WORDS  60  /* (Nr+1) * Nb = 15 * 4 */

/* -------------------------------------------------------------------------
 * Key Schedule Context
 * ---------------------------------------------------------------------- */
typedef struct {
    uint32_t round_keys[AES256_KEY_SCHEDULE_WORDS]; /* Expanded key schedule */
    uint32_t round_keys_inv[AES256_KEY_SCHEDULE_WORDS]; /* Inverse key schedule */
} AES256Ctx;

/* -------------------------------------------------------------------------
 * Key Expansion
 * ---------------------------------------------------------------------- */

/**
 * aes256_key_expand - Expand a 256-bit key into the full round key schedule.
 *
 * @ctx: Pointer to an AES256Ctx to be populated.
 * @key: 32-byte (256-bit) key material.
 */
void aes256_key_expand(AES256Ctx *ctx, const uint8_t key[AES256_KEY_SIZE]);

/* -------------------------------------------------------------------------
 * Block-level Encrypt / Decrypt (ECB, one 16-byte block)
 * ---------------------------------------------------------------------- */

/**
 * aes256_encrypt_block - Encrypt a single 16-byte block (in-place, ECB).
 *
 * @ctx:      Expanded key context.
 * @in:       16-byte plaintext block.
 * @out:      16-byte ciphertext block (may alias in).
 */
void aes256_encrypt_block(const AES256Ctx *ctx,
                          const uint8_t in[AES256_BLOCK_SIZE],
                          uint8_t out[AES256_BLOCK_SIZE]);

/**
 * aes256_decrypt_block - Decrypt a single 16-byte block (in-place, ECB).
 *
 * @ctx:      Expanded key context.
 * @in:       16-byte ciphertext block.
 * @out:      16-byte plaintext block (may alias in).
 */
void aes256_decrypt_block(const AES256Ctx *ctx,
                          const uint8_t in[AES256_BLOCK_SIZE],
                          uint8_t out[AES256_BLOCK_SIZE]);

/* -------------------------------------------------------------------------
 * CBC Mode Encrypt / Decrypt
 * ---------------------------------------------------------------------- */

/**
 * aes256_cbc_encrypt - Encrypt buffer in CBC mode.
 *
 * @ctx:         Expanded key context.
 * @iv:          16-byte initialisation vector (not modified).
 * @plaintext:   Input buffer; must be a multiple of AES256_BLOCK_SIZE.
 * @ciphertext:  Output buffer (same length as plaintext).
 * @len:         Number of bytes (must be % AES256_BLOCK_SIZE == 0).
 *
 * Returns 0 on success, -1 if len is not block-aligned.
 */
int aes256_cbc_encrypt(const AES256Ctx *ctx,
                       const uint8_t iv[AES256_IV_SIZE],
                       const uint8_t *plaintext,
                       uint8_t *ciphertext,
                       size_t len);

/**
 * aes256_cbc_decrypt - Decrypt buffer in CBC mode.
 *
 * @ctx:         Expanded key context.
 * @iv:          16-byte initialisation vector (not modified).
 * @ciphertext:  Input buffer; must be a multiple of AES256_BLOCK_SIZE.
 * @plaintext:   Output buffer (same length as ciphertext).
 * @len:         Number of bytes (must be % AES256_BLOCK_SIZE == 0).
 *
 * Returns 0 on success, -1 if len is not block-aligned.
 */
int aes256_cbc_decrypt(const AES256Ctx *ctx,
                       const uint8_t iv[AES256_IV_SIZE],
                       const uint8_t *ciphertext,
                       uint8_t *plaintext,
                       size_t len);

/* -------------------------------------------------------------------------
 * PKCS#7 Padding Helpers
 * ---------------------------------------------------------------------- */

/**
 * aes256_pkcs7_pad - Add PKCS#7 padding to plaintext.
 *
 * @in:        Input plaintext buffer.
 * @in_len:    Length of plaintext in bytes.
 * @out:       Output buffer; must be at least in_len + AES256_BLOCK_SIZE bytes.
 * @out_len:   Set to the padded length on return.
 */
void aes256_pkcs7_pad(const uint8_t *in, size_t in_len,
                      uint8_t *out, size_t *out_len);

/**
 * aes256_pkcs7_unpad - Remove PKCS#7 padding after decryption.
 *
 * @buf:      Buffer containing decrypted data with PKCS#7 padding.
 * @buf_len:  Length of buffer (block-aligned).
 * @out_len:  Set to the unpadded length on return.
 *
 * Returns 0 on success, -1 if padding is invalid.
 */
int aes256_pkcs7_unpad(const uint8_t *buf, size_t buf_len, size_t *out_len);

/* -------------------------------------------------------------------------
 * Benchmarking Entry Point
 * ---------------------------------------------------------------------- */

/**
 * aes256_bench_encrypt - Benchmarking-oriented AES-256-CBC encryption.
 *
 * Handles PKCS#7 padding internally, performs key expansion, and encrypts
 * the given data buffer.  Designed to be called in a tight timing loop.
 *
 * @data:       Plaintext input (any length).
 * @len:        Number of bytes in @data.
 * @key:        32-byte AES-256 key.
 * @iv:         16-byte initialisation vector.
 * @out:        Output buffer; must be at least (len + AES256_BLOCK_SIZE) bytes.
 * @out_len:    Set to the number of ciphertext bytes written.
 *
 * Returns 0 on success, -1 on failure.
 */
int aes256_bench_encrypt(const uint8_t *data, size_t len,
                         const uint8_t key[AES256_KEY_SIZE],
                         const uint8_t iv[AES256_IV_SIZE],
                         uint8_t *out, size_t *out_len);

#ifdef __cplusplus
}
#endif

#endif /* AES256_H */
