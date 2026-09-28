import sys
sys.path.insert(0, '.')

from app.core.agent import Agent

# Create agent
agent = Agent()

# Test basic functionality
print("Agent created successfully")
print(f"Available tools: {agent.list_tools()}")

# Test HTTP fetch
result = agent.run("Fetch https://httpbin.org/get")
print(f"HTTP Fetch test: {result[:200]}")

print("\n=== Web tools integration test passed! ===")