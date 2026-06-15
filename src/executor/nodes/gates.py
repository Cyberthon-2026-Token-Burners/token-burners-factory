import os
import sys
import asyncio
from pathlib import Path
# subprocess: only trusted, fixed-argument tool invocations (docker/bandit), never shell=True.
import subprocess  # nosec B404

from src.shared.core.observability import log
from src.shared.utils.subprocess_helpers import stream_subprocess_output
from src.shared.utils.git_helpers import get_git_root

# ==========================================
# PARALLEL RUNTIME GATES (Subprocess execution)
# ==========================================
async def run_qa_unit_tests(code_dir: str, tests_dir: str) -> tuple[bool, list[str]]:
    # Mount the WHOLE cloned repo read-write at a fixed container path so absolute imports
    # (e.g. `from src.shared.utils.x import y`) resolve from the repo root, and discover the agent-generated
    # test tree at its dynamic location. The git root (not a guessed parent) anchors the mount.
    repo_root = await get_git_root(code_dir)
    tests_rel = Path(tests_dir).resolve().relative_to(Path(repo_root).resolve()).as_posix()
    container_root = "/workspace/repo"
    tests_container = f"{container_root}/{tests_rel}"
    test_command = (
        f"export PYTHONPATH={container_root}; "
        f"python3 -m unittest discover -s {tests_container} -p 'test_*.py'"
    )
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{repo_root}:{container_root}:rw",
        "-w", container_root,
        "python:3.11-slim",
        "bash", "-c", test_command
    ]

    log.debug(f"Executing QA runtime gate: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_buffer, stderr_buffer = [], []

    await asyncio.gather(
        stream_subprocess_output("docker-qa-stdout", proc.stdout, stdout_buffer, verbose_to_console=False),
        stream_subprocess_output("docker-qa-stderr", proc.stderr, stderr_buffer, verbose_to_console=False)
    )
    await proc.wait()

    # Combine stdout and stderr outputs
    total_log = stdout_buffer + stderr_buffer
    log.debug(f"QA Runtime Gate completed with exit code: {proc.returncode}")
    return (proc.returncode == 0), total_log

async def run_security_scan(files: list[str]) -> tuple[bool, list[str]]:
    # Guard block to prevent Bandit from hanging or crashing
    if not files or not all(isinstance(f, str) and f.strip() for f in files):
        log.warning("SAST Error: No target execution files specified in contract.")
        return False, ["SAST Error: No target execution files specified in contract."]

    cmd = [sys.executable, "-m", "bandit", "-q", "-r"] + files
    log.debug(f"Executing SAST security gate: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_buffer, stderr_buffer = [], []

    await asyncio.gather(
        stream_subprocess_output("bandit-stdout", proc.stdout, stdout_buffer, verbose_to_console=False),
        stream_subprocess_output("bandit-stderr", proc.stderr, stderr_buffer, verbose_to_console=False)
    )
    await proc.wait()

    total_log = stdout_buffer + stderr_buffer
    if proc.returncode == 0 and not "".join(total_log).strip():
        total_log = ["Bandit execution passed. Zero vulnerabilities identified."]

    log.debug(f"SAST Security Gate completed with exit code: {proc.returncode}")
    return (proc.returncode == 0), total_log
