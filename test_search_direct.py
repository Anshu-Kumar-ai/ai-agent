import sys
sys.path.insert(0, '.')

from app.tools.web_tools import WebSearchTool

tool = WebSearchTool()
result = tool.execute(query='python asyncio tutorial')
print(f'Result: {result[:500]}')