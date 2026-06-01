from pathlib import Path

from src.core.observability import log
from src.core.config import DEVELOPER_MODEL_LABEL
from src.core.models import GlobalPipelineContext
from src.core.prompts import get_system_prompt, get_skill
from src.utils.subprocess_helpers import run_claude_cli
from src.utils.git_helpers import get_git_root, get_pipeline_snapshot_files

async def run_developer_node(ctx: GlobalPipelineContext, error_trace: str = "") -> None:
    model_name = DEVELOPER_MODEL_LABEL
    log.info(f"🟩 [ROLE] Developer Agent | [MODEL] {model_name}")

    prompt = get_system_prompt("developer").format(
        instruction=ctx.contract.instruction,
        function_signatures=ctx.contract.function_signatures,
        strict_type_validation_rules=ctx.contract.strict_type_validation_rules,
        code_dir=ctx.workspace_paths.code_dir,
    ) + "\n\n" + get_skill("engineering_guide")
    
    if error_trace:
        prompt += f"\n\nValidation Failure Context:\n{error_trace}"
        prompt += "\n\n" + get_skill("deterministic_mutation")

    code_dir_path = ctx.workspace_paths.code_dir
    code_dir = str(code_dir_path)

    # The clone is already a git repo on feat/ticket-<id>; agents only mutate the working tree.
    code_files = [str(code_dir_path / f) for f in ctx.contract.files_to_modify]
    returncode = await run_claude_cli(prompt, code_files, allowed_root=code_dir)

    log.info(f"   [TOKENS] Developer Agent | Tracked out-of-band via ccusage")

    # Snapshot the production-code delta from the real git root, scoped to the source subtree.
    repo_root = Path(await get_git_root(code_dir))
    subdir = code_dir_path.resolve().relative_to(repo_root.resolve()).as_posix()
    changed_files = await get_pipeline_snapshot_files(str(repo_root), ctx.base_branch, subdir=subdir)
    parts = []
    for rel_path in changed_files:
        abs_path = repo_root / rel_path
        if abs_path.exists():
            parts.append(f"=== FILE: {rel_path} ===\n{abs_path.read_text(encoding='utf-8')}")
        else:
            parts.append(f"=== FILE: {rel_path} (DELETED) ===")
    if parts:
        ctx.production_code_snapshot = "\n\n".join(parts)

    log.info(f"   [MUTATION] Modified: {changed_files} (Exit Code: {returncode})\n")
    log.debug(f"Developer code snapshot:\n{ctx.production_code_snapshot}")
