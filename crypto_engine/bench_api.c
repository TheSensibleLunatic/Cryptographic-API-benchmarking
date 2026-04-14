/**
 * bench_api.c — Unified C Benchmarking API Implementation
 *
 * Provides run_aes_bench() and run_sha_bench(), each of which:
 *   1. Allocates and fills a test buffer.
 *   2. Runs the target operation @iterations times.
 *   3. Collects per-call nanosecond timing via clock_gettime(CLOCK_MONOTONIC).
 *   4. Computes mean, min, max, stddev, and throughput (MB/s).
 *   5. Returns a populated BenchResult struct.
 *
 * Timing methodology:
 *   - clock_gettime(CLOCK_MONOTONIC) gives ~1 ns resolution on modern Linux.
 *   - Each measurement wraps a single crypto call to minimize noise.
 *   - A warm-up iteration (iteration 0) is excluded from statistics to
 *     avoid cold-cache effects skewing the mean.
 */

#include "bench_api.h"
#include "aes256.h"
#include "sha256.h"

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* =========================================================================
 * Timing helper — returns current time as nanoseconds since epoch
 * ====================================================================== */
static inline uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

/* =========================================================================
 * Statistics helpers
 * ====================================================================== */

static double compute_mean(const double *arr, int n) {
    double sum = 0.0;
    for (int i = 0; i < n; i++) sum += arr[i];
    return sum / (double)n;
}

static double compute_stddev(const double *arr, int n, double mean) {
    double sum_sq = 0.0;
    for (int i = 0; i < n; i++) {
        double diff = arr[i] - mean;
        sum_sq += diff * diff;
    }
    return sqrt(sum_sq / (double)n);
}

static double compute_min(const double *arr, int n) {
    double m = arr[0];
    for (int i = 1; i < n; i++) if (arr[i] < m) m = arr[i];
    return m;
}

static double compute_max(const double *arr, int n) {
    double m = arr[0];
    for (int i = 1; i < n; i++) if (arr[i] > m) m = arr[i];
    return m;
}

/* =========================================================================
 * AES-256-CBC Benchmark
 * ====================================================================== */

BenchResult run_aes_bench(size_t data_size_bytes, int iterations) {
    BenchResult result;
    memset(&result, 0, sizeof(result));

    if (data_size_bytes == 0 || iterations <= 0) return result;

    /* Fixed key and IV — deterministic, reproducible across runs */
    static const uint8_t KEY[AES256_KEY_SIZE] = {
        0x60,0x3d,0xeb,0x10,0x15,0xca,0x71,0xbe,
        0x2b,0x73,0xae,0xf0,0x85,0x7d,0x77,0x81,
        0x1f,0x35,0x2c,0x07,0x3b,0x61,0x08,0xd7,
        0x2d,0x98,0x10,0xa3,0x09,0x14,0xdf,0xf4
    };
    static const uint8_t IV[AES256_IV_SIZE] = {
        0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,
        0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f
    };

    /* Allocate input and output buffers */
    uint8_t *data = (uint8_t *)malloc(data_size_bytes);
    /* Output buffer: data + one extra AES block for PKCS#7 padding */
    uint8_t *out  = (uint8_t *)malloc(data_size_bytes + AES256_BLOCK_SIZE);
    /* Per-iteration latency samples (skip iteration 0 = warm-up) */
    double  *samples = (double *)malloc(sizeof(double) * iterations);

    if (!data || !out || !samples) goto cleanup_aes;

    /* Fill input with a deterministic byte pattern */
    for (size_t i = 0; i < data_size_bytes; i++)
        data[i] = (uint8_t)(i & 0xff);

    /* Warm-up + timed iterations */
    for (int iter = 0; iter < iterations; iter++) {
        size_t out_len = 0;
        uint64_t t0 = now_ns();
        aes256_bench_encrypt(data, data_size_bytes, KEY, IV, out, &out_len);
        uint64_t t1 = now_ns();
        samples[iter] = (double)(t1 - t0);
    }

    /* Compute statistics — skip first iteration (cold cache warm-up) */
    int stat_n = (iterations > 1) ? iterations - 1 : iterations;
    double *stat_samples = (iterations > 1) ? samples + 1 : samples;

    double mean   = compute_mean(stat_samples, stat_n);
    double stddev = compute_stddev(stat_samples, stat_n, mean);
    double min    = compute_min(stat_samples, stat_n);
    double max    = compute_max(stat_samples, stat_n);

    /*
     * Throughput (MB/s) = (data_size_bytes / 1048576) / (mean_ns / 1e9)
     *                   = data_size_bytes * 1e9 / (mean_ns * 1048576)
     */
    double throughput = (mean > 0.0)
        ? ((double)data_size_bytes * 1e9) / (mean * 1048576.0)
        : 0.0;

    result.mean_ns         = mean;
    result.min_ns          = min;
    result.max_ns          = max;
    result.stddev_ns       = stddev;
    result.throughput_mbps = throughput;
    result.iterations      = iterations;
    result.data_size       = data_size_bytes;

cleanup_aes:
    free(data);
    free(out);
    free(samples);
    return result;
}

/* =========================================================================
 * SHA-256 Benchmark
 * ====================================================================== */

BenchResult run_sha_bench(size_t data_size_bytes, int iterations) {
    BenchResult result;
    memset(&result, 0, sizeof(result));

    if (data_size_bytes == 0 || iterations <= 0) return result;

    uint8_t *data   = (uint8_t *)malloc(data_size_bytes);
    uint8_t  digest[SHA256_DIGEST_SIZE];
    double  *samples = (double *)malloc(sizeof(double) * iterations);

    if (!data || !samples) goto cleanup_sha;

    /* Fill input with a deterministic byte pattern */
    for (size_t i = 0; i < data_size_bytes; i++)
        data[i] = (uint8_t)((i * 7 + 13) & 0xff);

    /* Warm-up + timed iterations */
    for (int iter = 0; iter < iterations; iter++) {
        uint64_t t0 = now_ns();
        sha256_bench_hash(data, data_size_bytes, digest);
        uint64_t t1 = now_ns();
        samples[iter] = (double)(t1 - t0);
    }

    /* Compute statistics — skip first iteration (cold cache warm-up) */
    int stat_n = (iterations > 1) ? iterations - 1 : iterations;
    double *stat_samples = (iterations > 1) ? samples + 1 : samples;

    double mean   = compute_mean(stat_samples, stat_n);
    double stddev = compute_stddev(stat_samples, stat_n, mean);
    double min    = compute_min(stat_samples, stat_n);
    double max    = compute_max(stat_samples, stat_n);

    double throughput = (mean > 0.0)
        ? ((double)data_size_bytes * 1e9) / (mean * 1048576.0)
        : 0.0;

    result.mean_ns         = mean;
    result.min_ns          = min;
    result.max_ns          = max;
    result.stddev_ns       = stddev;
    result.throughput_mbps = throughput;
    result.iterations      = iterations;
    result.data_size       = data_size_bytes;

cleanup_sha:
    free(data);
    free(samples);
    return result;
}
