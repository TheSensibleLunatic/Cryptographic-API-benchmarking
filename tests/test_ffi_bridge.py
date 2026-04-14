"""
tests/test_ffi_bridge.py — Tests for benchmarker/ffi_bridge.py

Covers:
    - Library auto-discovery raises FileNotFoundError if not found
    - BenchResultPy field types are correct
    - Throughput > 0 for valid inputs
    - ValueError raised for non-positive data_size or iterations
    - Zero-length data raises ValueError (guards against C crash)
    - load_library() raises FileNotFoundError for a bad path
    - _c_to_py conversion preserves all fields exactly
"""

from __future__ import annotations

import ctypes
from unittest.mock import MagicMock, patch

import pytest

from benchmarker.ffi_bridge import (
    BenchResultPy,
    _BenchResultC,
    _c_to_py,
    _find_library,
    load_library,
    run_aes_bench,
    run_sha_bench,
)


# ---------------------------------------------------------------------------
# Helper: build a fake _BenchResultC
# ---------------------------------------------------------------------------


def _make_c_result(
    mean=1200.5,
    min_=980.0,
    max_=1500.0,
    stddev=110.0,
    throughput=2048.0,
    iterations=100,
    data_size=1024,
) -> _BenchResultC:
    r = _BenchResultC()
    r.mean_ns = mean
    r.min_ns = min_
    r.max_ns = max_
    r.stddev_ns = stddev
    r.throughput_mbps = throughput
    r.iterations = iterations
    r.data_size = data_size
    return r


# ---------------------------------------------------------------------------
# Tests: _c_to_py conversion
# ---------------------------------------------------------------------------


class TestCToPyConversion:
    def test_all_fields_preserved(self) -> None:
        c = _make_c_result()
        py = _c_to_py(c)
        assert py.mean_ns == pytest.approx(1200.5)
        assert py.min_ns == pytest.approx(980.0)
        assert py.max_ns == pytest.approx(1500.0)
        assert py.stddev_ns == pytest.approx(110.0)
        assert py.throughput_mbps == pytest.approx(2048.0)
        assert py.iterations == 100
        assert py.data_size == 1024

    def test_returns_benchresultpy_instance(self) -> None:
        c = _make_c_result()
        py = _c_to_py(c)
        assert isinstance(py, BenchResultPy)

    def test_field_types(self) -> None:
        c = _make_c_result()
        py = _c_to_py(c)
        assert isinstance(py.mean_ns, float)
        assert isinstance(py.min_ns, float)
        assert isinstance(py.max_ns, float)
        assert isinstance(py.stddev_ns, float)
        assert isinstance(py.throughput_mbps, float)
        assert isinstance(py.iterations, int)
        assert isinstance(py.data_size, int)


# ---------------------------------------------------------------------------
# Tests: Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_run_aes_bench_zero_size_raises(self) -> None:
        with pytest.raises(ValueError, match="data_size"):
            run_aes_bench(0, 100)

    def test_run_aes_bench_negative_size_raises(self) -> None:
        with pytest.raises(ValueError, match="data_size"):
            run_aes_bench(-1, 100)

    def test_run_aes_bench_zero_iterations_raises(self) -> None:
        with pytest.raises(ValueError, match="iterations"):
            run_aes_bench(1024, 0)

    def test_run_sha_bench_zero_size_raises(self) -> None:
        with pytest.raises(ValueError, match="data_size"):
            run_sha_bench(0, 100)

    def test_run_sha_bench_negative_iterations_raises(self) -> None:
        with pytest.raises(ValueError, match="iterations"):
            run_sha_bench(256, -5)


# ---------------------------------------------------------------------------
# Tests: Library loading
# ---------------------------------------------------------------------------


class TestLibraryLoading:
    def test_load_library_bad_path_raises(self) -> None:
        with pytest.raises((OSError, FileNotFoundError)):
            load_library("/nonexistent/path/libcryptobench.so")

    def test_find_library_raises_when_no_so_exists(self, tmp_path) -> None:
        """_find_library should raise FileNotFoundError if .so is absent."""
        with patch("benchmarker.ffi_bridge.pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="libcryptobench"):
                _find_library()


# ---------------------------------------------------------------------------
# Tests: run_aes_bench and run_sha_bench with mocked library
# ---------------------------------------------------------------------------


class TestBenchFunctions:
    def test_run_aes_bench_returns_correct_type(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(1024, 100)
        assert isinstance(result, BenchResultPy)

    def test_run_sha_bench_returns_correct_type(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_sha_bench(1024, 100)
        assert isinstance(result, BenchResultPy)

    def test_run_aes_throughput_positive(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(4096, 200)
        assert result.throughput_mbps > 0.0

    def test_run_sha_throughput_positive(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_sha_bench(4096, 200)
        assert result.throughput_mbps > 0.0

    def test_run_aes_mean_latency_positive(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(1024, 50)
        assert result.mean_ns > 0.0

    def test_run_aes_min_leq_mean(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(1024, 50)
        assert result.min_ns <= result.mean_ns

    def test_run_aes_mean_leq_max(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(1024, 50)
        assert result.mean_ns <= result.max_ns

    def test_as_dict_keys(self, mock_lib_loader) -> None:  # noqa: ARG002
        result = run_aes_bench(1024, 50)
        d = result.as_dict()
        expected_keys = {
            "mean_latency_ns",
            "min_latency_ns",
            "max_latency_ns",
            "jitter_ns",
            "throughput_mbps",
            "iterations",
            "data_size_bytes",
        }
        assert set(d.keys()) == expected_keys
