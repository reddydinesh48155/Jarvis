"""Ollama local LLM provider implementation."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings
from app.voice.providers.base import ChatMessage, LLMProvider, ProviderError

logger = logging.getLogger("nova.voice.providers.ollama")


class OllamaLLM(LLMProvider):
    """Local LLM provider calling an Ollama instance via HTTP."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [{"role": msg.role, "content": msg.content} for msg in messages]

    async def generate_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        url = f"{self.base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data.get("message", {}).get("content", "")).strip()
        except httpx.ConnectError as exc:
            logger.warning("failed to connect to Ollama at %s: %s", url, exc)
            raise ProviderError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.warning("timeout waiting for Ollama response from %s", url)
            raise ProviderError("Ollama request timed out.") from exc
        except Exception as exc:
            logger.exception("unexpected error calling Ollama")
            raise ProviderError(f"Ollama generation error: {exc}") from exc

    async def stream_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._format_messages(messages),
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        url = f"{self.base_url}/api/chat"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as exc:
            logger.warning("failed to connect to Ollama at %s: %s", url, exc)
            raise ProviderError(
                f"Cannot connect to Ollama at {self.base_url}. Ensure Ollama is running."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.warning("timeout during Ollama streaming from %s", url)
            raise ProviderError("Ollama stream timed out.") from exc
        except Exception as exc:
            logger.exception("unexpected error streaming from Ollama")
            raise ProviderError(f"Ollama streaming error: {exc}") from exc
