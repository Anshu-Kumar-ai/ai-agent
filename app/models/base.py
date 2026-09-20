from abc import ABC, abstractmethod


class BaseModel(ABC):
    name: str = "unknown"
    provider: str = "unknown"

    @abstractmethod
    def chat(self, message: str) -> str:
        """Send a message and return the model response."""
        raise NotImplementedError