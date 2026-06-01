import asyncio

from src.core.observability import log


async def _run_git(args: list[str], cwd: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode, stdout.decode().strip()


async def get_git_root(path: str) -> str:
    """Resolves the root of the git working tree containing ``path``.

    Built on ``git rev-parse --show-toplevel`` so callers never guess the root via ``.parent`` —
    this stays correct for nested source layouts (e.g. ``--src-dir backend/app/src``).
    """
    returncode, output = await _run_git(["rev-parse", "--show-toplevel"], cwd=path)
    if returncode != 0:
        raise RuntimeError(f"Not a git repository: {path}")
    return output


async def get_pipeline_snapshot_files(repo_path: str, base_branch: str, subdir: str | None = None) -> list[str]:
    """Returns the paths changed against ``base_branch``, scoped to ``subdir`` when given.

    Stages with ``git add -A`` first so brand-new (untracked) files are included, then takes the
    INDEX diff (``git diff --cached``) — a plain ``git diff`` would silently omit untracked files and
    starve the Reviewer of context. Paths are repo-root-relative; the ``subdir`` pathspec isolates an
    agent to its own subtree within the shared index. Agents never commit — changes remain staged.
    """
    await _run_git(["add", "-A"], cwd=repo_path)

    diff_args = ["diff", "--cached", base_branch, "--name-only"]
    if subdir:
        diff_args += ["--", subdir]

    returncode, output = await _run_git(diff_args, cwd=repo_path)

    if returncode != 0:
        log.error(f"🚨 CRITICAL: Base branch '{base_branch}' not found for diff.")
        return []

    files = [p for p in output.splitlines() if p]
    if ".gitignore" in files:
        files.remove(".gitignore")
    return files
