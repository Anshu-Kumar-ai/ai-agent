from typing import Any, List, Optional
from .provider import LLMProvider

class MockLLMProvider(LLMProvider):
    """
    A mock LLM provider that returns a predefined sequence of responses.
    Useful for testing.
    """
    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = responses or []
        self._index = 0

    def generate(self, prompt: str, **kwargs: Any) -> str:
        if not self._responses:
            # Default response: empty plan
            return "[]"
        if self._index >= len(self._responses):
            # If we run out of responses, repeat the last one or return empty?
            return self._responses[-1] if self._responses else "[]"
        response = self._responses[self._index]
        self._index += 1
        return response

    def is_available(self) -> bool:
        return True

    def set_responses(self, responses: List[str]) -> None:
        self._responses = responses
        self._index = 0
