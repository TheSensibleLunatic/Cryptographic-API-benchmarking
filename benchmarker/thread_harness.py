"""
benchmarker/thread_harness.py — Concurrency engine

Runs benchmark operations concurrently across a configurable list of thread
or process counts.  Supports two parallelism modes:

    threading   — concurrent.futures.ThreadPoolExecutor (subject to Python GIL)
    multiprocessing — multiprocessing.Pool (true parallelism, no GIL)

Main entry point:
    run_concurrent_bench(algo, data_size, thread_counts, iterations_per_thread,
                         mode="threading") -> list[SweepResult]

The C library's crypto functions release the GIL naturally (they are pure C
with no Python calls), so the threading mode can approach true parallelism
for CPU-bound crypto workloads.  The multiprocessing mode is provided for
comparison and bypasses the GIL entirely.
"""

from __future__ import annotations

import math
import multiprocessing
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional

from benchmarker.ffi_bridge import BenchResultPy, run_aes_bench, run_sha_bench
from benchmarker.session import SweepResult

# ---------------------------------------------------------------------------
# Internal per-worker result
# ---------------------------------------------------------------------------


@dataclass
class _WorkerResult:
    """Raw result from a single worker thread/process."""

    thread_id: int
    latency_ns: float  # mean latency reported by the C bench for this worker
    throughput_mbps: float
    min_ns: float
    max_ns: float
    stddev_ns: float
    iterations: int
    data_size: int
    wall_time_ns: int  # wall-clock time measured in Python (perf_counter_ns)


# ---------------------------------------------------------------------------
# Worker functions (must be picklable for multiprocessing)
# ---------------------------------------------------------------------------


def _threading_worker(
    algo: str,
    data_size: int,
    iterations: int,
    thread_id: int,
) -> _WorkerResult:
    """Worker executed in a ThreadPoolExecutor thread."""
    t0 = time.perf_counter_ns()
    if algo == "aes256":
        result: BenchResultPy = run_aes_bench(data_size, iterations)
    else:
        result = run_sha_bench(data_size, iterations)
    wall = time.perf_counter_ns() - t0

    return _WorkerResult(
        thread_id=thread_id,
        latency_ns=result.mean_ns,
        throughput_mbps=result.throughput_mbps,
        min_ns=result.min_ns,
        max_ns=result.max_ns,
        stddev_ns=result.stddev_ns,
        iterations=result.iterations,
        data_size=result.data_size,
        wall_time_ns=wall,
    )


def _mp_worker_fn(args: tuple[str, int, int, int]) -> _WorkerResult:
    """Picklable worker for multiprocessing.Pool."""
    algo, data_size, iterations, thread_id = args
    # Each process must load the library independently
    return _threading_worker(algo, data_size, iterations, thread_id)


# ---------------------------------------------------------------------------
# Aggregation helper
# ---------------------------------------------------------------------------


def _aggregate_workers(
    workers: list[_WorkerResult],
    data_size: int,
    thread_count: int,
) -> SweepResult:
    """Aggregate per-worker results into a single SweepResult.

    Aggregation strategy:
      - throughput_mbps: sum of per-thread throughput (parallel work)
      - mean_latency_ns: mean of per-thread latency means
      - min / max: overall min / max across all threads
      - jitter_ns: stddev of per-thread latency means (inter-thread variance)
      - iterations: iterations from first worker (all equal)
    """
    latencies = [w.latency_ns for w in workers]
    throughputs = [w.throughput_mbps for w in workers]

    mean_lat = statistics.mean(latencies)
    min_lat = min(w.min_ns for w in workers)
    max_lat = max(w.max_ns for w in workers)
    jitter = statistics.pstdev(latencies) if len(latencies) > 1 else 0.0
    total_tp = sum(throughputs)

    return SweepResult(
        packet_size_bytes=data_size,
        thread_count=thread_count,
        mean_latency_ns=mean_lat,
        min_latency_ns=min_lat,
        max_latency_ns=max_lat,
        jitter_ns=jitter,
        throughput_mbps=total_tp,
        iterations=workers[0].iterations if workers else 0,
    )


# ---------------------------------------------------------------------------
# Threading mode
# ---------------------------------------------------------------------------


