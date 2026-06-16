# Hardened, async Docker execution adapter. Runs a command inside the canonical image for a
# registered `environment_id` — least-privilege (non-root, no host network, ephemeral container).
import os
import asyncio
# subprocess: only PIPE constants with fixed-argument exec, never shell=True (repo convention).
import subprocess  # nosec B404

from src.shared.core.observability import log
from src.shared.core.environments import SUPPORTED_ENVIRONMENTS
from src.shared.utils.subprocess_helpers import stream_subprocess_output


async def execute_in_sandbox(environment_id: str, command: str, repo_path: str) -> tuple[int, str, str]:
    """Execute ``command`` inside the Docker image registered for ``environment_id``.

    Mounts ``repo_path`` at ``/workspace`` and returns ``(returncode, stdout, stderr)``.

    Hardening: the host NEVER spawns a shell — ``asyncio.create_subprocess_exec`` passes argv
    directly to docker; ``sh -c`` runs ONLY inside the throwaway (``--rm``), network-isolated
    (``--network none``), non-root container. ``command`` is sourced from the static registry
    (``test_cmd``/``sast_cmd``), never raw LLM text; control chars are rejected defensively rather
    than blind-suppressing the SAST linter.
    """
    if environment_id not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(
            f"Unsupported environment_id '{environment_id}'. "
            f"Choose one of: {sorted(SUPPORTED_ENVIRONMENTS)}."
        )
    if not isinstance(command, str) or not command.strip() or any(c in command for c in "\x00\n\r"):
        raise ValueError("Invalid sandbox command: must be a non-empty single-line string.")

    image = SUPPORTED_ENVIRONMENTS[environment_id]["image"]
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",                       # no host network access from the sandbox
        "-v", f"{repo_path}:/workspace", "-w", "/workspace",
    ]
    # os.getuid/getgid are POSIX-only. On POSIX hosts (incl. WSL) run as the calling user so files
    # written into the mounted volume are NOT root-owned. On win32, Docker Desktop maps ownership.
    if hasattr(os, "getuid"):
        cmd += ["--user", f"{os.getuid()}:{os.getgid()}"]
    cmd += [image, "sh", "-c", command]

    log.debug(f"Executing sandbox [{environment_id}]: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_buffer, stderr_buffer = [], []
    await asyncio.gather(
        stream_subprocess_output("docker-stdout", proc.stdout, stdout_buffer, verbose_to_console=False),
        stream_subprocess_output("docker-stderr", proc.stderr, stderr_buffer, verbose_to_console=False),
    )
    await proc.wait()
    log.debug(f"Sandbox [{environment_id}] completed with exit code: {proc.returncode}")
    return proc.returncode, "\n".join(stdout_buffer), "\n".join(stderr_buffer)
