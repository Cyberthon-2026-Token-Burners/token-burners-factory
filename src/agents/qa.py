import os
import sys
import asyncio

from src.core.observability import log, log_token_usage
from src.core.config import instructor_client, QA_MODEL
from src.core.models import QATestSuite, GlobalPipelineContext
from src.utils.api_retry import with_api_retry

async def run_qa_agent_node(ctx: GlobalPipelineContext, error_trace: str = "") -> None:
    model_name = QA_MODEL
    log.info(f"🔶 [ROLE] QA Agent | [MODEL] {model_name}")

    if not ctx.contract or not ctx.contract.files_to_modify:
        log.error("🚨 CRITICAL: Cannot generate tests without a locked Architecture Contract.")
        sys.exit(1)

    # Dynamically derive the test file name based on production code
    prod_file = ctx.contract.files_to_modify[0]
    module_name = prod_file.replace(".py", "")
    ctx.test_file_name = (ctx.workspace_paths.tests_dir / f"test_{prod_file}").as_posix()

    prompt = (
        f"You are a QA Agent. Write a comprehensive, robust Python unittest suite for: {ctx.contract.function_signatures}\n"
        f"Target module to import: {module_name}\n"
        f"Strict validation rules to enforce: {ctx.contract.strict_type_validation_rules}\n"
        f"CRITICAL RULE: The generated test suite must be completely deterministic. You are STRICTLY FORBIDDEN from wrapping boundary tests or type validation checks in try-except blocks, pass statements, or conditional if-else assertions. If a type or value is invalid according to the contract, use self.assertRaises() exclusively."
    )
    if error_trace:
        prompt += f"\n\nPrevious failure feedback to address:\n{error_trace}"

    @with_api_retry(max_retries=3, agent_name="QA Agent")
    async def _invoke_llm() -> tuple:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: instructor_client.chat.completions.create_with_completion(
                model=model_name,
                response_model=QATestSuite,
                messages=[
                    {"role": "system", "content": "You are an automated QA engineer producing pure Python unittest files. No markdown, no commentary."},
                    {"role": "user", "content": prompt}
                ]
            )
        )

    suite, raw_response = await _invoke_llm()

    ctx.test_code_snapshot = suite.test_code
    log_token_usage("QA Agent", raw_response)

    with open(ctx.test_file_name, "w", encoding="utf-8") as f:
        f.write(ctx.test_code_snapshot)

    log.info("   [THOUGHT] Generated deterministic unittest suite targeting strict type enforcement and contract safety.")
    log.info(f"   [ARTIFACT] Instantiated test suite at '{ctx.test_file_name}'\n")
    log.debug(f"QA Agent Output written to {ctx.test_file_name}")
