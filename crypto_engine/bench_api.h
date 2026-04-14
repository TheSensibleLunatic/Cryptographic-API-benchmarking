/**
 * bench_api.h — Unified C Benchmarking API
 *
 * Exposes run_aes_bench() and run_sha_bench() — each returning a BenchResult
 * struct populated with nanosecond-precision timing statistics and throughput.
 *
 * Timing uses clock_gettime(CLOCK_MONOTONIC) for high-resolution, monotonic
 * wall-clock measurement unaffected by NTP or system clock adjustments.
 */

#ifndef BENCH_API_H
#define BENCH_API_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* -------------------------------------------------------------------------
 * Result Structure
 *
 * All timing values are in nanoseconds.  Throughput is in MB/s (megabytes
 * per second, where 1 MB = 1,048,576 bytes).
 * ---------------------------------------------------------------------- */
typedef struct {
    double mean_ns;         /* Arithmetic mean latency per call (ns) */
    double min_ns;          /* Minimum observed latency (ns) */
    double max_ns;          /* Maximum observed latency (ns) */
    double stddev_ns;       /* Population standard deviation of latency (ns) */
    double throughput_mbps; /* Effective throughput in MB/s */
    int    iterations;      /* Number of benchmark iterations executed */
    size_t data_size;       /* Input data size in bytes */
} BenchResult;

/* -------------------------------------------------------------------------
 * AES-256-CBC Benchmark
 *
 * Allocates a buffer of @data_size_bytes, fills it with deterministic
 * pattern bytes, runs AES-256-CBC encryption @iterations times, and
 * returns timing statistics in a BenchResult.
 *
 * @data_size_bytes: Size of data to encrypt per call (bytes).
 * @iterations:      Number of timed encryption calls.
 *
 * Returns a BenchResult.  On allocation failure, all fields are 0.
 * ---------------------------------------------------------------------- */
BenchResult run_aes_bench(size_t data_size_bytes, int iterations);

/* -------------------------------------------------------------------------
 * SHA-256 Benchmark
 *
 * Allocates a buffer of @data_size_bytes, fills it with deterministic
 * pattern bytes, runs SHA-256 hashing @iterations times, and returns
 * timing statistics in a BenchResult.
 *
 * @data_size_bytes: Size of data to hash per call (bytes).
 * @iterations:      Number of timed hash calls.
 *
 * Returns a BenchResult.  On allocation failure, all fields are 0.
 * ---------------------------------------------------------------------- */
BenchResult run_sha_bench(size_t data_size_bytes, int iterations);

#ifdef __cplusplus
}
#endif

#endif /* BENCH_API_H */
