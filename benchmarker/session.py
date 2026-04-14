"""
benchmarker/session.py — BenchSession dataclass + serialisation

Stores all benchmark results for a single run, including:
    - Session metadata (id, timestamp, algo, mode)
    - System information (CPU, cores, RAM, OS)
    - All sweep results as a list of SweepResult
    - Saturation point metadata

Provides to_json(), to_csv(), from_json() for persistence.
"""

from __future__ import annotations

import csv
import io
import json
import platform
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


# ---------------------------------------------------------------------------
# System information collector
# ---------------------------------------------------------------------------


def collect_system_info() -> dict[str, Any]:
    """Collect CPU, RAM, and OS information.

    Uses psutil for RAM and CPU count if available; falls back to platform
    module for CPU name on systems without psutil.
    """
    cpu_name = platform.processor() or platform.machine() or "Unknown CPU"
    os_info = f"{platform.system()} {platform.release()}"

    cores = 1
    ram_gb = 0.0

    if _HAS_PSUTIL:
        cores = psutil.cpu_count(logical=True) or 1
        ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    else:
        try:
            import os  # noqa: PLC0415

            cores = os.cpu_count() or 1
        except Exception:  # noqa: BLE001
            pass

    return {
        "cpu": cpu_name,
        "cores": cores,
        "ram_gb": ram_gb,
        "os": os_info,
    }


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class SweepResult:
    """A single (packet_size × thread_count) measurement cell."""

    packet_size_bytes: int
    thread_count: int
    mean_latency_ns: float
    min_latency_ns: float
    max_latency_ns: float
    jitter_ns: float  # stddev across per-thread latency observations
    throughput_mbps: float
    iterations: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SaturationPoint:
    """Records where throughput gains flatten (<10% marginal improvement)."""

    packet_size_bytes: int
    thread_count: int
    throughput_mbps: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BenchSession:
    """Complete benchmarking session — all results for one run.

    JSON schema matches the specification exactly:
    {
        "session_id": "uuid4",
        "timestamp": "ISO8601",
        "system": { "cpu": "...", "cores": 8, "ram_gb": 16.0, "os": "..." },
        "algo": "aes256",
        "mode": "full",
        "saturation_point": { "packet_size_bytes": 4096, ... },
        "results": [ { "packet_size_bytes": 256, ... }, ... ]
    }
    """

    algo: str
    mode: str
    results: list[SweepResult] = field(default_factory=list)
    saturation_point: Optional[SaturationPoint] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    system: dict[str, Any] = field(default_factory=collect_system_info)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a dict matching the required JSON schema."""
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "system": self.system,
            "algo": self.algo,
            "mode": self.mode,
            "saturation_point": (
                self.saturation_point.as_dict() if self.saturation_point else None
            ),
            "results": [r.as_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise to a JSON string matching the required schema."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_csv(self) -> str:
        """Serialise all SweepResults to a CSV string.

        Columns:
            session_id, algo, mode, packet_size_bytes, thread_count,
            mean_latency_ns, min_latency_ns, max_latency_ns,
            jitter_ns, throughput_mbps, iterations
        """
        output = io.StringIO()
        fieldnames = [
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
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for r in self.results:
            row = r.as_dict()
            row["session_id"] = self.session_id
            row["algo"] = self.algo
            row["mode"] = self.mode
            writer.writerow({k: row[k] for k in fieldnames})
        return output.getvalue()

    # ------------------------------------------------------------------
    # Deserialisation
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchSession":
        """Reconstruct a BenchSession from a dict (e.g., parsed JSON)."""
        sat_data = data.get("saturation_point")
        saturation = (
            SaturationPoint(**sat_data) if sat_data else None
        )
        results = [SweepResult(**r) for r in data.get("results", [])]
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            system=data.get("system", collect_system_info()),
            algo=data["algo"],
            mode=data["mode"],
            saturation_point=saturation,
            results=results,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "BenchSession":
        """Reconstruct a BenchSession from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def add_result(self, result: SweepResult) -> None:
        """Append a SweepResult to the session."""
        self.results.append(result)

    def summary(self) -> str:
        """Return a human-readable one-line summary."""
        n = len(self.results)
        max_tp = max((r.throughput_mbps for r in self.results), default=0.0)
        sat = (
            f"saturation @ {self.saturation_point.packet_size_bytes}B "
            f"× {self.saturation_point.thread_count}T"
            if self.saturation_point
            else "no saturation detected"
        )
        return (
            f"[{self.algo.upper()} | {self.mode}] "
            f"{n} results, peak {max_tp:.1f} MB/s, {sat}"
        )
