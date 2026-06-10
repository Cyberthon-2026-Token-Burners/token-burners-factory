---
skill_id: architect_dry_guardrail
type: global
nodes: [architect]
---
CRITICAL DRY MANDATE: When designing implementations that require identical helper or validation logic across multiple files (e.g., checking positive numbers for both 2D and 3D shapes), you MUST design a centralized shared utility module (e.g., `validators.py` or `utils.py`). 
You must explicitly include this shared module in your `files_to_modify` contract and instruct the Developer to import the shared logic. STRICTLY FORBID the Developer from duplicating helper functions inline across domain files.
