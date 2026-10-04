import argparse
import ipaddress
import json
import math
import platform
import socket
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def _positive_int(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value):
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


def _nonnegative_float(value):
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite nonnegative number")
    return parsed


def _port(value):
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if not 1 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be between 1 and 65535")
    return parsed


def _ip_address(value):
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a valid IPv4 or IPv6 address") from error


def _http_url(value):
    if not value.startswith(("http://", "https://")):
        raise argparse.ArgumentTypeError("must start with http:// or https://")
    return value


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Check host reachability, iperf3 throughput, DNS resolution, and HTTP/HTTPS connectivity."
    )
    parser.add_argument("--ping-host", required=True, help="host to test with ping")
    parser.add_argument("--iperf-host", required=True, help="iperf3 server host")
    parser.add_argument("--dns-name", required=True, help="DNS name to resolve")
    parser.add_argument(
        "--ping-count",
        type=_positive_int,
        default=4,
        help="number of ping requests (default: 4)",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=15,
        help="subprocess timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--iperf-port",
        type=_port,
        default=5201,
        help="iperf3 server port (default: 5201)",
    )
    parser.add_argument(
        "--min-throughput-mbps",
        type=_nonnegative_float,
        default=0,
        help="minimum received throughput in Mbps (default: 0)",
    )
    parser.add_argument(
        "--expected-dns-ip",
        type=_ip_address,
        help="require this IP address to appear in DNS results",
    )
    parser.add_argument(
        "--http-url",
        type=_http_url,
        help="HTTP or HTTPS URL to check for a successful response (2xx status)",
    )
    parser.add_argument(
        "--http-status",
        type=_positive_int,
        help="require this exact HTTP status code (default: any 2xx)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="output format: text (default) or json",
    )
    return parser


def _command_failure(result):
    detail = result.stderr.strip() or result.stdout.strip()
    if detail:
        return detail
    return f"command exited with status {result.returncode}"


def run_ping(host, count, timeout_seconds):
    count_option = "-n" if platform.system() == "Windows" else "-c"
    command = ["ping", count_option, str(count), host]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return CheckResult("Ping", False, "ping executable was not found")
    except subprocess.TimeoutExpired:
        return CheckResult("Ping", False, f"ping timed out after {timeout_seconds:g}s")
    except OSError as error:
        return CheckResult("Ping", False, f"could not run ping: {error}")

    if result.returncode != 0:
        return CheckResult("Ping", False, _command_failure(result))
    return CheckResult("Ping", True, f"{host} responded to {count} ping request(s)")


def run_iperf(host, port, minimum_mbps, timeout_seconds):
    command = ["iperf3", "-c", host, "-p", str(port), "-t", "5", "-J"]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return CheckResult("iperf3", False, "iperf3 executable was not found")
    except subprocess.TimeoutExpired:
        return CheckResult(
            "iperf3", False, f"iperf3 timed out after {timeout_seconds:g}s"
        )
    except OSError as error:
        return CheckResult("iperf3", False, f"could not run iperf3: {error}")

    if result.returncode != 0:
        return CheckResult("iperf3", False, _command_failure(result))
    try:
        report = json.loads(result.stdout)
        bits_per_second = report["end"]["sum_received"]["bits_per_second"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return CheckResult("iperf3", False, "iperf3 returned invalid JSON or no received throughput")

    if (
        isinstance(bits_per_second, bool)
        or not isinstance(bits_per_second, (int, float))
        or not math.isfinite(bits_per_second)
        or bits_per_second < 0
    ):
        return CheckResult("iperf3", False, "iperf3 returned an invalid throughput value")

    throughput_mbps = bits_per_second / 1_000_000
    detail = f"{throughput_mbps:.2f} Mbps received (minimum {minimum_mbps:.2f} Mbps)"
    return CheckResult("iperf3", throughput_mbps >= minimum_mbps, detail)


def run_dns(name, expected_ip: Optional[str] = None):
    try:
        records = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        return CheckResult("DNS", False, f"could not resolve {name}: {error}")

    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        return CheckResult("DNS", False, f"no addresses found for {name}")

    if expected_ip is not None:
        expected = str(ipaddress.ip_address(expected_ip))
        normalized_addresses = [str(ipaddress.ip_address(address)) for address in addresses]
        if expected not in normalized_addresses:
            resolved = ", ".join(addresses)
            return CheckResult(
                "DNS",
                False,
                f"expected {expected} for {name}; resolved: {resolved}",
            )

    return CheckResult("DNS", True, f"{name} resolved to {', '.join(addresses)}")


def run_http(url, expected_status: Optional[int] = None, timeout_seconds: float = 15):
    """Perform an HTTP/HTTPS GET request and check the response status code.

    Passes when the response is 2xx (or matches ``expected_status`` exactly).
    Redirects are followed automatically by urllib.
    """
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "network-health-check/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except TimeoutError:
        return CheckResult("HTTP", False, f"HTTP request timed out after {timeout_seconds:g}s")
    except urllib.error.URLError as error:
        return CheckResult("HTTP", False, f"could not reach {url}: {error.reason}")
    except OSError as error:
        return CheckResult("HTTP", False, f"could not reach {url}: {error}")

    if expected_status is not None:
        passed = status == expected_status
        detail = f"{url} returned HTTP {status} (expected {expected_status})"
    else:
        passed = 200 <= status < 300
        detail = f"{url} returned HTTP {status}"

    return CheckResult("HTTP", passed, detail)


def _print_text(results):
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.detail}")


def _print_json(results):
    output = {
        "results": [
            {"name": r.name, "passed": r.passed, "detail": r.detail}
            for r in results
        ],
        "passed": all(r.passed for r in results),
    }
    print(json.dumps(output, indent=2))


def main(argv=None):
    args = _build_parser().parse_args(argv)
    results = [
        run_ping(args.ping_host, args.ping_count, args.timeout),
        run_iperf(
            args.iperf_host,
            args.iperf_port,
            args.min_throughput_mbps,
            args.timeout,
        ),
        run_dns(args.dns_name, args.expected_dns_ip),
    ]

    if args.http_url:
        results.append(
            run_http(args.http_url, args.http_status, args.timeout)
        )

    if args.output == "json":
        _print_json(results)
    else:
        _print_text(results)

    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
