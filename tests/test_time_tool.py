import unittest
from datetime import datetime

from app.core.agent import Agent
from app.core.planner import Planner
from app.tools.time_tool import TimeTool

TIME_TOOL = {
    "name": "time",
    "description": "Return the current local time.",
    "selection_phrases": ["what time is it", "current time"],
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}


class TimeToolTests(unittest.TestCase):
    def test_time_tool_returns_a_timezone_aware_iso_timestamp(self):
        result = TimeTool().execute()
        timestamp = datetime.fromisoformat(result)

        self.assertIsNotNone(timestamp.tzinfo)

    def test_time_tool_requires_no_arguments(self):
        tool = TimeTool()

        self.assertEqual(tool.parameters["type"], "object")
        self.assertEqual(tool.parameters["required"], [])
        self.assertFalse(tool.parameters["additionalProperties"])

    def test_planner_uses_time_tool_when_metadata_is_available(self):
        plan = Planner().plan(
            "What time is it?",
            available_tools=[TIME_TOOL],
        )

        self.assertEqual(plan.action, "use_tool")
        self.assertEqual(plan.tool_name, "time")
        self.assertEqual(plan.arguments, {})

    def test_planner_does_not_request_time_tool_when_unregistered(self):
        plan = Planner().plan(
            "What time is it?",
            available_tools=[],
        )

        self.assertEqual(plan.action, "respond")

    def test_agent_registers_and_uses_time_tool(self):
        agent = Agent()

        result = agent.run("What time is it?")
        timestamp = datetime.fromisoformat(result)

        self.assertIsNotNone(timestamp.tzinfo)
        self.assertIn("time", {tool["name"] for tool in agent.list_tools()})


if __name__ == "__main__":
    unittest.main()
