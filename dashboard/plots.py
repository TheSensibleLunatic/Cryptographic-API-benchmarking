"""
dashboard/plots.py — Static Matplotlib plot generators

Generates publication-quality plots (300 DPI, dark_background style,
Marvell-inspired palette) from a BenchSession.

Functions:
    plot_throughput_vs_size(session, output_path) → saves throughput_vs_size.png
    plot_latency_heatmap(session, output_path)    → saves latency_heatmap.png
    plot_thread_scaling(session, output_path)     → saves thread_scaling.png
    plot_jitter_distribution(session, output_path)→ saves jitter_dist.png

All functions accept an optional output_path. If None, defaults to the
function name's implied filename in the current directory.
"""

from __future__ import annotations

from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

matplotlib.use("Agg")  # Non-interactive backend for CI / server use

from benchmarker.session import BenchSession
from dashboard.chart_helpers import PALETTE, THREAD_COLORS, format_bytes, thread_color

# ---------------------------------------------------------------------------
# Style setup
# ---------------------------------------------------------------------------

plt.style.use("dark_background")

_FONT_TITLE = {"fontsize": 14, "fontweight": "bold", "color": PALETTE["text_primary"]}
_FONT_LABEL = {"fontsize": 11, "color": PALETTE["text_muted"]}
_FONT_TICK = {"labelsize": 9, "colors": PALETTE["text_muted"]}
_DPI = 300
_FIG_SIZE = (10, 6)


def _apply_dark_axes(ax: plt.Axes) -> None:
    """Apply Marvell dark theme to a matplotlib Axes."""
    ax.set_facecolor(PALETTE["bg_panel"])
    ax.figure.patch.set_facecolor(PALETTE["bg_dark"])
    ax.tick_params(axis="both", **_FONT_TICK)
    ax.spines["bottom"].set_color(PALETTE["grid"])
    ax.spines["left"].set_color(PALETTE["grid"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, color=PALETTE["grid"], linewidth=0.5, alpha=0.7)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------------------
# 1. Throughput vs Packet Size
# ---------------------------------------------------------------------------


def plot_throughput_vs_size(
    session: BenchSession,
    output_path: Optional[str] = "throughput_vs_size.png",
) -> str:
    """Line chart of throughput (MB/s) vs packet size per thread count.

    Marks the session's saturation point with a vertical dashed orange line.

    Args:
        session:     BenchSession containing sweep results.
        output_path: File path to save the PNG (default: throughput_vs_size.png).

    Returns:
        The resolved output path string.
    """
    fig, ax = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    _apply_dark_axes(ax)

    # Group results by thread count
    thread_counts = sorted(set(r.thread_count for r in session.results))

    for idx, tc in enumerate(thread_counts):
        tc_results = sorted(
            [r for r in session.results if r.thread_count == tc],
            key=lambda r: r.packet_size_bytes,
        )
        if not tc_results:
            continue
        sizes = [r.packet_size_bytes for r in tc_results]
        throughputs = [r.throughput_mbps for r in tc_results]
        color = thread_color(idx)
        ax.plot(
            sizes,
            throughputs,
            marker="o",
            markersize=5,
            linewidth=2,
            color=color,
            label=f"{tc}T",
        )

    # Mark saturation point
    if session.saturation_point:
        sp = session.saturation_point
        ax.axvline(
            x=sp.packet_size_bytes,
            color=PALETTE["accent_orange"],
            linestyle="--",
            linewidth=1.5,
            alpha=0.85,
        )
        ax.annotate(
            f"Saturation\n{format_bytes(sp.packet_size_bytes)}",
            xy=(sp.packet_size_bytes, sp.throughput_mbps),
            xytext=(sp.packet_size_bytes * 1.25, sp.throughput_mbps * 0.7),
            fontsize=8,
            color=PALETTE["accent_orange"],
            arrowprops={"arrowstyle": "->", "color": PALETTE["accent_orange"]},
        )

    ax.set_xscale("log", base=2)
    ax.set_xlabel("Packet Size (bytes)", **_FONT_LABEL)
    ax.set_ylabel("Throughput (MB/s)", **_FONT_LABEL)
    ax.set_title(
        f"{session.algo.upper()} — Throughput vs Packet Size",
        **_FONT_TITLE,
    )
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: format_bytes(int(v)))
    )
    ax.legend(
        title="Thread Count",
        title_fontsize=9,
        fontsize=8,
        loc="upper left",
        facecolor=PALETTE["bg_panel"],
        edgecolor=PALETTE["grid"],
        labelcolor=PALETTE["text_primary"],
    )

    fig.tight_layout()
    out = output_path or "throughput_vs_size.png"
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 2. Latency Heatmap
# ---------------------------------------------------------------------------


