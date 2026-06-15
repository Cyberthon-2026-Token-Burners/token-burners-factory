# Nexus Control Plane — Solution Architect agent. Turns an Epic into a technical Markdown Blueprint.
from pydantic import BaseModel, Field

from src.shared.core.observability import log
from src.shared.core.prompts import get_system_prompt
from src.shared.utils.llm import run_structured_llm


class Blueprint(BaseModel):
    """Structured wrapper carrying the architect's Markdown Blueprint."""
    markdown: str = Field(description="Technical Blueprint as Markdown: tech stack, core libraries, folder structure.")


async def run_sa(epic_text: str) -> str:
    """Invoke the Solution Architect on the Epic; returns the Blueprint markdown."""
    log.info("🟪 [ROLE] Solution Architect Agent | [PROVIDER] Gemini")
    result, _ = await run_structured_llm(
        "sa",
        Blueprint,
        [
            {"role": "system", "content": get_system_prompt("sa")},
            {"role": "user", "content": epic_text},
        ],
    )
    log.info("   [ARTIFACT] Blueprint drafted.")
    return result.markdown
