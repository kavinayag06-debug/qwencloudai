"""
LLM Provider Abstraction Layer.

All model calls go through this single interface.
Switch providers by changing .env only - no code changes needed.

Supported providers: openai, qwen, openrouter, mock

WE ARE USING QWEN3.7-MAX FOR "LLM PROVIDER" AND QWEN3-VL-PLUS FOR "VISION PROVIDER" (lines 150-180)

"""

import json
import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# API key values that mean "not actually configured": blank, or the committed
# .env.example placeholder copied verbatim into a machine-local .env.
PLACEHOLDER_API_KEYS = {"", "your-api-key-here"}


def _provider_unconfigured_reason(kind: str, provider: str, api_key: str) -> Optional[str]:
    """Shared check behind llm_unconfigured_reason/vision_unconfigured_reason.

    Mock mode is a legitimate setup for tests, but its output is canned text, so it
    still counts as "no real AI" for callers deciding whether to warn the operator.
    """
    if provider == "mock":
        return (
            f"{kind}_PROVIDER is 'mock' — all {kind.lower()} output is canned test text, not real AI. "
            f"Set {kind}_PROVIDER and {kind}_API_KEY in .env to use a real provider."
        )
    if api_key.strip() in PLACEHOLDER_API_KEYS:
        return (
            f"{kind}_PROVIDER is '{provider}' but {kind}_API_KEY is blank or the "
            "'your-api-key-here' placeholder — calls will fail. "
            f"Set a real {kind}_API_KEY in .env."
        )
    return None


def llm_unconfigured_reason() -> Optional[str]:
    """Why the configured text LLM cannot produce real AI output, or None if it looks usable."""
    settings = get_settings()
    return _provider_unconfigured_reason("LLM", settings.llm_provider, settings.llm_api_key)


def vision_unconfigured_reason() -> Optional[str]:
    """Why the configured vision model cannot produce real AI output, or None if it looks usable.

    Separate from llm_unconfigured_reason() because VISION_PROVIDER/VISION_API_KEY are
    configured independently — a real LLM_PROVIDER doesn't imply vision is usable, and
    steps that actually call get_vision_provider() (HTML build/critique) need this check.
    """
    settings = get_settings()
    return _provider_unconfigured_reason("VISION", settings.vision_provider, settings.vision_api_key)


class LLMResponse:
    """Standardized response from any LLM provider."""

    def __init__(self, content: str, usage: Optional[dict] = None, raw: Optional[dict] = None):
        self.content = content
        self.usage = usage or {}
        self.raw = raw or {}

    def as_json(self) -> dict:
        """Parse content as JSON, tolerating code fences and leading/trailing prose.

        Always returns a dict: every current call site expects one, and some models
        occasionally wrap the object in a top-level JSON array — normalize that here
        once instead of every caller re-implementing the same guard.
        """
        content = self.content.strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Find the first '{' or '[' and decode from there, ignoring anything
            # before or after (models often wrap JSON in ```fences``` and commentary).
            start = next((i for i, ch in enumerate(content) if ch in "{["), None)
            if start is None:
                raise json.JSONDecodeError("No JSON object found", content, 0)
            parsed, _ = json.JSONDecoder().raw_decode(content, start)

        if isinstance(parsed, list):
            parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else {}
        if not isinstance(parsed, dict):
            parsed = {}
        return parsed


