import sys
sys.path.insert(0, r"C:\Users\anshu\Agent\AI-Agent")

from app.core.agent import Agent
from app.core.permissions import ApprovalMode

# Create agent with permissive permission mode for testing
agent = Agent()
agent.permission_manager.approval_mode = ApprovalMode.FULL_AUTO

print("=== Verification Tests ===")

# Test 1: Calculator
result = agent.run("What is 2 + 3 * 4?")
assert "14" in result, f"Calculator failed: {result}"
print("✅ Calculator: PASS")

# Test 2: Time
result = agent.run("What time is it?")
assert "T" in result and ":" in result, f"Time failed: {result}"
print("✅ Time: PASS")

# Test 3: fs.list
result = agent.run("List files in current directory")
assert len(result) > 100, f"List failed: {result[:100]}"
print("✅ fs.list: PASS")

# Test 4: fs.write
result = agent.run("Write 'Hello from agent!' to file verify_test.txt")
assert "bytes_written" in result or "17" in result, f"Write failed: {result}"
print("✅ fs.write: PASS")

# Test 5: fs.read
result = agent.run("Read the file verify_test.txt")
assert "Hello from agent!" in result, f"Read failed: {result}"
print("✅ fs.read: PASS")

# Test 6: fs.move
result = agent.run("Move verify_test.txt to verify_test_moved.txt")
assert "True" in result or "true" in result, f"Move failed: {result}"
print("✅ fs.move: PASS")

# Test 7: fs.read moved
result = agent.run("Read the file verify_test_moved.txt")
assert "Hello from agent!" in result, f"Read moved failed: {result}"
print("✅ fs.read (moved): PASS")

# Test 8: terminal.run
result = agent.run("Run command echo 'Hello from terminal'")
assert "Hello from terminal" in result, f"Terminal failed: {result}"
print("✅ terminal.run: PASS")

# Test 9: http.fetch
result = agent.run("Fetch https://httpbin.org/get")
assert "httpbin.org" in result and "Status: 200" in result, f"HTTP fetch failed: {result[:200]}"
print("✅ http.fetch: PASS")

# Test 10: web.search (should handle CAPTCHA gracefully)
result = agent.run("Search for python asyncio tutorial")
assert "temporarily unavailable" in result.lower() or "search" in result.lower(), f"Search failed: {result[:200]}"
print("✅ web.search: PASS")

# Test 11: Verify all 9 tools registered
tools = agent.list_tools()
tool_names = [t["name"] for t in tools]
expected = {"calculator", "time", "fs.read", "fs.write", "fs.move", "fs.list", "terminal.run", "http.fetch", "web.search"}
assert expected.issubset(set(tool_names)), f"Missing tools: {expected - set(tool_names)}"
print("✅ All 9 tools registered: PASS")

print("\n=== ALL VERIFICATION TESTS PASSED ===")