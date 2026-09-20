from dataclasses import dataclass, field
import json
from typing import Any, Optional

from app.core.router import SmartRouter


@dataclass
class Plan:
    """A structured plan produced by the agent planner."""

    action: str
    tool_name: str | None = None
    arguments: dict = field(default_factory=dict)
    reason: str = ""

    def __post_init__(self):
        valid_actions = {"respond", "use_tool"}

        if not isinstance(self.action, str):
            raise TypeError("action must be a string")

        if not isinstance(self.arguments, dict):
            raise TypeError("arguments must be a dictionary")

        if not isinstance(self.reason, str):
            raise TypeError("reason must be a string")

        if self.action not in valid_actions:
            raise ValueError(
                f"Invalid action: {self.action}. "
                f"Expected one of: {valid_actions}"
            )

        if self.action == "use_tool" and not self.tool_name:
            raise ValueError(
                "tool_name is required when action is 'use_tool'"
            )

    def to_dict(self) -> dict:
        """Return a serializable representation of this validated plan."""
        return {
            "action": self.action,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "Plan":
        """Build a Plan from an untrusted serialized payload."""
        if not isinstance(payload, dict):
            raise TypeError("plan payload must be a dictionary")

        required_fields = {"action", "tool_name", "arguments", "reason"}
        missing_fields = required_fields - payload.keys()
        if missing_fields:
            raise ValueError(f"plan payload is missing fields: {sorted(missing_fields)}")

        return cls(
            action=payload["action"],
            tool_name=payload["tool_name"],
            arguments=payload["arguments"],
            reason=payload["reason"],
        )


class Planner:
    """Creates constrained plans without executing tools."""

    def plan(
        self,
        message: str,
        available_tools: list[dict],
        observations: list | None = None,
        context: Optional[str] = None,
    ) -> Plan:
        """Choose only from registered tool metadata supplied by the agent.
        The context parameter is ignored in this planner but kept for interface consistency.
        """
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        if not isinstance(available_tools, list):
            raise TypeError("available_tools must be a list")

        for tool in available_tools:
            if not isinstance(tool, dict):
                raise TypeError("each available tool must be metadata dictionary")

            name = tool.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("each available tool must include a name")

            if not isinstance(tool.get("description"), str):
                raise ValueError("each available tool must include a description")

            if not isinstance(tool.get("parameters"), dict):
                raise ValueError("each available tool must include parameters")

            selection_phrases = tool.get("selection_phrases", [])
            if (
                not isinstance(selection_phrases, list)
                or not all(isinstance(phrase, str) for phrase in selection_phrases)
            ):
                raise ValueError("selection_phrases must be a list of strings")

        message = message.strip()
        if not message:
            raise ValueError("message cannot be empty")

        if observations:
            return self.plan_response(
                reason="A tool result is available for the final response.",
            )

        message_lower = message.lower()
        expression = self._extract_expression(message)

        for tool in available_tools:
            phrases = tool.get("selection_phrases", [])
            if not any(phrase.lower() in message_lower for phrase in phrases):
                continue

            parameters = tool["parameters"]
            properties = parameters.get("properties", {})
            required = parameters.get("required", [])

            if "expression" in required:
                if not expression or "expression" not in properties:
                    continue
                arguments = {"expression": expression}
            elif required:
                continue
            else:
                arguments = {}

            return self.plan_tool(
                tool_name=tool["name"],
                arguments=arguments,
                reason=f"The request matches the registered {tool['name']} capability.",
            )

        return self.plan_response(
            reason="No registered tool is currently required.",
        )

    @staticmethod
    def _extract_expression(message: str) -> str | None:
        """Extract a basic arithmetic expression from a user message."""
        allowed = set("0123456789+-*/().% ")
        expression = "".join(
            character for character in message if character in allowed
        ).strip()

        if not expression or not any(character.isdigit() for character in expression):
            return None

        return expression.rstrip(".")

    def plan_response(self, reason: str = "") -> Plan:
        """Create a plan to answer directly."""
        return Plan(
            action="respond",
            reason=reason,
        )

    def plan_tool(
        self,
        tool_name: str,
        arguments: dict | None = None,
        reason: str = "",
    ) -> Plan:
        """Create a plan to use a registered tool."""
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be a string")

        tool_name = tool_name.strip()

        if not tool_name:
            raise ValueError("tool_name cannot be empty")

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, dict):
            raise TypeError("arguments must be a dictionary")

        return Plan(
            action="use_tool",
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
        )


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
        context: Optional[str] = None,
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

    def _build_prompt(self, message: str, available_tools: list[dict], context: Optional[str] = None) -> str:
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

        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

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