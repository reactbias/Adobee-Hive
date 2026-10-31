"""Thin wrapper around the Claude API for structured-JSON calls.

Every call uses server-side refusal fallbacks (beta) unless CLAUDE_FALLBACKS=off,
and checks stop_reason before reading the content.
"""

import json
import logging
from typing import Any

import anthropic

from . import config

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None
_fallbacks_ok = config.CLAUDE_FALLBACKS != "off"


class LLMError(RuntimeError):
    """Claude returned nothing usable (refusal, no text, or invalid structured output)."""


def client() -> anthropic.Anthropic:
    """Return the shared Anthropic client, created on first use."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# Server-side refusal fallbacks exist for these models only (not Haiku).
_FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5", "claude-sonnet-5-5")


def supports_fallbacks(model: str) -> bool:
    """Tell whether server-side model fallbacks can be requested for this model."""
    return _fallbacks_ok and model.startswith(_FALLBACK_MODELS)


def _create(**kwargs: Any):
    global _fallbacks_ok
    if supports_fallbacks(kwargs["model"]):
        try:
            return client().beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks=config.CLAUDE_FALLBACKS, **kwargs
            )
        except anthropic.BadRequestError as err:
            if "fallback" not in str(err).lower():
                raise
            log.warning("Refusal fallbacks rejected, continuing without them: %s", err)
            _fallbacks_ok = False
    return client().beta.messages.create(**kwargs)


def _text(response) -> str:
    if response.stop_reason == "refusal":
        raise LLMError("Claude declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMError("Claude's answer was cut off (max_tokens).")
    return "".join(b.text for b in response.content if b.type == "text")


def structured(
    system: str,
    user: str | list,
    schema: dict[str, Any],
    *,
    effort: str = "low",
    max_tokens: int = 8000,
    model: str | None = None,
) -> dict[str, Any]:
    """Ask Claude for JSON matching `schema` (structured outputs) and return it parsed."""
    response = _create(
        model=model or config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    return json.loads(_text(response))
