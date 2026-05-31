from pathlib import Path
from functools import lru_cache

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SYSTEM_DIR = _REPO_ROOT / "prompts" / "system"
_SKILLS_DIR = _REPO_ROOT / "prompts" / "skills"

PROMPT_SECTION_SEPARATOR = "\n---\n"


@lru_cache(maxsize=16)
def get_system_prompt(agent_name: str) -> str:
    path = _SYSTEM_DIR / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"System prompt '{agent_name}' not found at {path}")
    return path.read_text(encoding="utf-8").strip()


def get_system_prompt_sections(agent_name: str, separator: str = PROMPT_SECTION_SEPARATOR) -> tuple[str, str]:
    """Loads a two-section system prompt (system rules `---` user template) and validates
    its structure. Raises ValueError if the separator is missing or a section is empty."""
    raw = get_system_prompt(agent_name)
    if separator not in raw:
        raise ValueError(
            f"Malformed system prompt '{agent_name}': missing required section separator "
            f"'---' (on its own line). See prompts/system/{agent_name}.md."
        )
    head, tail = (part.strip() for part in raw.split(separator, 1))
    if not head or not tail:
        raise ValueError(
            f"Malformed system prompt '{agent_name}': both the system-rules and "
            f"user-template sections must be non-empty. See prompts/system/{agent_name}.md."
        )
    return head, tail


@lru_cache(maxsize=16)
def get_skill(skill_name: str) -> str:
    path = _SKILLS_DIR / f"{skill_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill prompt '{skill_name}' not found at {path}")
    return path.read_text(encoding="utf-8").strip()
