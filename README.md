# Network Health Checker

![CI](https://github.com/chandra23225/network-health-checker/actions/workflows/ci.yml/badge.svg)

A dependency-free Python CLI that validates host reachability, network
throughput, DNS resolution, and HTTP/HTTPS connectivity. Each check reports
`PASS` or `FAIL`, and the process exit code makes the tool usable in scripts
and CI pipelines.

## Prerequisites

- Python 3.9+
- The system `ping` command
- The `iperf3` client
- A reachable host running an `iperf3` server (`iperf3 -s`), listening on port
  5201 by default

No third-party Python packages are required. DNS checks use the machine's
configured resolver. HTTP/HTTPS checks use the Python standard library.

## Usage

### PowerShell

```powershell
python network_health_check.py `
  --ping-host <host-to-ping> `
  --iperf-host <iperf3-server> `
  --dns-name <name-to-resolve> `
  --http-url https://example.com `
  --min-throughput-mbps 10
```

### Bash (Linux/macOS)

```bash
python3 network_health_check.py \
  --ping-host <host-to-ping> \
  --iperf-host <iperf3-server> \
  --dns-name <name-to-resolve> \
  --http-url https://example.com \
  --min-throughput-mbps 10
```

For example:

```powershell
python network_health_check.py --ping-host 192.0.2.1 --iperf-host 192.0.2.2 --dns-name example.com --http-url https://example.com --min-throughput-mbps 10
```

The IP addresses in this example are reserved for documentation and must be
replaced with reachable hosts. The iperf3 server must be running on the
`--iperf-host` machine before the check.

### Options

| Option | Required | Default | Description |
| --- | --- | --- | --- |
| `--ping-host` | Yes | — | Host to check with `ping`. |
| `--iperf-host` | Yes | — | Host running the iperf3 server. |
| `--dns-name` | Yes | — | DNS name to resolve. |
| `--ping-count` | No | `4` | Number of ping requests; must be positive. |
| `--timeout` | No | `15` seconds | Timeout for each external command and HTTP request; must be positive. This does not impose a timeout on DNS resolution. |
| `--iperf-port` | No | `5201` | iperf3 server port, from 1 through 65535. |
| `--min-throughput-mbps` | No | `0` Mbps | Minimum received TCP throughput. Zero means any successful iperf3 transfer passes. |
| `--expected-dns-ip` | No | — | Require this IPv4 or IPv6 address to be among the DNS results. |
| `--http-url` | No | — | HTTP or HTTPS URL to GET. Passes on any 2xx response. Omit to skip the HTTP check. |
| `--http-status` | No | any 2xx | Require this exact HTTP status code instead of accepting any 2xx. |
| `--output` | No | `text` | Output format: `text` (human-readable) or `json` (machine-readable). |

The iperf3 check runs a five-second TCP test and reads the received throughput
from iperf3's JSON output. The ping command uses the native count option for
Windows or Unix-like systems. DNS passes when at least one address resolves,
or, if `--expected-dns-ip` is supplied, when that address appears in the
results. The HTTP check follows redirects and passes on any 2xx status, or on
the exact status supplied via `--http-status`.

## Results

The checker prints one line per check. It exits with:

- `0` when all checks pass.
- `1` when one or more checks fail.
- `2` when command-line arguments are invalid.

Missing commands, failed network checks, subprocess timeouts, HTTP errors, and
invalid iperf3 output are reported explicitly as failures.

### Text output (default)

```text
[PASS] Ping: 192.0.2.1 responded to 4 ping request(s)
[PASS] iperf3: 42.50 Mbps received (minimum 10.00 Mbps)
[PASS] DNS: example.com resolved to 93.184.216.34
[PASS] HTTP: https://example.com returned HTTP 200
```

### JSON output (`--output json`)

```json
{
  "results": [
    {"name": "Ping",   "passed": true,  "detail": "192.0.2.1 responded to 4 ping request(s)"},
    {"name": "iperf3", "passed": true,  "detail": "42.50 Mbps received (minimum 10.00 Mbps)"},
    {"name": "DNS",    "passed": true,  "detail": "example.com resolved to 93.184.216.34"},
    {"name": "HTTP",   "passed": true,  "detail": "https://example.com returned HTTP 200"}
  ],
  "passed": true
}
```

JSON output is useful for feeding results into CI pipelines, dashboards, or
automated test frameworks that consume structured data.

### Failure example

```text
[PASS] Ping: 192.0.2.1 responded to 4 ping request(s)
[FAIL] iperf3: 42.50 Mbps received (minimum 50.00 Mbps)
[FAIL] DNS: expected 192.0.2.53 for example.com; resolved: 93.184.216.34
[FAIL] HTTP: https://example.com returned HTTP 503
```

The all-PASS example exits with status `0`; the example with failures exits
with status `1`.

## Tests

Run the offline unit tests with:

```powershell
python -m unittest discover -s tests -v
```

The tests mock subprocess, DNS, and HTTP boundaries — no live network access,
`ping`, iperf3 server, or external URL is required. The CI workflow runs the
full suite on Python 3.9, 3.10, 3.11, and 3.12 on every push and pull request.

## Project

- **Network Health Checker** — Designed and built a dependency-free Python CLI
  and automated test suite that validates host reachability (ping), TCP
  throughput (iperf3), DNS resolution, and HTTP/HTTPS connectivity with
  per-check PASS/FAIL reporting and machine-readable JSON output. Mocked
  subprocess, socket, and urllib boundaries for offline unit tests across
  Python 3.9–3.12; integrated with GitHub Actions CI.
