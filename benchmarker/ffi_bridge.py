"""
benchmarker/ffi_bridge.py — ctypes FFI layer for libcryptobench.so

Loads the compiled C shared library and exposes clean Python callables:
    run_aes_bench(data_size: int, iterations: int) -> BenchResultPy
    run_sha_bench(data_size: int, iterations: int) -> BenchResultPy

Auto-discovers the shared library relative to the project root.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import pathlib
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Python-side BenchResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class BenchResultPy:
    """Python mirror of the C BenchResult struct."""

    mean_ns: float
    min_ns: float
    max_ns: float
    stddev_ns: float
    throughput_mbps: float
    iterations: int
    data_size: int

    def as_dict(self) -> dict:
        return {
            "mean_latency_ns": self.mean_ns,
            "min_latency_ns": self.min_ns,
            "max_latency_ns": self.max_ns,
            "jitter_ns": self.stddev_ns,
            "throughput_mbps": self.throughput_mbps,
            "iterations": self.iterations,
            "data_size_bytes": self.data_size,
        }


# ---------------------------------------------------------------------------
# ctypes struct mirroring C's BenchResult
# ---------------------------------------------------------------------------


class _BenchResultC(ctypes.Structure):
    """ctypes mirror of:

    typedef struct {
        double mean_ns;
        double min_ns;
        double max_ns;
        double stddev_ns;
        double throughput_mbps;
        int    iterations;
        size_t data_size;
    } BenchResult;
    """

    _fields_ = [
        ("mean_ns", ctypes.c_double),
        ("min_ns", ctypes.c_double),
        ("max_ns", ctypes.c_double),
        ("stddev_ns", ctypes.c_double),
        ("throughput_mbps", ctypes.c_double),
        ("iterations", ctypes.c_int),
        ("data_size", ctypes.c_size_t),
    ]


# ---------------------------------------------------------------------------
# Library discovery
# ---------------------------------------------------------------------------

_LIB_NAME = "libcryptobench.so"
_LIB: Optional[ctypes.CDLL] = None


def _find_library() -> pathlib.Path:
    """Search for libcryptobench.so in well-known locations.

    Search order:
    1. crypto_engine/ directory relative to this file's project root.
    2. Current working directory.
    3. LD_LIBRARY_PATH entries.
    """
    candidates: list[pathlib.Path] = []

    # Project root = parent of `benchmarker/`
    project_root = pathlib.Path(__file__).resolve().parent.parent
    candidates.append(project_root / "crypto_engine" / _LIB_NAME)
    candidates.append(project_root / _LIB_NAME)
    candidates.append(pathlib.Path.cwd() / _LIB_NAME)
    candidates.append(pathlib.Path.cwd() / "crypto_engine" / _LIB_NAME)

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        f"Could not locate {_LIB_NAME}. "
        "Compile it with: cd crypto_engine && make all"
    )


def load_library(path: Optional[str] = None) -> ctypes.CDLL:
    """Load libcryptobench.so and configure function signatures.

    Args:
        path: Optional explicit path to the shared library. If None, the
              library is auto-discovered relative to the project root.

    Returns:
        Loaded ctypes.CDLL with configured argtypes and restypes.
    """
    global _LIB

    lib_path = pathlib.Path(path) if path else _find_library()
    lib = ctypes.CDLL(str(lib_path))

    # run_aes_bench(size_t data_size_bytes, int iterations) -> BenchResult
    lib.run_aes_bench.argtypes = [ctypes.c_size_t, ctypes.c_int]
    lib.run_aes_bench.restype = _BenchResultC

    # run_sha_bench(size_t data_size_bytes, int iterations) -> BenchResult
    lib.run_sha_bench.argtypes = [ctypes.c_size_t, ctypes.c_int]
    lib.run_sha_bench.restype = _BenchResultC

    _LIB = lib
    return lib


def _get_lib() -> ctypes.CDLL:
    """Return the cached library handle, loading it if necessary."""
    global _LIB
    if _LIB is None:
        _LIB = load_library()
    return _LIB


def _c_to_py(c_result: _BenchResultC) -> BenchResultPy:
    """Convert a ctypes _BenchResultC to a Python BenchResultPy dataclass."""
    return BenchResultPy(
        mean_ns=c_result.mean_ns,
        min_ns=c_result.min_ns,
        max_ns=c_result.max_ns,
        stddev_ns=c_result.stddev_ns,
        throughput_mbps=c_result.throughput_mbps,
        iterations=c_result.iterations,
        data_size=c_result.data_size,
    )


# ---------------------------------------------------------------------------
# Public Python callables
# ---------------------------------------------------------------------------


def run_aes_bench(data_size: int, iterations: int) -> BenchResultPy:
    """Run AES-256-CBC benchmark via the C shared library.

    Args:
        data_size:  Number of bytes to encrypt per iteration.
        iterations: Number of timed iterations to execute.

    Returns:
        BenchResultPy with mean/min/max/stddev latency and throughput.

    Raises:
        ValueError: If data_size or iterations are non-positive.
        FileNotFoundError: If the shared library cannot be found.
    """
    if data_size <= 0:
        raise ValueError(f"data_size must be > 0, got {data_size}")
    if iterations <= 0:
        raise ValueError(f"iterations must be > 0, got {iterations}")

    lib = _get_lib()
    c_result = lib.run_aes_bench(ctypes.c_size_t(data_size), ctypes.c_int(iterations))
    return _c_to_py(c_result)


def run_sha_bench(data_size: int, iterations: int) -> BenchResultPy:
    """Run SHA-256 benchmark via the C shared library.

    Args:
        data_size:  Number of bytes to hash per iteration.
        iterations: Number of timed iterations to execute.

    Returns:
        BenchResultPy with mean/min/max/stddev latency and throughput.

    Raises:
        ValueError: If data_size or iterations are non-positive.
        FileNotFoundError: If the shared library cannot be found.
    """
    if data_size <= 0:
        raise ValueError(f"data_size must be > 0, got {data_size}")
    if iterations <= 0:
        raise ValueError(f"iterations must be > 0, got {iterations}")

    lib = _get_lib()
    c_result = lib.run_sha_bench(ctypes.c_size_t(data_size), ctypes.c_int(iterations))
    return _c_to_py(c_result)


# ---------------------------------------------------------------------------
# Module-level convenience: expose OS env override for library path
# ---------------------------------------------------------------------------

_env_lib_path = os.environ.get("CRYPTOBENCH_LIB_PATH")
if _env_lib_path:
    try:
        load_library(_env_lib_path)
    except (OSError, FileNotFoundError):
        pass  # Lazy load at first call
