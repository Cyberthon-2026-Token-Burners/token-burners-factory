# Nexus Control Plane — TPM agent. Breaks an Epic + Blueprint into atomic Developer task tickets.
from pydantic import BaseModel, Field, field_validator

from src.shared.core.environments import SUPPORTED_ENVIRONMENTS
from src.shared.core.observability import log
from src.shared.core.prompts import get_system_prompt_with_platforms
from src.shared.utils.llm import run_structured_llm


class TaskTicket(BaseModel):
    ticket_id: str = Field(description="Stable ticket id (e.g. TASK-01, TASK-02); numbering/ordering rules in the system prompt.")
    title: str = Field(description="Short imperative title for the task.")
    environment_id: str = Field(description="The supported Paved-Road platform id this ticket runs on, copied from the Blueprint.")
    description: str = Field(description="The full, self-contained ticket body following the PER-TICKET STRUCTURE in the system prompt (and, for TASK-01, a leading repository-preparation block).")

    @field_validator("environment_id")
    @classmethod
    def _validate_environment_id(cls, v: str) -> str:
        if v not in SUPPORTED_ENVIRONMENTS:
            raise ValueError(
                f"Unsupported environment_id '{v}'. "
                f"Choose one of: {sorted(SUPPORTED_ENVIRONMENTS)}."
            )
        return v


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
            {"role": "system", "content": get_system_prompt_with_platforms("tpm")},
            {"role": "user", "content": user_content},
        ],
    )
    log.info(f"   [ARTIFACT] Planned {len(result.tasks)} task ticket(s).")
    return [t.model_dump() for t in result.tasks]
