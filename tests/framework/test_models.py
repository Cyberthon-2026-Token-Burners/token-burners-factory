"""Unit tests for the SDLC contract models and workspace bootstrap.

Filesystem is fully isolated: every WorkspacePaths construction patches
``Path.mkdir`` so the suite never touches the real artifact tree.
"""
import unittest
from pathlib import Path
from unittest import mock

from src.core.models import (
    CODE_DIR,
    LOGS_DIR,
    REPORTS_DIR,
    TESTS_DIR,
    ArchitectureContract,
    GlobalPipelineContext,
    QATestSuite,
    ReviewReport,
    WorkspacePaths,
)


class QATestSuiteFenceCleaningTests(unittest.TestCase):
    """Validator ``clean_markdown_fences`` must strip LLM markdown artifacts."""

    def test_strips_python_language_fence(self) -> None:
        # Arrange
        raw = "```python\nprint('hi')\n```"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "print('hi')")

    def test_language_fence_is_case_insensitive(self) -> None:
        # Arrange
        raw = "```PYTHON\nimport os\n```"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "import os")

    def test_strips_bare_fence_without_language(self) -> None:
        # Arrange
        raw = "```\nx = 1\n```"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "x = 1")

    def test_tolerates_trailing_whitespace_after_language_tag(self) -> None:
        # Arrange
        raw = "```python   \ndef f():\n    return 1\n```"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "def f():\n    return 1")

    def test_trims_blank_edges_when_no_fence_present(self) -> None:
        # Arrange
        raw = "\n\n   value = 42   \n\n"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "value = 42")

    def test_clean_code_passes_through_unchanged(self) -> None:
        # Arrange
        raw = "def add(a: int, b: int) -> int:\n    return a + b"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, raw)

    def test_internal_fence_like_text_is_preserved(self) -> None:
        # Arrange — only edge fences are stripped, not interior content.
        raw = "s = '```not a fence```'"
        # Act
        suite = QATestSuite(test_code=raw)
        # Assert
        self.assertEqual(suite.test_code, "s = '```not a fence```'")


class WorkspacePathsTests(unittest.TestCase):
    """Workspace bootstrap creates the canonical tree without leaking to disk."""

    def test_defaults_match_canonical_artifact_dirs(self) -> None:
        # Arrange / Act
        with mock.patch.object(Path, "mkdir") as mkdir:
            paths = WorkspacePaths()
        # Assert
        self.assertEqual(paths.code_dir, CODE_DIR)
        self.assertEqual(paths.tests_dir, TESTS_DIR)
        self.assertEqual(paths.logs_dir, LOGS_DIR)
        self.assertEqual(paths.reports_dir, REPORTS_DIR)
        self.assertEqual(mkdir.call_count, 4)

    def test_post_init_creates_each_dir_recursively_and_idempotently(self) -> None:
        # Arrange / Act
        with mock.patch.object(Path, "mkdir") as mkdir:
            WorkspacePaths()
        # Assert — every directory is created with parents + exist_ok.
        self.assertTrue(mkdir.call_args_list)
        for call in mkdir.call_args_list:
            self.assertEqual(call, mock.call(parents=True, exist_ok=True))

    def test_custom_paths_are_honoured(self) -> None:
        # Arrange
        custom = Path("/tmp/sandbox/code")
        # Act
        with mock.patch.object(Path, "mkdir"):
            paths = WorkspacePaths(code_dir=custom)
        # Assert
        self.assertEqual(paths.code_dir, custom)


class ContractModelTests(unittest.TestCase):
    """Pydantic contracts parse expected payloads and defaults."""

    def test_architecture_contract_round_trips_fields(self) -> None:
        # Arrange
        payload = {
            "files_to_modify": ["src/core/calc.py"],
            "instruction": "Implement prime sieve.",
            "function_signatures": "def is_prime(n: int) -> bool",
            "strict_type_validation_rules": "bool must raise TypeError",
            "architecture_reasoning": "Guard against bool subtype of int.",
        }
        # Act
        contract = ArchitectureContract(**payload)
        # Assert
        self.assertEqual(contract.files_to_modify, ["src/core/calc.py"])
        self.assertIn("TypeError", contract.strict_type_validation_rules)

    def test_review_report_requires_explicit_approval_flags(self) -> None:
        # Arrange / Act
        report = ReviewReport(
            code_quality_analysis="clean",
            test_integrity_analysis="no softening",
            log_verification_analysis="bandit clean",
            code_quality_approved=True,
            test_integrity_approved=False,
            diagnostic_payload="tighten assertions",
        )
        # Assert
        self.assertTrue(report.code_quality_approved)
        self.assertFalse(report.test_integrity_approved)

    def test_global_context_applies_defaults(self) -> None:
        # Arrange / Act — default_factory builds WorkspacePaths, so isolate mkdir.
        with mock.patch.object(Path, "mkdir"):
            ctx = GlobalPipelineContext(pr_description="add prime util")
        # Assert
        self.assertEqual(ctx.base_branch, "main")
        self.assertIsNone(ctx.contract)
        self.assertIsNone(ctx.review_report)
        self.assertEqual(ctx.production_code_snapshot, "")
        self.assertIsInstance(ctx.workspace_paths, WorkspacePaths)


if __name__ == "__main__":
    unittest.main()
