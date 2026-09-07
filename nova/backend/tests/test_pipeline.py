"""Unit and integration tests for the VoicePipeline."""

import asyncio
from typing import Any

import pytest

from app.agents.registry import create_default_registry
from app.agents.router import AgentRouter
from app.voice.pipeline import VoicePipeline
from app.voice.providers.base import ChatMessage, ProviderError
from app.voice.providers.mock import MockLLM, MockSTT, MockTTS


@pytest.mark.asyncio
async def test_pipeline_successful_end_to_end_turn():
    events: list[dict[str, Any]] = []
    audio_chunks: list[bytes] = []

    async def on_event(event: dict[str, Any]) -> None:
        events.append(event)

    async def on_audio(chunk: bytes) -> None:
        audio_chunks.append(chunk)

    stt = MockSTT(transcription="How do I write a Python decorator?")
    router_llm = MockLLM(default_response="coding")
    agent_llm = MockLLM(default_response="A decorator wraps another function in Python.")
    tts = MockTTS(chunk_count=2, chunk_size=256)
    router = AgentRouter(registry=create_default_registry(), llm=router_llm)

    pipeline = VoicePipeline(
        stt=stt,
        llm=agent_llm,
        tts=tts,
        router=router,
        on_event=on_event,
        on_audio_chunk=on_audio,
    )

    fake_audio = b"\x00\x00" * 320
    await pipeline.process_audio_turn(fake_audio, sample_rate=16000)

    # Verify event flow
    event_types = [e["type"] for e in events]
    assert "agent_state" in event_types
    assert "user_transcript" in event_types
    assert "active_agent" in event_types
    assert "agent_transcript" in event_types

    # Verify user transcript
    user_event = next(e for e in events if e["type"] == "user_transcript")
    assert user_event["text"] == "How do I write a Python decorator?"

    # Verify active agent selected is coding
    active_agent_event = next(e for e in events if e["type"] == "active_agent")
    assert active_agent_event["name"] == "coding"

    # Verify agent transcript
    agent_event = next(e for e in events if e["type"] == "agent_transcript")
    assert "decorator wraps" in agent_event["text"]

    # Verify TTS was triggered and chunks were received
    assert len(audio_chunks) == 2
    assert tts.synthesized_texts == ["A decorator wraps another function in Python."]


@pytest.mark.asyncio
async def test_pipeline_interruption():
    events: list[dict[str, Any]] = []

    async def on_event(event: dict[str, Any]) -> None:
        events.append(event)

    # Slow TTS that yields several chunks with small delay
    class SlowTTS(MockTTS):
        async def synthesize(self, text: str):
            for _ in range(10):
                await asyncio.sleep(0.05)
                yield b"\x00" * 100

    stt = MockSTT(transcription="Tell me a long story")
    llm = MockLLM(default_response="Once upon a time...")
    tts = SlowTTS()

    pipeline = VoicePipeline(
        stt=stt,
        llm=llm,
        tts=tts,
        on_event=on_event,
    )

    # Start turn in task
    task = asyncio.create_task(pipeline.process_audio_turn(b"\x00" * 100))
    await asyncio.sleep(0.02)

    # User interrupts mid-response
    pipeline.interrupt()
    await task

    # Pipeline should return to listening
    assert pipeline._is_interrupted is True


@pytest.mark.asyncio
async def test_pipeline_graceful_degradation_on_stt_failure():
    events: list[dict[str, Any]] = []

    class FailingSTT(MockSTT):
        async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
            raise ProviderError("Microphone audio distorted")

    pipeline = VoicePipeline(
        stt=FailingSTT(),
        llm=MockLLM(),
        tts=MockTTS(),
        on_event=lambda e: events.append(e),
    )

    await pipeline.process_audio_turn(b"\x00" * 100)

    # Error event emitted without raising unhandled exception
    error_event = next((e for e in events if e["type"] == "error"), None)
    assert error_event is not None
    assert error_event["stage"] == "stt"
