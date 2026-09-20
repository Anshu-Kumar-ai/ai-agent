import unittest

from app.core.agent_loop import ToolObservation
from app.core.planner import Plan


class BoundaryContractTests(unittest.TestCase):
    def test_plan_round_trips_through_a_serializable_dictionary(self):
        plan = Plan(
            action="use_tool",
            tool_name="calculator",
            arguments={"expression": "2 + 3"},
            reason="The request matches a registered capability.",
        )

        serialized = plan.to_dict()
        restored = Plan.from_dict(serialized)

        self.assertEqual(
            serialized,
            {
                "action": "use_tool",
                "tool_name": "calculator",
                "arguments": {"expression": "2 + 3"},
                "reason": "The request matches a registered capability.",
            },
        )
        self.assertEqual(restored, plan)

    def test_plan_rejects_a_tool_action_without_a_dictionary_arguments_field(self):
        with self.assertRaisesRegex(TypeError, "arguments"):
            Plan.from_dict(
                {
                    "action": "use_tool",
                    "tool_name": "calculator",
                    "arguments": ["2 + 3"],
                    "reason": "bad payload",
                }
            )

    def test_tool_observation_round_trips_through_a_serializable_dictionary(self):
        observation = ToolObservation(tool_name="calculator", result=5)

        serialized = observation.to_dict()
        restored = ToolObservation.from_dict(serialized)

        self.assertEqual(serialized, {"tool_name": "calculator", "result": 5})
        self.assertEqual(restored, observation)

    def test_tool_observation_rejects_a_missing_result_field(self):
        with self.assertRaisesRegex(ValueError, "result"):
            ToolObservation.from_dict({"tool_name": "calculator"})


if __name__ == "__main__":
    unittest.main()
