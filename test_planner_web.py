import sys
sys.path.insert(0, '.')

from app.core.planner import Planner
from app.tools.web_tools import HTTPFetchTool, WebSearchTool

# Create planner
planner = Planner()

# Create mock tools with metadata
http_tool = HTTPFetchTool()
search_tool = WebSearchTool()

available_tools = [
    {
        "name": http_tool.name,
        "description": http_tool.description,
        "selection_phrases": http_tool.selection_phrases,
        "parameters": http_tool.parameters
    },
    {
        "name": search_tool.name,
        "description": search_tool.description,
        "selection_phrases": search_tool.selection_phrases,
        "parameters": search_tool.parameters
    }
]

# Test planner with fetch request
print("=== Testing Planner with Web Tools ===")
test_queries = [
    "Fetch https://example.com",
    "Get the content of https://httpbin.org/get",
    "Search for python tutorials",
    "Web search for AI agent frameworks",
    "Download https://github.com",
    "Find information about AI agents",
]

for query in test_queries:
    plan = planner.plan(query, available_tools, None, None)
    print(f"Query: '{query}'")
    print(f"  Action: {plan.action}, Tool: {plan.tool_name}, Args: {plan.arguments}")
    print()

print("=== Planner web tool selection test complete ===")