def plot_latency_heatmap(
    session: BenchSession,
    output_path: Optional[str] = "latency_heatmap.png",
) -> str:
    """Heatmap of mean latency across (thread_count × packet_size) grid.

    Args:
        session:     BenchSession containing sweep results.
        output_path: File path to save the PNG.

    Returns:
        The resolved output path string.
    """
    thread_counts = sorted(set(r.thread_count for r in session.results))
    packet_sizes = sorted(set(r.packet_size_bytes for r in session.results))

    if not thread_counts or not packet_sizes:
        return output_path or "latency_heatmap.png"

    data = np.zeros((len(thread_counts), len(packet_sizes)))
    for r in session.results:
        ti = thread_counts.index(r.thread_count)
        pi = packet_sizes.index(r.packet_size_bytes)
        data[ti, pi] = r.mean_latency_ns

    fig, ax = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    _apply_dark_axes(ax)

    im = ax.imshow(
        data,
        aspect="auto",
        cmap="plasma",
        interpolation="nearest",
    )

    cbar = fig.colorbar(im, ax=ax, pad=0.02)
    cbar.set_label("Mean Latency (ns)", color=PALETTE["text_muted"], fontsize=10)
    cbar.ax.yaxis.set_tick_params(color=PALETTE["text_muted"])
    plt.setp(cbar.ax.yaxis.get_ticklabels(), color=PALETTE["text_muted"])

    ax.set_xticks(range(len(packet_sizes)))
    ax.set_xticklabels(
        [format_bytes(s) for s in packet_sizes], rotation=45, ha="right", fontsize=7
    )
    ax.set_yticks(range(len(thread_counts)))
    ax.set_yticklabels([f"{t}T" for t in thread_counts], fontsize=8)
    ax.set_xlabel("Packet Size", **_FONT_LABEL)
    ax.set_ylabel("Thread Count", **_FONT_LABEL)
    ax.set_title(
        f"{session.algo.upper()} — Latency Heatmap (ns)",
        **_FONT_TITLE,
    )

    # Annotate cells with latency values
    for ti in range(len(thread_counts)):
        for pi in range(len(packet_sizes)):
            val = data[ti, pi]
            text = f"{val:,.0f}" if val < 10_000 else f"{val / 1000:.1f}k"
            ax.text(
                pi,
                ti,
                text,
                ha="center",
                va="center",
                fontsize=6,
                color="white" if val < (data.max() * 0.6) else "black",
            )

    fig.tight_layout()
    out = output_path or "latency_heatmap.png"
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 3. Thread Scaling
# ---------------------------------------------------------------------------


