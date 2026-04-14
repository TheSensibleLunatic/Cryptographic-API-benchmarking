# High-Concurrency Crypto Bench

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![C99](https://img.shields.io/badge/C-C99-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![CI](https://github.com/TheSensibleLunatic/Cryptographic-API-benchmarking/actions/workflows/ci.yml/badge.svg)

> *"In the era of high-speed cloud connectivity, software bottlenecks hide deep in the pipeline. We don't just measure throughput; we find exactly where it breaks."*

**High-Concurrency Crypto Bench** is a production-quality, high-concurrency cryptographic API benchmarking tool. It wraps pure C implementations of AES-256-CBC and SHA-256 with a concurrent Python harness to stress-test throughput under massive parallel load. Its primary goal is to definitively identify software saturation points — demonstrating the QA maturity aligned with high-performance throughput engineering.

## Architecture

```text
[CLI / Streamlit Dashboard]
          │
          ▼
[Python Harness (ThreadPoolExecutor / multiprocessing)]
          │ (ctypes FFI)
          ▼
[libcryptobench.so (AES-256 / SHA-256 pure C)]
          │
          ▼
[BenchResult Struct → JSON / CSV Export]
```

## Features

- **Pure C Engine:** Zero-dependency AES-256 and SHA-256 implementations.
- **Concurrent Harness:** Supports both `threading` (stressing the Python GIL) and `multiprocessing` (bypassing the GIL for true parallelism).
- **Saturation Detection:** Advanced first-derivative analysis to pinpoint exactly where marginal throughput gains drop below 10%.
- **Interactive Dashboard:** Fully offline `Streamlit` dashboard with `Plotly` charts.
- **Publication-Quality Plots:** Static `matplotlib` generators featuring a premium dark-theme aesthetic.
- **Strict Data Contracts:** JSON outputs perfectly adhere to a required rigid schema.

## Prerequisites

- Python 3.11+
- GCC and `make` (Linux x86-64 native recommended)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/TheSensibleLunatic/Cryptographic-API-benchmarking.git
   cd Cryptographic-API-benchmarking
   ```

2. **Compile the C library:**
   ```bash
   cd crypto_engine
   make all
   cd ..
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Command Line Interface

Run a full 2D sweep (sizes × threads) and export results:
```bash
python -m benchmarker.cli \
    --algo both \
    --mode full \
    --threads 1,2,4,8,16,32 \
    --sizes 64,256,1024,4096,16384,65536 \
    --iterations 1000 \
    --output results/session \
    --plot
```

Compare threading vs multiprocessing (GIL impact):
```bash
python -m benchmarker.cli --algo aes --mode thread-sweep --mp
```

For all options, see:
```bash
python -m benchmarker.cli --help
```

### Streamlit Dashboard

If you ran the CLI without `--no-dashboard`, the UI launches automatically. To launch it manually:
```bash
streamlit run dashboard/app.py
```
You can then upload a previously exported JSON session directly into the UI.

## Interpreting Results

- **Throughput Curve:** Measures MB/s processed. Expect this to rise linearly with larger packet sizes until system limits are hit.
- **Saturation Point:** Marked in the dashboard with an orange indicator. This is the exact packet size / thread count combination where increasing load yields <10% marginal gain (the bottleneck).
- **GIL Contention:** When comparing `--mp` (multiprocessing) with default threading, a high contention ratio indicates the Python Global Interpreter Lock is bottlenecking execution, despite the C engine releasing it cleanly.

### Sample JSON Output

```json
{
  "session_id": "893c5c16-e41c-4396-8ac4-9cf9b3a0fe63",
  "timestamp": "2025-01-01T12:00:00Z",
  "system": {
    "cpu": "Intel Core i9",
    "cores": 24,
    "ram_gb": 64.0,
    "os": "Linux"
  },
  "algo": "aes256",
  "mode": "full",
  "saturation_point": {
    "packet_size_bytes": 4096,
    "thread_count": 8,
    "throughput_mbps": 3200.5
  },
  "results": [
    {
      "packet_size_bytes": 4096,
      "thread_count": 8,
      "mean_latency_ns": 1240.3,
      "min_latency_ns": 980.1,
      "max_latency_ns": 1890.7,
      "jitter_ns": 145.2,
      "throughput_mbps": 3200.5,
      "iterations": 1000
    }
  ]
}
```

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, pulling requests, and how to add new algorithms.

## Security

Please read [SECURITY.md](SECURITY.md). **Do not use the C code in this repository for production cryptography.**

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
