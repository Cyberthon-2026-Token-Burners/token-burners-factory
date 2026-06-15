# Nexus Control Plane — TPM agent. Breaks an Epic + Blueprint into atomic Developer task tickets.
from pydantic import BaseModel, Field

from src.shared.core.observability import log
from src.shared.core.prompts import get_system_prompt
from src.shared.utils.llm import run_structured_llm


class TaskTicket(BaseModel):
    ticket_id: str = Field(description="Stable ticket id, e.g. TASK-01.")
    title: str = Field(description="Short imperative title for the task.")
    description: str = Field(description="Specific technical instructions grounded in the Blueprint architecture.")


class ProjectPlan(BaseModel):
    """Structured plan: the TPM returns its JSON array of tickets as this typed list."""
    tasks: list[TaskTicket] = Field(description="Atomic, ordered Developer tasks covering the whole project.")


async def run_tpm(epic_text: str, blueprint_text: str) -> list[dict]:
    """Invoke the TPM on the Epic + Blueprint; returns a list of task dicts (ticket_id/title/description)."""
    log.info("🟨 [ROLE] Technical Project Manager Agent | [PROVIDER] Gemini")
    user_content = (
        f"=== EPIC ===\n{epic_text}\n\n"
        f"=== BLUEPRINT ===\n{blueprint_text}"
    )
    result, _ = await run_structured_llm(
        "tpm",
        ProjectPlan,
        [
            {"role": "system", "content": get_system_prompt("tpm")},
            {"role": "user", "content": user_content},
        ],
    )
    log.info(f"   [ARTIFACT] Planned {len(result.tasks)} task ticket(s).")
    return [t.model_dump() for t in result.tasks]
