"""Provider Registry - Stage 32 Phase 2
Integrates providers with the extension registry system and handles configuration.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import os
from enum import Enum

from app.extensions.contracts import ProviderInterface
from app.extensions.registry import ProviderRegistry, ExtensionType, ExtensionManager
from app.extensions.provider_adapter import (
    GeminiProviderAdapter,
    GroqProviderAdapter,
    OpenRouterProviderAdapter,
    LocalProviderAdapter
)


class ProviderConfigModel:
    """Configuration model for a provider."""

    def __init__(
        self,
        provider_id: str,
        display_name: str,
        adapter_class: type,
        api_key_env: Optional[str] = None,
        enabled: bool = True,
        priority: int = 0,
        default_model: str = "",
        capabilities: List[str] = None,
        adapter_kwargs: Dict[str, Any] = None
    ):
        self.provider_id = provider_id
        self.display_name = display_name
        self.adapter_class = adapter_class
        self.api_key_env = api_key_env
        self.enabled = enabled
        self.priority = priority
        self.default_model = default_model
        self.capabilities = capabilities or []
        self.adapter_kwargs = adapter_kwargs or {}

    def is_configured(self) -> bool:
        """Check if provider is properly configured (API key if required)."""
        if not self.api_key_env:
            return True  # No API key needed (e.g., local)
        return bool(os.getenv(self.api_key_env))

    def create_adapter(self) -> ProviderInterface:
        """Create an adapter instance."""
        try:
            return self.adapter_class(self.provider_id, self.default_model, **self.adapter_kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to create {self.provider_id} adapter: {e}")


class ProviderRegistryEnhanced(ProviderRegistry):
    """Enhanced provider registry with configuration management."""
    
    def __init__(self):
        super().__init__()
        self._configs: Dict[str, ProviderConfigModel] = {}
        self._initialized_adapters: Dict[str, ProviderInterface] = {}
        self._setup_default_providers()
    
    def _setup_default_providers(self):
        """Setup the default providers from existing system."""
        # Gemini
        self._configs["gemini"] = ProviderConfigModel(
            provider_id="gemini",
            display_name="Gemini",
            adapter_class=GeminiProviderAdapter,
            api_key_env="GEMINI_API_KEY",
            priority=10,
            default_model="gemini-3.7-flash",
            capabilities=["text-generation"],
            adapter_kwargs=None
        )
        
        # Groq
        self._configs["groq"] = ProviderConfigModel(
            provider_id="groq",
            display_name="Groq",
            adapter_class=GroqProviderAdapter,
            api_key_env="GROQ_API_KEY",
            priority=20,
            default_model="openai/gpt-oss-20b",
            capabilities=["text-generation"],
            adapter_kwargs=None
        )
        
        # OpenRouter
        self._configs["openrouter"] = ProviderConfigModel(
            provider_id="openrouter",
            display_name="OpenRouter",
            adapter_class=OpenRouterProviderAdapter,
            api_key_env="OPENROUTER_API_KEY",
            priority=30,
            default_model="openrouter/free",
            capabilities=["text-generation"],
            adapter_kwargs=None
        )
        
        # Local
        self._configs["local"] = ProviderConfigModel(
            provider_id="local",
            display_name="Local",
            adapter_class=LocalProviderAdapter,
            api_key_env=None,  # No API key needed
            priority=40,
            default_model="local",
            capabilities=["text-generation"],
            adapter_kwargs=None
        )
    
    def register_from_config(self, provider_id: str) -> bool:
        """Register a provider from its configuration."""
        if provider_id not in self._configs:
            raise ValueError(f"Unknown provider: {provider_id}")

        config = self._configs[provider_id]

        # Check if already registered
        if provider_id in self._providers:
            return True  # Already registered

        # Check if configured
        if not config.is_configured():
            # Provider is not configured (missing API key) - don't register
            return False

        # Check if enabled
        if not config.enabled:
            # Provider is disabled - don't register
            return False

        try:
            # Create and register adapter
            adapter = config.create_adapter()
            self.register(adapter)
            self._initialized_adapters[provider_id] = adapter
            return True
        except Exception as e:
            print(f"[ProviderRegistry] Failed to register {provider_id}: {e}")
            return False
    
    def register_all_configured(self) -> Dict[str, bool]:
        """Register all providers that are properly configured."""
        results = {}
        for provider_id in self._configs:
            results[provider_id] = self.register_from_config(provider_id)
        return results
    
    def get_config(self, provider_id: str) -> Optional[ProviderConfigModel]:
        """Get configuration for a provider."""
        return self._configs.get(provider_id)
    
    def list_configs(self) -> List[Dict[str, Any]]:
        """List all provider configurations."""
        return [
            {
                "provider_id": config.provider_id,
                "display_name": config.display_name,
                "enabled": config.enabled,
                "priority": config.priority,
                "default_model": config.default_model,
                "capabilities": config.capabilities,
                "is_configured": config.is_configured(),
                "is_registered": provider_id in self._providers
            }
            for provider_id, config in self._configs.items()
        ]
    
    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider IDs."""
        return [
            provider_id for provider_id, config in self._configs.items()
            if config.enabled and config.is_configured()
        ]
    
    def get_provider_priority_list(self) -> List[str]:
        """Get providers sorted by priority (lower number = higher priority)."""
        enabled = self.get_enabled_providers()
        return sorted(
            enabled,
            key=lambda pid: self._configs[pid].priority if pid in self._configs else 999
        )
    
    def is_provider_available(self, provider_id: str) -> bool:
        """Check if a provider is available (configured, enabled, and working)."""
        if provider_id not in self._configs:
            return False

        config = self._configs[provider_id]
        if not config.enabled or not config.is_configured():
            return False

        # Check if registered and working
        if provider_id not in self._providers:
            # Not registered, so not available
            return False

        # Check if the registered provider is actually available
        provider = self.get(provider_id)
        if provider:
            return provider.is_available()

        return False
    
    def update_provider_config(self, provider_id: str, **kwargs):
        """Update provider configuration."""
        if provider_id not in self._configs:
            raise ValueError(f"Unknown provider: {provider_id}")
        
        config = self._configs[provider_id]
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                raise ValueError(f"Unknown configuration key: {key}")
        
        # If provider was registered, we need to re-register with new config
        if provider_id in self._providers:
            # Unregister and re-register
            self.unregister(provider_id)
            if provider_id in self._initialized_adapters:
                del self._initialized_adapters[provider_id]
            # Re-register if still configured
            if config.is_configured():
                self.register_from_config(provider_id)


def create_provider_registry() -> ProviderRegistryEnhanced:
    """Factory function to create a provider registry."""
    return ProviderRegistryEnhanced()


# Global instance
_provider_registry: Optional[ProviderRegistryEnhanced] = None


def get_provider_registry() -> ProviderRegistryEnhanced:
    """Get or create the global provider registry."""
    global _provider_registry
    if _provider_registry is None:
        _provider_registry = create_provider_registry()
    return _provider_registry


def initialize_providers() -> Dict[str, bool]:
    """Initialize all configured providers."""
    registry = get_provider_registry()
    return registry.register_all_configured()