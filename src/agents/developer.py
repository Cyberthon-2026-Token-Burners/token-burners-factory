import os

from src.core.observability import log
from src.core.config import DEVELOPER_MODEL_LABEL
from src.core.models import GlobalPipelineContext
from src.utils.subprocess_helpers import run_claude_cli

async def run_developer_node(ctx: GlobalPipelineContext, error_trace: str = "") -> None:
    model_name = DEVELOPER_MODEL_LABEL
    log.info(f"🟩 [ROLE] Developer Agent | [MODEL] {model_name}")

    prompt = (
        f"Implement the core logic. Directives: {ctx.contract.instruction}. "
        f"Signatures: {ctx.contract.function_signatures}. "
        f"Strict type rules: {ctx.contract.strict_type_validation_rules}. "
        f"Save all files under: {ctx.workspace_paths.code_dir}"
    )
    if error_trace:
        prompt += f"\n\nValidation Failure Context:\n{error_trace}"

    # Deterministically place generated code under the artifacts code dir
    code_files = [str(ctx.workspace_paths.code_dir / f) for f in ctx.contract.files_to_modify]
    returncode = await run_claude_cli(prompt, code_files, allowed_root=str(ctx.workspace_paths.code_dir))

    log.info(f"   [TOKENS] Developer Agent | Tracked out-of-band via ccusage")

    # Save a snapshot of the fresh code into state
    prod_file = ctx.workspace_paths.code_dir / ctx.contract.files_to_modify[0]
    if os.path.exists(prod_file):
        with open(prod_file, "r", encoding="utf-8") as f:
            ctx.production_code_snapshot = f.read()

    log.info(f"   [MUTATION] Modified: {code_files} (Exit Code: {returncode})\n")
    log.debug(f"Developer code snapshot:\n{ctx.production_code_snapshot}")
