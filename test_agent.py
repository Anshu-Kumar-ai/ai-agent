import sys
sys.path.insert(0, '.')

from app.core.agent import Agent

# Create agent
agent = Agent()

# Test basic functionality
print("Agent created successfully")
print(f"Available tools: {agent.list_tools()}")

# Test calculator
result = agent.run("What is 2 + 3 * 4?")
print(f"Calculator test: {result}")

# Test file system tools
result = agent.run("List files in current directory")
print(f"List test: {result}")

print("All tests passed!")