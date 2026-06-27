---
skill_id: shit_coder
type: fallback
nodes: [techlead, developer, qa, reviewer]
---
## Fallback Stack Guidance (no specific language skill matched)

The target stack is not one of the natively supported environments. No language-specific skill is
available. Apply the principles below to produce working code regardless.

### General rules (language-agnostic)

- **Write code that actually runs.** Prioritise a working solution over an elegant one. If you are
  unsure of an idiom, use the most conservative, readable option for the language.
- **Follow the language's standard conventions.** Use the standard package manager and dependency
  manifest the ecosystem expects (e.g. `Cargo.toml` for Rust, `pom.xml` for Java/Maven,
  `mix.exs` for Elixir). Declare every external dependency in that manifest.
- **Module / import structure.** Organise files so imports resolve without circular dependencies.
  Export only what the contract requires; keep helpers private/unexported.
- **Error handling.** Never silently swallow errors. Raise / return / propagate them explicitly.
  Use the language's idiomatic error type (exception, `Result<>`, error return, etc.).
- **Type safety.** Validate inputs at the public boundary. Reject wrong types explicitly; do not
  rely on implicit coercion. Store constructor arguments as their declared types.
- **No dead code.** Remove unused variables, imports, and unreachable branches before committing —
  many compilers treat them as errors.
- **Security basics.** Never construct shell commands or SQL from user input (use parameterised
  queries / safe APIs). Do not hardcode secrets or credentials.

### For the TechLead (contract design on an unknown stack)

- Choose `environment_id` that best approximates the stack (or the closest paved-road entry if the
  exact runtime is unsupported). State the mismatch in `techlead_reasoning`.
- Keep `files_to_modify` minimal — only what is strictly necessary for the ticket.
- Populate `acceptance_examples` with concrete input/output pairs to guide the QA agent.

### For the Developer (implementation on an unknown stack)

- Write the smallest amount of code that satisfies the contract and passes the acceptance examples.
- Add the project's entry-point boilerplate (main file, init file, build file) if absent.
- Prefer the standard library over external dependencies; only add a dependency when the task
  genuinely requires it, and add it to the manifest.

### For QA (testing on an unknown stack)

- Use the language's built-in test framework (e.g. JUnit, RSpec, ExUnit, cargo test).
- Cover: happy-path for every acceptance example, one boundary/edge case per function, and one
  error-path test for each documented exception/error type.
- Structure tests so they compile and run with a single standard command (`test`, `run tests`, etc.).

### For the Reviewer

- Accept reasonable approximations when an exact idiom is unknown — penalise only outright broken
  logic, security issues, or missing dependency declarations.
- Flag but do not hard-fail on style deviations from paved-road conventions; the stack is outside
  the normal guardrails.
