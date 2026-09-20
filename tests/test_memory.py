import unittest

from app.memory.memory import ConversationMemory


class ConversationMemoryTests(unittest.TestCase):
    def test_stores_and_retrieves_messages_in_order(self):
        memory = ConversationMemory(max_messages=5)

        memory.add_user_message("Hello")
        memory.add_agent_message("Hi there!")
        memory.add_user_message("How are you?")

        messages = memory.get_messages()

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Hello")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")

    def test_respects_max_messages_limit(self):
        memory = ConversationMemory(max_messages=3)

        memory.add_user_message("1")
        memory.add_agent_message("2")
        memory.add_user_message("3")
        memory.add_agent_message("4")

        messages = memory.get_messages()

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "2")

    def test_build_context_includes_previous_messages(self):
        memory = ConversationMemory(max_messages=5)

        memory.add_user_message("What is 2 + 2?")
        memory.add_agent_message("4")

        context = memory.build_context("What about 3 + 3?")

        self.assertIn("What is 2 + 2?", context)
        self.assertIn("4", context)
        self.assertIn("What about 3 + 3?", context)

    def test_clear_removes_all_messages(self):
        memory = ConversationMemory(max_messages=5)

        memory.add_user_message("Hello")
        memory.clear()

        self.assertEqual(len(memory.get_messages()), 0)

    def test_rejects_non_string_messages(self):
        memory = ConversationMemory()

        with self.assertRaisesRegex(TypeError, "message must be a string"):
            memory.add_user_message(123)

    def test_rejects_empty_messages(self):
        memory = ConversationMemory()

        with self.assertRaisesRegex(ValueError, "message cannot be empty"):
            memory.add_user_message("   ")

    def test_rejects_non_positive_max_messages(self):
        with self.assertRaisesRegex(ValueError, "max_messages must be greater than 0"):
            ConversationMemory(max_messages=0)


class EnhancedMemoryTests(unittest.TestCase):
    """Tests for the enhanced memory layer that stores tool observations and skills."""

    def test_stores_tool_observations_separately_from_conversation(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        memory.add_user_message("What is 2 + 2?")
        memory.add_tool_observation("calculator", 4)
        memory.add_agent_message("The answer is 4.")

        observations = memory.get_tool_observations()

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["tool"], "calculator")
        self.assertEqual(observations[0]["result"], 4)

    def test_tool_observations_are_included_in_context(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        memory.add_user_message("What is 2 + 2?")
        memory.add_tool_observation("calculator", 4)
        memory.add_agent_message("The answer is 4.")
        memory.add_user_message("Now add 5")

        context = memory.build_context("Now add 5")

        self.assertIn("calculator", context)
        self.assertIn("4", context)

    def test_can_store_and_retrieve_skills(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        skill = {
            "name": "calculate_average",
            "description": "Calculate the average of a list of numbers.",
            "steps": ["sum the numbers", "divide by count"],
        }

        memory.add_skill(skill)
        skills = memory.get_skills()

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "calculate_average")

    def test_skills_are_included_in_context(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        memory.add_skill({
            "name": "calculate_average",
            "description": "Calculate the average of a list of numbers.",
        })

        context = memory.build_context("Find the average of 10, 20, 30")

        self.assertIn("calculate_average", context)
        self.assertIn("average", context)

    def test_reflection_stores_evaluation_of_previous_turn(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        memory.add_user_message("What is 2 + 2?")
        memory.add_agent_message("5")
        memory.add_reflection("Incorrect: 2 + 2 = 4, not 5.")

        reflections = memory.get_reflections()

        self.assertEqual(len(reflections), 1)
        self.assertIn("Incorrect", reflections[0])

    def test_reflections_influence_next_context(self):
        from app.memory.enhanced import EnhancedMemory

        memory = EnhancedMemory(max_messages=5)

        memory.add_user_message("What is 2 + 2?")
        memory.add_agent_message("5")
        memory.add_reflection("Incorrect: 2 + 2 = 4, not 5.")
        memory.add_user_message("What is 3 + 3?")

        context = memory.build_context("What is 3 + 3?")

        self.assertIn("Incorrect", context)
        self.assertIn("4", context)


if __name__ == "__main__":
    unittest.main()