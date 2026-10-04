import contextlib
import io
import json
import platform
import socket
import subprocess
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

from network_health_check import CheckResult, main, run_dns, run_http, run_iperf, run_ping


class PingTests(unittest.TestCase):
    @patch("network_health_check.subprocess.run")
    def test_ping_passes_when_command_succeeds(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["ping"], returncode=0, stdout="reply", stderr=""
        )

        result = run_ping("router.example", 3, 10)

        self.assertTrue(result.passed)
        self.assertEqual(result.name, "Ping")
        command = run.call_args.args[0]
        self.assertEqual(command[-1], "router.example")
        self.assertIn("-n" if platform.system() == "Windows" else "-c", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 10)

    @patch("network_health_check.subprocess.run")
    def test_ping_fails_with_command_error(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=["ping"], returncode=1, stdout="", stderr="host unreachable"
        )

        result = run_ping("router.example", 3, 10)

        self.assertFalse(result.passed)
        self.assertIn("host unreachable", result.detail)

    @patch("network_health_check.subprocess.run", side_effect=FileNotFoundError)
    def test_ping_fails_when_executable_is_missing(self, _run):
        result = run_ping("router.example", 3, 10)

        self.assertFalse(result.passed)
        self.assertIn("ping", result.detail.lower())

    @patch(
        "network_health_check.subprocess.run",
        side_effect=subprocess.TimeoutExpired("ping", 10),
    )
    def test_ping_fails_when_command_times_out(self, _run):
        result = run_ping("router.example", 3, 10)

        self.assertFalse(result.passed)
        self.assertIn("timed out", result.detail.lower())


