---
skill_id: dotnet_qa
type: domain
triggers: [dotnet, csharp]
nodes: [qa, reviewer]
---
LANGUAGE TARGET: .NET (C#) — test-suite rules for the .NET tech stack.

## Testing Framework & Layout
- Use xUnit (`[Fact]` / `[Theory]`). Do NOT mix in NUnit or MSTest.
- Name the test file `<Name>Tests.cs` colocated with the type under test (e.g. `Converter.cs` →
  `ConverterTests.cs`). `dotnet test` requires a test project (a `.csproj` referencing
  `Microsoft.NET.Test.Sdk` + the xUnit packages and the project under test) — assume the contract /
  Developer provides that test project; emit the test class into it.
## Namespace & Placement Fidelity (MANDATORY)
- The test class's `namespace` MUST match the namespace of the type under test exactly as declared in
  its sibling in the PRODUCTION CODE SNAPSHOT — never a namespace borrowed from a collaborator. A
  mismatch breaks `internal` visibility and symbol resolution and fails the whole build.
- Use an external test namespace / `InternalsVisibleTo` ONLY when the contract exposes a public API;
  otherwise stay in the production type's own namespace (white-box).
- A thin entrypoint (a `Program`/`Main` bootstrap that only wires up and delegates) has no white-box
  logic of its own: test that logic where it lives. For the entrypoint emit at most a faithful minimal
  check in its OWN namespace — never a fabricated suite for a different type under a foreign namespace.

## Test Shape
- One `[Fact]` per single behavior; use `[Theory]` with `[InlineData(...)]` rows for the input matrix
  so each case is isolated and independently reported. Prefer one `[Theory]` over many near-duplicate
  `[Fact]` methods.

## Assertions & Exceptions
- Assert exceptions with `Assert.Throws<TException>(() => ...)` — the exception TYPE only.
- NEVER assert on `.Message`, `.ToString()`, or any message-derived property (per the CRITICAL RULE).
  Verify only the thrown type.

## Imports
- `using <Namespace>;` exactly as declared by the topology contract / production snapshot. Never guess
  namespaces; never re-declare production types in the test.

## Assembly Contract
- Return the COMPLETE test file content in `new_imports` (the `using` directives) + `new_test_code`
  and set `overwrite_existing` to true. The engine does not AST-merge C# — emit the whole file each
  time.
