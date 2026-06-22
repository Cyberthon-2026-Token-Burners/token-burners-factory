"""Unit tests for the E4 DevOps deploy-scaffolding node and its static-lint gate.

Hermetic: the LLM boundary and the `git add` subprocess are mocked, so the node test exercises the
read/classify/write/stage logic against a real TemporaryDirectory; the gate test runs pure host-side
validation (YAML well-formedness + Dockerfile directives) with no Docker/sandbox.
"""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

# devops imports src.shared.core.config at import time, which builds the genai client.
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from src.executor.agents import devops
from src.executor.nodes.gates import run_devops_gate
from src.shared.core.models import DevOpsManifests, GlobalPipelineContext, WorkspacePaths


def _ctx(repo: Path) -> GlobalPipelineContext:
    paths = WorkspacePaths(logs_dir=repo / "logs", reports_dir=repo / "reports", repo_dir=repo)
    return GlobalPipelineContext(pr_description="scaffold deployment", base_branch="main", workspace_paths=paths)


class RunDevopsNodeTests(unittest.IsolatedAsyncioTestCase):
    """The node writes the deploy manifests into the clone and stages them for the atomic commit."""

    async def test_web_service_writes_dockerfile_workflow_and_stages(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            ctx = _ctx(repo)
            manifests = DevOpsManifests(
                archetype="rest_api",
                dockerfile_content="FROM python:3.12-slim\nUSER nobody\nCMD [\"python\", \"app.py\"]\n",
                workflow_content="name: deploy\non:\n  push:\n    branches: [main]\n",
                env_scaffold_content="PORT=8080\n",
                engineering_reasoning="stateless web service → Cloud Run",
            )
            fake = (manifests, SimpleNamespace(usage_metadata=None))
            with (
                mock.patch.object(devops, "run_structured_llm", new=AsyncMock(return_value=fake)) as llm,
                mock.patch.object(devops.subprocess, "run") as git_run,
            ):
                await devops.run_devops_node(ctx, blueprint_text="a REST API", repo_map="app.py")

            # All three manifests written verbatim into the clone.
            self.assertEqual((repo / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8"),
                             manifests.workflow_content)
            self.assertEqual((repo / "Dockerfile").read_text(encoding="utf-8"), manifests.dockerfile_content)
            self.assertEqual((repo / ".env.example").read_text(encoding="utf-8"), manifests.env_scaffold_content)
            # Staged together so finalize_transaction's atomic commit includes them.
            git_run.assert_called_once()
            self.assertEqual(
                git_run.call_args.args[0],
                ["git", "add", ".github/workflows/deploy.yml", "Dockerfile", ".env.example"],
            )
            self.assertEqual(git_run.call_args.kwargs["cwd"], str(repo))
            # Against the devops role + DevOpsManifests schema; result stored on ctx.
            self.assertEqual(llm.call_args.args[0], "devops")
            self.assertIs(llm.call_args.args[1], DevOpsManifests)
            self.assertEqual(ctx.devops_manifests.archetype, "rest_api")

    async def test_cli_tool_writes_no_dockerfile(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            ctx = _ctx(repo)
            manifests = DevOpsManifests(
                archetype="cli_tool",
                dockerfile_content=None,                 # a CLI has no runtime container
                workflow_content="name: build\non:\n  push: {}\n",
                env_scaffold_content=None,
                engineering_reasoning="CLI → build/release matrix, no Cloud Run",
            )
            fake = (manifests, SimpleNamespace(usage_metadata=None))
            with (
                mock.patch.object(devops, "run_structured_llm", new=AsyncMock(return_value=fake)),
                mock.patch.object(devops.subprocess, "run") as git_run,
            ):
                await devops.run_devops_node(ctx, blueprint_text="a CLI tool", repo_map="main.py")

            self.assertTrue((repo / ".github" / "workflows" / "deploy.yml").is_file())
            self.assertFalse((repo / "Dockerfile").exists())       # hard rule: no Dockerfile for a CLI
            self.assertFalse((repo / ".env.example").exists())
            self.assertEqual(git_run.call_args.args[0], ["git", "add", ".github/workflows/deploy.yml"])

    async def test_retry_feeds_gate_feedback_into_prompt(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            ctx = _ctx(repo)
            captured: dict[str, str] = {}

            def _capture(role, model, messages):
                captured["user"] = messages[1]["content"]
                return (DevOpsManifests(archetype="rest_api", workflow_content="name: x\non: push\n",
                                        engineering_reasoning="r"),
                        SimpleNamespace(usage_metadata=None))

            with (
                mock.patch.object(devops, "run_structured_llm", new=AsyncMock(side_effect=_capture)),
                mock.patch.object(devops.subprocess, "run"),
            ):
                await devops.run_devops_node(ctx, blueprint_text="b", repo_map="m",
                                             gate_feedback="- deploy.yml is not valid YAML: bad indent")

            self.assertIn("deploy.yml is not valid YAML", captured["user"])


class RunDevopsGateTests(unittest.TestCase):
    """Static lint: deploy.yml must be well-formed YAML; a Dockerfile (if present) needs FROM + CMD."""

    def _write(self, repo: Path, workflow: str | None = None, dockerfile: str | None = None) -> None:
        if workflow is not None:
            wf = repo / ".github" / "workflows" / "deploy.yml"
            wf.parent.mkdir(parents=True, exist_ok=True)
            wf.write_text(workflow, encoding="utf-8")
        if dockerfile is not None:
            (repo / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    def test_clean_web_service_passes(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            self._write(repo, workflow="name: deploy\non:\n  push:\n    branches: [main]\n",
                        dockerfile="FROM python:3.12-slim\nCMD [\"python\", \"app.py\"]\n")
            self.assertEqual(run_devops_gate(repo), [])

    def test_clean_cli_passes_without_dockerfile(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            self._write(repo, workflow="name: build\non:\n  push: {}\n")   # no Dockerfile is fine for a CLI
            self.assertEqual(run_devops_gate(repo), [])

    def test_malformed_yaml_is_flagged(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            # A tab-indented mapping under a key is invalid YAML.
            self._write(repo, workflow="name: deploy\non:\n\tpush: bad\n")
            problems = run_devops_gate(repo)
            self.assertTrue(any("not valid YAML" in p for p in problems), problems)

    def test_missing_workflow_is_flagged(self) -> None:
        with TemporaryDirectory() as td:
            problems = run_devops_gate(Path(td))
            self.assertTrue(any("Missing .github/workflows/deploy.yml" in p for p in problems), problems)

    def test_dockerfile_missing_directives_is_flagged(self) -> None:
        with TemporaryDirectory() as td:
            repo = Path(td)
            self._write(repo, workflow="name: deploy\non:\n  push: {}\n",
                        dockerfile="RUN echo hi\n")   # no FROM, no CMD/ENTRYPOINT
            problems = run_devops_gate(repo)
            self.assertTrue(any("FROM" in p for p in problems), problems)
            self.assertTrue(any("CMD/ENTRYPOINT" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
