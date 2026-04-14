/**
 * aes256.c — Pure C AES-256-CBC Implementation
 *
 * Implements the full AES-256 specification (FIPS 197):
 *   - 14-round key schedule (KeyExpansion)
 *   - SubBytes, ShiftRows, MixColumns, AddRoundKey (forward cipher)
 *   - Inverse SubBytes, InvShiftRows, InvMixColumns (inverse cipher)
 *   - CBC mode using XOR chaining
 *   - PKCS#7 padding / unpadding
 *
 * SECURITY NOTE: Not hardened against side-channel attacks.
 *                Use OpenSSL for production cryptography.
 */

#include "aes256.h"
#include <string.h>
#include <stdlib.h>

/* =========================================================================
 * AES S-Box and Inverse S-Box (FIPS 197, Figure 7)
 * ====================================================================== */
static const uint8_t SBOX[256] = {
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
};

static const uint8_t INV_SBOX[256] = {
    0x52,0x09,0x6a,0xd5,0x30,0x36,0xa5,0x38,0xbf,0x40,0xa3,0x9e,0x81,0xf3,0xd7,0xfb,
    0x7c,0xe3,0x39,0x82,0x9b,0x2f,0xff,0x87,0x34,0x8e,0x43,0x44,0xc4,0xde,0xe9,0xcb,
    0x54,0x7b,0x94,0x32,0xa6,0xc2,0x23,0x3d,0xee,0x4c,0x95,0x0b,0x42,0xfa,0xc3,0x4e,
    0x08,0x2e,0xa1,0x66,0x28,0xd9,0x24,0xb2,0x76,0x5b,0xa2,0x49,0x6d,0x8b,0xd1,0x25,
    0x72,0xf8,0xf6,0x64,0x86,0x68,0x98,0x16,0xd4,0xa4,0x5c,0xcc,0x5d,0x65,0xb6,0x92,
    0x6c,0x70,0x48,0x50,0xfd,0xed,0xb9,0xda,0x5e,0x15,0x46,0x57,0xa7,0x8d,0x9d,0x84,
    0x90,0xd8,0xab,0x00,0x8c,0xbc,0xd3,0x0a,0xf7,0xe4,0x58,0x05,0xb8,0xb3,0x45,0x06,
    0xd0,0x2c,0x1e,0x8f,0xca,0x3f,0x0f,0x02,0xc1,0xaf,0xbd,0x03,0x01,0x13,0x8a,0x6b,
    0x3a,0x91,0x11,0x41,0x4f,0x67,0xdc,0xea,0x97,0xf2,0xcf,0xce,0xf0,0xb4,0xe6,0x73,
    0x96,0xac,0x74,0x22,0xe7,0xad,0x35,0x85,0xe2,0xf9,0x37,0xe8,0x1c,0x75,0xdf,0x6e,
    0x47,0xf1,0x1a,0x71,0x1d,0x29,0xc5,0x89,0x6f,0xb7,0x62,0x0e,0xaa,0x18,0xbe,0x1b,
    0xfc,0x56,0x3e,0x4b,0xc6,0xd2,0x79,0x20,0x9a,0xdb,0xc0,0xfe,0x78,0xcd,0x5a,0xf4,
    0x1f,0xdd,0xa8,0x33,0x88,0x07,0xc7,0x31,0xb1,0x12,0x10,0x59,0x27,0x80,0xec,0x5f,
    0x60,0x51,0x7f,0xa9,0x19,0xb5,0x4a,0x0d,0x2d,0xe5,0x7a,0x9f,0x93,0xc9,0x9c,0xef,
    0xa0,0xe0,0x3b,0x4d,0xae,0x2a,0xf5,0xb0,0xc8,0xeb,0xbb,0x3c,0x83,0x53,0x99,0x61,
    0x17,0x2b,0x04,0x7e,0xba,0x77,0xd6,0x26,0xe1,0x69,0x14,0x63,0x55,0x21,0x0c,0x7d
};

/* =========================================================================
 * Rcon table for key expansion (FIPS 197, Table 5)
 * ====================================================================== */
static const uint8_t RCON[11] = {
    0x00, /* unused, 1-indexed */
    0x01, 0x02, 0x04, 0x08, 0x10,
    0x20, 0x40, 0x80, 0x1b, 0x36
};

/* =========================================================================
 * GF(2^8) Multiplication helpers (for MixColumns / InvMixColumns)
 * ====================================================================== */

/* Multiply by 2 in GF(2^8) with irreducible polynomial x^8+x^4+x^3+x+1 */
static inline uint8_t xtime(uint8_t a) {
    return (uint8_t)(((a << 1) ^ ((a >> 7) ? 0x1b : 0x00)) & 0xff);
}

