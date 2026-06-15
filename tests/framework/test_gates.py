"""Unit tests for the runtime validation gates.

Docker is never invoked: ``asyncio.create_subprocess_exec`` and the git-root lookup are mocked so
the assembled ``docker run`` command can be inspected deterministically.
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

from src.executor.nodes.gates import run_qa_unit_tests


class RunQaUnitTestsDockerCommandTests(unittest.IsolatedAsyncioTestCase):
    """The QA gate must mount the whole clone and target dynamic paths — no artifacts hardcode."""

    @mock.patch("src.executor.nodes.gates.stream_subprocess_output", new_callable=AsyncMock)
    @mock.patch("src.executor.nodes.gates.asyncio.create_subprocess_exec", new_callable=AsyncMock)
    @mock.patch("src.executor.nodes.gates.get_git_root", new_callable=AsyncMock)
    async def test_mounts_repo_root_and_targets_dynamic_tests_dir(
        self, mock_root: AsyncMock, mock_exec: AsyncMock, _mock_stream: AsyncMock
    ) -> None:
        # Arrange — a real clone root with dynamic src/ + tests/ subdirs.
        with TemporaryDirectory() as td:
            repo = Path(td).resolve()
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            mock_root.return_value = str(repo)

            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = MagicMock()
            proc.stderr = MagicMock()
            proc.wait = AsyncMock()
            mock_exec.return_value = proc

            # Act
            ok, _log = await run_qa_unit_tests(str(repo / "src"), str(repo / "tests"))

            # Assert
            self.assertTrue(ok)
            cmd = list(mock_exec.call_args.args)
            joined = " ".join(cmd)
            # The retired artifacts/ sandbox must be gone entirely.
            self.assertNotIn("artifacts", joined)
            # The whole clone root is mounted rw at the fixed container path.
            mount = cmd[cmd.index("-v") + 1]
            self.assertEqual(mount, f"{repo}:/workspace/repo:rw")
            # Imports resolve from the repo root; discovery targets the dynamic tests subtree.
            bash_cmd = cmd[-1]
            self.assertIn("PYTHONPATH=/workspace/repo", bash_cmd)
            self.assertIn("discover -s /workspace/repo/tests", bash_cmd)

    @mock.patch("src.executor.nodes.gates.stream_subprocess_output", new_callable=AsyncMock)
    @mock.patch("src.executor.nodes.gates.asyncio.create_subprocess_exec", new_callable=AsyncMock)
    @mock.patch("src.executor.nodes.gates.get_git_root", new_callable=AsyncMock)
    async def test_nonzero_exit_reports_failure(
        self, mock_root: AsyncMock, mock_exec: AsyncMock, _mock_stream: AsyncMock
    ) -> None:
        # Arrange
        with TemporaryDirectory() as td:
            repo = Path(td).resolve()
            (repo / "src").mkdir()
            (repo / "tests").mkdir()
            mock_root.return_value = str(repo)
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout = MagicMock()
            proc.stderr = MagicMock()
            proc.wait = AsyncMock()
            mock_exec.return_value = proc

            # Act
            ok, _log = await run_qa_unit_tests(str(repo / "src"), str(repo / "tests"))

            # Assert
            self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