class IperfTests(unittest.TestCase):
    @staticmethod
    def completed(payload, returncode=0, stderr=""):
        return subprocess.CompletedProcess(
            args=["iperf3"], returncode=returncode, stdout=payload, stderr=stderr
        )

    @patch("network_health_check.subprocess.run")
    def test_iperf_passes_when_throughput_meets_minimum(self, run):
        run.return_value = self.completed(
            json.dumps({"end": {"sum_received": {"bits_per_second": 12_000_000}}})
        )

        result = run_iperf("iperf.example", 5201, 10, 15)

        self.assertTrue(result.passed)
        self.assertIn("12.00 Mbps", result.detail)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["iperf3", "-c", "iperf.example", "-p", "5201"])
        self.assertIn("-J", command)

    @patch("network_health_check.subprocess.run")
    def test_iperf_fails_when_throughput_is_below_minimum(self, run):
        run.return_value = self.completed(
            json.dumps({"end": {"sum_received": {"bits_per_second": 12_000_000}}})
        )

        result = run_iperf("iperf.example", 5201, 13, 15)

        self.assertFalse(result.passed)
        self.assertIn("12.00 Mbps", result.detail)
        self.assertIn("13.00 Mbps", result.detail)

    def test_iperf_fails_for_nonzero_exit_code(self):
        with patch("network_health_check.subprocess.run") as run:
            run.return_value = self.completed("", returncode=1, stderr="server refused")

            result = run_iperf("iperf.example", 5201, 0, 15)

        self.assertFalse(result.passed)
        self.assertIn("server refused", result.detail)

    def test_iperf_fails_when_executable_is_missing(self):
        with patch(
            "network_health_check.subprocess.run", side_effect=FileNotFoundError
        ):
            result = run_iperf("iperf.example", 5201, 0, 15)

        self.assertFalse(result.passed)
        self.assertIn("iperf3", result.detail.lower())

    def test_iperf_fails_when_command_times_out(self):
        with patch(
            "network_health_check.subprocess.run",
            side_effect=subprocess.TimeoutExpired("iperf3", 15),
        ):
            result = run_iperf("iperf.example", 5201, 0, 15)

        self.assertFalse(result.passed)
        self.assertIn("timed out", result.detail.lower())

    def test_iperf_fails_for_malformed_json(self):
        with patch("network_health_check.subprocess.run") as run:
            run.return_value = self.completed("{not json")

            result = run_iperf("iperf.example", 5201, 0, 15)

        self.assertFalse(result.passed)
        self.assertIn("json", result.detail.lower())

    def test_iperf_fails_when_throughput_is_missing_or_invalid(self):
        payloads = (
            json.dumps({"end": {"sum_sent": {"bits_per_second": 12_000_000}}}),
            json.dumps({"end": {"sum_received": {"bits_per_second": -1}}}),
            json.dumps({"end": {"sum_received": {"bits_per_second": "fast"}}}),
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                with patch("network_health_check.subprocess.run") as run:
                    run.return_value = self.completed(payload)

                    result = run_iperf("iperf.example", 5201, 0, 15)

                self.assertFalse(result.passed)


class DnsTests(unittest.TestCase):
    @staticmethod
    def record(address, family=socket.AF_INET):
        sockaddr = (address, 0) if family == socket.AF_INET else (address, 0, 0, 0)
        return (family, socket.SOCK_STREAM, 6, "", sockaddr)

    @patch("network_health_check.socket.getaddrinfo")
    def test_dns_passes_and_reports_unique_addresses(self, getaddrinfo):
        getaddrinfo.return_value = [
            self.record("192.0.2.5"),
            self.record("192.0.2.5"),
            self.record("2001:db8::5", socket.AF_INET6),
        ]

        result = run_dns("service.example")

        self.assertTrue(result.passed)
        self.assertIn("192.0.2.5", result.detail)
        self.assertIn("2001:db8::5", result.detail)
        self.assertEqual(result.detail.count("192.0.2.5"), 1)

    @patch("network_health_check.socket.getaddrinfo")
    def test_dns_passes_when_expected_ip_is_resolved(self, getaddrinfo):
        getaddrinfo.return_value = [self.record("192.0.2.5")]

        result = run_dns("service.example", "192.0.2.5")

        self.assertTrue(result.passed)

    @patch("network_health_check.socket.getaddrinfo")
    def test_dns_fails_when_expected_ip_is_not_resolved(self, getaddrinfo):
        getaddrinfo.return_value = [self.record("192.0.2.5")]

        result = run_dns("service.example", "192.0.2.6")

        self.assertFalse(result.passed)
        self.assertIn("192.0.2.6", result.detail)

    @patch(
        "network_health_check.socket.getaddrinfo",
        side_effect=socket.gaierror("name not found"),
    )
    def test_dns_fails_when_name_does_not_resolve(self, _getaddrinfo):
        result = run_dns("missing.example")

        self.assertFalse(result.passed)
        self.assertIn("name not found", result.detail)


class HttpTests(unittest.TestCase):
    """Tests for run_http — all network I/O is mocked via urllib.request.urlopen."""

    @staticmethod
    def _mock_response(status):
        response = MagicMock()
        response.status = status
        response.__enter__ = lambda s: s
        response.__exit__ = MagicMock(return_value=False)
        return response

    @patch("network_health_check.urllib.request.urlopen")
    def test_http_passes_on_200(self, urlopen):
        urlopen.return_value = self._mock_response(200)

        result = run_http("https://example.com")

        self.assertTrue(result.passed)
        self.assertEqual(result.name, "HTTP")
        self.assertIn("200", result.detail)

    @patch("network_health_check.urllib.request.urlopen")
    def test_http_passes_on_any_2xx(self, urlopen):
        for status in (201, 204, 206):
            with self.subTest(status=status):
                urlopen.return_value = self._mock_response(status)
                result = run_http("https://example.com")
                self.assertTrue(result.passed)

    @patch("network_health_check.urllib.request.urlopen")
    def test_http_fails_on_server_error(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=None,
        )

        result = run_http("https://example.com")

        self.assertFalse(result.passed)
        self.assertIn("503", result.detail)

    @patch("network_health_check.urllib.request.urlopen")
    def test_http_passes_when_expected_status_matches(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com",
            code=301,
            msg="Moved Permanently",
            hdrs=None,
            fp=None,
        )

        result = run_http("https://example.com", expected_status=301)

        self.assertTrue(result.passed)
        self.assertIn("301", result.detail)

    @patch("network_health_check.urllib.request.urlopen")
    def test_http_fails_when_expected_status_does_not_match(self, urlopen):
        urlopen.return_value = self._mock_response(200)

        result = run_http("https://example.com", expected_status=204)

        self.assertFalse(result.passed)
        self.assertIn("200", result.detail)
        self.assertIn("204", result.detail)

    @patch(
        "network_health_check.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    )
    def test_http_fails_on_url_error(self, _urlopen):
        result = run_http("https://example.com")

        self.assertFalse(result.passed)
        self.assertIn("connection refused", result.detail)

    @patch(
        "network_health_check.urllib.request.urlopen",
        side_effect=TimeoutError(),
    )
    def test_http_fails_on_timeout(self, _urlopen):
        result = run_http("https://example.com", timeout_seconds=5)

        self.assertFalse(result.passed)
        self.assertIn("timed out", result.detail.lower())


class CliTests(unittest.TestCase):
    arguments = [
        "--ping-host", "router.example",
        "--iperf-host", "iperf.example",
        "--dns-name", "service.example",
    ]

    def _all_pass_patches(self):
        return (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        )

    def test_main_reports_all_pass_and_returns_zero(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(self.arguments)

        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().count("[PASS]"), 3)

    def test_main_reports_failure_and_returns_one(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", False, "server unavailable")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(self.arguments)

        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue().count("[FAIL]"), 1)
        self.assertIn("server unavailable", output.getvalue())

    def test_main_rejects_invalid_numeric_and_ip_arguments(self):
        invalid_options = (
            ("--ping-count", "-1"),
            ("--timeout", "0"),
            ("--iperf-port", "65536"),
            ("--min-throughput-mbps", "-1"),
            ("--expected-dns-ip", "not-an-ip"),
            ("--http-url", "ftp://example.com"),
        )
        for option, value in invalid_options:
            with self.subTest(option=option):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as error:
                        main(self.arguments + [option, value])
                self.assertEqual(error.exception.code, 2)
                self.assertIn("error:", stderr.getvalue())

    def test_main_runs_http_check_when_url_provided(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
            patch("network_health_check.run_http",
                  return_value=CheckResult("HTTP", True, "https://example.com returned HTTP 200")) as mock_http,
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(self.arguments + ["--http-url", "https://example.com"])

        self.assertEqual(status, 0)
        mock_http.assert_called_once()
        self.assertEqual(output.getvalue().count("[PASS]"), 4)

    def test_main_skips_http_check_when_url_not_provided(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
            patch("network_health_check.run_http") as mock_http,
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(self.arguments)

        mock_http.assert_not_called()

    # ── JSON output mode ──────────────────────────────────────────────────────

    def test_json_output_is_valid_json(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(self.arguments + ["--output", "json"])

        parsed = json.loads(output.getvalue())
        self.assertIn("results", parsed)
        self.assertIn("passed", parsed)
        self.assertTrue(parsed["passed"])
        self.assertEqual(len(parsed["results"]), 3)

    def test_json_output_marks_overall_passed_false_on_any_failure(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", False, "too slow")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(self.arguments + ["--output", "json"])

        parsed = json.loads(output.getvalue())
        self.assertFalse(parsed["passed"])
        self.assertEqual(status, 1)

    def test_json_output_contains_expected_fields_per_result(self):
        with (
            patch("network_health_check.run_ping",
                  return_value=CheckResult("Ping", True, "reachable")),
            patch("network_health_check.run_iperf",
                  return_value=CheckResult("iperf3", True, "12.00 Mbps")),
            patch("network_health_check.run_dns",
                  return_value=CheckResult("DNS", True, "192.0.2.5")),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(self.arguments + ["--output", "json"])

        parsed = json.loads(output.getvalue())
        for item in parsed["results"]:
            self.assertIn("name", item)
            self.assertIn("passed", item)
            self.assertIn("detail", item)
            self.assertIsInstance(item["passed"], bool)


if __name__ == "__main__":
    unittest.main()