/* Multiply by 3 in GF(2^8) */
static inline uint8_t xtime3(uint8_t a) { return xtime(a) ^ a; }

/* Multiply by 9, 11, 13, 14 in GF(2^8) — needed for InvMixColumns */
static inline uint8_t gmul(uint8_t a, uint8_t b) {
    uint8_t p = 0;
    for (int i = 0; i < 8; i++) {
        if (b & 1) p ^= a;
        uint8_t hi = a & 0x80;
        a <<= 1;
        if (hi) a ^= 0x1b;
        b >>= 1;
    }
    return p;
}

/* =========================================================================
 * AES State helpers — the state is a 4×4 byte matrix stored column-major
 * ====================================================================== */

static inline void load_state(uint8_t state[4][4], const uint8_t *in) {
    for (int c = 0; c < 4; c++)
        for (int r = 0; r < 4; r++)
            state[r][c] = in[c * 4 + r];
}

static inline void store_state(uint8_t *out, const uint8_t state[4][4]) {
    for (int c = 0; c < 4; c++)
        for (int r = 0; r < 4; r++)
            out[c * 4 + r] = state[r][c];
}

/* =========================================================================
 * AES Forward Round Operations
 * ====================================================================== */

static void sub_bytes(uint8_t state[4][4]) {
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++)
            state[r][c] = SBOX[state[r][c]];
}

static void shift_rows(uint8_t state[4][4]) {
    uint8_t tmp;
    /* Row 1: shift left by 1 */
    tmp = state[1][0]; state[1][0] = state[1][1]; state[1][1] = state[1][2];
    state[1][2] = state[1][3]; state[1][3] = tmp;
    /* Row 2: shift left by 2 */
    tmp = state[2][0]; state[2][0] = state[2][2]; state[2][2] = tmp;
    tmp = state[2][1]; state[2][1] = state[2][3]; state[2][3] = tmp;
    /* Row 3: shift left by 3 (= right by 1) */
    tmp = state[3][3]; state[3][3] = state[3][2]; state[3][2] = state[3][1];
    state[3][1] = state[3][0]; state[3][0] = tmp;
}

static void mix_columns(uint8_t state[4][4]) {
    for (int c = 0; c < 4; c++) {
        uint8_t s0 = state[0][c], s1 = state[1][c];
        uint8_t s2 = state[2][c], s3 = state[3][c];
        state[0][c] = xtime(s0) ^ xtime3(s1) ^ s2 ^ s3;
        state[1][c] = s0 ^ xtime(s1) ^ xtime3(s2) ^ s3;
        state[2][c] = s0 ^ s1 ^ xtime(s2) ^ xtime3(s3);
        state[3][c] = xtime3(s0) ^ s1 ^ s2 ^ xtime(s3);
    }
}

static void add_round_key(uint8_t state[4][4], const uint32_t *rk) {
    for (int c = 0; c < 4; c++) {
        uint32_t word = rk[c];
        state[0][c] ^= (uint8_t)(word >> 24);
        state[1][c] ^= (uint8_t)(word >> 16);
        state[2][c] ^= (uint8_t)(word >>  8);
        state[3][c] ^= (uint8_t)(word);
    }
}

/* =========================================================================
 * AES Inverse Round Operations
 * ====================================================================== */

static void inv_sub_bytes(uint8_t state[4][4]) {
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++)
            state[r][c] = INV_SBOX[state[r][c]];
}

static void inv_shift_rows(uint8_t state[4][4]) {
    uint8_t tmp;
    /* Row 1: shift right by 1 */
    tmp = state[1][3]; state[1][3] = state[1][2]; state[1][2] = state[1][1];
    state[1][1] = state[1][0]; state[1][0] = tmp;
    /* Row 2: shift right by 2 */
    tmp = state[2][0]; state[2][0] = state[2][2]; state[2][2] = tmp;
    tmp = state[2][1]; state[2][1] = state[2][3]; state[2][3] = tmp;
    /* Row 3: shift right by 3 (= left by 1) */
    tmp = state[3][0]; state[3][0] = state[3][1]; state[3][1] = state[3][2];
    state[3][2] = state[3][3]; state[3][3] = tmp;
}

