"""Abstract base provider interfaces for STT, LLM, and TTS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """A single turn in an LLM conversation."""

    role: str  # "system" | "user" | "assistant"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Base exception for voice and model providers."""


class STTProvider(ABC):
    """Abstract interface for Speech-to-Text providers."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Transcribe raw 16-bit mono PCM audio bytes into text."""

    async def transcribe_stream(
        self, audio_stream: AsyncIterable[bytes], sample_rate: int = 16000
    ) -> AsyncIterator[str]:
        """Stream partial/final transcriptions from an incoming audio stream.

        Default fallback buffers the stream and yields the single final transcript.
        """
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)
        if chunks:
            full_audio = b"".join(chunks)
            text = await self.transcribe(full_audio, sample_rate=sample_rate)
            if text:
                yield text


class LLMProvider(ABC):
    """Abstract interface for Language Model providers."""

    @abstractmethod
    async def generate_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a complete text response from conversation messages."""

    @abstractmethod
    async def stream_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream text response tokens from conversation messages."""


class TTSProvider(ABC):
    """Abstract interface for Text-to-Speech providers."""

    @abstractmethod
    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text into a stream of raw 16-bit mono PCM audio chunks."""
