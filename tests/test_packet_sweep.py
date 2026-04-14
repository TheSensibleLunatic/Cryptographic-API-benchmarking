"""
tests/test_packet_sweep.py — Tests for benchmarker/packet_sweep.py

Covers:
    - Sweep returns exactly one result per packet size
    - Thread sweep returns one result per thread count
    - Full sweep returns len(sizes) × len(threads) results
    - Saturation point index is within bounds of results list
    - Throughput is positive for all result cells
    - detect_saturation returns None for monotonically increasing curve
    - detect_saturation correctly flags the first <10% gain step
    - Progress callback is called the correct number of times
"""

from __future__ import annotations

from unittest.mock import call, patch

import pytest

from benchmarker.packet_sweep import (
    SATURATION_THRESHOLD,
    detect_saturation,
    run_full_sweep,
    run_packet_sweep,
    run_thread_sweep,
)
from benchmarker.session import BenchSession, SweepResult


# ---------------------------------------------------------------------------
# Tests: detect_saturation
# ---------------------------------------------------------------------------


class TestDetectSaturation:
    def _make_result(self, pkt: int, tp: float) -> SweepResult:
        return SweepResult(
            packet_size_bytes=pkt,
            thread_count=4,
            mean_latency_ns=1000.0,
            min_latency_ns=800.0,
            max_latency_ns=1400.0,
            jitter_ns=50.0,
            throughput_mbps=tp,
            iterations=100,
        )

    def test_returns_none_for_monotonically_increasing(self) -> None:
        """A curve that always grows > 10% should not saturate."""
        results = [
            self._make_result(64, 100),
            self._make_result(256, 200),
            self._make_result(1024, 400),
            self._make_result(4096, 800),
        ]
        assert detect_saturation(results) is None

    def test_detects_first_flat_step(self) -> None:
        """Should detect saturation at the first < 10% gain."""
        results = [
            self._make_result(64, 100),
            self._make_result(256, 200),   # +100% — OK
            self._make_result(1024, 210),  # +5%   — SATURATED ← should flag this
            self._make_result(4096, 220),
        ]
        sp = detect_saturation(results)
        assert sp is not None
        assert sp.packet_size_bytes == 1024

    def test_returns_none_for_empty(self) -> None:
        assert detect_saturation([]) is None

    def test_returns_none_for_single_element(self) -> None:
        results = [self._make_result(64, 100)]
        assert detect_saturation(results) is None

    def test_saturation_throughput_matches_result(self) -> None:
        results = [
            self._make_result(64, 500),
            self._make_result(256, 504),  # <10% gain
        ]
        sp = detect_saturation(results)
        assert sp is not None
        assert sp.throughput_mbps == pytest.approx(504.0)

    def test_saturation_index_within_bounds(self) -> None:
        results = [
            self._make_result(64 * (2**i), 100 + i * 2) for i in range(8)
        ]
        sp = detect_saturation(results)
        if sp is not None:
            pkt_sizes = [r.packet_size_bytes for r in results]
            assert sp.packet_size_bytes in pkt_sizes

    def test_threshold_exactly_at_boundary(self) -> None:
        """A gain of exactly SATURATION_THRESHOLD should NOT trigger saturation
        (must be strictly less than)."""
        # 10% gain exactly: 100 → 110
        results = [
            self._make_result(64, 100.0),
            self._make_result(256, 110.0),  # exactly +10% — NOT saturated
        ]
        sp = detect_saturation(results)
        assert sp is None  # gain_ratio == 0.10, not < 0.10


# ---------------------------------------------------------------------------
# Tests: run_packet_sweep (mocked FFI)
# ---------------------------------------------------------------------------


class TestRunPacketSweep:
    def test_result_count_equals_packet_sizes(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("aes256", small_packet_sizes, 2, 50)
        assert len(session.results) == len(small_packet_sizes)

    def test_returns_bench_session(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("aes256", small_packet_sizes, 2, 50)
        assert isinstance(session, BenchSession)

    def test_all_throughputs_positive(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("aes256", small_packet_sizes, 2, 50)
        for r in session.results:
            assert r.throughput_mbps > 0.0

    def test_algo_set_on_session(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("sha256", small_packet_sizes, 1, 50)
        assert session.algo == "sha256"

    def test_mode_set_on_session(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("aes256", small_packet_sizes, 2, 50)
        assert session.mode == "packet-sweep"

    def test_packet_sizes_in_results(self, mock_lib_loader, small_packet_sizes) -> None:  # noqa: ARG002
        session = run_packet_sweep("aes256", small_packet_sizes, 2, 50)
        result_sizes = sorted(r.packet_size_bytes for r in session.results)
        assert result_sizes == sorted(small_packet_sizes)

    def test_progress_callback_called_correct_times(
        self, mock_lib_loader, small_packet_sizes
    ) -> None:  # noqa: ARG002
        calls_made = []
        run_packet_sweep("aes256", small_packet_sizes, 1, 50, progress_cb=lambda d, t: calls_made.append(d))
        assert len(calls_made) == len(small_packet_sizes)

    def test_invalid_algo_raises(self, small_packet_sizes) -> None:
        with pytest.raises(ValueError, match="algo"):
            run_packet_sweep("des56", small_packet_sizes, 1, 10)


# ---------------------------------------------------------------------------
# Tests: run_thread_sweep (mocked FFI)
# ---------------------------------------------------------------------------


class TestRunThreadSweep:
    def test_result_count_equals_thread_counts(
        self, mock_lib_loader, small_thread_counts
    ) -> None:  # noqa: ARG002
        session = run_thread_sweep("aes256", 1024, small_thread_counts, 50)
        assert len(session.results) == len(small_thread_counts)

    def test_mode_set_correctly(self, mock_lib_loader, small_thread_counts) -> None:  # noqa: ARG002
        session = run_thread_sweep("aes256", 1024, small_thread_counts, 50)
        assert session.mode == "thread-sweep"


# ---------------------------------------------------------------------------
# Tests: run_full_sweep (mocked FFI)
# ---------------------------------------------------------------------------


class TestRunFullSweep:
    def test_result_count_is_size_times_threads(
        self, mock_lib_loader, small_packet_sizes, small_thread_counts
    ) -> None:  # noqa: ARG002
        session = run_full_sweep("aes256", small_packet_sizes, small_thread_counts, 50)
        expected = len(small_packet_sizes) * len(small_thread_counts)
        assert len(session.results) == expected

    def test_all_packet_sizes_present(
        self, mock_lib_loader, small_packet_sizes, small_thread_counts
    ) -> None:  # noqa: ARG002
        session = run_full_sweep("aes256", small_packet_sizes, small_thread_counts, 50)
        found_sizes = set(r.packet_size_bytes for r in session.results)
        assert found_sizes == set(small_packet_sizes)

    def test_all_thread_counts_present(
        self, mock_lib_loader, small_packet_sizes, small_thread_counts
    ) -> None:  # noqa: ARG002
        session = run_full_sweep("aes256", small_packet_sizes, small_thread_counts, 50)
        found_tcs = set(r.thread_count for r in session.results)
        assert found_tcs == set(small_thread_counts)

    def test_mode_set_to_full(
        self, mock_lib_loader, small_packet_sizes, small_thread_counts
    ) -> None:  # noqa: ARG002
        session = run_full_sweep("aes256", small_packet_sizes, small_thread_counts, 50)
        assert session.mode == "full"
