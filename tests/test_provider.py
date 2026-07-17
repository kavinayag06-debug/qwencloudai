"""Tests for LLM provider abstraction."""

import os
import pytest
import pytest_asyncio
from pathlib import Path

# Force mock mode
os.environ["LLM_PROVIDER"] = "mock"
os.environ["VISION_PROVIDER"] = "mock"

from app.core.llm_provider import (
    get_llm_provider,
    get_vision_provider,
    llm_unconfigured_reason,
    MockProvider,
    OpenAICompatibleProvider,
    LLMResponse,
)


def test_mock_provider_creation():
    """Mock provider is returned when LLM_PROVIDER=mock."""
    import app.config as config_module
    config_module._settings = None
    provider = get_llm_provider("mock")
    assert isinstance(provider, MockProvider)
    config_module._settings = None


def test_openai_provider_creation():
    """OpenAI-compatible provider is returned for openai/qwen/openrouter."""
    provider = get_llm_provider("openai", "gpt-4o", "test-key", "https://api.openai.com/v1")
    assert isinstance(provider, OpenAICompatibleProvider)


def test_qwen_provider_creation():
    """Qwen uses the same OpenAI-compatible provider."""
    provider = get_llm_provider("qwen", "qwen-max", "test-key", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    assert isinstance(provider, OpenAICompatibleProvider)


@pytest.mark.asyncio
async def test_mock_complete():
    """Mock provider returns valid response."""
    provider = MockProvider()
    response = await provider.complete(
        messages=[{"role": "user", "content": "test"}],
    )
    assert isinstance(response, LLMResponse)
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_mock_complete_json_mode():
    """Mock provider returns parseable JSON in json_mode."""
    provider = MockProvider()
    response = await provider.complete(
        messages=[{"role": "user", "content": "test"}],
        json_mode=True,
    )
    data = response.as_json()
    assert isinstance(data, dict)
    assert "score" in data


@pytest.mark.asyncio
async def test_mock_vision():
    """Mock vision returns style traits."""
    provider = MockProvider()
    response = await provider.vision(
        prompt="Analyze this design",
        image_paths=[],
    )
    data = response.as_json()
    assert "style_traits" in data
    assert "color_palette" in data["style_traits"]


def test_vision_provider_factory():
    """Vision provider factory returns mock in test mode."""
    import app.config as config_module
    config_module._settings = None
    provider = get_vision_provider()
    assert isinstance(provider, MockProvider)
    config_module._settings = None


def test_llm_response_as_json():
    """LLMResponse.as_json() parses JSON content."""
    resp = LLMResponse(content='{"key": "value"}')
    assert resp.as_json() == {"key": "value"}


def test_llm_response_as_json_with_code_block():
    """LLMResponse handles JSON wrapped in markdown code blocks."""
    resp = LLMResponse(content='```json\n{"key": "value"}\n```')
    assert resp.as_json() == {"key": "value"}


def test_provider_switching_by_env():
    """Provider type is determined by environment variable."""
    import app.config as config_module
    config_module._settings = None
    os.environ["LLM_PROVIDER"] = "mock"
    provider = get_llm_provider()
    assert isinstance(provider, MockProvider)
    config_module._settings = None


def test_unconfigured_reason_for_mock_provider(monkeypatch):
    """Mock mode is reported as 'no real AI' with fix instructions."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    reason = llm_unconfigured_reason()
    assert reason is not None
    assert "mock" in reason
    assert "LLM_API_KEY" in reason


def test_unconfigured_reason_for_placeholder_key(monkeypatch):
    """A real provider with the .env.example placeholder key counts as unconfigured."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "your-api-key-here")
    reason = llm_unconfigured_reason()
    assert reason is not None
    assert "LLM_API_KEY" in reason


def test_unconfigured_reason_for_blank_key(monkeypatch):
    """A real provider with a blank key counts as unconfigured."""
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("LLM_API_KEY", "")
    reason = llm_unconfigured_reason()
    assert reason is not None


def test_unconfigured_reason_none_when_configured(monkeypatch):
    """A real provider with a real-looking key is considered configured."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "sk-real-key")
    assert llm_unconfigured_reason() is None
