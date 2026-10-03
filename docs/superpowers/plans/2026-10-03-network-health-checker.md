# Network Health Checker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish a dependency-free Python CLI that checks ping reachability, iperf3 throughput, and DNS resolution, reporting individual and overall pass/fail.

**Architecture:** `network_health_check.py` parses arguments and coordinates three check functions, each returning a typed result. The ping and iperf3 clients run through argument-list subprocess calls with timeouts; DNS uses `socket.getaddrinfo`. `unittest` mocks external processes and DNS so the suite is deterministic and needs no live network.

**Tech Stack:** Python 3 standard library (`argparse`, `dataclasses`, `ipaddress`, `json`, `platform`, `socket`, `subprocess`, `unittest`), system `ping` and `iperf3`.

---

## File map

- Create `network_health_check.py`: CLI, check implementations, report, exit status.
- Create `tests/test_network_health_check.py`: offline unit tests for check results, validation, and command orchestration.
- Create `README.md`: prerequisites, setup, invocation, result behavior, and portfolio project bullet.
- Keep the approved design and this plan in `docs/superpowers/`.

## Task 1: Specify check behavior with offline tests

**Files:**
- Create: `tests/test_network_health_check.py`

- [ ] **Step 1: Add tests for ping outcomes.** Use `unittest` and `unittest.mock.patch` to test `run_ping("router.example", 3, 10)` with a successful `CompletedProcess`, a nonzero return code, `FileNotFoundError`, and `TimeoutExpired`. Assert each result's `passed` field and that the command includes the expected host and platform-specific count switch (`-n` on Windows, `-c` otherwise).
- [ ] **Step 2: Add tests for iperf3 parsing and thresholds.** Mock `subprocess.run` to return JSON containing `end.sum_received.bits_per_second`. Assert 12,000,000 bps passes a 10 Mbps minimum and reports 12.00 Mbps; the same payload fails a 13 Mbps minimum. Also assert nonzero command status, missing executable, timeout, malformed JSON, and absent throughput data all return failed results.
- [ ] **Step 3: Add DNS tests.** Mock `socket.getaddrinfo` with IPv4 and IPv6 records; assert resolution passes and reports unique addresses. Assert an expected address passes when present, fails when absent, and `socket.gaierror` returns a failed result.
- [ ] **Step 4: Add CLI/report tests.** Patch the three check functions and call `main([...])` with all required targets. Assert all-pass returns 0, any failed check returns 1, and each output line is marked `[PASS]` or `[FAIL]`. Assert negative ping count, nonpositive timeout/port, negative throughput, and an invalid expected IP are rejected by argparse.
- [ ] **Step 5: Run the new tests to confirm the intended initial failure.**

Run: `python -m unittest discover -s tests -v`

Expected: test import fails because `network_health_check.py` does not exist yet.

- [ ] **Step 6: Commit the test specification.**

Run:

