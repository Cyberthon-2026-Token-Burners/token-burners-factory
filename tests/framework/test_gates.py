"""Unit tests for the runtime validation gates.

Docker is never invoked: ``execute_in_sandbox`` / ``run_in_image`` are mocked so the registry-sourced
commands, the network phasing, and the adapter's ``(returncode, stdout, stderr)`` contract can be
inspected deterministically.
"""
import unittest
from unittest import mock
from unittest.mock import AsyncMock, call

from src.executor.nodes.gates import (
    run_qa_unit_tests, run_security_scan, run_build_gate, build_failure_is_test_only,
)
from src.shared.core.environments import SUPPORTED_ENVIRONMENTS, SAST_IMAGE, SAST_CMD

_ENV = "python-3.12-core"
_REPO = "/abs/repo/root"
_SETUP = SUPPORTED_ENVIRONMENTS[_ENV]["setup_cmd"]
_TEST = SUPPORTED_ENVIRONMENTS[_ENV]["test_cmd"]
_BUILD = SUPPORTED_ENVIRONMENTS[_ENV]["build_cmd"]


class RunQaUnitTestsTests(unittest.IsolatedAsyncioTestCase):
    """The QA gate restores deps (network ON) then runs the registry test_cmd (network OFF)."""

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_restore_then_test_with_network_phasing(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.side_effect = [(0, "restored", ""), (0, "ran 3 tests", "")]

        ok, log_lines = await run_qa_unit_tests(environment_id=_ENV, repo_root=_REPO)

        self.assertTrue(ok)
        # Restore runs first (network ON), then tests (network OFF).
        self.assertEqual(mock_sandbox.await_args_list, [
            call(_ENV, _SETUP, _REPO, network="bridge"),
            call(_ENV, _TEST, _REPO, network="none"),
        ])
        self.assertEqual(log_lines, ["restored", "ran 3 tests"])

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_restore_failure_short_circuits_before_tests(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.return_value = (1, "could not resolve deps", "")

        ok, log_lines = await run_qa_unit_tests(environment_id=_ENV, repo_root=_REPO)

        self.assertFalse(ok)
        mock_sandbox.assert_awaited_once_with(_ENV, _SETUP, _REPO, network="bridge")  # tests never reached
        self.assertIn("🚨 Dependency restore failed:", log_lines[0])

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_nonzero_test_exit_reports_failure(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.side_effect = [(0, "", ""), (1, "out line", "err line")]

        ok, log_lines = await run_qa_unit_tests(environment_id=_ENV, repo_root=_REPO)

        self.assertFalse(ok)
        self.assertEqual(log_lines, ["out line", "err line"])


class RunBuildGateTests(unittest.IsolatedAsyncioTestCase):
    """The compile gate restores deps (network ON) then builds (network OFF) — build/run only."""

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_restore_then_build_with_network_phasing(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.side_effect = [(0, "restored", ""), (0, "build ok", "")]

        ok, log_lines = await run_build_gate(environment_id=_ENV, repo_root=_REPO)

        self.assertTrue(ok)
        self.assertEqual(mock_sandbox.await_args_list, [
            call(_ENV, _SETUP, _REPO, network="bridge"),
            call(_ENV, _BUILD, _REPO, network="none"),
        ])

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_nonzero_build_exit_reports_failure(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.side_effect = [(0, "", ""), (1, "undefined: Foo", "")]

        ok, log_lines = await run_build_gate(environment_id=_ENV, repo_root=_REPO)

        self.assertFalse(ok)
        self.assertIn("undefined: Foo", log_lines)

    @mock.patch("src.executor.nodes.gates.execute_in_sandbox", new_callable=AsyncMock)
    async def test_restore_failure_short_circuits_before_build(self, mock_sandbox: AsyncMock) -> None:
        mock_sandbox.return_value = (1, "deps error", "")

        ok, log_lines = await run_build_gate(environment_id=_ENV, repo_root=_REPO)

        self.assertFalse(ok)
        mock_sandbox.assert_awaited_once_with(_ENV, _SETUP, _REPO, network="bridge")  # build never reached


class RunSecurityScanTests(unittest.IsolatedAsyncioTestCase):
    """The SAST gate runs the GENERIC Semgrep image (not the language image) over the repo."""

    @mock.patch("src.executor.nodes.gates.run_in_image", new_callable=AsyncMock)
    async def test_runs_generic_semgrep_image_offline(self, mock_run: AsyncMock) -> None:
        mock_run.return_value = (1, "findings", "")

        ok, log_lines = await run_security_scan(environment_id=_ENV, repo_root=_REPO)

        self.assertFalse(ok)
        # Vendored-rules image → fully offline (no semgrep.dev call behind the corporate proxy).
        mock_run.assert_awaited_once_with(SAST_IMAGE, SAST_CMD, _REPO, network="none")
        self.assertEqual(log_lines, ["findings"])

    @mock.patch("src.executor.nodes.gates.run_in_image", new_callable=AsyncMock)
    async def test_silent_success_injects_pass_message(self, mock_run: AsyncMock) -> None:
        mock_run.return_value = (0, "", "")

        ok, log_lines = await run_security_scan(environment_id=_ENV, repo_root=_REPO)

        self.assertTrue(ok)
        self.assertEqual(log_lines, ["SAST execution passed. Zero vulnerabilities identified."])


class BuildFailureClassifierTests(unittest.TestCase):
    """`build_failure_is_test_only` decides whether a build failure is QA-owned (test files only)."""

    _GO = "go-1.23-cli"

    def test_test_only_failure_is_true(self) -> None:
        lines = [
            "internal/converter/processor_test.go:1:1: expected 'package', found 'import'",
            "cmd/json2csv/main_test.go:1:1: expected 'package', found 'import'",
        ]
        self.assertTrue(build_failure_is_test_only(self._GO, lines))

    def test_mixed_prod_and_test_is_false(self) -> None:
        lines = [
            "internal/converter/processor.go:10:2: undefined: Foo",
            "internal/converter/processor_test.go:1:1: expected 'package', found 'import'",
        ]
        self.assertFalse(build_failure_is_test_only(self._GO, lines))

    def test_production_only_is_false(self) -> None:
        self.assertFalse(build_failure_is_test_only(self._GO, ["cmd/json2csv/main.go:3:1: syntax error"]))

    def test_no_file_refs_is_false(self) -> None:
        self.assertFalse(build_failure_is_test_only(self._GO, ["go: some toolchain error", ""]))


if __name__ == "__main__":
    unittest.main()
