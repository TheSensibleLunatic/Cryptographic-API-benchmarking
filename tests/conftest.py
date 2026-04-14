"""
tests/conftest.py — Shared pytest fixtures

Provides:
    - mock_session:       A BenchSession populated with deterministic synthetic data
    - mock_lib_loader:    Monkeypatches ffi_bridge to return deterministic BenchResultPy
    - small_packet_sizes: Small default list for fast tests
    - small_thread_counts: Small default concurrency list for fast tests
"""

from __future__ import annotations

import math
import random
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from benchmarker.ffi_bridge import BenchResultPy
from benchmarker.session import BenchSession, SaturationPoint, SweepResult

# ---------------------------------------------------------------------------
# Deterministic synthetic data constants
# ---------------------------------------------------------------------------

SYNTHETIC_PACKET_SIZES = [64, 256, 1024, 4096, 16384, 65536, 1048576]
SYNTHETIC_THREAD_COUNTS = [1, 2, 4, 8]
SYNTHETIC_ITERATIONS = 100

# Throughput model: rises quickly then saturates.
# throughput(size, threads) = base * log2(size) * min(threads, 4) * noise
_BASE_MBPS = 150.0
_RNG = random.Random(42)  # fixed seed for reproducibility


def _synthetic_throughput(packet_size: int, thread_count: int) -> float:
    """Deterministic synthetic throughput that saturates after 4096 bytes."""
    size_factor = math.log2(max(packet_size, 64)) / math.log2(65536)
    thread_factor = min(thread_count, 4) / 4.0
    noise = 1.0 + _RNG.gauss(0, 0.02)
    return _BASE_MBPS * size_factor * thread_factor * noise


def _synthetic_latency(packet_size: int) -> float:
    """Deterministic synthetic latency in nanoseconds."""
    return 500.0 + packet_size * 0.1 + _RNG.gauss(0, 20)


def _make_sweep_result(packet_size: int, thread_count: int) -> SweepResult:
    lat = _synthetic_latency(packet_size)
    tp = _synthetic_throughput(packet_size, thread_count)
    return SweepResult(
        packet_size_bytes=packet_size,
        thread_count=thread_count,
        mean_latency_ns=lat,
        min_latency_ns=lat * 0.85,
        max_latency_ns=lat * 1.25,
        jitter_ns=abs(_RNG.gauss(0, lat * 0.05)),
        throughput_mbps=tp,
        iterations=SYNTHETIC_ITERATIONS,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> BenchSession:
    """A BenchSession with realistic synthetic data covering all (size × thread) cells."""
    _RNG.seed(42)  # reset for determinism
    session = BenchSession(
        algo="aes256",
        mode="full",
        session_id="test-session-uuid-0001",
        timestamp="2025-01-01T00:00:00+00:00",
        system={
            "cpu": "Intel Core i9-13900K @ 3.00GHz",
            "cores": 24,
            "ram_gb": 64.0,
            "os": "Linux 6.5.0",
        },
    )

    for ps in SYNTHETIC_PACKET_SIZES:
        for tc in SYNTHETIC_THREAD_COUNTS:
            session.add_result(_make_sweep_result(ps, tc))

    session.saturation_point = SaturationPoint(
        packet_size_bytes=4096,
        thread_count=8,
        throughput_mbps=_synthetic_throughput(4096, 8),
    )
    return session


@pytest.fixture
def mock_sha_session() -> BenchSession:
    """Like mock_session but for SHA-256."""
    _RNG.seed(99)
    session = BenchSession(
        algo="sha256",
        mode="packet-sweep",
        session_id="test-session-sha-0001",
        timestamp="2025-01-01T00:00:00+00:00",
        system={
            "cpu": "AMD Ryzen 9 7950X",
            "cores": 32,
            "ram_gb": 128.0,
            "os": "Linux 6.6.0",
        },
    )
    for ps in SYNTHETIC_PACKET_SIZES:
        session.add_result(_make_sweep_result(ps, 4))
    return session


@pytest.fixture
def small_packet_sizes() -> list[int]:
    """Small packet size list for fast unit tests."""
    return [64, 256, 1024]


@pytest.fixture
def small_thread_counts() -> list[int]:
    """Small thread count list for fast unit tests."""
    return [1, 2]


@pytest.fixture
def mock_bench_result() -> BenchResultPy:
    """A deterministic BenchResultPy for FFI mock returns."""
    return BenchResultPy(
        mean_ns=1240.3,
        min_ns=980.1,
        max_ns=1890.7,
        stddev_ns=145.2,
        throughput_mbps=1800.4,
        iterations=100,
        data_size=1024,
    )


@pytest.fixture
def mock_lib_loader(mock_bench_result: BenchResultPy) -> Generator[MagicMock, None, None]:
    """Monkeypatches ffi_bridge.run_aes_bench and run_sha_bench to return
    deterministic mock results without touching the C shared library."""
    with (
        patch("benchmarker.ffi_bridge.run_aes_bench", return_value=mock_bench_result) as mock_aes,
        patch("benchmarker.ffi_bridge.run_sha_bench", return_value=mock_bench_result) as mock_sha,
    ):
        yield {"aes": mock_aes, "sha": mock_sha}