```powershell
git add tests/test_network_health_check.py
git commit -m "test: specify network health checks" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 2: Implement the checker and make tests pass

**Files:**
- Create: `network_health_check.py`
- Test: `tests/test_network_health_check.py`

- [ ] **Step 1: Define the shared result type and argument validation.** Add `@dataclass(frozen=True) class CheckResult` with `name: str`, `passed: bool`, `detail: str`. Build an `argparse.ArgumentParser` requiring `--ping-host`, `--iperf-host`, and `--dns-name`; accept `--ping-count` (positive integer, default 4), `--timeout` (positive seconds, default 15), `--iperf-port` (1-65535, default 5201), `--min-throughput-mbps` (nonnegative float, default 0), and `--expected-dns-ip` (validated by `ipaddress.ip_address`). Use actionable parser errors for invalid values.
- [ ] **Step 2: Implement `run_ping(host, count, timeout_seconds)`.** Build `["ping", "-n" if platform.system() == "Windows" else "-c", str(count), host]`, call `subprocess.run` with `capture_output=True`, `text=True`, `timeout=timeout_seconds`, and `check=False`. Return a passed result only for return code 0. Convert missing executable and timeout exceptions into failed results with explicit details; on command failure include stderr, falling back to stdout or the exit code.
- [ ] **Step 3: Implement `run_iperf(host, port, minimum_mbps, timeout_seconds)`.** Run `["iperf3", "-c", host, "-p", str(port), "-t", "5", "-J"]` with captured text, timeout, and `check=False`. Fail explicitly for missing executable, timeout, nonzero status, invalid JSON, or absent/non-numeric/negative `end.sum_received.bits_per_second`. Convert bps to Mbps by dividing by 1,000,000; pass when measured Mbps is greater than or equal to the requested minimum and include the measurement in the detail.
- [ ] **Step 4: Implement `run_dns(name, expected_ip=None)`.** Call `socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)`, extract unique addresses from each result's sockaddr, and report all resolved addresses. Pass if resolution is nonempty and, when supplied, the expected IP (normalized with `ipaddress.ip_address`) is present. Convert `socket.gaierror` into a failed result.
- [ ] **Step 5: Implement `main(argv=None)`.** Parse args; execute all three checks in ping, iperf3, DNS order; print one `[PASS]` or `[FAIL]` line per result; return 0 only if every result passed, otherwise 1. Add the `if __name__ == "__main__": raise SystemExit(main())` entry point.
- [ ] **Step 6: Run the targeted unit suite.**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass without invoking real network tools.

- [ ] **Step 7: Commit the implementation.**

Run:

```powershell
git add network_health_check.py tests/test_network_health_check.py
git commit -m "feat: add network health checker" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 3: Document and smoke-test the CLI

**Files:**
- Create: `README.md`
- Test: `network_health_check.py`

- [ ] **Step 1: Document prerequisites, usage, options, output, and limitations.** Include Python 3, `ping`, an `iperf3` client and reachable iperf3 server, port 5201, and the fact that DNS resolution uses the machine's configured resolver and has no per-call timeout. Add this runnable example:

```powershell
python network_health_check.py --ping-host 192.0.2.1 --iperf-host 192.0.2.2 --dns-name example.com --min-throughput-mbps 10
```

State that example IP addresses are documentation-only and must be replaced for a real run. Describe the exit codes (0 all pass, 1 one or more fail, argparse usage error for invalid options).
- [ ] **Step 2: Add the project bullet to README.** Use a concise, accurate bullet such as: “**Network Health Checker** — Built a dependency-free Python CLI that validates host reachability, iperf3 throughput thresholds, and DNS resolution with per-check PASS/FAIL reporting and scriptable exit codes.”
- [ ] **Step 3: Verify CLI help and tests.**

Run:

```powershell
python network_health_check.py --help
python -m unittest discover -s tests -v
```

Expected: help shows all required and optional arguments; all unit tests pass.

- [ ] **Step 4: Commit documentation.**

Run:

```powershell
git add README.md
git commit -m "docs: document network health checker" -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

## Task 4: Publish the requested public GitHub repository

**Files:**
- Repository: current workspace

- [ ] **Step 1: Verify local status and GitHub CLI authentication.**

Run: `git status --short --branch; gh auth status`

Expected: worktree is clean and `gh` reports an authenticated account. If the CLI is missing or no account is authenticated, stop and ask the user to install/sign in before creating a remote; do not attempt to access or disclose credentials.

- [ ] **Step 2: Create and push the public repository.**

Run: `gh repo create network-health-checker --public --source=. --remote=origin --push`

Expected: GitHub reports repository creation and the current branch is pushed to `origin`.

- [ ] **Step 3: Verify publication.**

Run: `git remote -v; git status --short --branch; gh repo view --json name,url,isPrivate`

Expected: `origin` points to the new repository, the worktree is clean, the repository name is `network-health-checker`, and `isPrivate` is `false`.
