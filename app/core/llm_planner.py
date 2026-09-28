import json
from typing import Any

from app.core.planner import Plan
from app.core.router import SmartRouter


class LLMPlanner:
    """An LLM-based planner that proposes plans validated through Plan.from_dict().

    This planner uses an LLM (via SmartRouter) to generate structured plans,
    then validates them against the Plan contract and the available tool metadata.
    The planner also incorporates the context (which includes evaluations) into the prompt.
    """

    def __init__(self, router: SmartRouter | None = None):
        self.router = router or SmartRouter()

    def plan(
        self,
        message: str,
        available_tools: list[dict],
        observations: list[Any] | None = None,
        context: str | None = None,
    ) -> Plan:
        """Generate a plan using the LLM and validate it through Plan.from_dict().
        The context is incorporated into the prompt to inform the LLM about past evaluations.
        """
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        if not isinstance(available_tools, list):
            raise TypeError("available_tools must be a list")

        tool_names = {tool["name"] for tool in available_tools if isinstance(tool, dict) and tool.get("name")}

        if observations:
            return Plan(
                action="respond",
                reason="A tool result is available for the final response.",
            )

        prompt = self._build_prompt(message, available_tools, context)
        response = self.router.ask(prompt)

        plan_dict = self._parse_llm_response(response)
        self._validate_tool_name(plan_dict, tool_names)

        return Plan.from_dict(plan_dict)

    def _build_prompt(self, message: str, available_tools: list[dict], context: str | None = None) -> str:
        """Construct a system prompt with tool schemas, instructions, and context."""
        tools_json = json.dumps(available_tools, indent=2)

        # Build the context section if provided.
        context_section = ""
        if context:
            context_section = f"\nCONTEXT:\n{context}\n"

        return f"""You are a planning agent. Given a user request, available tools, and context, output a single JSON plan object.

AVAILABLE TOOLS:
{tools_json}{context_section}
PLAN SCHEMA:
{{
  "action": "use_tool" | "respond",
  "tool_name": string | null,
  "arguments": object,
  "reason": string
}}

RULES:
1. "action" must be "use_tool" or "respond"
2. If "action" is "use_tool", "tool_name" must be one of the available tool names
3. "arguments" must be an object matching the tool's parameters schema
4. If "action" is "respond", "tool_name" must be null and "arguments" must be {{}}
5. Output ONLY the JSON object, no extra text

USER REQUEST: {message}
"""

    def _parse_llm_response(self, response: str) -> dict:
        """Parse and validate the LLM's JSON response."""
        response = response.strip()

        response = response.removeprefix("```json")
        response = response.removeprefix("```")
        response = response.removesuffix("```")

        response = response.strip()

        try:
            plan_dict = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

        if not isinstance(plan_dict, dict):
            raise ValueError("plan payload must be a dictionary")

        return plan_dict

    def _validate_tool_name(self, plan_dict: dict, valid_tool_names: set[str]) -> None:
        """Ensure the proposed tool is registered."""
        tool_name = plan_dict.get("tool_name")

        if plan_dict.get("action") == "use_tool":
            if not tool_name or tool_name not in valid_tool_names:
                raise ValueError(
                    f"tool_name must be a registered tool: got '{tool_name}', "
                    f"valid options are: {sorted(valid_tool_names)}"
                )