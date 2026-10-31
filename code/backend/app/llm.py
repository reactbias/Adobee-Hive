"""Thin wrapper around the model APIs (OpenAI or Claude, per LLM_PROVIDER) for structured-JSON calls.

Claude calls use server-side refusal fallbacks (beta) unless CLAUDE_FALLBACKS=off, and check stop_reason before
reading the content. OpenAI calls use structured outputs and store nothing at OpenAI.
"""

import json
import logging
from typing import Any

import anthropic
import openai

from . import config

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None
_fallbacks_ok = config.CLAUDE_FALLBACKS != "off"


class LLMError(RuntimeError):
    """The model returned nothing usable (refusal, no text, or invalid structured output)."""


# What callers catch to fall back to the offline path: any vendor error or an unusable answer.
FAILURES = (LLMError, anthropic.APIError, openai.OpenAIError, json.JSONDecodeError)


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
    """Ask the configured model for JSON matching `schema` (structured outputs) and return it parsed."""
    if config.LLM_PROVIDER == "openai":
        return _structured_openai(system, user, schema, max_tokens)
    response = _create(
        model=model or config.CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    return json.loads(_text(response))


_openai: openai.OpenAI | None = None


def _structured_openai(system: str, user: str | list, schema: dict[str, Any], max_tokens: int) -> dict[str, Any]:
    global _openai
    if _openai is None:
        _openai = openai.OpenAI(api_key=config.OPENAI_API_KEY)
    response = _openai.responses.create(
        model=config.OPENAI_MODEL,
        instructions=system,
        input=user if isinstance(user, str) else json.dumps(user),
        text={"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}},
        reasoning={"effort": "low"},
        max_output_tokens=max_tokens,
        store=False,
    )
    if response.status != "completed" or not response.output_text:
        raise LLMError(f"OpenAI returned no usable answer ({response.status}).")
    return json.loads(response.output_text)
