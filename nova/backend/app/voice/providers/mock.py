"""Mock implementations of STT, LLM, and TTS providers for testing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.voice.providers.base import ChatMessage, LLMProvider, STTProvider, TTSProvider


class MockSTT(STTProvider):
    """Mock STT provider that returns a fixed transcription or canned responses."""

    def __init__(self, transcription: str = "Hello NOVA") -> None:
        self.transcription = transcription
        self.last_audio_len = 0

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        self.last_audio_len = len(audio_data)
        return self.transcription


class MockLLM(LLMProvider):
    """Mock LLM provider that returns canned responses or echoes messages."""

    def __init__(
        self,
        default_response: str = "This is a mock LLM response.",
        intent_responses: dict[str, str] | None = None,
    ) -> None:
        self.default_response = default_response
        self.intent_responses = intent_responses or {}
        self.recorded_messages: list[list[ChatMessage]] = []

    async def generate_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        self.recorded_messages.append(messages)
        last_message = messages[-1].content if messages else ""

        # Check if there is an exact or substring match in intent_responses
        for key, response in self.intent_responses.items():
            if key.lower() in last_message.lower():
                return response

        return self.default_response

    async def stream_response(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        full_text = await self.generate_response(messages, temperature, max_tokens)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            token = word if i == 0 else " " + word
            await asyncio.sleep(0.001)
            yield token


class MockTTS(TTSProvider):
    """Mock TTS provider that yields fixed synthetic PCM chunks."""

    def __init__(self, chunk_count: int = 4, chunk_size: int = 1024) -> None:
        self.chunk_count = chunk_count
        self.chunk_size = chunk_size
        self.synthesized_texts: list[str] = []

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.synthesized_texts.append(text)
        sample_chunk = b"\x00\x00" * (self.chunk_size // 2)
        for _ in range(self.chunk_count):
            await asyncio.sleep(0.001)
            yield sample_chunk
