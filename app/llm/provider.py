from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    """Interface for language model providers."""
    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from the model given a prompt."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider/service is reachable."""
