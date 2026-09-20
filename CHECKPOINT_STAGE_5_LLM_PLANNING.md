# Stage 5 Checkpoint — Constrained LLM Planning

**Project:** `C:\Users\anshu\Videos\AI-Agent`

## Milestone completed

A thin LLM planner layer proposes plans that are **validated through `Plan.from_dict()`** and executed through the **unchanged registry/executor boundary**. The deterministic loop and safety limits remain intact.

```text
User request
  → LLMPlanner (schema-aware prompt + SmartRouter)
  → Plan.from_dict()  (validates structure + registered tool name)
  → AgentLoop         (bounded: max_steps=3)
  → ToolExecutor      (registry authorization)
  → ToolObservation   (serializable, validated)
  → AgentLoop re-plan / final response
```

## New component

`app/core/llm_planner.py` — `LLMPlanner`:

- Accepts a `SmartRouter` (or mock) for LLM calls.
- Builds a prompt that includes the **full tool metadata** (name, description, selection phrases, JSON-schema parameters).
- Instructs the LLM to output **only a single JSON `Plan` object**.
- Parses the response, strips code fences, and validates via `Plan.from_dict()`.
- **Rejects any tool name not in `available_tools`** with a clear error.
- Falls back to a `respond` plan after the first tool observation (preserves current deterministic behavior).

## Test-first behaviors verified

| Test | What it proves |
|------|----------------|
| `test_llm_planner_proposes_valid_plan_for_arithmetic` | Valid LLM JSON → validated `Plan` with correct tool + args |
| `test_llm_planner_rejects_invalid_json_and_falls_back` | Malformed JSON raises a clear `ValueError`, no silent crash |
| `test_llm_planner_rejects_unknown_tool_name` | LLM-proposed unregistered tool is rejected |
| `test_llm_planner_integration_with_agent_loop` | End-to-end through `AgentLoop` with re-plan after observation |

## Safety preserved

- **Executor trust boundary unchanged**: only registered tools execute.
- **Plan contract enforced**: `Plan.from_dict()` validates every field.
- **Loop limit active**: `AgentLoop.max_steps = 3` default.
- **Observation handling unchanged**: after first tool result, planner responds.
- **Existing deterministic planner still available** (`app/core/planner.py`) for comparison and fallback.

## Test results

- New LLM planner tests: **4 passed**
- Full discovered suite: **25 tests passed**
- Integration test unchanged: `AGENT: 110`

Commands used:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_llm_planner -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m tests.test_agent_tools
```

## Next small milestone

Add **memory/skills/reflection** so the agent can recall prior tool results, learned procedures, and self-evaluate. The validated `Plan`/`ToolObservation` contracts and bounded loop provide a safe foundation for these layers.