def _run_threading(
    algo: str,
    data_size: int,
    thread_count: int,
    iterations: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[_WorkerResult]:
    """Run benchmark using ThreadPoolExecutor."""
    results: list[_WorkerResult] = []
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        futures = {
            pool.submit(_threading_worker, algo, data_size, iterations, tid): tid
            for tid in range(thread_count)
        }
        completed = 0
        for future in as_completed(futures):
            results.append(future.result())
            completed += 1
            if progress_cb:
                progress_cb(completed, thread_count)
    return results


# ---------------------------------------------------------------------------
# Multiprocessing mode
# ---------------------------------------------------------------------------


def _run_multiprocessing(
    algo: str,
    data_size: int,
    thread_count: int,
    iterations: int,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[_WorkerResult]:
    """Run benchmark using multiprocessing.Pool (true parallelism, no GIL)."""
    args = [
        (algo, data_size, iterations, tid) for tid in range(thread_count)
    ]
    results: list[_WorkerResult] = []
    with multiprocessing.Pool(processes=thread_count) as pool:
        for i, result in enumerate(pool.imap_unordered(_mp_worker_fn, args)):
            results.append(result)
            if progress_cb:
                progress_cb(i + 1, thread_count)
    return results


# ---------------------------------------------------------------------------
# GIL contention ratio estimate
# ---------------------------------------------------------------------------


def _estimate_gil_contention(
    threading_results: list[SweepResult],
    mp_results: list[SweepResult],
) -> list[dict[str, Any]]:
    """Compare threading vs multiprocessing throughput to estimate GIL impact.

    Gil contention ratio = 1 - (threading_tp / mp_tp)
    A ratio near 0 means no GIL contention (crypto releases GIL effectively).
    A ratio near 1 means heavy GIL contention.
    """
    comparison = []
    for t_res, m_res in zip(threading_results, mp_results):
        if m_res.throughput_mbps > 0:
            ratio = 1.0 - (t_res.throughput_mbps / m_res.throughput_mbps)
        else:
            ratio = 0.0
        comparison.append(
            {
                "thread_count": t_res.thread_count,
                "threading_mbps": t_res.throughput_mbps,
                "multiprocessing_mbps": m_res.throughput_mbps,
                "gil_contention_ratio": max(0.0, ratio),
            }
        )
    return comparison


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_concurrent_bench(
    algo: str,
    data_size: int,
    thread_counts: list[int],
    iterations_per_thread: int,
    mode: str = "threading",
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> list[SweepResult]:
    """Run benchmark across a list of thread/process counts.

    Args:
        algo:                Algorithm — "aes256" or "sha256".
        data_size:           Data packet size in bytes per iteration.
        thread_counts:       List of concurrency levels, e.g. [1, 2, 4, 8, 16].
        iterations_per_thread: How many timed calls each worker performs.
        mode:                "threading" (default) or "multiprocessing".
        progress_cb:         Optional callback(completed, total) for progress.

    Returns:
        List of SweepResult — one per thread_count value.

    Raises:
        ValueError: If algo or mode is invalid.
    """
    if algo not in ("aes256", "sha256"):
        raise ValueError(f"algo must be 'aes256' or 'sha256', got '{algo}'")
    if mode not in ("threading", "multiprocessing"):
        raise ValueError(f"mode must be 'threading' or 'multiprocessing', got '{mode}'")

    run_fn = _run_threading if mode == "threading" else _run_multiprocessing
    sweep_results: list[SweepResult] = []

    for tc in thread_counts:
        workers = run_fn(algo, data_size, tc, iterations_per_thread, progress_cb)
        sweep_results.append(_aggregate_workers(workers, data_size, tc))

    return sweep_results


def compare_threading_vs_mp(
    algo: str,
    data_size: int,
    thread_counts: list[int],
    iterations: int,
) -> dict[str, Any]:
    """Run both threading and multiprocessing modes and compare GIL impact.

    Args:
        algo:          "aes256" or "sha256".
        data_size:     Packet size in bytes.
        thread_counts: Concurrency levels to test.
        iterations:    Iterations per worker.

    Returns:
        Dict with:
            "threading":       list[SweepResult]
            "multiprocessing": list[SweepResult]
            "gil_comparison":  list of per-thread-count comparison dicts
    """
    t_results = run_concurrent_bench(algo, data_size, thread_counts, iterations, "threading")
    mp_results = run_concurrent_bench(
        algo, data_size, thread_counts, iterations, "multiprocessing"
    )
    comparison = _estimate_gil_contention(t_results, mp_results)

    return {
        "threading": t_results,
        "multiprocessing": mp_results,
        "gil_comparison": comparison,
    }
