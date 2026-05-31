# Iteration Release Documentation Prompt Template

Analyze the current state of the codebase and document the release of Iteration [ITERATION_NUMBER] ([SHORT_TECHNICAL_FEATURE_NAME]).

## === ARCHITECTURAL CONTEXT FOR ITERATION [ITERATION_NUMBER] ===

In this iteration, the following problem was resolved: [DESCRIPTION_OF_THE_ARCHITECTURAL_OR_LOGICAL_PROBLEM_BEFORE_CHANGES].

### Key implementations:

1. **[COMPONENT/FEATURE 1]**: 
   - [Specific code/model changes].
   - [Architectural benefit gained or bug eliminated].

2. **[COMPONENT/FEATURE 2]**:
   - [Specific code/model changes].
   - [Architectural benefit gained or bug eliminated].

3. **[CHANGES IN AGENT PROMPTS/CONSTRAINTS]** (if applicable):
   - [Core of the new constraint or rule].
   - [Which anti-pattern it prevents].

## === TASK ===

1. Create the directory `docs/archive/iteration_[ITERATION_NUMBER]/`. 
2. Write `docs/archive/iteration_[ITERATION_NUMBER]/iteration_[ITERATION_NUMBER]_README.md`. Structure the document: Problem Statement, Implemented Solutions, Metrics/Logs analysis.
3. Update `PRACTICUM.md`. Add a new row to the "Development Steps" table. Add a new bullet point to "Key Engineering Takeaways": articulate the primary engineering pattern derived from this iteration ([MAIN_ENGINEERING_TAKEAWAY_OF_THIS_ITERATION]).
4. Update the root `README.md`. If new CLI arguments, environment variables, or execution graph changes were introduced, update the relevant documentation blocks.

## Placeholders to customize:

- `[ITERATION_NUMBER]` — numeric iteration identifier
- `[SHORT_TECHNICAL_FEATURE_NAME]` — concise feature/fix name
- `[DESCRIPTION_OF_THE_ARCHITECTURAL_OR_LOGICAL_PROBLEM_BEFORE_CHANGES]` — problem statement
- `[COMPONENT/FEATURE N]` — specific component modified
- `[Specific code/model changes]` — details of implementation
- `[Architectural benefit gained or bug eliminated]` — impact/value
- `[CHANGES IN AGENT PROMPTS/CONSTRAINTS]` — optional agent/constraint updates
- `[MAIN_ENGINEERING_TAKEAWAY_OF_THIS_ITERATION]` — key learning/pattern
