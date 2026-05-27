import os
import sys
import asyncio
import instructor
from google.genai.errors import ClientError

from src.core.observability import log, log_token_usage
from src.core.config import get_genai_client, handle_quota_error, QA_MODEL
from src.core.models import QATestSuite, GlobalPipelineContext

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

    client = instructor.from_genai(
        client=get_genai_client(),
        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
    )

    prompt = (
        f"You are a QA Agent. Write a comprehensive, robust Python unittest suite for: {ctx.contract.function_signatures}\n"
        f"Target module to import: {module_name}\n"
        f"Strict validation rules to enforce: {ctx.contract.strict_type_validation_rules}\n"
        f"CRITICAL RULE: The generated test suite must be completely deterministic. You are STRICTLY FORBIDDEN from wrapping boundary tests or type validation checks in try-except blocks, pass statements, or conditional if-else assertions. If a type or value is invalid according to the contract, use self.assertRaises() exclusively."
    )
    if error_trace:
        prompt += f"\n\nPrevious failure feedback to address:\n{error_trace}"

    max_api_retries = 3
    for api_attempt in range(1, max_api_retries + 1):
        try:
            loop = asyncio.get_running_loop()
            suite, raw_response = await loop.run_in_executor(
                None, lambda: client.chat.completions.create_with_completion(
                    model=model_name,
                    response_model=QATestSuite,
                    messages=[
                        {"role": "system", "content": "You are an automated QA engineer producing pure Python unittest files. No markdown, no commentary."},
                        {"role": "user", "content": prompt}
                    ]
                )
            )

            ctx.test_code_snapshot = suite.test_code
            log_token_usage("QA Agent", raw_response)

            with open(ctx.test_file_name, "w") as f:
                f.write(ctx.test_code_snapshot)

            log.info("   [THOUGHT] Generated deterministic unittest suite targeting strict type enforcement and contract safety.")
            log.info(f"   [ARTIFACT] Instantiated test suite at '{ctx.test_file_name}'\n")
            log.debug(f"QA Agent Output written to {ctx.test_file_name}")
            return
        except ClientError as e:
            if e.status_code == 429:
                handle_quota_error(e)
                sys.exit(1)
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: QA Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"QA Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
        except Exception as e:
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: QA Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"QA Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
