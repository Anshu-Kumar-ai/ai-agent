import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.router import SmartRouter
from app.tools.capabilities import (
    ToolCapability,
    get_capability,
    get_capabilities_by_operation,
    CapabilityCategory,
)


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
    """Creates constrained plans without executing tools.

    Uses capability-based semantic selection in addition to keyword matching.
    """

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

    def plan(
        self,
        message: str,
        available_tools: list[dict],
        observations: list | None = None,
        context: str | None = None,
    ) -> Plan:
        """Choose only from registered tool metadata supplied by the agent.
        Uses capability-based semantic selection in addition to keyword matching.
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

        # If we have observations, first try phrase matching (preserves existing behavior)
        # Then try capability-based selection for special cases like average
        # Fall back to responding if no special handling needed
        if observations:
            # First try phrase matching - this preserves existing behavior
            phrase_tool = self._select_by_phrases(message, available_tools, observations)
            if phrase_tool:
                # If phrase matching returns a plan, use it (could be use_tool or respond)
                return phrase_tool

            # If no phrase match, try capability-based
            # for special cases like average
            capability_tool = self._select_by_capability(message, available_tools, observations)
            if capability_tool:
                return capability_tool

            # If no special handling needed, respond with the observation
            return self.plan_response(
                reason="A tool result is available for the final response.",
            )

        # No observations: first try capability-based selection
        capability_tool = self._select_by_capability(message, available_tools, observations)
        if capability_tool:
            return capability_tool

        # Fallback to selection phrase matching (preserves existing behavior)
        return self._select_by_phrases(message, available_tools, observations)

    def _select_by_capability(
        self,
        message: str,
        available_tools: list[dict],
        observations: list | None = None,
    ) -> Plan | None:
        """Select tool using capability-based semantic matching."""
        from app.tools.capabilities import (
            get_capabilities_by_operation,
            get_all_capabilities,
            CapabilityCategory,
        )

        message_lower = message.lower()
        expression = self._extract_expression(message)

        # Build tool name -> capability mapping
        tool_capabilities = {}
        for tool in available_tools:
            cap = get_capability(tool["name"])
            if cap:
                tool_capabilities[tool["name"]] = cap

        # If we have an expression, prefer computation tools
        if expression:
            # Look for tools with computation capability that accept expression
            for tool in available_tools:
                cap = tool_capabilities.get(tool["name"])
                if cap and CapabilityCategory.COMPUTATION in cap.categories:
                    parameters = tool.get("parameters", {})
                    required = parameters.get("required", [])
                    properties = parameters.get("properties", {})

                    if "expression" in required and "expression" in properties:
                        # For average requests, construct appropriate expression
                        if "average" in message_lower:
                            return self._plan_average(message, tool, observations)
                        elif observations:
                            return self.plan_response(
                                reason="Expression evaluation complete."
                            )
                        return self.plan_tool(
                            tool_name=tool["name"],
                            arguments={"expression": expression},
                            reason=f"Mathematical expression detected: {expression}",
                        )

        # Semantic operation matching
        # Define operation keywords -> capability operations
        operation_keywords = {
            "arithmetic": ["calculate", "compute", "solve", "math", "arithmetic", "what is", "evaluate"],
            "average": ["average", "mean", "avg"],
            "percentage": ["percent", "percentage", "%"],
            "unit_conversion": ["convert", "conversion", "to mb", "to gb", "to kb"],
            "current_time": ["time", "date", "clock", "when"],
            "read": ["read", "cat", "view", "show", "display", "open"],
            "write": ["write", "create", "save", "put", "make file"],
            "list": ["list", "ls", "dir", "show files", "what files"],
            "move": ["move", "rename", "mv"],
            "execute": ["run", "execute", "command", "shell", "terminal"],
            "fetch": ["fetch", "download", "get", "http", "url"],
            "search": ["search", "find", "look", "web"],
            "code": ["execute", "run", "python", "code", "script"],
            "navigate": ["navigate", "go to", "visit", "open", "browse"],
            "click": ["click", "press", "tap"],
            "type": ["type", "input", "fill", "enter text"],
            "observe": ["observe", "inspect", "what's on", "page state", "get page info"],
            "focus": ["focus", "activate", "bring to front"],
            "click_desktop": ["click", "press button"],
            "type_desktop": ["type", "enter text", "fill field"],
            "rag_add": ["add", "store", "save", "knowledge", "index", "remember"],
            "rag_query": ["ask", "query", "search", "find", "knowledge", "what", "who", "where", "when", "how", "why"],
            "rag_stats": ["stats", "statistics", "status", "size", "count", "how many"],
        }

        # Find matching operations
        matched_operations = set()
        for op, keywords in operation_keywords.items():
            if any(kw in message_lower for kw in keywords):
                matched_operations.add(op)

        if not matched_operations:
            return None

        # Find candidate tools for matched operations
        candidate_tools = []
        for op in matched_operations:
            caps = get_capabilities_by_operation(op)
            for cap in caps:
                # Check if a tool with this capability is available
                for tool in available_tools:
                    if tool["name"] == cap.name:
                        candidate_tools.append((tool, cap, op))

        if not candidate_tools:
            return None

        # Rank candidates: prefer exact operation match, then by risk level (lower first)
        ranked = []
        for tool, cap, matched_op in candidate_tools:
            # Check if tool accepts required parameters
            parameters = tool.get("parameters", {})
            required = parameters.get("required", [])
            properties = parameters.get("properties", {})

            # For now, if tool is available, consider it
            risk_order = {"low": 0, "medium": 1, "high": 2}
            risk_score = risk_order.get(cap.risk_level, 1)

            ranked.append((risk_score, matched_op, tool, cap))

        if ranked:
            ranked.sort(key=lambda x: (x[1] != "average", x[0]))  # Prefer average-specific, then low risk
            best_tool, best_cap, matched_op = ranked[0][2], ranked[0][3], ranked[0][1]

            # Build arguments based on tool
            parameters = best_tool.get("parameters", {})
            required = parameters.get("required", [])
            properties = parameters.get("properties", {})

            if "expression" in required:
                if expression:
                    return self.plan_tool(
                        tool_name=best_tool["name"],
                        arguments={"expression": expression},
                        reason=f"Selected {best_cap.name} for {matched_op} capability",
                    )
            elif required:
                # Tool has required parameters - let executor validate
                return self.plan_tool(
                    tool_name=best_tool["name"],
                    arguments={},
                    reason=f"Selected {best_cap.name} for {matched_op} capability (requires manual arguments)",
                )
            else:
                return self.plan_tool(
                    tool_name=best_tool["name"],
                    arguments={},
                    reason=f"Selected {best_cap.name} for {matched_op} capability",
                )

        return None

    def _plan_average(self, message: str, tool: dict, observations: list | None) -> Plan:
        """Plan average calculation using the calculator tool."""
        message_lower = message.lower()
        numbers = re.findall(r'\d+', message)

        if len(numbers) < 2:
            return self.plan_tool(
                tool_name=tool["name"],
                arguments={"expression": "0"},
                reason="Average requested but insufficient numbers found",
            )

        sum_expr = " + ".join(numbers)

        if not observations:
            # First step: compute the sum
            final_expression = sum_expr
        elif len(observations) == 1:
            # Second step: divide sum by count
            prev_result = observations[0].result
            final_expression = f"({prev_result}) / {len(numbers)}"
        else:
            # We have 2+ observations for an average request - we're done
            return self.plan_response(
                reason="Average calculation complete.",
            )

        return self.plan_tool(
            tool_name=tool["name"],
            arguments={"expression": final_expression},
            reason=f"Average calculation step: {final_expression}",
        )

    def _select_by_phrases(
        self,
        message: str,
        available_tools: list[dict],
        observations: list | None = None,
    ) -> Plan:
        """Fallback: selection phrase matching (original behavior)."""
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
                arguments = {}
            else:
                arguments = {}

            # If we have observations and this is a selection-phrase match,
            # we should respond instead of planning another tool (unless it's an average request)
            if observations and "average" not in message_lower:
                return self.plan_response(
                    reason="A tool result is available for the final response.",
                )

            return self.plan_tool(
                tool_name=tool["name"],
                arguments=arguments,
                reason=f"The request matches the registered {tool['name']} capability.",
            )

        # Fallback: if no selection phrases matched but we have an expression
        # and there are tools that accept expression parameters, use the first one
        if expression:
            expression_tools = []
            for tool in available_tools:
                parameters = tool.get("parameters", {})
                properties = parameters.get("properties", {})
                required = parameters.get("required", [])
                if "expression" in required and "expression" in properties:
                    expression_tools.append(tool)

            if expression_tools:
                # Prefer calculator if available
                selected_tool = None
                for tool in expression_tools:
                    if tool.get("name") == "calculator":
                        selected_tool = tool
                        break
                if not selected_tool:
                    selected_tool = expression_tools[0]

                # For average requests, construct the appropriate expression based on step
                final_expression = expression
                message_lower = message.lower()
                if "average" in message_lower:
                    numbers = re.findall(r'\d+', message)
                    if len(numbers) >= 2:
                        sum_expr = " + ".join(numbers)
                        if not observations:
                            final_expression = sum_expr
                        elif len(observations) == 1:
                            prev_result = observations[0].result
                            final_expression = f"({prev_result}) / {len(numbers)}"
                        else:
                            return self.plan_response(
                                reason="Average calculation complete.",
                            )
                elif observations:
                    return self.plan_response(
                        reason="Expression evaluation complete.",
                    )

                return self.plan_tool(
                    tool_name=selected_tool.get("name"),
                    arguments={"expression": final_expression},
                    reason=f"The request appears to contain a mathematical expression: {final_expression}",
                )

        return self.plan_response(
            reason="No registered tool is currently required.",
        )


class LLMPlanner:
    """An LLM-based planner that proposes plans validated through Plan.from_dict().

    This planner uses an LLM (via SmartRouter) to generate structured plans,
    then validates them against the Plan contract and the available tool metadata.
    The planner also incorporates the context (which includes evaluations) into the prompt.
    """

    def __init__(self, router: SmartRouter | None = None, fallback_gateway=None):
        self.router = router or SmartRouter()
        self.fallback_gateway = fallback_gateway

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
        # Try OmniRoute-style router first (select_provider + ask with two args)
        if hasattr(self.router, 'select_provider') and hasattr(self.router, 'ask'):
            try:
                provider_type = self.router.select_provider(message=prompt)
                response = self.router.ask(provider_type, prompt)
            except TypeError:
                # Router's ask method has different signature, fall back
                response = self.router.ask(prompt)
        else:
            response = self.router.ask(prompt)

        # Fallback to local model if remote fails
        if isinstance(response, Exception) or (isinstance(response, str) and "error" in response.lower()):
            if self.fallback_gateway is not None:
                try:
                    response = self.fallback_gateway.ask("local", prompt)
                except Exception:
                    pass  # Keep original response

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

        # Extract tool names for clarity
        tool_names = [tool["name"] for tool in available_tools if isinstance(tool, dict) and tool.get("name")]
        tool_names_str = ", ".join(f"'{n}'" for n in tool_names)

        return (
            "You are a planning agent. Given a user request, available tools, and context, output a single JSON plan object.\n\n"
            f"AVAILABLE TOOLS:\n{tools_json}{context_section}"
            f"VALID TOOL NAMES: {tool_names_str}\n\n"
            "PLAN SCHEMA:\n"
            "{\n"
            '  "action": "use_tool" | "respond",\n'
            '  "tool_name": string | null,\n'
            '  "arguments": object,\n'
            '  "reason": string\n'
            "}\n\n"
            "RULES:\n"
            '1. "action" must be "use_tool" or "respond"\n'
            '2. If "action" is "use_tool", "tool_name" MUST be exactly one of the VALID TOOL NAMES above\n'
            '3. "arguments" must be an object matching the tool\'s parameters schema\n'
            '4. If "action" is "respond", "tool_name" must be null and "arguments" must be {}\n'
            "5. Output ONLY the JSON object, no extra text\n\n"
            "EXAMPLES:\n"
            '- To calculate: {"action": "use_tool", "tool_name": "calculator", "arguments": {"expression": "2 + 3 * 4"}, "reason": "Evaluate arithmetic"}\n'
            '- To read file: {"action": "use_tool", "tool_name": "fs.read", "arguments": {"path": "test.txt"}, "reason": "Read file content"}\n'
            '- To write file: {"action": "use_tool", "tool_name": "fs.write", "arguments": {"path": "test.txt", "content": "hello"}, "reason": "Write file"}\n'
            '- To list files: {"action": "use_tool", "tool_name": "fs.list", "arguments": {}, "reason": "List directory"}\n'
            '- To respond: {"action": "respond", "tool_name": null, "arguments": {}, "reason": "Tool result available"}\n\n'
            f"USER REQUEST: {message}"
        )

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