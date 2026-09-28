import sys
sys.path.insert(0, '.')

from app.tools.web_tools import HTTPFetchTool

# Test the tool directly
tool = HTTPFetchTool()
result = tool.execute(url="https://httpbin.org/get")
print(f"Tool result type: {type(result)}")
print(f"Tool result: {result[:500]}")