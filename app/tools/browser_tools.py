"""Browser automation tools for Stage 15 - Browser Automation.

Provides web browser automation using Playwright:
- Navigate to URLs
- Click elements
- Type text
- Take screenshots
- Execute JavaScript
- Extract page content
"""

import asyncio
from typing import Any

from app.tools.base import BaseTool


class BrowserTool(BaseTool):
    """Base class for browser automation tools."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    async def _ensure_browser(self):
        """Ensure browser is launched."""
        if self._page is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._page = await self._browser.new_page()

    async def _close_browser(self):
        """Close browser and cleanup."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _run_async(self, coro):
        """Run async coroutine in sync context."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


class BrowserNavigateTool(BrowserTool):
    """Navigate to a URL in the browser."""

    name = "browser.navigate"
    description = "Navigate to a URL in the browser"
    selection_phrases = ("go to", "navigate to", "open url", "visit", "browse to")
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to navigate to",
            },
            "wait_until": {
                "type": "string",
                "description": "When to consider navigation complete",
                "enum": ["load", "domcontentloaded", "networkidle"],
                "default": "networkidle",
            },
            "timeout": {
                "type": "integer",
                "description": "Navigation timeout in milliseconds",
                "default": 30000,
                "minimum": 1000,
                "maximum": 120000,
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "url" not in arguments:
            raise ValueError("Missing required argument: 'url'")
        url = arguments["url"]
        if not isinstance(url, str):
            raise ValueError("'url' must be a string")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("'url' must start with http:// or https://")

    def execute(self, **kwargs) -> dict[str, Any]:
        url = kwargs["url"]
        wait_until = kwargs.get("wait_until", "networkidle")
        timeout = kwargs.get("timeout", 30000)

        async def _navigate():
            await self._ensure_browser()
            response = await self._page.goto(url, wait_until=wait_until, timeout=timeout)
            return {
                "url": self._page.url,
                "title": await self._page.title(),
                "status": response.status if response else None,
            }

        try:
            result = self._run_async(_navigate())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


class BrowserClickTool(BrowserTool):
    """Click an element on the page."""

    name = "browser.click"
    description = "Click an element on the page using a CSS selector"
    selection_phrases = ("click", "press", "tap", "select element")
    parameters = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector for the element to click",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
                "minimum": 100,
                "maximum": 30000,
            },
            "force": {
                "type": "boolean",
                "description": "Force click even if element is not visible",
                "default": False,
            },
        },
        "required": ["selector"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "selector" not in arguments:
            raise ValueError("Missing required argument: 'selector'")
        if not isinstance(arguments["selector"], str):
            raise ValueError("'selector' must be a string")

    def execute(self, **kwargs) -> dict[str, Any]:
        selector = kwargs["selector"]
        timeout = kwargs.get("timeout", 5000)
        force = kwargs.get("force", False)

        async def _click():
            await self._ensure_browser()
            await self._page.click(selector, timeout=timeout, force=force)
            return {"clicked": True, "selector": selector}

        try:
            result = self._run_async(_click())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


class BrowserTypeTool(BrowserTool):
    """Type text into an input field."""

    name = "browser.type"
    description = "Type text into an input field using a CSS selector"
    selection_phrases = ("type", "input", "fill", "enter text", "write in")
    parameters = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector for the input element",
            },
            "text": {
                "type": "string",
                "description": "Text to type",
            },
            "delay": {
                "type": "integer",
                "description": "Delay between keystrokes in milliseconds",
                "default": 0,
                "minimum": 0,
                "maximum": 1000,
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in milliseconds",
                "default": 5000,
                "minimum": 100,
                "maximum": 30000,
            },
        },
        "required": ["selector", "text"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "selector" not in arguments:
            raise ValueError("Missing required argument: 'selector'")
        if "text" not in arguments:
            raise ValueError("Missing required argument: 'text'")
        if not isinstance(arguments["selector"], str):
            raise ValueError("'selector' must be a string")
        if not isinstance(arguments["text"], str):
            raise ValueError("'text' must be a string")

    def execute(self, **kwargs) -> dict[str, Any]:
        selector = kwargs["selector"]
        text = kwargs["text"]
        delay = kwargs.get("delay", 0)
        timeout = kwargs.get("timeout", 5000)

        async def _type():
            await self._ensure_browser()
            await self._page.fill(selector, text, timeout=timeout)
            if delay > 0:
                # For character-by-character typing
                await self._page.type(selector, text, delay=delay, timeout=timeout)
            return {"typed": True, "selector": selector, "text": text}

        try:
            result = self._run_async(_type())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


class BrowserScreenshotTool(BrowserTool):
    """Take a screenshot of the current page."""

    name = "browser.screenshot"
    description = "Take a screenshot of the current page"
    selection_phrases = ("screenshot", "capture", "take picture", "snapshot", "save page as image")
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to save screenshot (optional, returns base64 if not provided)",
                "default": "",
            },
            "full_page": {
                "type": "boolean",
                "description": "Capture full page or just viewport",
                "default": False,
            },
            "quality": {
                "type": "integer",
                "description": "JPEG quality (1-100), only for JPEG format",
                "default": 80,
                "minimum": 1,
                "maximum": 100,
            },
        },
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        path = kwargs.get("path", "")
        full_page = kwargs.get("full_page", False)
        quality = kwargs.get("quality", 80)

        async def _screenshot():
            await self._ensure_browser()
            if path:
                await self._page.screenshot(path=path, full_page=full_page, quality=quality)
                return {"path": path, "base64": None}
            else:
                # Return base64 encoded
                img_bytes = await self._page.screenshot(full_page=full_page, quality=quality)
                import base64
                return {"path": None, "base64": base64.b64encode(img_bytes).decode()}

        try:
            result = self._run_async(_screenshot())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


class BrowserContentTool(BrowserTool):
    """Get the content of the current page."""

    name = "browser.content"
    description = "Get the HTML content or text content of the current page"
    selection_phrases = ("get content", "page content", "html", "text content", "extract text")
    parameters = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "Format to return content in",
                "enum": ["html", "text", "markdown"],
                "default": "text",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector to extract content from specific element",
                "default": "",
            },
        },
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        format_type = kwargs.get("format", "text")
        selector = kwargs.get("selector", "")

        async def _content():
            await self._ensure_browser()
            if selector:
                element = await self._page.query_selector(selector)
                if not element:
                    return {"error": f"Element not found: {selector}"}
                if format_type == "html":
                    content = await element.inner_html()
                elif format_type == "markdown":
                    # Simple markdown conversion
                    html = await element.inner_html()
                    content = self._html_to_markdown(html)
                else:
                    content = await element.inner_text()
            else:
                if format_type == "html":
                    content = await self._page.content()
                elif format_type == "markdown":
                    html = await self._page.content()
                    content = self._html_to_markdown(html)
                else:
                    content = await self._page.inner_text("body")
            return {"content": content, "format": format_type}

        try:
            result = self._run_async(_content())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def _html_to_markdown(self, html: str) -> str:
        """Simple HTML to markdown conversion."""
        import re
        # Very basic conversion
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


class BrowserEvaluateTool(BrowserTool):
    """Execute JavaScript in the browser context."""

    name = "browser.evaluate"
    description = "Execute JavaScript code in the browser context"
    selection_phrases = ("execute js", "run javascript", "evaluate", "run script", "browser eval")
    parameters = {
        "type": "object",
        "properties": {
            "script": {
                "type": "string",
                "description": "JavaScript code to execute",
            },
            "await_result": {
                "type": "boolean",
                "description": "Whether to await the result (for async functions)",
                "default": True,
            },
        },
        "required": ["script"],
        "additionalProperties": False,
    }

    def validate_arguments(self, arguments: dict) -> None:
        if "script" not in arguments:
            raise ValueError("Missing required argument: 'script'")
        if not isinstance(arguments["script"], str):
            raise ValueError("'script' must be a string")

    def execute(self, **kwargs) -> dict[str, Any]:
        script = kwargs["script"]
        await_result = kwargs.get("await_result", True)

        async def _evaluate():
            await self._ensure_browser()
            if await_result:
                result = await self._page.evaluate(script)
            else:
                result = await self._page.evaluate(f"({script})()")
            return {"result": result}

        try:
            result = self._run_async(_evaluate())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


class BrowserCloseTool(BrowserTool):
    """Close the browser."""

    name = "browser.close"
    description = "Close the browser and cleanup resources"
    selection_phrases = ("close browser", "quit browser", "exit browser")
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    def execute(self, **kwargs) -> dict[str, Any]:
        async def _close():
            await self._close_browser()
            return {"closed": True}

        try:
            result = self._run_async(_close())
            return {
                "success": True,
                **result,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }


def create_browser_tools(headless: bool = True) -> list:
    """Create all browser tools."""
    return [
        BrowserNavigateTool(headless=headless),
        BrowserClickTool(headless=headless),
        BrowserTypeTool(headless=headless),
        BrowserScreenshotTool(headless=headless),
        BrowserContentTool(headless=headless),
        BrowserEvaluateTool(headless=headless),
        BrowserCloseTool(headless=headless),
    ]
