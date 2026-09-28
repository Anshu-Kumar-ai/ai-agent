"""Web and HTTP tools for the AI agent.

Provides safe HTTP operations and web search capabilities.
"""

import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.tools.base import BaseTool


class HTTPFetchTool(BaseTool):
    """Fetch content from a URL via HTTP/HTTPS."""

    name = "http.fetch"
    description = "Fetch content from a URL (GET request)"
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30},
            "headers": {"type": "object", "description": "Optional HTTP headers", "additionalProperties": {"type": "string"}},
            "max_chars": {"type": "integer", "description": "Maximum characters to return (0 = no limit)", "default": 50000},
        },
        "required": ["url"]
    }
    selection_phrases = ["fetch", "download", "get url", "http get", "http fetch"]

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        url = arguments.get("url")
        if url is None:
            return False, "Missing 'url' argument"
        if not isinstance(url, str):
            return False, "'url' must be a string"
        # Basic URL validation
        if not (url.startswith("http://") or url.startswith("https://")):
            return False, "'url' must start with http:// or https://"
        timeout = arguments.get("timeout", 30)
        if timeout is not None:
            if not isinstance(timeout, (int, float)) or timeout <= 0:
                return False, "'timeout' must be a positive number"
        max_chars = arguments.get("max_chars", 50000)
        if max_chars is not None:
            if not isinstance(max_chars, int) or max_chars < 0:
                return False, "'max_chars' must be a non-negative integer"
        headers = arguments.get("headers")
        if headers is not None:
            if not isinstance(headers, dict):
                return False, "'headers' must be an object"
            for k, v in headers.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    return False, "Header keys and values must be strings"
        return True, ""

    def execute(self, **kwargs) -> Any:
        url = kwargs.get("url")
        timeout = kwargs.get("timeout", 30)
        headers = kwargs.get("headers", {})
        max_chars = kwargs.get("max_chars", 50000)

        # Prepare request
        req = urllib.request.Request(url, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode('utf-8', errors='replace')
                status_code = response.getcode()
                content_type = response.getheader('Content-Type', '')
        except urllib.error.HTTPError as e:
            return {
                "status": "error",
                "error": f"HTTP {e.code}: {e.reason}",
                "status_code": e.code,
                "url": url
            }
        except urllib.error.URLError as e:
            return {
                "status": "error",
                "error": f"URL error: {e.reason}",
                "url": url
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Fetch failed: {e}",
                "url": url
            }

        # Truncate if needed
        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars] + f"\n... [truncated at {max_chars} chars]"

        return f"Fetched: {url}\nStatus: {status_code}\nContent-Type: {content_type}\nSize: {len(content)} chars\n\n{content}"


class WebSearchTool(BaseTool):
    """Search the web using a search API (DuckDuckGo HTML fallback)."""

    name = "web.search"
    description = "Search the web for information"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Maximum results to return", "default": 10},
        },
        "required": ["query"]
    }
    selection_phrases = ["search web", "web search", "search internet", "google search", "duckduckgo"]

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str]:
        query = arguments.get("query")
        if query is None:
            return False, "Missing 'query' argument"
        if not isinstance(query, str) or not query.strip():
            return False, "'query' must be a non-empty string"
        max_results = arguments.get("max_results", 10)
        if max_results is not None:
            if not isinstance(max_results, int) or max_results <= 0:
                return False, "'max_results' must be a positive integer"
        return True, ""

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query")
        max_results = kwargs.get("max_results", 10)

        # Use DuckDuckGo HTML as a free search fallback
        # This is a simplified implementation - in production you'd use a proper search API
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

        req = urllib.request.Request(
            search_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8', errors='replace')
        except Exception as e:
            return (
                f"Search failed: {e}"
            )

        # Check for CAPTCHA/challenge page
        if "anomaly-modal" in html or "bots use DuckDuckGo" in html:
            return (
                "Search temporarily unavailable: DuckDuckGo is showing a CAPTCHA challenge. "
                "This is a known limitation of the free HTML interface. "
                "Consider using a proper search API (Google, Bing, SerpAPI) for production use."
            )

        # Parse HTML for results (simplified regex-based extraction)
        # Updated patterns for current DuckDuckGo HTML structure
        # Try multiple patterns for different HTML structures
        result_patterns = [
            r'class="result__snippet">([^<]+)</a>',
            r'class="result__snippet">([^<]+)</span>',
            r'data-result="snippet">([^<]+)</a>',
            r'data-result="snippet">([^<]+)</span>',
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>([^<]+)</a>',
        ]
        
        url_patterns = [
            r'class="result__url">([^<]+)</a>',
            r'class="result__url">([^<]+)</span>',
            r'data-result="url">([^<]+)</a>',
            r'data-result="url">([^<]+)</span>',
        ]
        
        snippets = []
        urls = []
        
        # Try each pattern until we find matches
        for pattern in result_patterns:
            snippets = re.findall(pattern, html)
            if snippets:
                break
        
        for pattern in url_patterns:
            urls = re.findall(pattern, html)
            if urls:
                break

        # If still no results, try more generic patterns
        if not snippets:
            # Try to find any text that looks like a search result
            generic_pattern = r'<a[^>]*class="[^"]*result[^"]*"[^>]*>([^<]{20,})</a>'
            snippets = re.findall(generic_pattern, html)
        
        if not urls:
            generic_url_pattern = r'<a[^>]*class="[^"]*result__url[^"]*"[^>]*>([^<]+)</a>'
            urls = re.findall(generic_url_pattern, html)

        for i, (snippet, url) in enumerate(zip(snippets, urls)):
            if i >= max_results:
                break
            results.append({
                "title": snippet[:100],
                "snippet": snippet,
                "url": url.strip()
            })

        # If parsing failed, return basic info
        if not results:
            return (
                "Search completed but no structured results extracted. "
                "DuckDuckGo's HTML structure may have changed. "
                "Consider using a proper search API (Google, Bing, SerpAPI) for production use."
            )

        # Format results as a readable string
        lines = [f"Search results for: {query}"]
        for i, result in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {result.get('title', '')}")
            lines.append(f"   URL: {result.get('url', '')}")
            lines.append(f"   Snippet: {result.get('snippet', '')}")
            lines.append("")
        return "\n".join(lines)


def register_web_tools(registry, executor):
    """Register web tools with the tool registry."""
    tools = [
        HTTPFetchTool(),
        WebSearchTool(),
    ]
    for tool in tools:
        registry.register(tool)