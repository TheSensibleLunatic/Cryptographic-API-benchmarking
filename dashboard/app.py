"""
dashboard/app.py — Full Streamlit Dashboard for crypto-bench

Tabs:
    1. Throughput Analysis  — MB/s vs packet size, saturation annotation
    2. Latency & Jitter     — dual-axis + Plotly heatmap
    3. Thread Scaling       — throughput vs thread count + efficiency %
    4. Raw Data             — sortable dataframe + JSON/CSV download
    5. System Info          — CPU/RAM/OS + GIL comparison chart

Features:
    - Sidebar controls (algo, mode, threads, sizes, iterations, Run button)
    - Live progress bar during benchmark runs
    - Session state preserved between tab switches
    - Load a saved JSON session without re-running the benchmark
    - Fully offline — no external API calls
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Ensure project root is on the path
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from benchmarker.session import BenchSession, SweepResult
from dashboard.chart_helpers import (
    PALETTE,
    format_bytes,
    format_mbps,
    format_ns,
    plotly_dark_layout,
    thread_color,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Crypto Bench",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0D1117;
        color: #E6EDF3;
    }
    .stApp { background-color: #0D1117; }
    .main .block-container { padding-top: 1rem; padding-bottom: 2rem; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #161B22;
        border-right: 1px solid #21262D;
    }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background-color: #161B22;
        border: 1px solid #21262D;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="metric-container"] label { color: #8B949E !important; font-size: 12px; }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #00C8E0 !important; font-size: 24px; font-weight: 600;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        background-color: #161B22 !important;
        color: #8B949E !important;
        border-radius: 6px 6px 0 0;
        font-weight: 500;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: #00C8E0 !important;
        border-bottom: 2px solid #00C8E0 !important;
    }

    /* Buttons */
    div.stButton > button {
        background: linear-gradient(135deg, #0057B8, #00C8E0);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        transition: opacity 0.2s;
    }
    div.stButton > button:hover { opacity: 0.85; }

    /* Headers */
    h1 { color: #E6EDF3 !important; }
    h2, h3 { color: #00C8E0 !important; }

    /* Dataframe */
    .stDataFrame { border: 1px solid #21262D; border-radius: 8px; }

    /* Alert boxes */
    .sat-box {
        background: linear-gradient(135deg, #1A1F2E, #1A2A1A);
        border-left: 4px solid #FF6B00;
        border-radius: 6px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PACKET_SIZES = [64, 256, 1024, 4096, 16384, 65536, 1048576]
DEFAULT_THREAD_COUNTS = [1, 2, 4, 8, 16, 32]

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


def _init_state() -> None:
    defaults = {
        "session": None,
        "session_aes": None,
        "session_sha": None,
        "running": False,
        "progress": 0.0,
        "progress_label": "",
        "error": None,
        "gil_comparison": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar() -> dict:
    """Render sidebar controls and return user configuration dict."""
    with st.sidebar:
        st.markdown(
            "## ⚡ Crypto Bench",
        )
        st.markdown(
            "<p style='color:#8B949E;font-size:12px;margin-top:-8px;'>"
            "High-Concurrency Cryptographic API Benchmarking</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        # Load from file
        st.markdown("**📂 Load Saved Session**")
        uploaded = st.file_uploader("Upload JSON session", type=["json"], label_visibility="collapsed")
        if uploaded:
            try:
                json_str = uploaded.read().decode("utf-8")
                loaded = BenchSession.from_json(json_str)
                st.session_state["session"] = loaded
                if loaded.algo == "aes256":
                    st.session_state["session_aes"] = loaded
                else:
                    st.session_state["session_sha"] = loaded
                st.success(f"Loaded: {loaded.algo.upper()} — {len(loaded.results)} results")
            except Exception as e:  # noqa: BLE001
                st.error(f"Failed to load: {e}")

        st.divider()
        st.markdown("**🔧 Benchmark Configuration**")

        algo = st.selectbox(
            "Algorithm",
            options=["aes256", "sha256", "both"],
            index=0,
            help="Cryptographic algorithm to benchmark",
        )
        mode = st.selectbox(
            "Mode",
            options=["packet-sweep", "thread-sweep", "full"],
            index=2,
            help="Sweep dimension(s) to explore",
        )
        parallelism = st.radio(
            "Parallelism",
            options=["threading", "multiprocessing"],
            index=0,
            horizontal=True,
            help="threading: may share GIL  |  multiprocessing: true parallelism",
        )

        st.markdown("**Thread Counts**")
        thread_counts = st.multiselect(
            "Select thread counts",
            options=[1, 2, 4, 8, 16, 32, 64],
            default=[1, 2, 4, 8, 16],
            label_visibility="collapsed",
        )
        if not thread_counts:
            thread_counts = [1]

        st.markdown("**Packet Size Range (bytes)**")
        min_exp, max_exp = st.slider(
            "Log2 packet size range",
            min_value=6,
            max_value=20,
            value=(6, 20),
            help="64 B (2^6) → 1 MiB (2^20)",
            label_visibility="collapsed",
        )
        packet_sizes = [2**e for e in range(min_exp, max_exp + 1, 2)]
        st.caption(f"Sizes: {[format_bytes(s) for s in packet_sizes]}")

        iterations = st.number_input(
            "Iterations per cell",
            min_value=10,
            max_value=10000,
            value=500,
            step=100,
            help="More iterations = more stable statistics",
        )

        compare_mp = st.checkbox(
            "Compare GIL vs Multiprocessing",
            value=False,
            help="Run both modes and show GIL contention ratio (slower)",
        )

        st.divider()
        run_clicked = st.button("▶  Run Benchmark", use_container_width=True)

    return {
        "algo": algo,
        "mode": mode,
        "parallelism": parallelism,
        "thread_counts": sorted(thread_counts),
        "packet_sizes": packet_sizes,
        "iterations": int(iterations),
        "compare_mp": compare_mp,
        "run_clicked": run_clicked,
    }


# ---------------------------------------------------------------------------
# Benchmark runner (background thread)
# ---------------------------------------------------------------------------


def _run_benchmark_bg(
    algo: str,
    mode: str,
    packet_sizes: list[int],
    thread_counts: list[int],
    iterations: int,
    parallelism: str,
    compare_mp: bool,
) -> None:
    """Run benchmark in background thread; update session_state when done."""
    from benchmarker.packet_sweep import (  # noqa: PLC0415
        run_full_sweep,
        run_packet_sweep,
        run_thread_sweep,
    )
    from benchmarker.thread_harness import compare_threading_vs_mp  # noqa: PLC0415

    def make_cb(prefix: str):
        def cb(done: int, total: int) -> None:
            st.session_state["progress"] = done / max(total, 1)
            st.session_state["progress_label"] = f"{prefix}: {done}/{total}"

        return cb

    algos = ["aes256", "sha256"] if algo == "both" else [algo]

    try:
        for alg in algos:
            pct_prefix = f"{alg.upper()} {mode}"
            cb = make_cb(pct_prefix)

            if mode == "packet-sweep":
                session = run_packet_sweep(
                    algo=alg,
                    packet_sizes=packet_sizes,
                    thread_count=thread_counts[-1],
                    iterations=iterations,
                    mode=parallelism,
                    progress_cb=cb,
                )
            elif mode == "thread-sweep":
                session = run_thread_sweep(
                    algo=alg,
                    data_size=packet_sizes[-1],
                    thread_counts=thread_counts,
                    iterations=iterations,
                    mode=parallelism,
                    progress_cb=cb,
                )
            else:
                session = run_full_sweep(
                    algo=alg,
                    packet_sizes=packet_sizes,
                    thread_counts=thread_counts,
                    iterations=iterations,
                    mode=parallelism,
                    progress_cb=cb,
                )

            st.session_state["session"] = session
            st.session_state[f"session_{alg[:3]}"] = session  # session_aes / session_sha

            # GIL comparison
            if compare_mp and len(thread_counts) > 0:
                st.session_state["progress_label"] = f"{alg.upper()} GIL comparison..."
                gil_data = compare_threading_vs_mp(
                    algo=alg,
                    data_size=packet_sizes[-1],
                    thread_counts=thread_counts,
                    iterations=iterations,
                )
                st.session_state["gil_comparison"] = gil_data

    except Exception as e:  # noqa: BLE001
        st.session_state["error"] = str(e)
    finally:
        st.session_state["running"] = False
        st.session_state["progress"] = 1.0


# ---------------------------------------------------------------------------
# Chart: Throughput vs Packet Size (Plotly)
# ---------------------------------------------------------------------------


def _chart_throughput_vs_size(session: BenchSession) -> go.Figure:
    thread_counts = sorted(set(r.thread_count for r in session.results))
    fig = go.Figure()

    for idx, tc in enumerate(thread_counts):
        tc_results = sorted(
            [r for r in session.results if r.thread_count == tc],
            key=lambda r: r.packet_size_bytes,
        )
        if not tc_results:
            continue
        x = [format_bytes(r.packet_size_bytes) for r in tc_results]
        y = [r.throughput_mbps for r in tc_results]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                name=f"{tc}T",
                line={"color": thread_color(idx), "width": 2},
                marker={"size": 7},
                hovertemplate="<b>%{x}</b><br>%{y:.1f} MB/s<extra></extra>",
            )
        )

    # Saturation annotation
    if session.saturation_point:
        sp = session.saturation_point
        sp_label = format_bytes(sp.packet_size_bytes)
        fig.add_vline(
            x=sp_label,
            line_dash="dash",
            line_color=PALETTE["accent_orange"],
            annotation_text=f"Saturation @ {sp_label}",
            annotation_position="top",
            annotation_font_color=PALETTE["accent_orange"],
        )

    layout = plotly_dark_layout(
        f"{session.algo.upper()} — Throughput vs Packet Size", height=420
    )
    layout["xaxis"]["title"] = "Packet Size"
    layout["yaxis"]["title"] = "Throughput (MB/s)"
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Chart: Latency + Jitter dual-axis (Plotly)
# ---------------------------------------------------------------------------


def _chart_latency_jitter(session: BenchSession) -> go.Figure:
    thread_counts = sorted(set(r.thread_count for r in session.results))
    mid_tc = thread_counts[len(thread_counts) // 2] if thread_counts else 1

    tc_results = sorted(
        [r for r in session.results if r.thread_count == mid_tc],
        key=lambda r: r.packet_size_bytes,
    )
    x = [format_bytes(r.packet_size_bytes) for r in tc_results]
    latencies = [r.mean_latency_ns for r in tc_results]
    jitters = [r.jitter_ns for r in tc_results]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=latencies,
            name="Mean Latency (ns)",
            line={"color": PALETTE["primary"], "width": 2},
            marker={"size": 6},
            yaxis="y",
            hovertemplate="<b>%{x}</b><br>Latency: %{y:,.0f} ns<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=jitters,
            name="Jitter / Stddev (ns)",
            line={"color": PALETTE["accent_orange"], "width": 2, "dash": "dot"},
            marker={"size": 6},
            yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Jitter: %{y:,.1f} ns<extra></extra>",
        )
    )

    layout = plotly_dark_layout(
        f"{session.algo.upper()} — Latency & Jitter @ {mid_tc}T", height=400
    )
    layout["yaxis"] = {**layout.get("yaxis", {}), "title": "Mean Latency (ns)"}
    layout["yaxis2"] = {
        "title": "Jitter / Stddev (ns)",
        "overlaying": "y",
        "side": "right",
        "gridcolor": PALETTE["grid"],
        "tickfont": {"color": PALETTE["text_muted"]},
    }
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Chart: Latency heatmap (Plotly)
# ---------------------------------------------------------------------------


def _chart_latency_heatmap(session: BenchSession) -> go.Figure:
    thread_counts = sorted(set(r.thread_count for r in session.results))
    packet_sizes = sorted(set(r.packet_size_bytes for r in session.results))

    z = []
    for tc in thread_counts:
        row = []
        for ps in packet_sizes:
            match = [r for r in session.results if r.thread_count == tc and r.packet_size_bytes == ps]
            row.append(match[0].mean_latency_ns if match else 0)
        z.append(row)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[format_bytes(s) for s in packet_sizes],
            y=[f"{t}T" for t in thread_counts],
            colorscale="Plasma",
            colorbar={"title": "Mean Latency (ns)", "tickfont": {"color": PALETTE["text_muted"]}},
            hovertemplate="Threads: %{y}<br>Size: %{x}<br>Latency: %{z:,.0f} ns<extra></extra>",
        )
    )
    layout = plotly_dark_layout(
        f"{session.algo.upper()} — Mean Latency Heatmap (ns)", height=380
    )
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Chart: Thread Scaling (Plotly)
# ---------------------------------------------------------------------------


def _chart_thread_scaling(session: BenchSession) -> go.Figure:
    packet_sizes = sorted(set(r.packet_size_bytes for r in session.results))
    if not packet_sizes:
        return go.Figure()

    target = packet_sizes[-1]
    tc_results = sorted(
        [r for r in session.results if r.packet_size_bytes == target],
        key=lambda r: r.thread_count,
    )
    if not tc_results:
        return go.Figure()

    tcs = [r.thread_count for r in tc_results]
    actuals = [r.throughput_mbps for r in tc_results]
    baseline = actuals[0] if actuals else 1
    ideals = [baseline * tc for tc in tcs]
    efficiency = [(a / i * 100) if i > 0 else 0 for a, i in zip(actuals, ideals)]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=tcs,
            y=actuals,
            name="Actual Throughput",
            marker_color=PALETTE["primary"],
            hovertemplate="Threads: %{x}<br>Throughput: %{y:.1f} MB/s<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=tcs,
            y=ideals,
            name="Ideal Linear",
            line={"color": PALETTE["accent_orange"], "dash": "dash", "width": 2},
            mode="lines+markers",
            marker={"size": 7},
            yaxis="y",
            hovertemplate="Threads: %{x}<br>Ideal: %{y:.1f} MB/s<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=tcs,
            y=efficiency,
            name="Efficiency %",
            line={"color": PALETTE["accent_cyan"], "width": 2},
            mode="lines+markers",
            marker={"size": 6, "symbol": "square"},
            yaxis="y2",
            hovertemplate="Threads: %{x}<br>Efficiency: %{y:.1f}%%<extra></extra>",
        )
    )

    layout = plotly_dark_layout(
        f"{session.algo.upper()} — Thread Scaling @ {format_bytes(target)}", height=420
    )
    layout["xaxis"]["title"] = "Thread Count"
    layout["yaxis"]["title"] = "Throughput (MB/s)"
    layout["yaxis2"] = {
        "title": "Efficiency (%)",
        "overlaying": "y",
        "side": "right",
        "range": [0, 130],
        "gridcolor": PALETTE["grid"],
        "tickfont": {"color": PALETTE["text_muted"]},
    }
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Chart: GIL comparison (Plotly)
# ---------------------------------------------------------------------------


def _chart_gil_comparison(gil_data: dict) -> Optional[go.Figure]:
    comparison = gil_data.get("gil_comparison", [])
    if not comparison:
        return None

    tcs = [d["thread_count"] for d in comparison]
    t_tp = [d["threading_mbps"] for d in comparison]
    mp_tp = [d["multiprocessing_mbps"] for d in comparison]
    ratios = [d["gil_contention_ratio"] * 100 for d in comparison]

    fig = go.Figure()
    fig.add_trace(go.Bar(x=tcs, y=t_tp, name="Threading", marker_color=PALETTE["primary"]))
    fig.add_trace(go.Bar(x=tcs, y=mp_tp, name="Multiprocessing", marker_color=PALETTE["success"]))
    fig.add_trace(
        go.Scatter(
            x=tcs,
            y=ratios,
            name="GIL Contention %",
            yaxis="y2",
            line={"color": PALETTE["danger"], "width": 2},
            mode="lines+markers",
        )
    )

    layout = plotly_dark_layout("Threading vs Multiprocessing — GIL Impact", height=380)
    layout["barmode"] = "group"
    layout["xaxis"]["title"] = "Thread Count"
    layout["yaxis"]["title"] = "Throughput (MB/s)"
    layout["yaxis2"] = {
        "title": "GIL Contention (%)",
        "overlaying": "y",
        "side": "right",
        "gridcolor": PALETTE["grid"],
        "tickfont": {"color": PALETTE["text_muted"]},
    }
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Tab renderers
# ---------------------------------------------------------------------------


def _tab_throughput(session: BenchSession) -> None:
    st.markdown("### 📈 Throughput vs Packet Size")

    # KPI row
    if session.results:
        max_tp = max(r.throughput_mbps for r in session.results)
        avg_tp = sum(r.throughput_mbps for r in session.results) / len(session.results)
        peak_thr = max(r.thread_count for r in session.results)
        cols = st.columns(4)
        cols[0].metric("Peak Throughput", format_mbps(max_tp))
        cols[1].metric("Avg Throughput", format_mbps(avg_tp))
        cols[2].metric("Max Threads", str(peak_thr))
        cols[3].metric(
            "Saturation Point",
            format_bytes(session.saturation_point.packet_size_bytes)
            if session.saturation_point
            else "Not detected",
        )

    st.plotly_chart(_chart_throughput_vs_size(session), use_container_width=True)

    if session.saturation_point:
        sp = session.saturation_point
        st.markdown(
            f"""<div class="sat-box">
            🔴 <b>Software Saturation Detected</b><br>
            The throughput curve flattens below 10% marginal gain at
            <b>{format_bytes(sp.packet_size_bytes)}</b> with <b>{sp.thread_count} threads</b>,
            achieving <b>{sp.throughput_mbps:.1f} MB/s</b>.<br>
            Beyond this point, increasing packet size yields diminishing returns —
            this is the software pipeline bottleneck consistent with high-performance
            high-throughput hardware offload design philosophy.
            </div>""",
            unsafe_allow_html=True,
        )


def _tab_latency(session: BenchSession) -> None:
    st.markdown("### ⏱ Latency & Jitter Analysis")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.plotly_chart(_chart_latency_jitter(session), use_container_width=True)
    with c2:
        st.plotly_chart(_chart_latency_heatmap(session), use_container_width=True)

    if session.results:
        min_lat = min(r.mean_latency_ns for r in session.results)
        max_lat = max(r.mean_latency_ns for r in session.results)
        avg_jitter = sum(r.jitter_ns for r in session.results) / len(session.results)
        cols = st.columns(3)
        cols[0].metric("Min Latency", format_ns(min_lat))
        cols[1].metric("Max Latency", format_ns(max_lat))
        cols[2].metric("Avg Jitter", format_ns(avg_jitter))


def _tab_thread_scaling(session: BenchSession) -> None:
    st.markdown("### 🧵 Thread Scaling Analysis")
    st.plotly_chart(_chart_thread_scaling(session), use_container_width=True)

    # Efficiency table
    packet_sizes = sorted(set(r.packet_size_bytes for r in session.results))
    if packet_sizes:
        target = packet_sizes[-1]
        tc_results = sorted(
            [r for r in session.results if r.packet_size_bytes == target],
            key=lambda r: r.thread_count,
        )
        baseline = tc_results[0].throughput_mbps if tc_results else 1

        eff_data = []
        for r in tc_results:
            ideal = baseline * r.thread_count
            eff = (r.throughput_mbps / ideal * 100) if ideal > 0 else 0
            eff_data.append(
                {
                    "Threads": r.thread_count,
                    "Actual (MB/s)": f"{r.throughput_mbps:.1f}",
                    "Ideal (MB/s)": f"{ideal:.1f}",
                    "Efficiency (%)": f"{eff:.1f}%",
                    "Jitter (ns)": f"{r.jitter_ns:.1f}",
                }
            )
        st.markdown(f"**Efficiency breakdown @ {format_bytes(target)}**")
        st.dataframe(pd.DataFrame(eff_data), use_container_width=True, hide_index=True)


def _tab_raw_data(session: BenchSession) -> None:
    st.markdown("### 📊 Raw Benchmark Data")

    df = pd.DataFrame([r.as_dict() for r in session.results])
    if not df.empty:
        # Formatting
        for col in ["mean_latency_ns", "min_latency_ns", "max_latency_ns", "jitter_ns"]:
            if col in df.columns:
                df[col] = df[col].round(1)
        if "throughput_mbps" in df.columns:
            df["throughput_mbps"] = df["throughput_mbps"].round(2)

        st.dataframe(
            df,
            use_container_width=True,
            height=400,
        )

        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "⬇ Download JSON",
                data=session.to_json(),
                file_name=f"bench_{session.algo}_{session.session_id[:8]}.json",
                mime="application/json",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "⬇ Download CSV",
                data=session.to_csv(),
                file_name=f"bench_{session.algo}_{session.session_id[:8]}.csv",
                mime="text/csv",
                use_container_width=True,
            )
    else:
        st.info("No results yet. Run a benchmark to populate this table.")


def _tab_system_info(session: BenchSession) -> None:
    st.markdown("### 💻 System Information")
    sys_info = session.system

    cols = st.columns(4)
    cols[0].metric("CPU", sys_info.get("cpu", "Unknown")[:30])
    cols[1].metric("Cores", str(sys_info.get("cores", "?")))
    cols[2].metric("RAM", f"{sys_info.get('ram_gb', 0):.1f} GB")
    cols[3].metric("OS", sys_info.get("os", "Unknown")[:20])

    # Session metadata
    st.markdown("**Session Metadata**")
    meta_df = pd.DataFrame(
        [
            {"Field": "Session ID", "Value": session.session_id},
            {"Field": "Timestamp", "Value": session.timestamp},
            {"Field": "Algorithm", "Value": session.algo.upper()},
            {"Field": "Mode", "Value": session.mode},
            {"Field": "Results Count", "Value": str(len(session.results))},
        ]
    )
    st.dataframe(meta_df, use_container_width=True, hide_index=True)

    # GIL comparison chart
    gil_data = st.session_state.get("gil_comparison")
    if gil_data:
        st.markdown("**GIL vs Multiprocessing Comparison**")
        fig = _chart_gil_comparison(gil_data)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

            comparison = gil_data.get("gil_comparison", [])
            if comparison:
                avg_contention = sum(d["gil_contention_ratio"] for d in comparison) / len(comparison)
                st.info(
                    f"Average GIL contention ratio: **{avg_contention * 100:.1f}%**\n\n"
                    "A low ratio means the C crypto code releases the GIL effectively, "
                    "allowing near-true parallelism with threading."
                )
    else:
        st.info(
            "Run with **'Compare GIL vs Multiprocessing'** enabled in the sidebar "
            "to see the GIL contention analysis chart."
        )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


def main() -> None:
    cfg = render_sidebar()

    # Header
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:0.5rem;">
            <div style="font-size:2rem;">⚡</div>
            <div>
                <h1 style="margin:0;font-size:1.8rem;font-weight:700;">
                    High-Concurrency Crypto Bench
                </h1>
                <p style="margin:0;color:#8B949E;font-size:13px;">
                    AES-256-CBC & SHA-256 · High-Concurrency · Saturation Analysis
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()

    # Handle Run button
    if cfg["run_clicked"] and not st.session_state["running"]:
        st.session_state["running"] = True
        st.session_state["progress"] = 0.0
        st.session_state["error"] = None

        t = threading.Thread(
            target=_run_benchmark_bg,
            args=(
                cfg["algo"],
                cfg["mode"],
                cfg["packet_sizes"],
                cfg["thread_counts"],
                cfg["iterations"],
                cfg["parallelism"],
                cfg["compare_mp"],
            ),
            daemon=True,
        )
        t.start()

    # Progress display
    if st.session_state["running"]:
        prog = st.session_state["progress"]
        label = st.session_state["progress_label"]
        st.markdown(f"**🔄 Running:** {label}")
        st.progress(prog)
        time.sleep(0.5)
        st.rerun()

    if st.session_state.get("error"):
        st.error(f"Benchmark error: {st.session_state['error']}")

    # Determine which session to display
    active_session: Optional[BenchSession] = st.session_state.get("session")

    if active_session is None:
        st.markdown(
            """
            <div style="text-align:center;padding:60px 20px;color:#8B949E;">
                <div style="font-size:4rem;margin-bottom:1rem;">📊</div>
                <div style="font-size:1.2rem;font-weight:600;color:#E6EDF3;">
                    No benchmark data yet
                </div>
                <div style="margin-top:0.5rem;font-size:0.9rem;">
                    Configure parameters in the sidebar and click
                    <b style="color:#00C8E0;">▶ Run Benchmark</b>,
                    or upload a saved JSON session to explore results.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "📈 Throughput",
            "⏱ Latency & Jitter",
            "🧵 Thread Scaling",
            "📊 Raw Data",
            "💻 System Info",
        ]
    )
    with tab1:
        _tab_throughput(active_session)
    with tab2:
        _tab_latency(active_session)
    with tab3:
        _tab_thread_scaling(active_session)
    with tab4:
        _tab_raw_data(active_session)
    with tab5:
        _tab_system_info(active_session)


if __name__ == "__main__":
    main()
