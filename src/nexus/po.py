# Nexus Control Plane — Product Owner agent. Turns a raw idea string into a Markdown Epic.
from pydantic import BaseModel, Field

from src.shared.core.observability import log
from src.shared.core.prompts import get_system_prompt
from src.shared.utils.llm import run_structured_llm


class EpicDocument(BaseModel):
    """Structured wrapper so the markdown Epic comes back through the (structured-only) LLM utility."""
    markdown: str = Field(description="The full Epic as Markdown: Title, Goal, and 3-5 User Stories.")


async def run_po(raw_idea: str) -> str:
    """Invoke the Product Owner to expand a raw idea into a Markdown Epic; returns the markdown."""
    log.info("🟦 [ROLE] Product Owner Agent | [PROVIDER] Gemini")
    result, _ = await run_structured_llm(
        "po",
        EpicDocument,
        [
            {"role": "system", "content": get_system_prompt("po")},
            {"role": "user", "content": raw_idea},
        ],
    )
    log.info("   [ARTIFACT] Epic drafted.")
    return result.markdown
