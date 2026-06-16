---
name: run-tests-via-wsl
description: "Run this project's tests/bandit/python through WSL — the Windows interpreter lacks the deps; the venv is WSL-only."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: faab62af-8912-45c5-a39b-33e505d9fa57
---

Always run this project's test suite, `bandit`, and any `venv/bin/python` invocation through **WSL**, never the Windows interpreter.

**Why:** The Windows `python` (3.13, under `~/AppData/.../Python313`) does NOT have the project dependencies (`instructor`, `google.genai`, …) → `ModuleNotFoundError`. The project `venv/` is a WSL-created venv (POSIX `venv/bin/` layout, Python 3.12, symlinked to `/usr/bin/python3`); from Windows/Git-Bash that `python` symlink is a **broken link**, so it only resolves inside WSL.

**How to apply:** Wrap commands, e.g.
- tests: `wsl -e bash -lc "cd /mnt/c/code/async-agentic-sdlc && export GEMINI_API_KEY=test-key && venv/bin/python -m unittest discover -s tests"`
- bandit: `wsl -e bash -lc "cd /mnt/c/code/async-agentic-sdlc && venv/bin/bandit -r src/"`

`GEMINI_API_KEY` must be set before import (config builds the genai client at module-import time; a dummy `test-key` suffices for the mocked suites). Related: [[debugging-protocol]].
