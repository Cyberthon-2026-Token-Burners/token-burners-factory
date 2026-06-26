---
skill_id: claude_cli_inference
type: domain
triggers: [claude, anthropic, llm, ai_api, generative, completion, chat_completion]
nodes: [techlead, developer, reviewer]
---
LANGUAGE TARGET: Python — rules for invoking the **Claude Code CLI** (`claude`) as an inference
back-end from application code.

## Approach
The application shells out to the `claude` CLI binary (already authenticated via the operator's
Claude subscription — no separate API key management in app code). The binary is invoked in
**one-shot print mode** (`-p`): it reads the prompt, streams the assistant's text to stdout, then
exits. The application captures stdout and returns it as the model's response. No SDK dependency.

## Configuration (env vars — no hard-coded values)
```python
import os

CLAUDE_CLI_BIN  = os.environ.get("CLAUDE_CLI_BIN",  "claude")
CLAUDE_MODEL    = os.environ.get("CLAUDE_MODEL",    "claude-sonnet-4-6")
CLAUDE_TIMEOUT  = int(os.environ.get("CLAUDE_TIMEOUT", "60"))   # seconds
```

## Core helper — async (FastAPI / async route handlers)
Combine the system prompt and user message into a single prompt string passed via `-p`.
Use `asyncio.create_subprocess_exec` so the call is non-blocking inside an async event loop:

```python
import asyncio, subprocess

async def call_claude(system_prompt: str, user_message: str) -> str:
    """Invoke the Claude CLI and return the assistant's text response."""
    if not user_message or not user_message.strip():
        raise ValueError("user_message must not be blank")

    combined_prompt = f"{system_prompt.strip()}\n\n---\n\n{user_message.strip()}"
    cmd = [CLAUDE_CLI_BIN, "-p", combined_prompt, "--model", CLAUDE_MODEL]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"Claude CLI timed out after {CLAUDE_TIMEOUT}s")

    if proc.returncode != 0:
        err_snippet = stderr.decode(errors="replace")[:300]
        raise RuntimeError(f"Claude CLI exited with rc={proc.returncode}: {err_snippet}")

    result = stdout.decode(errors="replace").strip()
    if not result:
        raise ValueError("Claude CLI returned an empty response")
    return result
```

## Retry on transient failures
Wrap `call_claude` with simple exponential-backoff for non-zero exit codes that indicate
transient infrastructure issues (rate limit, temporary unavailability — `rc=1` with "rate"
or "overloaded" in stderr). Do **NOT** retry authentication failures:

```python
MAX_RETRIES = 3

async def call_claude_with_retry(system_prompt: str, user_message: str) -> str:
    last_err: Exception = RuntimeError("unreachable")
    for attempt in range(MAX_RETRIES):
        try:
            return await call_claude(system_prompt, user_message)
        except RuntimeError as e:
            last_err = e
            msg = str(e).lower()
            if "rate" in msg or "overloaded" in msg or "503" in msg:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
            raise   # non-retriable error — surface immediately
    raise last_err
```

## Security
- Never log `system_prompt` or `user_message` in full when they may contain user-supplied
  content or PII — log only lengths: `f"call_claude len(system)={len(system_prompt)} len(user)={len(user_message)}"`.
- `CLAUDE_CLI_BIN` is read from env and never constructed from user input — prevents
  command injection. Do not interpolate any user-controlled string into `cmd` directly.
- `stdin=subprocess.DEVNULL` prevents the subprocess from reading from the process stdin.

## Dependency Declaration
- No Python package dependency. The `claude` CLI must be available on `PATH` in the runtime
  container. Add to the Dockerfile:
  ```dockerfile
  RUN npm install -g @anthropic-ai/claude-code
  ```
  And to `requirements.txt` — no entry needed for the CLI itself.

## Test Pattern
Patch `asyncio.create_subprocess_exec` at the **import location** of your module:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

@patch("myapp.ai_client.asyncio.create_subprocess_exec")
async def test_call_claude_success(mock_exec):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"helpful answer", b""))
    mock_proc.returncode = 0
    mock_exec.return_value = mock_proc

    result = await call_claude("You are a helper.", "What is 2+2?")
    assert result == "helpful answer"

@patch("myapp.ai_client.asyncio.create_subprocess_exec")
async def test_call_claude_cli_error(mock_exec):
    mock_proc = MagicMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b"rate limit exceeded"))
    mock_proc.returncode = 1
    mock_exec.return_value = mock_proc

    with pytest.raises(RuntimeError, match="rc=1"):
        await call_claude("system", "hello")
```