def build_image_content_parts(image_paths: list[Path]) -> list[dict]:
    """Build OpenAI-style image_url content parts from local file paths.

    Shared by any call site that needs to attach real reference images to a
    chat completion (not just the vision() path) — e.g. HTML generation and
    critique steps that need to see the actual design references, not a text
    paraphrase of them.
    """
    parts = []
    for img_path in image_paths:
        img_data = img_path.read_bytes()
        b64 = base64.b64encode(img_data).decode("utf-8")
        suffix = img_path.suffix.lower().lstrip(".")
        mime = "image/jpeg" if suffix in ("jpg", "jpeg") else (f"image/{suffix}" if suffix in ("png", "gif", "webp") else "image/png")
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        })
    return parts


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(self, messages: list[dict], temperature: float = 0.7,
                       max_tokens: int = 4096, json_mode: bool = False) -> LLMResponse:
        """Send a chat completion request."""
        ...

    @abstractmethod
    async def vision(self, prompt: str, image_paths: list[Path],
                     temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse:
        """Send a vision request with images."""
        ...


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for OpenAI-compatible APIs (OpenAI, Qwen, OpenRouter)."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)

    async def complete(self, messages: list[dict], temperature: float = 0.7,
                       max_tokens: int = 4096, json_mode: bool = False) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # Qwen's hybrid-thinking models (qwen3.6-*, qwen3.7-*, etc.) generate a
        # hidden chain-of-thought before every visible answer unless told not to.
        # This is the single biggest source of extra latency on DashScope.
        # We don't need reasoning traces for HTML generation/scoring, so turn it
        # off. Harmless no-op on OpenAI/OpenRouter, which ignore unknown fields.
        if "qwen" in self.model.lower():
            payload["enable_thinking"] = False

        url = f"{self.base_url}/chat/completions"
        logger.info(f"LLM request to {url} model={self.model}")

        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(content=content, usage=usage, raw=data)

    async def vision(self, prompt: str, image_paths: list[Path],
                     temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse:
        content_parts = [{"type": "text", "text": prompt}]

        for img_path in image_paths:
            img_data = img_path.read_bytes()
            b64 = base64.b64encode(img_data).decode("utf-8")
            suffix = img_path.suffix.lower().lstrip(".")
            mime = "image/jpeg" if suffix in ("jpg", "jpeg") else (f"image/{suffix}" if suffix in ("png", "gif", "webp") else "image/png")
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"}
            })

        messages = [{"role": "user", "content": content_parts}]
        return await self.complete(messages, temperature=temperature, max_tokens=max_tokens)


class MockProvider(BaseLLMProvider):
    """Mock provider for testing without API keys."""

    async def complete(self, messages: list[dict], temperature: float = 0.7,
                       max_tokens: int = 4096, json_mode: bool = False) -> LLMResponse:
        last_msg = messages[-1]["content"] if messages else ""
        logger.info(f"MockProvider.complete called with {len(messages)} messages")

        if json_mode:
            content = json.dumps({
                "response": "mock response",
                "analysis": "This is a mock analysis for testing.",
                "score": 75,
                "recommendations": ["Improve layout", "Add mobile responsiveness"]
            })
        else:
            content = (
                "This is a mock LLM response for testing purposes. "
                "The system is working correctly in mock mode. "
                "Switch LLM_PROVIDER in .env to use a real provider."
            )
        return LLMResponse(content=content, usage={"total_tokens": 50})

    async def vision(self, prompt: str, image_paths: list[Path],
                     temperature: float = 0.7, max_tokens: int = 4096) -> LLMResponse:
        logger.info(f"MockProvider.vision called with {len(image_paths)} images")
        content = json.dumps({
            "style_traits": {
                "color_palette": ["#2C3E50", "#ECF0F1", "#3498DB", "#E74C3C"],
                "typography": "modern sans-serif",
                "layout_style": "clean minimalist",
                "mood": "professional and approachable",
                "industry_fit": ["retail", "services", "food"],
            },
            "design_patterns": ["hero section", "grid cards", "sticky nav", "CTA buttons"],
            "quality_score": 82,
        })
        return LLMResponse(content=content, usage={"total_tokens": 80})


def get_llm_provider(provider_type: str = None, model: str = None,
                     api_key: str = None, base_url: str = None) -> BaseLLMProvider:
    """Factory function to get the configured LLM provider."""
    settings = get_settings()

    provider_type = provider_type or settings.llm_provider
    model = model or settings.llm_model
    api_key = api_key or settings.llm_api_key
    base_url = base_url or settings.llm_base_url

    if provider_type == "mock":
        return MockProvider()

    # openai, qwen, openrouter all use OpenAI-compatible API
    return OpenAICompatibleProvider(api_key=api_key, base_url=base_url, model=model)


def get_vision_provider() -> BaseLLMProvider:
    """Factory function to get the configured vision provider."""
    settings = get_settings()

    if settings.vision_provider == "mock":
        return MockProvider()

    return OpenAICompatibleProvider(
        api_key=settings.vision_api_key,
        base_url=settings.vision_base_url,
        model=settings.vision_model,
    )
