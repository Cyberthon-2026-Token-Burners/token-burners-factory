import sys
import asyncio
import instructor
from google.genai.errors import ClientError

from src.core.observability import log, log_token_usage
from src.core.config import get_genai_client, handle_quota_error, ARCHITECT_MODEL
from src.core.models import ArchitectureContract, GlobalPipelineContext

# ==========================================
# AGENT NODES
# ==========================================
async def run_architect_node(ctx: GlobalPipelineContext) -> None:
    model_name = ARCHITECT_MODEL
    log.info(f"🔷 [ROLE] Architect Agent | [MODEL] {model_name}")

    client = instructor.from_genai(
        client=get_genai_client(),
        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
    )

    sys_prompt = "You are a Principal Architect. Define strict production file mappings, type guards, and function signatures. Be concise. No prose."

    max_api_retries = 3
    for api_attempt in range(1, max_api_retries + 1):
        try:
            loop = asyncio.get_running_loop()
            contract, raw_response = await loop.run_in_executor(
                None, lambda: client.chat.completions.create_with_completion(
                    model=model_name,
                    response_model=ArchitectureContract,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": ctx.pr_description}
                    ]
                )
            )
            ctx.contract = contract
            log_token_usage("Architect", raw_response)

            log.info(f"   [THOUGHT] {ctx.contract.architecture_reasoning}")
            log.info(f"   [ARTIFACT] Contract locked for: {ctx.contract.files_to_modify}\n")
            log.debug(f"Architect Node Output: {ctx.contract.model_dump_json(indent=2)}")
            return
        except ClientError as e:
            if e.status_code == 429:
                handle_quota_error(e)
                sys.exit(1)
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: Architect Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"Architect Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
        except Exception as e:
            if api_attempt == max_api_retries:
                log.error(f"🚨 CRITICAL: Architect Agent API call failed after {max_api_retries} attempts.")
                raise e
            log.warning(f"Architect Agent attempt {api_attempt} failed, retrying...")
            await asyncio.sleep(2 ** api_attempt)
