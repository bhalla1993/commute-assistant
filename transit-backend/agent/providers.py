"""
Multi-Provider AI Client
--------------------------
Supports Groq, OpenAI, and Gemini via their OpenAI-compatible APIs.

Fallback chain:
  - Primary provider is set by AI_PROVIDER env var (default: groq).
  - On RateLimitError (429), retries with exponential backoff.
  - If retries exhausted, automatically tries the next configured provider.
  - If all providers fail, raises the last exception.

Rate limit strategy:
  - RATE_LIMIT_RETRIES retries per provider before falling back.
  - Backoff starts at RATE_LIMIT_BACKOFF_BASE seconds, doubling each retry.
"""
import logging
import os
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

logger = logging.getLogger(__name__)

# Retries on a single provider before switching to the next
RATE_LIMIT_RETRIES = 1
# Initial backoff in seconds (doubles each retry)
RATE_LIMIT_BACKOFF_BASE = 2
# Per-call timeout passed to the OpenAI SDK
_CALL_TIMEOUT = 10.0


@dataclass
class _ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str


def _load_providers() -> list[_ProviderConfig]:
    """
    Build an ordered list of providers from environment variables.
    Primary provider (AI_PROVIDER) is first; others follow as fallbacks.
    Providers without a configured API key are skipped.
    """
    primary = os.getenv("AI_PROVIDER", "groq").lower()

    all_configs: dict[str, _ProviderConfig] = {
        "groq": _ProviderConfig(
            name="groq",
            # Backward-compat: fall back to OPENAI_API_KEY if GROQ_API_KEY not set
            api_key=os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            model=os.getenv("GROQ_MODEL") or os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile"),
        ),
        "openai": _ProviderConfig(
            name="openai",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        ),
        "gemini": _ProviderConfig(
            name="gemini",
            api_key=os.getenv("GEMINI_API_KEY", ""),
            base_url=os.getenv(
                "GEMINI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        ),
    }

    # Primary first, remaining providers as fallbacks
    order = [primary] + [k for k in ("groq", "openai", "gemini") if k != primary]
    return [
        all_configs[name]
        for name in order
        if name in all_configs and all_configs[name].api_key
    ]


def _make_client(config: _ProviderConfig) -> OpenAI:
    """Create an OpenAI-compatible client for the given provider config."""
    return OpenAI(api_key=config.api_key, base_url=config.base_url)


def get_completion(
    messages: list[dict],
    tools: list[dict],
    tool_choice: str = "auto",
    timeout: float = _CALL_TIMEOUT,
) -> object:
    """
    Call the chat completions API with automatic provider fallback.

    Tries each configured provider in order.  On RateLimitError, retries
    with exponential backoff before falling back to the next provider.

    Returns the raw response object (OpenAI-compatible).
    Raises APITimeoutError immediately (let the caller handle it).
    Raises the last RateLimitError if all providers are exhausted.
    """
    providers = _load_providers()

    if not providers:
        raise RuntimeError(
            "No AI provider configured. "
            "Set AI_PROVIDER and at least one of GROQ_API_KEY, OPENAI_API_KEY, "
            "or GEMINI_API_KEY in your .env file."
        )

    last_exc: Exception | None = None

    for provider in providers:
        client = _make_client(provider)
        backoff = RATE_LIMIT_BACKOFF_BASE

        for attempt in range(1 + RATE_LIMIT_RETRIES):
            try:
                logger.debug(
                    "[providers] %s model=%s attempt=%d",
                    provider.name,
                    provider.model,
                    attempt + 1,
                )
                response = client.chat.completions.create(
                    model=provider.model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    timeout=timeout,
                )
                if attempt > 0:
                    logger.info(
                        "[providers] Recovered on %s after %d retry(ies)",
                        provider.name,
                        attempt,
                    )
                return response

            except APIConnectionError as exc:
                # Provider is unreachable (network error, bad base URL, etc.)
                # No point retrying — skip to the next provider immediately.
                last_exc = exc
                logger.warning(
                    "[providers] Connection error on provider=%s — skipping. %s",
                    provider.name,
                    exc,
                )
                break  # next provider

            except RateLimitError as exc:
                last_exc = exc
                logger.warning(
                    "[providers] Rate limit hit — provider=%s attempt=%d/%d",
                    provider.name,
                    attempt + 1,
                    1 + RATE_LIMIT_RETRIES,
                )
                if attempt < RATE_LIMIT_RETRIES:
                    logger.info("[providers] Backing off %ds before retry…", backoff)
                    time.sleep(backoff)
                    backoff *= 2
                # Final attempt exhausted → break to next provider

            except APITimeoutError:
                # Bubble up immediately; agent.py maps this to AgentTimeoutError
                raise

        logger.warning(
            "[providers] Exhausted retries for provider=%s, trying next…",
            provider.name,
        )

    logger.error("[providers] All providers exhausted.")
    raise last_exc  # type: ignore[misc]
