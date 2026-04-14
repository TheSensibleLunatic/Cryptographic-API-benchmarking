"""
tests/test_plots.py — Tests for dashboard/plots.py

Covers:
    - All 4 plot functions execute without error.
    - Output .png files are generated on disk.
    - Output files have non-zero size.

Uses tmp_path fixture to avoid polluting the workspace with test artifacts.
"""

from __future__ import annotations

import pathlib

import pytest

try:
    import matplotlib
except ImportError:
    matplotlib = None

from benchmarker.session import BenchSession

# Skip if matplotlib is missing entirely in test environment
pytestmark = pytest.mark.skipif(matplotlib is None, reason="matplotlib not installed")

# Ensure matplotlib uses the non-interactive backend for tests
if matplotlib is not None:
    matplotlib.use("Agg")

from dashboard.plots import (
    plot_jitter_distribution,
    plot_latency_heatmap,
    plot_thread_scaling,
    plot_throughput_vs_size,
)


class TestPlots:
    # We use mock_session with substantial synthetic data
    # to ensure plot rendering logic executes fully.

    def test_plot_throughput_vs_size(self, tmp_path: pathlib.Path, mock_session: BenchSession) -> None:
        out_file = tmp_path / "throughput.png"
        res = plot_throughput_vs_size(mock_session, str(out_file))

        assert res == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 1024  # Should easily be > 1KB

    def test_plot_latency_heatmap(self, tmp_path: pathlib.Path, mock_session: BenchSession) -> None:
        out_file = tmp_path / "heatmap.png"
        res = plot_latency_heatmap(mock_session, str(out_file))

        assert res == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 1024

    def test_plot_thread_scaling(self, tmp_path: pathlib.Path, mock_session: BenchSession) -> None:
        out_file = tmp_path / "scaling.png"
        res = plot_thread_scaling(mock_session, str(out_file), optimal_packet_size=4096)

        assert res == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 1024

    def test_plot_jitter_distribution(self, tmp_path: pathlib.Path, mock_session: BenchSession) -> None:
        out_file = tmp_path / "jitter.png"
        res = plot_jitter_distribution(mock_session, str(out_file))

        assert res == str(out_file)
        assert out_file.exists()
        assert out_file.stat().st_size > 1024

    def test_plots_with_empty_session_do_not_crash(self, tmp_path: pathlib.Path) -> None:
        """Even with an empty result set, plotting functions should handle it gracefully
        and simply output minimal/blank charts."""
        empty_session = BenchSession(algo="aes256", mode="test")

        plot_throughput_vs_size(empty_session, str(tmp_path / "empty_tp.png"))
        plot_latency_heatmap(empty_session, str(tmp_path / "empty_heat.png"))
        plot_thread_scaling(empty_session, str(tmp_path / "empty_scale.png"))
        plot_jitter_distribution(empty_session, str(tmp_path / "empty_jitter.png"))

        # Check they exist
        assert (tmp_path / "empty_tp.png").exists()
        assert (tmp_path / "empty_heat.png").exists()
        assert (tmp_path / "empty_scale.png").exists()
        assert (tmp_path / "empty_jitter.png").exists()
