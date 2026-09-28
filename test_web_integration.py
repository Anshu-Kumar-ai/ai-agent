import sys
sys.path.insert(0, '.')

from app.core.agent import Agent

# Create agent
agent = Agent()

print("=== Testing Web Tools Integration ===")

# Test HTTP fetch
print("\n1. Testing HTTP Fetch:")
result = agent.run("Fetch https://httpbin.org/get")
print(f"Result: {result[:300]}")

# Test web search
print("\n2. Testing Web Search:")
result = agent.run("Search for python asyncio tutorial")
print(f"Result: {result[:300]}")

# Test that all tools are registered
print("\n3. All registered tools:")
for tool in agent.list_tools():
    print(f"  - {tool['name']}: {tool['description']}")

print("\n=== Web Tools Integration Test Complete ===")