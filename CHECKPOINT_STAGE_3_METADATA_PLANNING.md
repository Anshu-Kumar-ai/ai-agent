# Stage 3 Checkpoint — Metadata-Driven Deterministic Planning

**Project:** `C:\Users\anshu\Videos\AI-Agent`

## Milestone completed

The deterministic Planner no longer receives only a set of tool names and no longer contains calculator/time-specific routing branches.

```text
Agent
  -> ToolRegistry.list_tools() metadata
  -> AgentLoop
  -> Planner
  -> Plan for a registered capability
  -> ToolExecutor
```

## Tool-selection metadata

`BaseTool` now includes an optional generic capability field:

- `selection_phrases`: a tuple of user-facing phrases that identify when the capability is relevant.

`ToolRegistry.list_tools()` publishes the following constrained planning inputs:

- `name`
- `description`
- `selection_phrases`
- `parameters` (JSON-Schema-style input definition)

The calculator and time tools declare their own selection phrases. The Planner iterates over metadata supplied by the registry and chooses the matched capability. It does not hardcode `calculator` or `time` as decision branches.

## Input and safety behavior

- `Planner.plan()` now requires a list of tool metadata dictionaries, not a bare name set.
- It validates each metadata item has a valid `name`, `description`, `parameters`, and well-formed `selection_phrases` when supplied.
- It generates an `expression` argument only when the selected capability's schema requires an `expression` property.
- It declines tools with required inputs it cannot safely produce.
- `ToolExecutor` remains the execution trust boundary: a selected name still must be registered before it can run.
- The Stage 2 bounded `AgentLoop` limit remains active.

## Test-first proof

A new test first failed with a renamed arithmetic tool:

```text
name: math_engine
selection_phrases: ["solve", "calculate"]
request: "Please solve 7 * 6."
```

The old Planner returned `respond` because it only recognized the literal name `calculator`. After the metadata-driven implementation, the test passed and produced:

```text
Plan(action="use_tool", tool_name="math_engine", arguments={"expression": "7 * 6"})
```

This also fixed trailing sentence punctuation being retained in extracted arithmetic expressions.

## Verification

- Targeted planner, time, metadata, and loop tests: **17 passed**
- Full discovered suite: **17 passed**

Command used:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Next small milestone

Formalize `Plan` and `ToolObservation` as serializable, validated boundary objects. Keep planning deterministic and preserve the registry/executor trust boundary; do not introduce LLM planning or arbitrary code execution yet.
