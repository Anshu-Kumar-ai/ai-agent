import json
import time
from pathlib import Path

from app.core.gateway import ModelGateway
from app.core.providers import ProviderType, get_provider_manager


class SmartRouter:
    def __init__(self, provider_manager=None):
        self.provider_manager = provider_manager or get_provider_manager()
        self.gateway = ModelGateway(provider_manager=self.provider_manager)

        self.priority_profiles = {
            "general": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "coding": [ProviderType.GROQ, ProviderType.GEMINI, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "reasoning": [ProviderType.GEMINI, ProviderType.GROQ, ProviderType.OPENROUTER, ProviderType.LOCAL],
            "creative": [ProviderType.GEMINI, ProviderType.OPENROUTER, ProviderType.GROQ, ProviderType.LOCAL],
            "local": [ProviderType.LOCAL],
        }

        self.keyword_profiles = {
            "coding": {
                "code", "python", "javascript", "typescript", "java",
                "program", "programming", "function", "debug",
                "debugging", "bug", "sql", "api", "class",
                "compile", "compiler", "exception",
            },
            "reasoning": {
                "analyze", "analysis", "compare", "comparison",
                "reason", "reasoning", "logic", "calculate",
                "prove", "derive", "solve", "evaluate", "algorithm",
                "algorithms", "efficient", "efficiency", "complexity",
                "tradeoff",
            },
            "creative": {
                "story", "poem", "poetry", "creative", "fiction",
                "script", "brainstorm", "rewrite",
            },
            "local": {
                "offline", "local", "private", "without internet",
                "no internet",
            },
        }

        self.cooldowns = {}
        self.cooldown_seconds = 30

        self.stats_path = Path("data/provider_stats.json")
        self.stats_path.parent.mkdir(parents=True, exist_ok=True)

        self.stats = self._load_stats()

    def _default_stats(self) -> dict:
        return {
            provider.value: {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "total_latency": 0.0,
                "health_ema": 0.5,
                "latency_ema": 0.0,
            }
            for provider in ProviderType
        }

    def _load_stats(self) -> dict:
        if not self.stats_path.exists():
            return self._default_stats()

        try:
            data = json.loads(
                self.stats_path.read_text(encoding="utf-8")
            )

            defaults = self._default_stats()

            for provider in defaults:
                if provider not in data:
                    data[provider] = defaults[provider]
                for key in defaults[provider]:
                    if key not in data[provider]:
                        data[provider][key] = defaults[provider][key]

            return data

        except (json.JSONDecodeError, OSError):
            print("[Router] Could not load saved stats. Starting fresh.")
            return self._default_stats()

    def _save_stats(self) -> None:
        try:
            self.stats_path.write_text(
                json.dumps(self.stats, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            print(f"[Router] Could not save stats: {error}")

    def _classify(self, message: str) -> str:
        text = message.lower()

        if any(
            keyword in text
            for keyword in self.keyword_profiles["local"]
        ):
            return "local"

        strong_reasoning = {
            "compare",
            "comparison",
            "analyze",
            "analysis",
            "reasoning",
            "logic",
            "evaluate",
            "tradeoff",
            "efficiency",
            "complexity",
        }

        if any(keyword in text for keyword in strong_reasoning):
            return "reasoning"

        scores = {
            "coding": 0,
            "reasoning": 0,
            "creative": 0,
        }

        for profile in scores:
            for keyword in self.keyword_profiles[profile]:
                if keyword in text:
                    scores[profile] += 1

        best_profile = max(scores, key=scores.get)

        if scores[best_profile] == 0:
            return "general"

        return best_profile

    def _is_available(self, provider: str) -> bool:
        """Check if provider is available (has API key and not in cooldown)."""
        # First check if provider has API key configured
        try:
            provider_type = ProviderType(provider)
            if not self.provider_manager.is_available(provider_type):
                return False
        except ValueError:
            pass

        # Then check cooldown
        cooldown_until = self.cooldowns.get(provider)

        if cooldown_until is None:
            return True

        if time.monotonic() >= cooldown_until:
            del self.cooldowns[provider]
            print(f"[Router] Cooldown expired: {provider}")
            return True

        return False

    def _mark_failed(self, provider: str) -> None:
        self.cooldowns[provider] = (
            time.monotonic() + self.cooldown_seconds
        )

    def _record_success(self, provider: str, latency: float) -> None:
        stats = self.stats[provider]

        stats["requests"] += 1
        stats["successes"] += 1
        stats["total_latency"] += latency

        alpha = 0.30

        stats["health_ema"] = (
            (1.0 - alpha) * stats.get("health_ema", 0.5)
            + alpha * 1.0
        )

        previous_latency = stats.get("latency_ema", 0.0)

        if previous_latency == 0.0:
            stats["latency_ema"] = latency
        else:
            stats["latency_ema"] = (
                (1.0 - alpha) * previous_latency
                + alpha * latency
            )

        self._save_stats()

    def _record_failure(self, provider: str, latency: float) -> None:
        stats = self.stats[provider]

        stats["requests"] += 1
        stats["failures"] += 1
        stats["total_latency"] += latency

        alpha = 0.30

        stats["health_ema"] = (
            (1.0 - alpha) * stats.get("health_ema", 0.5)
            + alpha * 0.0
        )

        previous_latency = stats.get("latency_ema", 0.0)

        if previous_latency == 0.0:
            stats["latency_ema"] = latency
        else:
            stats["latency_ema"] = (
                (1.0 - alpha) * previous_latency
                + alpha * latency
            )

        self._save_stats()

    def get_stats(self) -> dict:
        result = {}

        for provider, stats in self.stats.items():
            requests = stats["requests"]

            result[provider] = {
                "requests": requests,
                "successes": stats["successes"],
                "failures": stats["failures"],
                "average_latency": (
                    stats["total_latency"] / requests
                    if requests
                    else 0.0
                ),
                "success_rate": (
                    stats["successes"] / requests
                    if requests
                    else 0.0
                ),
            }

        return result

    def get_health_scores(self) -> dict:
        scores = {}

        for provider, stats in self.stats.items():
            requests = stats.get("requests", 0)

            if requests == 0:
                scores[provider] = 50.0
                continue

            recent_health = stats.get("health_ema", 0.5)
            recent_latency = stats.get("latency_ema", 0.0)

            reliability_score = recent_health * 70.0

            latency_score = max(
                0.0,
                30.0 * (
                    1.0 - min(recent_latency / 5.0, 1.0)
                ),
            )

            scores[provider] = reliability_score + latency_score

        return scores

    def _select_priority(self, message: str) -> list[str]:
        profile = self._classify(message)
        base_priority = self.provider_manager.get_priority_list(profile)
        health = self.get_health_scores()

        task_scores = {
            provider: score
            for provider, score in zip(
                base_priority,
                [1.00, 0.85, 0.70, 0.55],
            )
        }

        scores = {}

        for provider in base_priority:
            task_score = task_scores[provider] * 50.0
            health_score = health.get(provider.value, 50.0) * 0.50

            scores[provider] = (
                task_score
                + health_score
            )

        return sorted(
            base_priority,
            key=lambda provider: scores[provider],
            reverse=True,
        )

    def ask(self, message: str, model_message: str | None = None) -> str:
        if not isinstance(message, str):
            raise TypeError("message must be a string")

        message = message.strip()

        if not message:
            raise ValueError("message cannot be empty")

        if model_message is None:
            model_message = message
        elif not isinstance(model_message, str):
            raise TypeError("model_message must be a string")

        model_message = model_message.strip()

        if not model_message:
            raise ValueError("model_message cannot be empty")

        # Classify based on the user's actual request, not the full prompt
        profile = self._classify(model_message)
        priority = self._select_priority(model_message)

        print(f"[Router] Task type: {profile}")
        print(
            f"[Router] Health-aware priority: "
            f"{' ? '.join(p.value for p in priority)}"
        )

        errors = []

        for provider in priority:
            if not self._is_available(provider.value):
                print(f"[Router] Skipping unavailable: {provider.value}")
                continue

            start = time.perf_counter()

            try:
                print(f"[Router] Trying: {provider.value}")

                response = self.gateway.ask(
                    provider.value,
                    model_message,
                )

                latency = time.perf_counter() - start
                self._record_success(provider.value, latency)

                print(
                    f"[Router] Success: {provider.value} "
                    f"({latency:.3f}s)"
                )

                self.cooldowns.pop(provider.value, None)

                return response

            except Exception as error:
                latency = time.perf_counter() - start
                self._record_failure(provider.value, latency)

                print(
                    f"[Router] Failed: {provider.value} "
                    f"({latency:.3f}s)"
                )

                self._mark_failed(provider.value)
                errors.append(f"{provider.value}: {error}")

        # Fall back to local if all providers failed
        if ProviderType.LOCAL not in priority:
            print("[Router] Falling back to local...")
            try:
                response = self.gateway.ask(ProviderType.LOCAL.value, model_message)
                return response
            except Exception as e:
                errors.append(f"local: {e}")

        raise RuntimeError(
            "All available AI providers failed:\n"
            + "\n".join(errors)
        )
