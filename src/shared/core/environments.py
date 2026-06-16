# Platform Paved Road — single source of truth for executable runtimes.
# The SA selects an `environment_id` from this registry; downstream agents and the Docker
# adapter look up the canonical image + commands here, so no agent can invent a tech stack.

SUPPORTED_ENVIRONMENTS = {
    "python-3.11-core": {
        "image": "python:3.11-slim",
        "sast_cmd": "bandit -r .",
        "test_cmd": "pytest",
        "description": "Python 3.11 core runtime (bandit SAST, pytest).",
    },
    "python-3.12-core": {
        "image": "python:3.12-slim",
        "sast_cmd": "bandit -r .",
        "test_cmd": "pytest",
        "description": "Python 3.12 core runtime (slim — stable C-extension builds; bandit SAST, pytest).",
    },
    "go-1.22-cli": {
        "image": "golang:1.22-alpine",
        "sast_cmd": "gosec ./...",
        "test_cmd": "go test ./...",
        "description": "Go 1.22 CLI runtime, full compile toolchain (gosec SAST, go test).",
    },
    "go-1.23-cli": {
        "image": "golang:1.23-alpine",
        "sast_cmd": "gosec ./...",
        "test_cmd": "go test ./...",
        "description": "Go 1.23 CLI runtime, full compile toolchain (gosec SAST, go test).",
    },
    "node-20-web": {
        "image": "node:20-alpine",
        "sast_cmd": "npm audit --audit-level=high",
        "test_cmd": "npm test",
        "description": "Node.js 20 / JS / React (node, npm, yarn — frontend build & tests; npm audit SAST).",
    },
    "dotnet-8-sdk": {
        "image": "mcr.microsoft.com/dotnet/sdk:8.0-alpine",
        "sast_cmd": "dotnet list package --vulnerable --include-transitive",
        "test_cmd": "dotnet test",
        "description": ".NET 8 SDK (full toolchain — dotnet build & dotnet test; vulnerable-package scan SAST).",
    },
}
