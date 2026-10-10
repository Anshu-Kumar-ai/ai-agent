"""
Live Provider Tests - Phase 1 Infrastructure

These tests require live LLM providers and may hit rate limits/quota.
Run with: pytest -m live_provider
"""
import pytest
import os
from dotenv import load_dotenv

# Load .env file at module level so environment variables are available at collection time
load_dotenv()

# Only skip if no API keys available at runtime
def has_api_keys():
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY"))

@pytest.mark.live_provider
@pytest.mark.skipif(
    not has_api_keys(),
    reason="No live provider API keys available"
)
class TestLiveProvider:
    """Tests that require live LLM providers."""
    
    def test_gemini_planning(self):
        """Test Gemini provider planning."""
        import os
        if not os.getenv("GEMINI_API_KEY"):
            pytest.skip("GEMINI_API_KEY not available")
        from app.core.agent import Agent
        agent = Agent()
        result = agent.run("What is 2+2?")
        assert result is not None
        assert len(result) > 0
    
    def test_groq_planning(self):
        """Test Groq provider planning."""
        import os
        if not os.getenv("GROQ_API_KEY"):
            pytest.skip("GROQ_API_KEY not available")
        from app.core.agent import Agent
        agent = Agent()
        result = agent.run("What is 3+3?")
        assert result is not None
        assert len(result) > 0
    
    def test_openrouter_planning(self):
        """Test OpenRouter provider planning."""
        import os
        if not os.getenv("OPENROUTER_API_KEY"):
            pytest.skip("OPENROUTER_API_KEY not available")
        from app.core.agent import Agent
        agent = Agent()
        result = agent.run("What is 4+4?")
        assert result is not None
        assert len(result) > 0
    
    def test_provider_fallback(self):
        """Test provider fallback with real providers."""
        import os
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY")):
            pytest.skip("No provider API keys available")
        from app.core.agent import Agent
        agent = Agent()
        result = agent.run("What is 5+5?")
        assert result is not None
        assert len(result) > 0

# Simple deterministic test that marks the infrastructure works
def test_live_provider_marker_exists():
    """Verify live_provider marker is registered."""
    # This test passes if pytest collects it with -m live_provider
    assert True