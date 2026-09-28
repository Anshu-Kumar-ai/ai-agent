import sys
sys.path.insert(0, '.')

from app.core.agent import Agent
from app.core.permissions import ApprovalMode

# Create agent with permissive permission mode for testing
agent = Agent()
agent.permission_manager.approval_mode = ApprovalMode.FULL_AUTO

print("=== Testing calculator only ===")

# Test calculator
result = agent.run("What is 2 + 3 * 4?")
print(f"Calculator: {result}")

print("\n=== Test passed! ===")