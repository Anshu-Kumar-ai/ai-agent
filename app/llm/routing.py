from typing import Any

from .provider import LLMProvider


class LLMRouter:
    """Selects an LLMProvider based on policy. For MVP, just returns the given provider."""
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return self.provider.generate(prompt, **kwargs)

    def is_available(self) -> bool:
        return self.provider.is_available()