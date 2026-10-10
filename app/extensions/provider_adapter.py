"""Provider Adapter - Stage 32 Phase 2
Adapts existing model implementations to ProviderInterface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import time

from app.extensions.contracts import ProviderInterface
from app.models.base import BaseModel


class ProviderAdapter(ProviderInterface, ABC):
    """Base adapter that wraps existing BaseModel implementations to conform to ProviderInterface."""
    
    def __init__(self, model: BaseModel, provider_id: str, model_id: str):
        self._model = model
        self._provider_id = provider_id
        self._model_id = model_id
        self._last_health_check = 0
        self._failure_count = 0
        self._last_failure_time = 0
        # Set initial health based on model availability
        if self.is_available():
            self._health_info = {"status": "healthy", "latency_ms": 0}
        else:
            self._health_info = {"status": "unknown", "latency_ms": 0}
    
    @property
    def provider_id(self) -> str:
        return self._provider_id
    
    @property
    def model_id(self) -> str:
        return self._model_id
    
    def is_available(self) -> bool:
        # Delegate to the model's availability check
        # Most models check this during initialization
        return hasattr(self._model, 'client') and self._model.client is not None
    
    def invoke(self, prompt: str, **kwargs) -> str:
        start_time = time.time()
        try:
            # Most models have a chat method
            if hasattr(self._model, 'chat'):
                response = self._model.chat(prompt)
            else:
                # Fallback for models with different interfaces
                response = str(self._model)
            
            # Update health info on success
            latency = (time.time() - start_time) * 1000
            self._health_info = {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "last_success": time.time()
            }
            self._failure_count = 0
            return response
            
        except Exception as e:
            # Update health info on failure
            latency = (time.time() - start_time) * 1000
            self._health_info = {
                "status": "unhealthy",
                "latency_ms": round(latency, 2),
                "last_error": str(e),
                "last_failure": time.time()
            }
            self._failure_count += 1
            self._last_failure_time = time.time()
            raise e
    
    def get_timeout(self) -> float:
        # Default timeout - can be overridden
        return 30.0
    
    def classify_failure(self, exception: Exception) -> str:
        """Classify exception into failure categories."""
        error_str = str(exception).lower()
        
        if "timeout" in error_str or "timed out" in error_str:
            return "timeout"
        elif "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif "authentication" in error_str or "unauthorized" in error_str or "401" in error_str or "403" in error_str:
            return "authentication"
        elif "connection" in error_str or "network" in error_str:
            return "connection"
        elif "malformed" in error_str or "invalid response" in error_str:
            return "malformed_response"
        else:
            return "unknown_provider_error"
    
    def get_token_usage(self) -> Dict[str, int]:
        # Most models don't expose token usage easily
        # Return empty dict or estimate if possible
        return {}
    
    def get_health_info(self) -> Dict[str, Any]:
        return self._health_info.copy()


class GeminiProviderAdapter(ProviderAdapter):
    """Adapter for GeminiModel."""

    def __init__(self, provider_id: str = None, model_id: str = None):
        from app.models.gemini import GeminiModel
        model = GeminiModel()
        super().__init__(model, provider_id or "gemini", model_id or "gemini-3.7-flash")


class GroqProviderAdapter(ProviderAdapter):
    """Adapter for GroqModel."""

    def __init__(self, provider_id: str = None, model_id: str = None):
        from app.models.groq import GroqModel
        model = GroqModel()
        super().__init__(model, provider_id or "groq", model_id or "openai/gpt-oss-20b")


class OpenRouterProviderAdapter(ProviderAdapter):
    """Adapter for OpenRouterModel."""

    def __init__(self, provider_id: str = None, model_id: str = None):
        from app.models.openrouter import OpenRouterModel
        model = OpenRouterModel()
        super().__init__(model, provider_id or "openrouter", model_id or "openrouter/free")


class LocalProviderAdapter(ProviderAdapter):
    """Adapter for LocalModel."""

    def __init__(self, provider_id: str = None, model_id: str = None):
        from app.models.local import LocalModel
        model = LocalModel()
        super().__init__(model, provider_id or "local", model_id or "local")