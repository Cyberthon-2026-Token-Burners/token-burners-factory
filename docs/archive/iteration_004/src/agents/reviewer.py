import sys
import asyncio
import instructor
from google.genai.errors import ClientError

from src.core.observability import log, log_token_usage
from src.core.config import get_genai_client, handle_quota_error, REVIEWER_MODEL
from src.core.models import ReviewReport, GlobalPipelineContext

async def run_reviewer_node(ctx: GlobalPipelineContext, qa_success: bool, qa_log: list[str], sec_success: bool, sec_log: list[str]) -> None:
    model_name = REVIEWER_MODEL
    log.info(f"🔍 [ROLE] Reviewer Agent | [MODEL] {model_name}")

    client = instructor.from_genai(
        client=get_genai_client(),
        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
    )

    qa_report = "\n".join(qa_log) if qa_log else "No logs produced."
    sec_report = "\n".join(sec_log) if sec_log else "No logs produced."

    user_content = (
        f"=== ORIGINAL USER REQUIREMENT ===\n{ctx.pr_description}\n\n"
        f"=== ARCHITECT CONTRACT ===\n{ctx.contract.model_dump_json(indent=2)}\n\n"
        f"=== GENERATED PRODUCTION CODE ===\n{ctx.production_code_snapshot}\n\n"
        f"=== GENERATED TEST SUITE ===\n{ctx.test_code_snapshot}\n\n"
        f"=== FUNCTIONAL TESTS RUN ({'PASSED' if qa_success else 'FAILED'}) ===\n{qa_report}\n\n"
        f"=== SAST SECURITY SCAN ({'PASSED' if sec_success else 'FAILED'}) ===\n{sec_report}"
    )

    sys_prompt = (
        "You are an elite, brutal Code Reviewer and QA Auditor. Your goal is to enforce extreme standards of code quality, "
        "type guard strictness, and test integrity. Analyze production code against the requirements, test suite against "
        "the contract (strictly reject any try-except blocks, pass, or softness), and interpret the raw runner outputs."
    )

    max_api_retries = 3
    for api_attempt in range(1, max_api_retries + 1):
        try:
            loop = asyncio.get_running_loop()
            report, raw_response = await loop.run_in_executor(
                None, lambda: client.chat.completions.create_with_completion(
                    model=model_name,
                    response_model=ReviewReport,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_content}
                    ]
                )
            )
            ctx.review_report = report
            log_token_usage("Reviewer Agent", raw_response)

            log.info(f"   [THOUGHT] Multi-angle review processed:")
            log.info(f"     ├─ [CODE AUDIT] {ctx.review_report.code_quality_analysis}")
            log.info(f"     ├─ [TEST AUDIT] {ctx.review_report.test_integrity_analysis}")
            log.info(f"     └─ [LOG INTERPRETATION] {ctx.review_report.log_verification_analysis}")
            log.info(f"   ├── [GATE][FUNCTIONAL-TESTS] {'PASSED' if qa_success else 'FAILED'}")
            log.info(f"   ├── [GATE][SAST-SECURITY] {'PASSED' if sec_success else 'FAILED'}")
            log.info(f"   └── [AUDIT] Code Approved: {ctx.review_report.code_quality_approved} | Tests Approved: {ctx.review_report.test_integrity_approved}\n")

            log.debug(f"Reviewer Node Output: {ctx.review_report.model_dump_json(indent=2)}")
            return
        except ClientError as e:
            if e.status_code == 429:
                handle_quota_error(e)
                sys.exit(1)
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: Reviewer Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"Reviewer Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
        except Exception as e:
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: Reviewer Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"Reviewer Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
