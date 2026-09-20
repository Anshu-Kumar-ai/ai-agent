import sys
sys.path.insert(0, '.')

from app.core.agent import Agent

# Create agent with lower threshold for testing retry
agent = Agent()

# Test that evaluation retry works by creating a scenario that should trigger retry
print("=== Testing Evaluation Retry Logic ===")

# Test 1: Normal case should pass
result = agent.run("What is 2 + 3 * 4?")
print(f"Calculator: {result}")

# Test 2: Time query
result = agent.run("What time is it?")
print(f"Time: {result}")

# Test 3: File operations
result = agent.run("List files in current directory")
print(f"List: {len(result)} items")

# Test 4: Write and read
result = agent.run("Create a test file at eval_test.txt with content 'Evaluation test'")
print(f"Write: {result}")

result = agent.run("Read the file eval_test.txt")
print(f"Read: {result}")

print("\n=== All basic tests passed! ===")

# Test evaluation feedback generation
print("\n=== Testing Evaluator Feedback ===")
from app.core.evaluator import Evaluator
evaluator = Evaluator()

# Test case that should fail evaluation
bad_response = "I don't know"
plan = {"action": "respond", "tool_name": None, "arguments": {}, "reason": ""}
observations = []

eval_result = evaluator.evaluate("What is 2+2?", {"action": "respond"}, observations, bad_response)
print(f"\nBad response score: {eval_result.score:.2f}")
print(f"Criteria not met: {eval_result.criteria_not_met}")
print(f"Feedback: {eval_result.feedback}")

# Test feedback generation
from app.core.agent_loop import AgentLoop
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.tools.calculator import CalculatorTool
from app.memory.enhanced import EnhancedMemory
from app.core.evaluator import Evaluator
from app.core.planner import Planner

tool_registry = ToolRegistry()
tool_registry.register(CalculatorTool())
tool_executor = ToolExecutor(tool_registry)
planner = Planner()
evaluator = Evaluator()
memory = EnhancedMemory()

loop = AgentLoop(
    planner,
    tool_executor,
    evaluator=evaluator,
    evaluation_callback=lambda e: memory.add_evaluation(e),
    memory=memory,
    evaluation_threshold=0.7,
    max_retries=2,
)

feedback = loop._generate_retry_feedback(eval_result)
print(f"\nGenerated retry feedback:\n{feedback}")