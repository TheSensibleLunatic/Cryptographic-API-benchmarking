# Security Policy

## Supported Versions

Currently, only the `main` branch is actively supported.

## Educational / Benchmarking Warning

**⚠️ CRITICAL WARNING:**

The C implementations of AES-256 and SHA-256 located in the `crypto_engine/` directory are designed **exclusively for benchmarking, educational, and performance analysis purposes.**

These implementations:
1. Are **NOT** hardened against side-channel attacks (such as cache-timing attacks).
2. Have **NOT** undergone formal cryptographic security audits.
3. Prioritize clean, cross-platform algorithmic execution over safe memory scrubbing or constant-time secrets handling.

**DO NOT use `libcryptobench.so` or the C source files for production cryptography, key exchange, data protection, or any real-world security engineering.**

For production cryptographic needs, please rely on heavily audited, industry-standard libraries such as [OpenSSL](https://www.openssl.org/), [BoringSSL](https://boringssl.googlesource.com/boringssl/), or [libsodium](https://doc.libsodium.org/).

## Reporting a Vulnerability

If you discover a vulnerability in the *Python harness*, *Streamlit application*, or *automation scripting* (e.g., path traversal, code injection), please open an issue in the tracker or contact the maintainers directly.

Vulnerabilities regarding side-channels in the C implementations will be noted but are fundamentally out-of-scope for the design intent of this repository.
