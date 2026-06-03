---
skill_id: qa_math_guardrail
type: domain
nodes: [qa]
triggers: [math, analytics, geometry, float, numbers]
---
CRITICAL MATH TESTING RULE: NEVER hardcode floating-point expectations (e.g., `1.256e+301` or `float('inf')`) for geometric calculations. You MUST calculate the expected value dynamically inside the test method using standard Python math (e.g., `expected_area = math.pi * radius ** 2`). Always use `math.isclose()` for float comparisons.