import sys
sys.path.insert(0, '.')

from app.core.planner import LLMPlanner
from app.core.router import SmartRouter
from app.tools.web_tools import HTTPFetchTool, WebSearchTool

# Create router and LLM planner
router = SmartRouter()
planner = LLMPlanner(router)

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

# Test LLM planner with fetch request
print("=== Testing LLMPlanner with Web Tools ===")
test_queries = [
    "Fetch https://example.com",
    "Search for python tutorials",
    "Get the content of https://httpbin.org/get",
]

for query in test_queries:
    try:
        plan = planner.plan(query, available_tools, None, None)
        print(f"Query: '{query}'")
        print(f"  Action: {plan.action}, Tool: {plan.tool_name}, Args: {plan.arguments}")
    except Exception as e:
        print(f"Query: '{query}' -> ERROR: {e}")
    print()

print("=== LLM Planner test complete ===")