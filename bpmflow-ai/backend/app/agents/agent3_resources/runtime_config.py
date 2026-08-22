"""Agent 3-local runtime configuration and OpenAI client lifecycle management."""

from dataclasses import dataclass
import inspect
import logging
import os
from typing import Optional, Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Agent3LLMConfig:
    """Agent 3-local runtime LLM configuration.

    API Key is stored securely and excluded from standard __repr__ and string conversions.
    """
    enabled: bool = False
    model: str = "gpt-4o-mini"
    timeout_seconds: float = 5.0
    max_output_tokens: int = 500
    temperature: Optional[float] = None
    api_key: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"Agent3LLMConfig(enabled={self.enabled}, model={self.model!r}, "
            f"timeout_seconds={self.timeout_seconds}, max_output_tokens={self.max_output_tokens}, "
            f"temperature={self.temperature}, api_key='[REDACTED]')"
        )


def _parse_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None or val.strip() == "":
        return default
    s = val.strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"Invalid boolean environment variable value: {val!r}")


def get_agent3_llm_config() -> Agent3LLMConfig:
    """Read Agent 3 LLM configuration lazily from environment variables.

    Environment Variables:
    - AGENT3_LLM_EXPLANATIONS_ENABLED (default: False)
    - AGENT3_LLM_MODEL (default: "gpt-4o-mini")
    - AGENT3_LLM_TIMEOUT_SECONDS (default: 5.0)
    - AGENT3_LLM_MAX_OUTPUT_TOKENS (default: 500)
    - AGENT3_LLM_TEMPERATURE (default: None)
    - OPENAI_API_KEY (default: "")
    """
    enabled_str = os.getenv("AGENT3_LLM_EXPLANATIONS_ENABLED")
    enabled = _parse_bool(enabled_str, default=False)

    model = os.getenv("AGENT3_LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    timeout_str = os.getenv("AGENT3_LLM_TIMEOUT_SECONDS")
    timeout_seconds = 5.0
    if timeout_str and timeout_str.strip():
        try:
            timeout_seconds = float(timeout_str.strip())
            if timeout_seconds <= 0 or timeout_seconds > 120.0:
                raise ValueError("Timeout out of bounds")
        except Exception:
            raise ValueError("Invalid AGENT3_LLM_TIMEOUT_SECONDS value")

    tokens_str = os.getenv("AGENT3_LLM_MAX_OUTPUT_TOKENS")
    max_output_tokens = 500
    if tokens_str and tokens_str.strip():
        try:
            max_output_tokens = int(tokens_str.strip())
            if max_output_tokens <= 0 or max_output_tokens > 4096:
                raise ValueError("Max output tokens out of bounds")
        except Exception:
            raise ValueError("Invalid AGENT3_LLM_MAX_OUTPUT_TOKENS value")

    temp_str = os.getenv("AGENT3_LLM_TEMPERATURE")
    temperature: Optional[float] = None
    if temp_str and temp_str.strip():
        try:
            temperature = float(temp_str.strip())
            if temperature < 0.0 or temperature > 2.0:
                raise ValueError("Temperature out of bounds")
        except Exception:
            raise ValueError("Invalid AGENT3_LLM_TEMPERATURE value")

    api_key_env = os.getenv("OPENAI_API_KEY")
    api_key = api_key_env.strip() if api_key_env and api_key_env.strip() else None

    return Agent3LLMConfig(
        enabled=enabled,
        model=model,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        api_key=api_key,
    )


# Shared LLM runtime client lifecycle state
_shared_openai_client: Optional[Any] = None
_client_factory: Optional[Any] = None  # Hook for test injection
_client_close_count: int = 0


def set_openai_client_factory(factory: Optional[Any]) -> None:
    """Set custom client factory for testing."""
    global _client_factory
    _client_factory = factory


def get_shared_openai_client(config: Optional[Agent3LLMConfig] = None) -> Optional[Any]:
    """Get or create the single shared AsyncOpenAI client per application lifespan.

    Returns None if feature is disabled, or if API key is missing/invalid.
    No client is instantiated when feature is disabled.
    """
    global _shared_openai_client, _client_factory

    if config is None:
        try:
            config = get_agent3_llm_config()
        except Exception:
            return None

    if not config.enabled:
        return None

    if not config.api_key:
        return None

    if _shared_openai_client is None:
        if _client_factory is not None:
            _shared_openai_client = _client_factory(config)
        else:
            from openai import AsyncOpenAI
            _shared_openai_client = AsyncOpenAI(api_key=config.api_key)

    return _shared_openai_client


async def close_agent3_llm_runtime() -> None:
    """Close the shared AsyncOpenAI client during application shutdown.

    Safe to call repeatedly (idempotent).
    """
    global _shared_openai_client, _client_close_count
    if _shared_openai_client is not None:
        client = _shared_openai_client
        _shared_openai_client = None
        _client_close_count += 1
        if hasattr(client, "close") and callable(client.close):
            res = client.close()
            if inspect.isawaitable(res):
                await res


def reset_agent3_llm_runtime() -> None:
    """Reset internal runtime state for test cleanups."""
    global _shared_openai_client, _client_factory, _client_close_count
    _shared_openai_client = None
    _client_factory = None
    _client_close_count = 0
