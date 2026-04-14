# Contributing to Marvell Crypto Bench

Thank you for your interest in improving this tool!

## Development Setup

1. Fork the repo and clone it locally.
2. Create a virtual environment (`python -m venv venv && source venv/bin/activate`).
3. Install dev dependencies: `pip install -e ".[dev]"`.
4. Compile the C engine: `cd crypto_engine && make all`.

## Code Style

This project strictly follows `black` formatting and `flake8` linting conventions. The maximum line length is set to 100 characters.

Before committing, run:
```bash
black .
flake8 .
```

## Adding a New Algorithm

To add a new cryptographic algorithm to the benchmark suite, please complete the following checklist:

1. **C Engine (`crypto_engine/`)**:
   - Create `{algo}.c` and `{algo}.h` with pure C implementations.
   - Expose a `run_{algo}_bench(size_t, int)` function in `bench_api.c`.
   - Update `Makefile` to compile the new objects into `libcryptobench.so`.
2. **FFI Bridge (`benchmarker/ffi_bridge.py`)**:
   - Add the new `run_{algo}_bench` wrapper to `load_library()`.
3. **CLI (`benchmarker/cli.py`)**:
   - Update `--algo` argument choices.
4. **Dashboard (`dashboard/app.py`)**:
   - Add the new algorithm to the sidebar dropdown if necessary.
5. **Tests (`tests/`)**:
   - Add mock data and test coverage for the new algorithm path.
6. **PR Review**:
   - Ensure the C code compiles with zero warnings under `-Wall -Wextra`.

## Committing

Please use descriptive commit messages and reference related issues where applicable.

Make sure CI passes on your fork before opening a Pull Request!
