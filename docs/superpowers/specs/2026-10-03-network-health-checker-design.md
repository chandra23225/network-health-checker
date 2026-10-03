# Network Health Checker Design

## Goal

Provide a small, dependency-free Python command-line utility that runs ping,
iperf3, and DNS checks against user-supplied targets and reports an overall
pass/fail result suitable for a networking project portfolio.

## Interface and behavior

The user supplies the ping host, iperf3 server, and DNS name as command-line
arguments. Optional arguments configure the ping count and timeout, iperf3
server port, minimum throughput in Mbps, and an expected DNS IP address.
The iperf3 port defaults to 5201; the throughput threshold defaults to 0 Mbps,
so a successful iperf3 run passes unless a higher threshold is requested.

The program runs a bounded ping check and an iperf3 TCP client test, requesting
JSON output so throughput can be measured. DNS resolution uses Python's
standard resolver. DNS passes when at least one address resolves, or, when an
expected address is specified, only when that address is among the results.
Each check reports PASS or FAIL with a useful result or error. The program
exits successfully only when all three checks pass. Missing executables,
timeouts, command failures, and malformed iperf3 output are reported as
failures rather than silently treated as successes.

The ping command will use the platform-appropriate count and timeout options
for Windows versus Unix-like systems. Commands are invoked as argument arrays,
not shell strings. Python DNS resolution uses `socket.getaddrinfo`.

## Components and data flow

- `network_health_check.py` parses and validates command-line options, runs
  each check, formats the report, and selects the process exit status.
- A small test module verifies check results and overall exit behavior while
  mocking subprocess execution and DNS resolution; tests do not require live
  network access or installed networking tools.
- `README.md` documents prerequisites (Python, `ping`, `iperf3`, and a
  reachable iperf3 server), usage, options, and the project portfolio bullet.

The data flow is CLI options -> independent ping, iperf3, and DNS checks ->
per-check report -> exit code. No targets or credentials are embedded in the
script, and no third-party Python packages are required.

## Failure handling

Every check has a bounded command timeout where supported. Expected operational
failures (unavailable host/server, DNS lookup failure, missing tool, timeout,
throughput below threshold, or invalid tool output) become explicit per-check
FAIL results. Invalid CLI options are rejected with argparse's usage error.
The report includes the measured throughput for iperf3 when available. The
standard-library DNS lookup does not provide a per-call timeout; the report
will make resolution failures explicit.

## Validation

Unit tests cover all-checks-pass, each check failing, throughput below the
configured minimum, expected DNS IP matching/mismatching, and missing or
malformed iperf3 results. Run the tests without network access, then perform a
CLI help/smoke check. Live network tests are not required because they depend
on external hosts and an iperf3 server.

## Delivery

Publish the source, tests, and README in a new public GitHub repository named
`network-health-checker`. The README will include a concise project bullet
describing the implemented checks and pass/fail behavior.
