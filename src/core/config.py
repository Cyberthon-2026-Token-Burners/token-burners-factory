import os
import sys
import shutil
import instructor
from dataclasses import dataclass
from google import genai
from google.genai.errors import ClientError

from src.core.observability import log
from src.core.models import ARTIFACTS_DIR, CODE_DIR, TESTS_DIR, LOGS_DIR, REPORTS_DIR  # noqa: F401  (central directory map)

# ==========================================
# MODEL ROUTING (single source of truth)
# ==========================================
TECHLEAD_MODEL = "gemini-3.1-flash-lite"
QA_MODEL = "gemini-3.1-flash-lite"
REVIEWER_MODEL = "gemini-3.1-flash-lite"
# Developer agent (Claude CLI) — edit here to change model / reasoning effort.
DEVELOPER_MODEL = "sonnet"     # alias (sonnet|opus|haiku) or full name e.g. "claude-sonnet-4-6"
DEVELOPER_EFFORT = "medium"    # reasoning effort: low | medium | high | xhigh | max

# ==========================================
# FINOPS — Financial Circuit Breaker budget
# ==========================================
# Cumulative token budget (input+output across every agent) for a single pipeline run.
# Env-overridable; persisted telemetry is checked against this after each cost-accruing node,
# and a breach triggers a deterministic Hard Halt. Generous default so normal runs never trip.
PIPELINE_BUDGET_TOKENS = int(os.environ.get("PIPELINE_BUDGET_TOKENS", "1000000"))

# Role -> (model, human-readable agent name) for structured (instructor) LLM calls.
ROLE_MODELS = {
    "techlead": (TECHLEAD_MODEL, "TechLead Agent"),
    "qa":        (QA_MODEL,        "QA Agent"),
    "reviewer":  (REVIEWER_MODEL,  "Reviewer Agent"),
}

# ==========================================
# FINOPS — Gemini cost estimation (cache-aware + tiered)
# ==========================================
# Gemini's API does not return a cost figure (unlike the Claude CLI, which reports
# total_cost_usd authoritatively), so Gemini spend is ESTIMATED from token counts.
# All rates are USD per 1,000,000 tokens — ESTIMATES; tune them to your billing tier.
# Accuracy notes baked into the model:
#   * Cached input (context caching) bills far cheaper than fresh input — priced separately.
#   * Heavy models apply a long-context surcharge (≈2x) once the prompt exceeds a threshold.
#   * Multimodal (image/audio) tokens bill differently; treated as a text-rate approximation.
@dataclass(frozen=True)
class GeminiPricing:
    input: float                                 # standard uncached input
    output: float                                # standard output
    cached_input: float                          # cached input (discounted)
    long_context_threshold: int | None = None    # prompt tokens; None = no tiering
    input_long: float | None = None              # input above threshold
    output_long: float | None = None             # output above threshold


MODEL_PRICING: dict[str, GeminiPricing] = {
    # Flat-rate lite/flash tiers (no long-context surcharge).
    "gemini-3.1-flash-lite": GeminiPricing(input=0.10, output=0.40, cached_input=0.025),
    "gemini-2.5-flash":      GeminiPricing(input=0.10, output=0.40, cached_input=0.025),
    # Tiered example: rates ≈ double once the prompt exceeds 200k tokens.
    "gemini-2.5-pro": GeminiPricing(
        input=1.25, output=10.0, cached_input=0.31,
        long_context_threshold=200_000, input_long=2.50, output_long=15.0,
    ),
}
DEFAULT_GEMINI_PRICING = GeminiPricing(input=0.10, output=0.40, cached_input=0.025)


def estimate_gemini_cost_usd(model_name: str, usage_metadata) -> float:
    """Estimate USD cost for one Gemini call from its ``usage_metadata`` object.

    Accounts for context-cache discounts (``cached_content_token_count`` priced at the cheaper
    ``cached_input`` rate) and the long-context surcharge (input+output rates switch to the
    ``*_long`` tier once the prompt exceeds ``long_context_threshold``). Multimodal prompts are
    priced at the text rate with a debug warning. Reads every field defensively — never raises.
    """
    try:
        pricing = MODEL_PRICING.get(model_name)
        if pricing is None:
            log.debug(f"No pricing for model '{model_name}'; using default Gemini rates.")
            pricing = DEFAULT_GEMINI_PRICING

        prompt = int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
        cached = int(getattr(usage_metadata, "cached_content_token_count", 0) or 0)
        output = int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
        uncached = max(prompt - cached, 0)

        over_threshold = (
            pricing.long_context_threshold is not None
            and prompt > pricing.long_context_threshold
        )
        in_rate = pricing.input_long if (over_threshold and pricing.input_long is not None) else pricing.input
        out_rate = pricing.output_long if (over_threshold and pricing.output_long is not None) else pricing.output

        details = getattr(usage_metadata, "prompt_tokens_details", None) or []
        if any(str(getattr(d, "modality", "TEXT")).upper().endswith("TEXT") is False for d in details):
            log.debug("Non-text modality detected; Gemini cost is a text-rate approximation.")

        return (uncached * in_rate + cached * pricing.cached_input + output * out_rate) / 1_000_000
    except Exception as e:  # pragma: no cover - pricing must never break the pipeline
        log.debug(f"Failed to estimate Gemini cost for '{model_name}': {e}")
        return 0.0

# ==========================================
# ENVIRONMENT CHECKER
# ==========================================
def check_environment():
    log.info("🔍 Pre-flight environment check...")
    for tool in ["docker", "claude", "bandit"]:
        if not shutil.which(tool):
            log.error(f"🚨 CRITICAL: Binary '{tool}' not found in PATH.")
            sys.exit(1)

    if not os.environ.get("GEMINI_API_KEY"):
        log.error("🚨 CRITICAL: GEMINI_API_KEY is not set.")
        sys.exit(1)

    # Container hardening: in docker mode the framework source must be immutable so the
    # Developer agent cannot mutate the pipeline itself (mount src/ :ro or run as non-root).
    if os.environ.get("RUNTIME_ENV") == "docker":
        if os.access("src", os.W_OK):
            log.error("🚨 CRITICAL: RUNTIME_ENV=docker but 'src/' is writable. "
                      "Mount it read-only (:ro) or run as a non-root user to prevent self-mutation.")
            sys.exit(1)
        log.info("  ✓ src/ confirmed read-only (container hardening).")

    log.info("  ✓ Environment verified.\n")

# ==========================================
# GENAI / INSTRUCTOR CLIENT SINGLETONS
# ==========================================
def get_genai_client() -> genai.Client:
    """Returns the module-level Google AI Studio client singleton."""
    return _genai_client


def _build_genai_client() -> genai.Client:
    log.debug("Initializing Google AI Studio client via GEMINI_API_KEY")
    return genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


_genai_client: genai.Client = _build_genai_client()

instructor_client: instructor.Instructor = instructor.from_genai(
    client=_genai_client,
    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
)

# ==========================================
# HELPER FOR GRACEFUL QUOTA ERROR HANDLING
# ==========================================
def handle_quota_error(e: ClientError):
    log.error("\n🚨 RATE LIMIT EXHAUSTED (429) DETECTED!")
    log.error("   Your project is currently hitting the Google AI Studio quota limit.")
    log.error("   Ensure your AI Studio project is on a Pay-as-you-go plan.")
    log.error("\n   Details:")
    log.error(f"   {e}")
