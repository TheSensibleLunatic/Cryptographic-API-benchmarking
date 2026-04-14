"""
benchmarker/packet_sweep.py — Packet size sweep engine

Sweeps across a list of increasing packet sizes at a fixed thread count,
recording throughput and latency at each point.

Saturation point detection algorithm:
    Uses a first-difference threshold on the throughput curve.
    The saturation point is defined as the FIRST packet size where the
    marginal throughput gain drops below 10% of the previous step:

        Δ_throughput[i] = throughput[i] - throughput[i-1]
        gain_ratio[i]   = Δ_throughput[i] / throughput[i-1]

        saturation if gain_ratio[i] < SATURATION_THRESHOLD (0.10)

    This reflects the point where increasing packet size yields diminishing
    returns — i.e., the load has saturated the software pipeline.

Main entry point:
    run_packet_sweep(algo, packet_sizes, thread_count, iterations) -> BenchSession
"""

from __future__ import annotations

from typing import Callable, Optional

from benchmarker.session import BenchSession, SaturationPoint, SweepResult
from benchmarker.thread_harness import run_concurrent_bench

# ---------------------------------------------------------------------------
# Saturation detection threshold (10% marginal gain threshold)
# ---------------------------------------------------------------------------

SATURATION_THRESHOLD = 0.10  # 10% — documented algorithm parameter


