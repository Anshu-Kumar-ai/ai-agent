# Stage 2 Checkpoint — Bounded Deterministic Agent Loop

**Project:** `C:\Users\anshu\Videos\AI-Agent`

## Milestone completed

The project now has a real bounded agent loop rather than a single plan-and-execute pass.

```text
plan
  -> execute registered tool
  -> store observation
  -> re-plan with observations
  -> final response
```

## New components

### `app/core/agent_loop.py`

- `ToolObservation`: captures a registered tool's name and returned result.
- `AgentLoop`: owns the iterative execution flow.
- Requires a positive `max_steps`; the Agent currently uses the safe default of `3`.
- Raises `RuntimeError` if the planner does not reach a response before the tool-step limit.

## Integration

`Agent` now delegates tool work to `AgentLoop`.

For the current deterministic Planner, the first completed tool result triggers a final response, so existing calculator/time behavior remains unchanged. The loop is nevertheless capable of multiple steps: later planners can use observations to issue another valid tool call before responding.

## Verified multi-step example

The automated loop test used a deterministic planner for:

```text
Find the average of 10, 20 and 30.
```

Observed execution:

```text
calculator("10 + 20 + 30") -> 60
calculator("60 / 3") -> 20.0
final response -> The average is 20.0.
```

## Safety verification

- A planner that endlessly requests calculator calls is stopped after its configured two-step limit.
- Non-positive step limits are rejected at construction time.
- Only `ToolExecutor` executes actions, so tools must still be registered.

## Test results

- `python -m unittest tests.test_agent_loop -v` — 3 passed
- `python -m tests.test_agent_tools` — calculator integration returned `110`
- `python -m unittest discover -s tests -v` — 15 discovered tests passed

## Next small milestone

Make deterministic planning consume tool metadata rather than hardcoded tool names/keywords. The Planner should receive tool descriptions and schemas from `ToolRegistry`, while the executor continues to validate every requested tool against the registry.

Do not introduce LLM planning yet; first preserve and test deterministic multi-tool selection through the generic tool interface.
