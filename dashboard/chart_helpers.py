"""
dashboard/chart_helpers.py — Shared chart utilities

Provides:
    - Marvell-inspired color palette constants
    - Saturation point detector (wraps packet_sweep.detect_saturation)
    - Axis formatters for ns and MB/s units
    - Color-per-thread-count helper
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Marvell-inspired color palette
# ---------------------------------------------------------------------------

PALETTE = {
    "primary": "#0057B8",      # Marvell deep blue
    "accent_cyan": "#00C8E0",  # Electric cyan
    "accent_orange": "#FF6B00",  # Marvell orange
    "success": "#00D48A",      # Teal green
    "warning": "#FFD600",      # Amber
    "danger": "#FF3B30",       # Alert red
    "bg_dark": "#0D1117",      # Dark background
    "bg_panel": "#161B22",     # Panel background
    "text_primary": "#E6EDF3",  # Primary text
    "text_muted": "#8B949E",   # Muted text
    "grid": "#21262D",         # Grid lines
}

# Ordered color sequence for multi-line thread charts
THREAD_COLORS = [
    "#0057B8",  # deep blue
    "#00C8E0",  # cyan
    "#00D48A",  # teal
    "#FFD600",  # amber
    "#FF6B00",  # orange
    "#FF3B30",  # red
    "#A371F7",  # purple
    "#F778BA",  # pink
]


def thread_color(index: int) -> str:
    """Return a color from THREAD_COLORS by index (wraps around)."""
    return THREAD_COLORS[index % len(THREAD_COLORS)]


# ---------------------------------------------------------------------------
# Axis formatters
# ---------------------------------------------------------------------------


def format_ns(value: float) -> str:
    """Format nanosecond value with appropriate unit prefix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f} s"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} ms"
    if value >= 1_000:
        return f"{value / 1_000:.2f} µs"
    return f"{value:.0f} ns"


def format_mbps(value: float) -> str:
    """Format MB/s throughput value."""
    if value >= 1_000:
        return f"{value / 1_000:.2f} GB/s"
    return f"{value:.1f} MB/s"


def format_bytes(value: int) -> str:
    """Format byte size with IEC unit prefix."""
    if value >= 1024 * 1024:
        return f"{value // (1024 * 1024)} MiB"
    if value >= 1024:
        return f"{value // 1024} KiB"
    return f"{value} B"


# ---------------------------------------------------------------------------
# Saturation point detector (thin wrapper)
# ---------------------------------------------------------------------------


def find_saturation_point(results: list) -> Optional[object]:
    """Detect the saturation point in a list of SweepResults.

    Delegates to the canonical implementation in packet_sweep.detect_saturation.

    Args:
        results: list of SweepResult objects ordered by ascending metric.

    Returns:
        SaturationPoint or None.
    """
    from benchmarker.packet_sweep import detect_saturation  # noqa: PLC0415

    return detect_saturation(results)


# ---------------------------------------------------------------------------
# Plotly layout defaults
# ---------------------------------------------------------------------------


def plotly_dark_layout(title: str = "", height: int = 450) -> dict:
    """Return a dark-theme Plotly layout dict matching Marvell palette."""
    return {
        "title": {
            "text": title,
            "font": {"color": PALETTE["text_primary"], "size": 16},
        },
        "paper_bgcolor": PALETTE["bg_dark"],
        "plot_bgcolor": PALETTE["bg_panel"],
        "font": {"color": PALETTE["text_primary"], "family": "Inter, sans-serif"},
        "height": height,
        "xaxis": {
            "gridcolor": PALETTE["grid"],
            "zerolinecolor": PALETTE["grid"],
            "tickfont": {"color": PALETTE["text_muted"]},
        },
        "yaxis": {
            "gridcolor": PALETTE["grid"],
            "zerolinecolor": PALETTE["grid"],
            "tickfont": {"color": PALETTE["text_muted"]},
        },
        "legend": {
            "bgcolor": PALETTE["bg_panel"],
            "bordercolor": PALETTE["grid"],
            "borderwidth": 1,
            "font": {"color": PALETTE["text_primary"]},
        },
        "margin": {"l": 60, "r": 30, "t": 60, "b": 60},
    }
