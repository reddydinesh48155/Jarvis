"""Unit tests for STT, LLM, and TTS providers."""

import pytest

from app.voice.providers.base import ChatMessage, ProviderError
from app.voice.providers.mock import MockLLM, MockSTT, MockTTS
from app.voice.providers.ollama import OllamaLLM
from app.voice.providers.piper import PiperTTS
from app.voice.providers.whisper import FasterWhisperSTT


@pytest.mark.asyncio
async def test_mock_stt_transcribes_audio():
    stt = MockSTT(transcription="test speech")
    result = await stt.transcribe(b"\x00\x00" * 100, sample_rate=16000)
    assert result == "test speech"
    assert stt.last_audio_len == 200


@pytest.mark.asyncio
async def test_mock_llm_generation_and_streaming():
    llm = MockLLM(
        default_response="Default answer",
        intent_responses={"code": "Python code solution"},
    )

    # Default generation
    resp = await llm.generate_response([ChatMessage(role="user", content="hello")])
    assert resp == "Default answer"

    # Intent-based generation
    code_resp = await llm.generate_response(
        [ChatMessage(role="user", content="Write some code")]
    )
    assert code_resp == "Python code solution"

    # Streaming
    tokens: list[str] = []
    async for token in llm.stream_response([ChatMessage(role="user", content="code")]):
        tokens.append(token)
    assert "".join(tokens) == "Python code solution"


@pytest.mark.asyncio
async def test_mock_tts_synthesizes_audio_chunks():
    tts = MockTTS(chunk_count=3, chunk_size=512)
    chunks: list[bytes] = []
    async for chunk in tts.synthesize("Hello world"):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert len(chunks[0]) == 512
    assert tts.synthesized_texts == ["Hello world"]


@pytest.mark.asyncio
async def test_faster_whisper_empty_audio_returns_empty_string():
    stt = FasterWhisperSTT()
    result = await stt.transcribe(b"")
    assert result == ""


def test_piper_missing_binary_raises_provider_error():
    tts = PiperTTS(binary_path="non_existent_piper_binary_12345")
    with pytest.raises(ProviderError, match="not found on PATH"):
        tts._check_binary()


def test_ollama_message_formatting():
    llm = OllamaLLM(base_url="http://localhost:11434", model="llama3.1")
    messages = [
        ChatMessage(role="system", content="System instruction"),
        ChatMessage(role="user", content="User question"),
    ]
    formatted = llm._format_messages(messages)
    assert formatted == [
        {"role": "system", "content": "System instruction"},
        {"role": "user", "content": "User question"},
    ]