def plot_thread_scaling(
    session: BenchSession,
    output_path: Optional[str] = "thread_scaling.png",
    optimal_packet_size: Optional[int] = None,
) -> str:
    """Bar + line chart: throughput vs thread count at fixed packet size.

    Overlays an ideal linear scaling reference line and annotates efficiency %.

    Args:
        session:             BenchSession.
        output_path:         Output file path.
        optimal_packet_size: Packet size to use for scaling analysis.
                             Defaults to the largest available size.

    Returns:
        The resolved output path string.
    """
    packet_sizes = sorted(set(r.packet_size_bytes for r in session.results))
    if not packet_sizes:
        return output_path or "thread_scaling.png"

    target_size = optimal_packet_size or packet_sizes[-1]
    # Fall back to closest size if exact not found
    if target_size not in packet_sizes:
        target_size = min(packet_sizes, key=lambda s: abs(s - target_size))

    tc_results = sorted(
        [r for r in session.results if r.packet_size_bytes == target_size],
        key=lambda r: r.thread_count,
    )
    if not tc_results:
        return output_path or "thread_scaling.png"

    thread_counts = [r.thread_count for r in tc_results]
    throughputs = [r.throughput_mbps for r in tc_results]
    baseline_tp = throughputs[0]
    ideal_tp = [baseline_tp * tc for tc in thread_counts]
    efficiency = [
        (actual / ideal * 100) if ideal > 0 else 0
        for actual, ideal in zip(throughputs, ideal_tp)
    ]

    fig, ax1 = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    _apply_dark_axes(ax1)
    ax2 = ax1.twinx()

    bar_width = 0.35
    x = range(len(thread_counts))

    bars = ax1.bar(
        x,
        throughputs,
        width=bar_width,
        color=PALETTE["primary"],
        alpha=0.85,
        label="Actual Throughput",
    )
    ax1.plot(
        x,
        ideal_tp,
        color=PALETTE["accent_orange"],
        linestyle="--",
        linewidth=2,
        marker="^",
        markersize=6,
        label="Ideal Linear Scaling",
    )
    ax2.plot(
        x,
        efficiency,
        color=PALETTE["accent_cyan"],
        linestyle="-",
        linewidth=1.5,
        marker="s",
        markersize=5,
        label="Efficiency %",
    )
    ax2.set_ylabel("Parallel Efficiency (%)", color=PALETTE["accent_cyan"], fontsize=10)
    ax2.tick_params(axis="y", colors=PALETTE["accent_cyan"])
    ax2.set_ylim(0, 130)
    ax2.spines["right"].set_color(PALETTE["accent_cyan"])

    ax1.set_xticks(list(x))
    ax1.set_xticklabels([str(t) for t in thread_counts])
    ax1.set_xlabel("Thread Count", **_FONT_LABEL)
    ax1.set_ylabel("Throughput (MB/s)", **_FONT_LABEL)
    ax1.set_title(
        f"{session.algo.upper()} — Thread Scaling @ {format_bytes(target_size)}",
        **_FONT_TITLE,
    )

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper left",
        fontsize=8,
        facecolor=PALETTE["bg_panel"],
        edgecolor=PALETTE["grid"],
        labelcolor=PALETTE["text_primary"],
    )

    # Efficiency annotations on bars
    for bar_obj, eff in zip(bars, efficiency):
        ax1.annotate(
            f"{eff:.0f}%",
            xy=(bar_obj.get_x() + bar_obj.get_width() / 2, bar_obj.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=7,
            color=PALETTE["text_muted"],
        )

    fig.tight_layout()
    out = output_path or "thread_scaling.png"
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# 4. Jitter Distribution
# ---------------------------------------------------------------------------


def plot_jitter_distribution(
    session: BenchSession,
    output_path: Optional[str] = "jitter_dist.png",
) -> str:
    """Dual-axis line chart: mean latency + jitter (stddev) vs packet size.

    Args:
        session:     BenchSession.
        output_path: Output file path.

    Returns:
        The resolved output path string.
    """
    thread_counts = sorted(set(r.thread_count for r in session.results))
    if not thread_counts:
        return output_path or "jitter_dist.png"

    # Use the median thread count for the jitter chart (representative)
    mid_tc = thread_counts[len(thread_counts) // 2]
    tc_results = sorted(
        [r for r in session.results if r.thread_count == mid_tc],
        key=lambda r: r.packet_size_bytes,
    )
    if not tc_results:
        return output_path or "jitter_dist.png"

    sizes = [r.packet_size_bytes for r in tc_results]
    latencies = [r.mean_latency_ns for r in tc_results]
    jitters = [r.jitter_ns for r in tc_results]

    fig, ax1 = plt.subplots(figsize=_FIG_SIZE, dpi=_DPI)
    _apply_dark_axes(ax1)
    ax2 = ax1.twinx()

    ax1.plot(
        sizes,
        latencies,
        color=PALETTE["primary"],
        linewidth=2,
        marker="o",
        markersize=5,
        label="Mean Latency (ns)",
    )
    ax1.fill_between(
        sizes,
        [lt - jt for lt, jt in zip(latencies, jitters)],
        [lt + jt for lt, jt in zip(latencies, jitters)],
        alpha=0.18,
        color=PALETTE["primary"],
    )

    ax2.plot(
        sizes,
        jitters,
        color=PALETTE["accent_orange"],
        linewidth=1.8,
        marker="s",
        markersize=5,
        linestyle="--",
        label="Jitter / Stddev (ns)",
    )

    ax1.set_xscale("log", base=2)
    ax1.set_xlabel("Packet Size (bytes)", **_FONT_LABEL)
    ax1.set_ylabel("Mean Latency (ns)", color=PALETTE["primary"], fontsize=10)
    ax1.tick_params(axis="y", colors=PALETTE["primary"])
    ax2.set_ylabel("Jitter / Stddev (ns)", color=PALETTE["accent_orange"], fontsize=10)
    ax2.tick_params(axis="y", colors=PALETTE["accent_orange"])
    ax1.set_title(
        f"{session.algo.upper()} — Latency & Jitter @ {mid_tc}T",
        **_FONT_TITLE,
    )
    ax1.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda v, _: format_bytes(int(v)))
    )

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper left",
        fontsize=8,
        facecolor=PALETTE["bg_panel"],
        edgecolor=PALETTE["grid"],
        labelcolor=PALETTE["text_primary"],
    )
    ax2.spines["right"].set_color(PALETTE["accent_orange"])

    fig.tight_layout()
    out = output_path or "jitter_dist.png"
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    return out
