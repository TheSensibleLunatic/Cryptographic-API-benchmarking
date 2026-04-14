"""
benchmarker/cli.py — Command-line interface for marvell-crypto-bench

Usage examples:

    # AES packet sweep, default sizes, 4 threads, 500 iterations
    python -m benchmarker.cli --algo aes --mode packet-sweep --threads 4 --iterations 500

    # Full SHA sweep, custom sizes + thread list, export JSON + CSV + plots
    python -m benchmarker.cli \\
        --algo sha --mode full \\
        --threads 1,2,4,8,16,32 \\
        --sizes 64,256,1024,4096,16384,65536,1048576 \\
        --iterations 1000 \\
        --output results/session \\
        --plot

    # Run both algos, skip dashboard, just export
    python -m benchmarker.cli --algo both --mode full --no-dashboard --output out/session

    # Compare GIL vs multiprocessing
    python -m benchmarker.cli --algo aes --mode thread-sweep --mp
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from benchmarker.packet_sweep import run_full_sweep, run_packet_sweep, run_thread_sweep
from benchmarker.session import BenchSession

console = Console()

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_THREAD_COUNTS = [1, 2, 4, 8, 16, 32]
DEFAULT_PACKET_SIZES = [64, 128, 256, 512, 1024, 4096, 16384, 65536, 1048576]
DEFAULT_ITERATIONS = 1000


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marvell-crypto-bench",
        description=(
            "High-Concurrency Cryptographic API Benchmarking Tool\n"
            "AES-256-CBC and SHA-256 under variable data sizes and thread counts."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--algo",
        choices=["aes", "sha", "both"],
        default="both",
        help="Cryptographic algorithm to benchmark (default: both)",
    )
    parser.add_argument(
        "--mode",
        choices=["packet-sweep", "thread-sweep", "full"],
        default="full",
        help="Benchmark mode (default: full)",
    )
    parser.add_argument(
        "--threads",
        default=",".join(str(t) for t in DEFAULT_THREAD_COUNTS),
        help="Comma-separated thread counts (default: 1,2,4,8,16,32)",
    )
    parser.add_argument(
        "--sizes",
        default=",".join(str(s) for s in DEFAULT_PACKET_SIZES),
        help="Comma-separated packet sizes in bytes (default: 64…1048576)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Iterations per benchmark cell (default: 1000)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Base path for JSON + CSV export (e.g. results/session → writes session.json, session.csv)",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Skip launching Streamlit dashboard after benchmarking",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Save static Matplotlib plots to disk alongside JSON/CSV output",
    )
    parser.add_argument(
        "--mp",
        action="store_true",
        help="Use multiprocessing mode instead of threading (bypasses GIL)",
    )
    parser.add_argument(
        "--lib-path",
        default=None,
        help="Explicit path to libcryptobench.so (auto-discovered if omitted)",
    )
    return parser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_int_list(s: str, name: str) -> list[int]:
    try:
        return sorted(set(int(x.strip()) for x in s.split(",") if x.strip()))
    except ValueError:
        console.print(f"[red]ERROR:[/red] Invalid --{name} value: {s}")
        sys.exit(1)


def _run_for_algo(
    algo_key: str,
    mode: str,
    packet_sizes: list[int],
    thread_counts: list[int],
    iterations: int,
    mp_mode: bool,
    progress: Progress,
) -> BenchSession:
    """Run the requested mode for one algorithm and return a BenchSession."""
    parallelism = "multiprocessing" if mp_mode else "threading"
    total_cells = {
        "packet-sweep": len(packet_sizes),
        "thread-sweep": len(thread_counts),
        "full": len(packet_sizes) * len(thread_counts),
    }[mode]

    task = progress.add_task(
        f"[cyan]{algo_key.upper()}[/cyan] [{mode}]", total=total_cells
    )

    def cb(done: int, total: int) -> None:  # noqa: ARG001
        progress.update(task, completed=done)

    if mode == "packet-sweep":
        session = run_packet_sweep(
            algo=algo_key,
            packet_sizes=packet_sizes,
            thread_count=thread_counts[-1],
            iterations=iterations,
            mode=parallelism,
            progress_cb=cb,
        )
    elif mode == "thread-sweep":
        session = run_thread_sweep(
            algo=algo_key,
            data_size=packet_sizes[-1],
            thread_counts=thread_counts,
            iterations=iterations,
            mode=parallelism,
            progress_cb=cb,
        )
    else:  # full
        session = run_full_sweep(
            algo=algo_key,
            packet_sizes=packet_sizes,
            thread_counts=thread_counts,
            iterations=iterations,
            mode=parallelism,
            progress_cb=cb,
        )

    progress.update(task, completed=total_cells)
    return session


def _export_session(session: BenchSession, base_path: str) -> None:
    """Export session as JSON and CSV."""
    p = pathlib.Path(base_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    json_path = p.with_suffix(".json")
    csv_path = p.with_suffix(".csv")

    json_path.write_text(session.to_json(), encoding="utf-8")
    csv_path.write_text(session.to_csv(), encoding="utf-8")

    console.print(f"  [green]✔[/green] JSON → {json_path}")
    console.print(f"  [green]✔[/green] CSV  → {csv_path}")


def _save_plots(session: BenchSession, base_path: Optional[str]) -> None:
    """Save static Matplotlib plots."""
    try:
        from dashboard.plots import (  # noqa: PLC0415
            plot_jitter_distribution,
            plot_latency_heatmap,
            plot_thread_scaling,
            plot_throughput_vs_size,
        )
    except ImportError as e:
        console.print(f"[yellow]WARNING:[/yellow] Could not import plots: {e}")
        return

    out_dir = pathlib.Path(base_path).parent if base_path else pathlib.Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    plot_throughput_vs_size(session, str(out_dir / "throughput_vs_size.png"))
    plot_latency_heatmap(session, str(out_dir / "latency_heatmap.png"))
    plot_thread_scaling(session, str(out_dir / "thread_scaling.png"))
    plot_jitter_distribution(session, str(out_dir / "jitter_dist.png"))
    console.print(f"  [green]✔[/green] Plots saved to {out_dir}/")


def _print_summary_table(session: BenchSession) -> None:
    """Print a rich summary table of results."""
    table = Table(
        title=f"{session.algo.upper()} Benchmark Results",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Packet Size", justify="right")
    table.add_column("Threads", justify="right")
    table.add_column("Mean Latency (ns)", justify="right")
    table.add_column("Throughput (MB/s)", justify="right")
    table.add_column("Jitter (ns)", justify="right")

    for r in sorted(session.results, key=lambda x: (x.thread_count, x.packet_size_bytes)):
        table.add_row(
            f"{r.packet_size_bytes:,}",
            str(r.thread_count),
            f"{r.mean_latency_ns:,.1f}",
            f"{r.throughput_mbps:,.1f}",
            f"{r.jitter_ns:,.1f}",
        )

    console.print(table)

    if session.saturation_point:
        sp = session.saturation_point
        console.print(
            Panel(
                f"[bold yellow]Saturation Point Detected[/bold yellow]\n"
                f"Packet size: [cyan]{sp.packet_size_bytes:,}[/cyan] bytes | "
                f"Threads: [cyan]{sp.thread_count}[/cyan] | "
                f"Throughput: [cyan]{sp.throughput_mbps:.1f}[/cyan] MB/s\n\n"
                "Beyond this point, marginal throughput gains fall below 10%.\n"
                "This marks the software saturation boundary.",
                title="Saturation Analysis",
                border_style="yellow",
            )
        )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load library (validates it exists before we start timing)
    if args.lib_path:
        from benchmarker.ffi_bridge import load_library  # noqa: PLC0415

        try:
            load_library(args.lib_path)
        except (OSError, FileNotFoundError) as e:
            console.print(f"[red]ERROR:[/red] Cannot load library: {e}")
            return 1

    thread_counts = _parse_int_list(args.threads, "threads")
    packet_sizes = _parse_int_list(args.sizes, "sizes")
    algos = ["aes256", "sha256"] if args.algo == "both" else [f"{args.algo}256"]

    console.print(
        Panel(
            "[bold cyan]marvell-crypto-bench[/bold cyan]\n"
            f"Algo: [yellow]{args.algo}[/yellow] | Mode: [yellow]{args.mode}[/yellow] | "
            f"Threads: [yellow]{thread_counts}[/yellow]\n"
            f"Sizes: [yellow]{[f'{s:,}' for s in packet_sizes]}[/yellow] bytes | "
            f"Iterations: [yellow]{args.iterations:,}[/yellow] per cell\n"
            f"Parallelism: [yellow]{'multiprocessing (no GIL)' if args.mp else 'threading'}[/yellow]",
            title="Benchmark Configuration",
            border_style="cyan",
        )
    )

    sessions: list[BenchSession] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        for algo_key in algos:
            start = time.perf_counter()
            session = _run_for_algo(
                algo_key,
                args.mode,
                packet_sizes,
                thread_counts,
                args.iterations,
                args.mp,
                progress,
            )
            elapsed = time.perf_counter() - start
            sessions.append(session)
            console.print(
                f"\n[bold green]✔[/bold green] {algo_key.upper()} complete in {elapsed:.1f}s"
            )

    # Print summary tables
    for session in sessions:
        _print_summary_table(session)

    # Export
    for i, session in enumerate(sessions):
        if args.output:
            suffix = f"_{session.algo}" if len(sessions) > 1 else ""
            _export_session(session, f"{args.output}{suffix}")
        if args.plot:
            out_base = f"{args.output}_{session.algo}" if args.output else f"output_{session.algo}"
            _save_plots(session, out_base)

    # Launch Streamlit dashboard
    if not args.no_dashboard:
        import subprocess  # noqa: PLC0415

        dashboard_path = pathlib.Path(__file__).parent.parent / "dashboard" / "app.py"
        if sessions and args.output:
            json_path = pathlib.Path(f"{args.output}_{sessions[0].algo}.json")
            env_session = str(json_path) if json_path.exists() else ""
        else:
            env_session = ""

        console.print(
            "\n[bold cyan]Launching Streamlit dashboard...[/bold cyan]\n"
            "Press Ctrl+C to stop."
        )
        cmd = [sys.executable, "-m", "streamlit", "run", str(dashboard_path)]
        if env_session:
            cmd += ["--", f"--session={env_session}"]
        subprocess.run(cmd, check=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
