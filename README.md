# Network Health Checker

A small, dependency-free Python CLI that checks host reachability, network
throughput, and DNS resolution. Each check reports `PASS` or `FAIL`, and the
process exit code makes the result usable in scripts and CI.

## Prerequisites

- Python 3
- The system `ping` command
- The `iperf3` client
- A reachable host running an `iperf3` server (`iperf3 -s`), listening on port
  5201 by default

No third-party Python packages are required. DNS checks use the machine's
configured resolver.

## Usage

```powershell
python network_health_check.py `
  --ping-host <host-to-ping> `
  --iperf-host <iperf3-server> `
  --dns-name <name-to-resolve> `
  --min-throughput-mbps 10
```

For example:

```powershell
python network_health_check.py --ping-host 192.0.2.1 --iperf-host 192.0.2.2 --dns-name example.com --min-throughput-mbps 10
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
| `--timeout` | No | `15` seconds | Timeout for each external command; must be positive. This does not impose a timeout on DNS resolution. |
| `--iperf-port` | No | `5201` | iperf3 server port, from 1 through 65535. |
| `--min-throughput-mbps` | No | `0` Mbps | Minimum received TCP throughput. Zero means any successful iperf3 transfer passes. |
| `--expected-dns-ip` | No | — | Require this IPv4 or IPv6 address to be among the DNS results. |

The iperf3 check runs a five-second TCP test and reads the received throughput
from iperf3's JSON output. The ping command uses the native count option for
Windows or Unix-like systems. DNS passes when at least one address resolves,
or, if `--expected-dns-ip` is supplied, when that address resolves.

## Results

The checker prints one line per check. It exits with:

- `0` when ping, iperf3, and DNS all pass.
- `1` when one or more checks fail.
- `2` when command-line arguments are invalid.

Missing commands, failed network checks, subprocess timeouts, and invalid
iperf3 output are reported explicitly as failures.

## Project

- **Network Health Checker** — Built a dependency-free Python CLI that
  validates host reachability, iperf3 throughput thresholds, and DNS
  resolution with per-check PASS/FAIL reporting and scriptable exit codes.

## Tests

Run the offline unit tests with:

```powershell
python -m unittest discover -s tests -v
```

The tests mock subprocess and DNS boundaries, so they do not require live
network access, `ping`, or an iperf3 server.
