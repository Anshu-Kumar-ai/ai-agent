"""Provider configuration and API key management for Stage 13.

Manages API key loading, validation, and provider availability.
"""

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv


class ProviderType(Enum):
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    LOCAL = "local"


@dataclass
class ProviderConfig:
    """Configuration for a single provider."""
    type: ProviderType
    name: str
    api_key_env: str
    base_url: str
    model_name: str
    enabled: bool = False
    api_key: str | None = None

    def check_api_key(self) -> bool:
        """Check if API key is available and valid."""
        if self.api_key_env:
            key = os.getenv(self.api_key_env)
            if key:
                self.api_key = key
                self.enabled = True
                return True
        self.enabled = False
        return False


class ProviderManager:
    """Manages all provider configurations and availability."""

    def __init__(self, env_file: str | None = None):
        # Load environment variables
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to find .env file using absolute project path
            project_root = Path(__file__).parent.parent.parent
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)
            else:
                # Fallback to relative paths
                for path in [".env", "../.env", "../../.env"]:
                    if Path(path).exists():
                        load_dotenv(path)
                        break

        self.providers: dict[ProviderType, ProviderConfig] = {
            ProviderType.GEMINI: ProviderConfig(
                type=ProviderType.GEMINI,
                name="Gemini",
                api_key_env="GEMINI_API_KEY",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model_name="gemini-3.7-flash",
            ),
            ProviderType.GROQ: ProviderConfig(
                type=ProviderType.GROQ,
                name="Groq",
                api_key_env="GROQ_API_KEY",
                base_url="https://api.groq.com/openai/v1",
                model_name="openai/gpt-oss-20b",
            ),
            ProviderType.OPENROUTER: ProviderConfig(
                type=ProviderType.OPENROUTER,
                name="OpenRouter",
                api_key_env="OPENROUTER_API_KEY",
                base_url="https://openrouter.ai/api/v1",
                model_name="openrouter/free",
            ),
            ProviderType.LOCAL: ProviderConfig(
                type=ProviderType.LOCAL,
                name="Local",
                api_key_env=None,  # No API key needed
                base_url="",
                model_name="local",
            ),
        }

        # Check all providers
        self._check_all_providers()

    def _check_all_providers(self) -> None:
        """Check API keys for all providers."""
        for provider_type, config in self.providers.items():
            if provider_type != ProviderType.LOCAL:
                config.check_api_key()
                if config.enabled:
                    print(f"[ProviderManager] {config.name}: API key found ✓")
                else:
                    print(f"[ProviderManager] {config.name}: No API key (using fallback)")
            else:
                config.enabled = True
                print(f"[ProviderManager] {config.name}: Always available ✓")

    def get_available_providers(self) -> list[ProviderType]:
        """Get list of available providers (with API keys)."""
        available = []
        for provider_type, config in self.providers.items():
            if config.enabled:
                available.append(provider_type)
        return available

    def get_config(self, provider_type: ProviderType) -> ProviderConfig | None:
        """Get configuration for a specific provider."""
        return self.providers.get(provider_type)

    def get_priority_list(self, profile: str = "general") -> list[ProviderType]:
        """Get provider priority list for a profile, filtering to available providers."""
        # Priority profiles from SmartRouter
        priority_profiles = {
            "general": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "coding": [ProviderType.GROQ, ProviderType.GEMINI, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "reasoning": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "creative": [ProviderType.GEMINI, ProviderType.OPENROUTER, ProviderType.GROQ, ProviderType.LOCAL],
            "local": [ProviderType.LOCAL],
        }

        full_list = priority_profiles.get(profile, priority_profiles["general"])
        available = self.get_available_providers()

        # Filter to only available providers
        return [p for p in full_list if p in available]

    def is_available(self, provider_type: ProviderType) -> bool:
        """Check if a specific provider is available."""
        config = self.providers.get(provider_type)
        return config is not None and config.enabled

    def print_status(self) -> None:
        """Print status of all providers."""
        print("\n=== Provider Status ===")
        for provider_type, config in self.providers.items():
            status = "✓ ENABLED" if config.enabled else "✗ DISABLED"
            key_status = "KEY FOUND" if config.api_key else ("N/A" if provider_type == ProviderType.LOCAL else "MISSING")
            print(f"  {config.name:12} [{status}] ({key_status})")
        print()


# Global provider manager instance
_provider_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    """Get or create the global provider manager."""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager


def reload_providers() -> ProviderManager:
    """Reload provider configurations (e.g., after .env changes)."""
    global _provider_manager
    _provider_manager = ProviderManager()
    return _provider_manager
