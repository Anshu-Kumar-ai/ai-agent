import unittest

from app.core.agent_loop import AgentLoop
from app.core.planner import Plan
from app.tools.calculator import CalculatorTool
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry


class AveragePlanner:
    """Deterministic test planner that needs two calculator actions."""

    def __init__(self):
        self.observation_counts = []

    def plan(self, message, available_tools, observations=None, context=None):
        observations = observations or []
        self.observation_counts.append(len(observations))

        if not observations:
            return Plan(
                action="use_tool",
                tool_name="calculator",
                arguments={"expression": "10 + 20 + 30"},
            )

        if len(observations) == 1:
            return Plan(
                action="use_tool",
                tool_name="calculator",
                arguments={"expression": f"{observations[0].result} / 3"},
            )

        return Plan(action="respond")


class EndlessToolPlanner:
    def plan(self, message, available_tools, observations=None, context=None):
        return Plan(
            action="use_tool",
            tool_name="calculator",
            arguments={"expression": "1 + 1"},
        )


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        self.executor = ToolExecutor(registry)

    def test_replans_after_observations_until_a_final_response(self):
        planner = AveragePlanner()
        loop = AgentLoop(planner, self.executor, max_steps=3)

        result = loop.run(
            "Find the average of 10, 20 and 30.",
            available_tools={"calculator"},
            responder=lambda observations: f"The average is {observations[-1].result}.",
        )

        self.assertEqual(result, "The average is 20.0.")
        self.assertEqual(planner.observation_counts, [0, 1, 2])

    def test_stops_when_the_maximum_tool_step_limit_is_reached(self):
        loop = AgentLoop(EndlessToolPlanner(), self.executor, max_steps=2)

        with self.assertRaisesRegex(RuntimeError, "maximum tool steps"):
            loop.run(
                "Keep calculating.",
                available_tools={"calculator"},
                responder=lambda observations: "unreachable",
            )

    def test_rejects_a_non_positive_step_limit(self):
        with self.assertRaisesRegex(ValueError, "max_steps"):
            AgentLoop(AveragePlanner(), self.executor, max_steps=0)


if __name__ == "__main__":
    unittest.main()