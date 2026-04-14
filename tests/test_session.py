"""
tests/test_session.py — Tests for benchmarker/session.py

Covers:
    - BenchSession -> JSON -> BenchSession round-trip is lossless
    - CSV export contains correct headers and row count
    - System info fields are present and non-empty
    - Schema compliance exactly matches the specification
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from benchmarker.session import BenchSession, SaturationPoint, SweepResult


# ---------------------------------------------------------------------------
# Tests: Serialisation Round-Trip
# ---------------------------------------------------------------------------


class TestSessionSerialisation:
    def test_json_round_trip(self, mock_session: BenchSession) -> None:
        """Serialising and immediately deserialising must preserve all fields."""
        json_str = mock_session.to_json()
        reconstructed = BenchSession.from_json(json_str)

        # Basic metadata
        assert reconstructed.session_id == mock_session.session_id
        assert reconstructed.timestamp == mock_session.timestamp
        assert reconstructed.algo == mock_session.algo
        assert reconstructed.mode == mock_session.mode

        # System
        assert reconstructed.system == mock_session.system

        # Saturation point
        assert reconstructed.saturation_point is not None
        assert mock_session.saturation_point is not None
        assert (
            reconstructed.saturation_point.packet_size_bytes
            == mock_session.saturation_point.packet_size_bytes
        )
        assert (
            reconstructed.saturation_point.throughput_mbps
            == mock_session.saturation_point.throughput_mbps
        )

        # Results exactly match
        assert len(reconstructed.results) == len(mock_session.results)
        for r_orig, r_recon in zip(mock_session.results, reconstructed.results):
            assert r_recon.packet_size_bytes == r_orig.packet_size_bytes
            assert r_recon.thread_count == r_orig.thread_count
            assert r_recon.mean_latency_ns == pytest.approx(r_orig.mean_latency_ns)
            assert r_recon.min_latency_ns == pytest.approx(r_orig.min_latency_ns)
            assert r_recon.max_latency_ns == pytest.approx(r_orig.max_latency_ns)
            assert r_recon.jitter_ns == pytest.approx(r_orig.jitter_ns)
            assert r_recon.throughput_mbps == pytest.approx(r_orig.throughput_mbps)

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            BenchSession.from_json("{broken json")


# ---------------------------------------------------------------------------
# Tests: CSV Export
# ---------------------------------------------------------------------------


class TestCSVExport:
    def test_csv_has_correct_headers(self, mock_session: BenchSession) -> None:
        csv_str = mock_session.to_csv()
        reader = csv.reader(io.StringIO(csv_str))
        headers = next(reader)
        expected_headers = [
            "session_id",
            "algo",
            "mode",
            "packet_size_bytes",
            "thread_count",
            "mean_latency_ns",
            "min_latency_ns",
            "max_latency_ns",
            "jitter_ns",
            "throughput_mbps",
            "iterations",
        ]
        assert headers == expected_headers

    def test_csv_row_count_matches(self, mock_session: BenchSession) -> None:
        csv_str = mock_session.to_csv()
        reader = csv.reader(io.StringIO(csv_str))
        _headers = next(reader)
        rows = list(reader)
        assert len(rows) == len(mock_session.results)


# ---------------------------------------------------------------------------
# Tests: System Info
# ---------------------------------------------------------------------------


class TestSystemInfo:
    def test_system_info_fields_are_populated(self) -> None:
        """collect_system_info() defaults to real system data if not overridden."""
        session = BenchSession(algo="aes256", mode="test")
        sys = session.system
        assert "cpu" in sys
        assert "cores" in sys
        assert "ram_gb" in sys
        assert "os" in sys

        # Even on CI, strings shouldn't be empty, numbers shouldn't be negative
        assert isinstance(sys["cpu"], str) and len(sys["cpu"]) > 0
        assert isinstance(sys["os"], str) and len(sys["os"]) > 0
        assert isinstance(sys["cores"], int) and sys["cores"] > 0
        assert isinstance(sys["ram_gb"], float) and sys["ram_gb"] >= 0.0


# ---------------------------------------------------------------------------
# Tests: Schema Compliance
# ---------------------------------------------------------------------------


class TestSchemaCompliance:
    def test_dict_matches_exact_schema(self, mock_session: BenchSession) -> None:
        """The output dict must exactly match the required schema."""
        d = mock_session.to_dict()

        assert "session_id" in d
        assert "timestamp" in d
        assert "system" in d
        assert "algo" in d
        assert "mode" in d
        assert "saturation_point" in d
        assert "results" in d

        sys = d["system"]
        assert "cpu" in sys
        assert "cores" in sys
        assert "ram_gb" in sys
        assert "os" in sys

        sat = d["saturation_point"]
        if sat is not None:
            assert "packet_size_bytes" in sat
            assert "thread_count" in sat
            assert "throughput_mbps" in sat

        res = d["results"][0]
        assert "packet_size_bytes" in res
        assert "thread_count" in res
        assert "mean_latency_ns" in res
        assert "min_latency_ns" in res
        assert "max_latency_ns" in res
        assert "jitter_ns" in res
        assert "throughput_mbps" in res
        assert "iterations" in res
