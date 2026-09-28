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

# Debug: print tool metadata
for tool in available_tools:
    print(f"Tool: {tool['name']}")
    print(f"  Phrases: {tool['selection_phrases']}")
    print()

# Test planner with fetch request
print("=== Testing Planner with Web Tools ===")
test_queries = [
    "Fetch https://example.com",
    "fetch https://example.com",
    "get https://example.com",
    "download https://example.com",
    "http get https://example.com",
    "http fetch https://example.com",
    "search web for python",
    "web search for AI",
    "search internet for AI agents",
    "google search AI",
    "duckduckgo AI",
]

for query in test_queries:
    message_lower = query.lower()
    print(f"Query: '{query}' -> lower: '{message_lower}'")
    for tool in available_tools:
        phrases = tool.get("selection_phrases", [])
        matches = [phrase for phrase in phrases if phrase.lower() in message_lower]
        if matches:
            print(f"  MATCHES {tool['name']} via: {matches}")
            break
    else:
        print(f"  NO MATCH")
    
    plan = planner.plan(query, available_tools, None, None)
    print(f"  Plan: Action={plan.action}, Tool={plan.tool_name}")
    print()

print("=== Done ===")