static void inv_mix_columns(uint8_t state[4][4]) {
    for (int c = 0; c < 4; c++) {
        uint8_t s0 = state[0][c], s1 = state[1][c];
        uint8_t s2 = state[2][c], s3 = state[3][c];
        state[0][c] = gmul(s0,14) ^ gmul(s1,11) ^ gmul(s2,13) ^ gmul(s3,9);
        state[1][c] = gmul(s0, 9) ^ gmul(s1,14) ^ gmul(s2,11) ^ gmul(s3,13);
        state[2][c] = gmul(s0,13) ^ gmul(s1, 9) ^ gmul(s2,14) ^ gmul(s3,11);
        state[3][c] = gmul(s0,11) ^ gmul(s1,13) ^ gmul(s2, 9) ^ gmul(s3,14);
    }
}

/* =========================================================================
 * Key Expansion (FIPS 197, Section 5.2)
 *
 * AES-256: Nk=8, Nr=14, total words = (Nr+1)*4 = 60
 * ====================================================================== */

static inline uint32_t sub_word(uint32_t w) {
    return ((uint32_t)SBOX[(w >> 24) & 0xff] << 24) |
           ((uint32_t)SBOX[(w >> 16) & 0xff] << 16) |
           ((uint32_t)SBOX[(w >>  8) & 0xff] <<  8) |
           ((uint32_t)SBOX[(w      ) & 0xff]);
}

static inline uint32_t rot_word(uint32_t w) {
    return (w << 8) | (w >> 24);
}

static inline uint32_t bytes_to_word(const uint8_t *b) {
    return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) |
           ((uint32_t)b[2] <<  8) | ((uint32_t)b[3]);
}

void aes256_key_expand(AES256Ctx *ctx, const uint8_t key[AES256_KEY_SIZE]) {
    const int Nk = 8;  /* words in key */
    const int Nr = 14; /* rounds */
    const int total = (Nr + 1) * 4; /* 60 words */
    uint32_t *W = ctx->round_keys;

    /* Load key into first Nk words */
    for (int i = 0; i < Nk; i++)
        W[i] = bytes_to_word(key + i * 4);

    /* Expand remaining words */
    for (int i = Nk; i < total; i++) {
        uint32_t temp = W[i - 1];
        if (i % Nk == 0) {
            temp = sub_word(rot_word(temp)) ^ ((uint32_t)RCON[i / Nk] << 24);
        } else if (i % Nk == 4) {
            temp = sub_word(temp);
        }
        W[i] = W[i - Nk] ^ temp;
    }

    /*
     * Build the inverse key schedule for decryption.
     * The inverse schedule is the encryption schedule with InvMixColumns
     * applied to all round keys except the first and last.
     */
    uint32_t *WI = ctx->round_keys_inv;
    /* Copy round keys */
    memcpy(WI, W, sizeof(uint32_t) * total);

    /* Apply InvMixColumns to middle round keys */
    for (int round = 1; round < Nr; round++) {
        uint8_t tmp[AES256_BLOCK_SIZE];
        uint8_t state[4][4];
        /* Extract 4 words = one round key block */
        for (int c = 0; c < 4; c++) {
            uint32_t word = WI[round * 4 + c];
            tmp[c * 4 + 0] = (uint8_t)(word >> 24);
            tmp[c * 4 + 1] = (uint8_t)(word >> 16);
            tmp[c * 4 + 2] = (uint8_t)(word >>  8);
            tmp[c * 4 + 3] = (uint8_t)(word);
        }
        load_state(state, tmp);
        inv_mix_columns(state);
        store_state(tmp, state);
        for (int c = 0; c < 4; c++) {
            WI[round * 4 + c] = bytes_to_word(tmp + c * 4);
        }
    }
}

/* =========================================================================
 * AES-256 Block Encryption (Forward Cipher — FIPS 197, Section 5.1)
 * ====================================================================== */

void aes256_encrypt_block(const AES256Ctx *ctx,
                          const uint8_t in[AES256_BLOCK_SIZE],
                          uint8_t out[AES256_BLOCK_SIZE]) {
    uint8_t state[4][4];
    load_state(state, in);

    /* Initial round key addition */
    add_round_key(state, ctx->round_keys);

    /* Rounds 1 .. Nr-1 */
    for (int round = 1; round < AES256_NUM_ROUNDS; round++) {
        sub_bytes(state);
        shift_rows(state);
        mix_columns(state);
        add_round_key(state, ctx->round_keys + round * 4);
    }

    /* Final round (no MixColumns) */
    sub_bytes(state);
    shift_rows(state);
    add_round_key(state, ctx->round_keys + AES256_NUM_ROUNDS * 4);

    store_state(out, state);
}

/* =========================================================================
 * AES-256 Block Decryption (Inverse Cipher — FIPS 197, Section 5.3)
 * ====================================================================== */

