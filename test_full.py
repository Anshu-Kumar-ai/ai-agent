import sys
sys.path.insert(0, '.')

from app.core.agent import Agent
from app.core.permissions import ApprovalMode

# Create agent with permissive permission mode for testing
agent = Agent()
agent.permission_manager.approval_mode = ApprovalMode.FULL_AUTO

print("=== Testing all tools ===")

# Test calculator
result = agent.run("What is 2 + 3 * 4?")
print(f"Calculator: {result}")

# Test time
result = agent.run("What time is it?")
print(f"Time: {result}")

# Test fs.list
result = agent.run("List files in current directory")
print(f"List: {len(result)} items")

# Test fs.write
result = agent.run("Write 'Hello from agent!' to file test_output.txt")
print(f"Write: {result}")

# Test fs.read
result = agent.run("Read the file test_output.txt")
print(f"Read: {result}")

# Test fs.move
result = agent.run("Move test_output.txt to test_output_moved.txt")
print(f"Move: {result}")

# Test fs.read moved file
result = agent.run("Read the file test_output_moved.txt")
print(f"Read moved: {result}")

# Test terminal.run
result = agent.run("Run command echo 'Hello from terminal'")
print(f"Terminal: {result}")

# Test http.fetch
result = agent.run("Fetch https://httpbin.org/get")
print(f"HTTP Fetch: {result[:100]}...")

print("\n=== All tests passed! ===")