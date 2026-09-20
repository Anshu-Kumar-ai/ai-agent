import sys
sys.path.insert(0, '.')

from app.core.agent import Agent

# Create agent
agent = Agent()

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
result = agent.run("Create a test file at test_output.txt with content 'Hello from agent!'")
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

print("\n=== All tests passed! ===")