void aes256_decrypt_block(const AES256Ctx *ctx,
                          const uint8_t in[AES256_BLOCK_SIZE],
                          uint8_t out[AES256_BLOCK_SIZE]) {
    uint8_t state[4][4];
    load_state(state, in);

    /* Initial round key addition (last round key first) */
    add_round_key(state, ctx->round_keys + AES256_NUM_ROUNDS * 4);

    /* Rounds Nr-1 .. 1 */
    for (int round = AES256_NUM_ROUNDS - 1; round >= 1; round--) {
        inv_shift_rows(state);
        inv_sub_bytes(state);
        add_round_key(state, ctx->round_keys + round * 4);
        inv_mix_columns(state);
    }

    /* Final round */
    inv_shift_rows(state);
    inv_sub_bytes(state);
    add_round_key(state, ctx->round_keys);

    store_state(out, state);
}

/* =========================================================================
 * CBC Mode
 * ====================================================================== */

int aes256_cbc_encrypt(const AES256Ctx *ctx,
                       const uint8_t iv[AES256_IV_SIZE],
                       const uint8_t *plaintext,
                       uint8_t *ciphertext,
                       size_t len) {
    if (len % AES256_BLOCK_SIZE != 0) return -1;

    uint8_t prev[AES256_BLOCK_SIZE];
    memcpy(prev, iv, AES256_BLOCK_SIZE);

    for (size_t offset = 0; offset < len; offset += AES256_BLOCK_SIZE) {
        uint8_t block[AES256_BLOCK_SIZE];
        /* XOR plaintext with previous ciphertext block (CBC chaining) */
        for (int i = 0; i < AES256_BLOCK_SIZE; i++)
            block[i] = plaintext[offset + i] ^ prev[i];
        aes256_encrypt_block(ctx, block, ciphertext + offset);
        memcpy(prev, ciphertext + offset, AES256_BLOCK_SIZE);
    }
    return 0;
}

int aes256_cbc_decrypt(const AES256Ctx *ctx,
                       const uint8_t iv[AES256_IV_SIZE],
                       const uint8_t *ciphertext,
                       uint8_t *plaintext,
                       size_t len) {
    if (len % AES256_BLOCK_SIZE != 0) return -1;

    uint8_t prev[AES256_BLOCK_SIZE];
    memcpy(prev, iv, AES256_BLOCK_SIZE);

    for (size_t offset = 0; offset < len; offset += AES256_BLOCK_SIZE) {
        uint8_t block[AES256_BLOCK_SIZE];
        aes256_decrypt_block(ctx, ciphertext + offset, block);
        /* XOR with previous ciphertext block */
        for (int i = 0; i < AES256_BLOCK_SIZE; i++)
            plaintext[offset + i] = block[i] ^ prev[i];
        memcpy(prev, ciphertext + offset, AES256_BLOCK_SIZE);
    }
    return 0;
}

/* =========================================================================
 * PKCS#7 Padding
 * ====================================================================== */

void aes256_pkcs7_pad(const uint8_t *in, size_t in_len,
                      uint8_t *out, size_t *out_len) {
    size_t pad_len = AES256_BLOCK_SIZE - (in_len % AES256_BLOCK_SIZE);
    *out_len = in_len + pad_len;
    memcpy(out, in, in_len);
    memset(out + in_len, (int)pad_len, pad_len);
}

int aes256_pkcs7_unpad(const uint8_t *buf, size_t buf_len, size_t *out_len) {
    if (buf_len == 0 || buf_len % AES256_BLOCK_SIZE != 0) return -1;
    uint8_t pad_byte = buf[buf_len - 1];
    if (pad_byte == 0 || pad_byte > AES256_BLOCK_SIZE) return -1;
    for (size_t i = buf_len - pad_byte; i < buf_len; i++) {
        if (buf[i] != pad_byte) return -1;
    }
    *out_len = buf_len - pad_byte;
    return 0;
}

/* =========================================================================
 * Benchmarking Entry Point
 * ====================================================================== */

int aes256_bench_encrypt(const uint8_t *data, size_t len,
                         const uint8_t key[AES256_KEY_SIZE],
                         const uint8_t iv[AES256_IV_SIZE],
                         uint8_t *out, size_t *out_len) {
    /* Allocate padded input buffer: max extra block for PKCS#7 */
    size_t padded_len = 0;
    uint8_t *padded = (uint8_t *)malloc(len + AES256_BLOCK_SIZE);
    if (!padded) return -1;

    aes256_pkcs7_pad(data, len, padded, &padded_len);

    AES256Ctx ctx;
    aes256_key_expand(&ctx, key);

    int ret = aes256_cbc_encrypt(&ctx, iv, padded, out, padded_len);
    free(padded);

    if (ret == 0) *out_len = padded_len;
    return ret;
}
