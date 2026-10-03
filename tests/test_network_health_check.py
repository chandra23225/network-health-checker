import contextlib
import io
import json
import platform
import socket
import subprocess
import unittest
from unittest.mock import patch

from network_health_check import CheckResult, main, run_dns, run_iperf, run_ping


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


class CliTests(unittest.TestCase):
    arguments = [
        "--ping-host",
        "router.example",
        "--iperf-host",
        "iperf.example",
        "--dns-name",
        "service.example",
    ]

    def test_main_reports_all_pass_and_returns_zero(self):
        with (
            patch(
                "network_health_check.run_ping",
                return_value=CheckResult("Ping", True, "reachable"),
            ),
            patch(
                "network_health_check.run_iperf",
                return_value=CheckResult("iperf3", True, "12.00 Mbps"),
            ),
            patch(
                "network_health_check.run_dns",
                return_value=CheckResult("DNS", True, "192.0.2.5"),
            ),
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = main(self.arguments)

        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue().count("[PASS]"), 3)

    def test_main_reports_failure_and_returns_one(self):
        with (
            patch(
                "network_health_check.run_ping",
                return_value=CheckResult("Ping", True, "reachable"),
            ),
            patch(
                "network_health_check.run_iperf",
                return_value=CheckResult("iperf3", False, "server unavailable"),
            ),
            patch(
                "network_health_check.run_dns",
                return_value=CheckResult("DNS", True, "192.0.2.5"),
            ),
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
        )
        for option, value in invalid_options:
            with self.subTest(option=option):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as error:
                        main(self.arguments + [option, value])
                self.assertEqual(error.exception.code, 2)
                self.assertIn("error:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
