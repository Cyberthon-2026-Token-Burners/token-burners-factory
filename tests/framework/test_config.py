"""Unit tests for FinOps Gemini cost estimation (cache-aware + tiered).

``estimate_gemini_cost_usd`` must never raise and must reflect the three billing realities:
context-cache discounts, the long-context surcharge, and an unknown-model fallback.
"""
import os
import unittest
from types import SimpleNamespace

# config imports src.core.config at import time and needs a key present.
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from src.core.config import estimate_gemini_cost_usd, MODEL_PRICING


def _usage(prompt: int, output: int, cached: int = 0, details=None) -> SimpleNamespace:
    return SimpleNamespace(
        prompt_token_count=prompt,
        candidates_token_count=output,
        cached_content_token_count=cached,
        prompt_tokens_details=details,
    )


class EstimateGeminiCostTests(unittest.TestCase):
    FLASH = "gemini-3.1-flash-lite"   # input 0.10, output 0.40, cached 0.025 /1M
    PRO = "gemini-2.5-pro"            # tiered at 200k: 1.25/10.0 -> 2.50/15.0, cached 0.31

    def test_uncached_input_and_output(self) -> None:
        # 1M uncached input @0.10 + 1M output @0.40 = 0.50
        cost = estimate_gemini_cost_usd(self.FLASH, _usage(prompt=1_000_000, output=1_000_000))
        self.assertAlmostEqual(cost, 0.50, places=6)

    def test_cached_tokens_are_cheaper_than_flat(self) -> None:
        # 100k prompt of which 60k cached, 10k output.
        usage = _usage(prompt=100_000, output=10_000, cached=60_000)
        cost = estimate_gemini_cost_usd(self.FLASH, usage)
        # Expected: 40k*0.10 + 60k*0.025 + 10k*0.40, all /1e6.
        expected = (40_000 * 0.10 + 60_000 * 0.025 + 10_000 * 0.40) / 1_000_000
        self.assertAlmostEqual(cost, expected, places=8)
        # And it must be strictly cheaper than pricing all input at the flat uncached rate.
        flat = (100_000 * 0.10 + 10_000 * 0.40) / 1_000_000
        self.assertLess(cost, flat)

    def test_long_context_surcharge_applies_over_threshold(self) -> None:
        # 300k prompt (> 200k) → input_long 2.50 / output_long 15.0.
        over = estimate_gemini_cost_usd(self.PRO, _usage(prompt=300_000, output=1_000))
        expected_over = (300_000 * 2.50 + 1_000 * 15.0) / 1_000_000
        self.assertAlmostEqual(over, expected_over, places=8)

    def test_standard_tier_under_threshold(self) -> None:
        # 100k prompt (<= 200k) → standard input 1.25 / output 10.0.
        under = estimate_gemini_cost_usd(self.PRO, _usage(prompt=100_000, output=1_000))
        expected_under = (100_000 * 1.25 + 1_000 * 10.0) / 1_000_000
        self.assertAlmostEqual(under, expected_under, places=8)

    def test_unknown_model_uses_default_rates(self) -> None:
        self.assertNotIn("gemini-imaginary", MODEL_PRICING)
        cost = estimate_gemini_cost_usd("gemini-imaginary", _usage(prompt=1_000_000, output=0))
        self.assertAlmostEqual(cost, 0.10, places=6)  # default input rate

    def test_missing_fields_do_not_crash(self) -> None:
        # A bare object with no usage attributes → 0.0, no exception.
        self.assertEqual(estimate_gemini_cost_usd(self.FLASH, object()), 0.0)

    def test_cached_exceeding_prompt_never_negative(self) -> None:
        # Defensive: cached > prompt must not produce negative uncached cost.
        cost = estimate_gemini_cost_usd(self.FLASH, _usage(prompt=10, output=0, cached=1000))
        self.assertGreaterEqual(cost, 0.0)


if __name__ == "__main__":
    unittest.main()