def detect_saturation(results: list[SweepResult]) -> Optional[SaturationPoint]:
    """Detect the saturation point in a throughput curve.

    Algorithm (first-difference threshold method):
        For each consecutive pair of sweep results ordered by packet_size_bytes:
            gain_ratio = (tp[i] - tp[i-1]) / tp[i-1]
            If gain_ratio < SATURATION_THRESHOLD, flag result[i] as saturation.

        Returns the FIRST detected saturation point, or None if the curve
        never flattens within the tested range.

    Args:
        results: List of SweepResult ordered by ascending packet_size_bytes.

    Returns:
        SaturationPoint or None.
    """
    if len(results) < 2:
        return None

    # Sort by packet size to ensure correct derivative ordering
    sorted_results = sorted(results, key=lambda r: r.packet_size_bytes)

    for i in range(1, len(sorted_results)):
        prev_tp = sorted_results[i - 1].throughput_mbps
        curr_tp = sorted_results[i].throughput_mbps

        if prev_tp <= 0.0:
            continue  # Skip degenerate points

        gain_ratio = (curr_tp - prev_tp) / prev_tp

        if gain_ratio < SATURATION_THRESHOLD:
            # Saturation detected at this packet size
            r = sorted_results[i]
            return SaturationPoint(
                packet_size_bytes=r.packet_size_bytes,
                thread_count=r.thread_count,
                throughput_mbps=r.throughput_mbps,
            )

    return None  # No saturation detected in the tested range


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_packet_sweep(
    algo: str,
    packet_sizes: list[int],
    thread_count: int,
    iterations: int,
    mode: str = "threading",
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> BenchSession:
    """Sweep across packet sizes at a fixed thread count.

    For each packet size in @packet_sizes, runs the benchmark with
    @thread_count concurrent workers and @iterations per worker.
    After all sizes are collected, the saturation point is detected and
    annotated on the returned BenchSession.

    Args:
        algo:         "aes256" or "sha256".
        packet_sizes: List of packet sizes in bytes (ascending recommended).
                      Example: [64, 128, 256, 512, 1024, 4096, 16384, 65536]
        thread_count: Number of concurrent threads/processes.
        iterations:   Timed iterations per worker per packet size.
        mode:         "threading" or "multiprocessing".
        progress_cb:  Optional callback(completed_sizes, total_sizes).

    Returns:
        A BenchSession containing all SweepResults and the detected
        SaturationPoint (or None if none found).
    """
    if algo not in ("aes256", "sha256"):
        raise ValueError(f"algo must be 'aes256' or 'sha256', got '{algo}'")

    session = BenchSession(algo=algo, mode="packet-sweep")
    total = len(packet_sizes)

    for idx, pkt_size in enumerate(sorted(packet_sizes)):
        # run_concurrent_bench returns one SweepResult per thread_count entry.
        # We pass [thread_count] to get a single-element list.
        sweep_results = run_concurrent_bench(
            algo=algo,
            data_size=pkt_size,
            thread_counts=[thread_count],
            iterations_per_thread=iterations,
            mode=mode,
        )
        if sweep_results:
            session.add_result(sweep_results[0])

        if progress_cb:
            progress_cb(idx + 1, total)

    # Detect and annotate saturation point
    session.saturation_point = detect_saturation(session.results)

    return session


def run_thread_sweep(
    algo: str,
    data_size: int,
    thread_counts: list[int],
    iterations: int,
    mode: str = "threading",
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> BenchSession:
    """Sweep across thread counts at a fixed packet size.

    For each thread count in @thread_counts, runs the benchmark with
    @data_size bytes and @iterations per worker.
    Saturation detection is applied to the throughput-vs-threads curve.

    Args:
        algo:          "aes256" or "sha256".
        data_size:     Fixed packet size in bytes.
        thread_counts: List of concurrency levels, e.g. [1, 2, 4, 8, 16, 32].
        iterations:    Timed iterations per worker per thread count.
        mode:          "threading" or "multiprocessing".
        progress_cb:   Optional callback(completed, total).

    Returns:
        A BenchSession containing all SweepResults and the detected
        SaturationPoint on the thread-scaling curve.
    """
    if algo not in ("aes256", "sha256"):
        raise ValueError(f"algo must be 'aes256' or 'sha256', got '{algo}'")

    session = BenchSession(algo=algo, mode="thread-sweep")
    total = len(thread_counts)

    for idx, tc in enumerate(sorted(thread_counts)):
        sweep_results = run_concurrent_bench(
            algo=algo,
            data_size=data_size,
            thread_counts=[tc],
            iterations_per_thread=iterations,
            mode=mode,
        )
        if sweep_results:
            session.add_result(sweep_results[0])

        if progress_cb:
            progress_cb(idx + 1, total)

    session.saturation_point = detect_saturation(session.results)
    return session


def run_full_sweep(
    algo: str,
    packet_sizes: list[int],
    thread_counts: list[int],
    iterations: int,
    mode: str = "threading",
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> BenchSession:
    """Full 2-D sweep: every (packet_size × thread_count) combination.

    Total benchmark cells = len(packet_sizes) × len(thread_counts).
    Saturation detection is applied across all results grouped by thread count
    to find the global saturation point.

    Args:
        algo:          "aes256" or "sha256".
        packet_sizes:  List of packet sizes in bytes.
        thread_counts: List of concurrency levels.
        iterations:    Timed iterations per worker per cell.
        mode:          "threading" or "multiprocessing".
        progress_cb:   Optional callback(completed_cells, total_cells).

    Returns:
        A BenchSession with all len(packet_sizes) × len(thread_counts) results.
    """
    if algo not in ("aes256", "sha256"):
        raise ValueError(f"algo must be 'aes256' or 'sha256', got '{algo}'")

    session = BenchSession(algo=algo, mode="full")
    total = len(packet_sizes) * len(thread_counts)
    completed = 0

    for pkt_size in sorted(packet_sizes):
        for tc in sorted(thread_counts):
            sweep_results = run_concurrent_bench(
                algo=algo,
                data_size=pkt_size,
                thread_counts=[tc],
                iterations_per_thread=iterations,
                mode=mode,
            )
            if sweep_results:
                session.add_result(sweep_results[0])

            completed += 1
            if progress_cb:
                progress_cb(completed, total)

    # Detect saturation across maximum-thread-count results (most loaded path)
    max_tc = max(thread_counts) if thread_counts else 1
    max_tc_results = [r for r in session.results if r.thread_count == max_tc]
    session.saturation_point = detect_saturation(max_tc_results)

    return session
