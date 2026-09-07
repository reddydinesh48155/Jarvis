"""LiveKit Agents worker integrating STT, intent routing, multi-agent reasoning, and TTS.

Part 4 replaces the simple transport echo with an intelligent multi-agent pipeline:
user speech -> STT -> AgentRouter -> specialized agent -> response -> TTS -> user.
It also supports user interruption and publishes live transcription and agent metadata.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import shutil
from collections import deque
from typing import Any

from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli

from app.agents.registry import create_default_registry
from app.agents.router import AgentRouter
from app.core.config import settings
from app.voice.pipeline import VoicePipeline
from app.voice.providers.base import LLMProvider, STTProvider, TTSProvider
from app.voice.providers.mock import MockLLM, MockSTT, MockTTS
from app.voice.providers.ollama import OllamaLLM
from app.voice.providers.piper import PiperTTS
from app.voice.providers.whisper import FasterWhisperSTT

logger = logging.getLogger("nova.voice.worker")

SAMPLE_RATE = 48_000
NUM_CHANNELS = 1
RMS_SPEECH_THRESHOLD = 500.0
MIN_SPEECH_SECONDS = 0.15
END_OF_SPEECH_SILENCE_SECONDS = 0.60

EVENT_TOPIC = "nova.voice.events"
ACK_TOPIC = "nova.voice.ack"


def frame_duration(frame: rtc.AudioFrame) -> float:
    return frame.samples_per_channel / frame.sample_rate


def frame_rms(frame: rtc.AudioFrame) -> float:
    samples = frame.data
    if not samples:
        return 0.0
    square_sum = sum(float(sample) * float(sample) for sample in samples)
    return math.sqrt(square_sum / len(samples))


def copy_frame(frame: rtc.AudioFrame) -> rtc.AudioFrame:
    return rtc.AudioFrame(
        data=bytes(frame.data),
        sample_rate=frame.sample_rate,
        num_channels=frame.num_channels,
        samples_per_channel=frame.samples_per_channel,
    )


class SilenceDetector:
    """Detect speech segments and track real-time speech activity for interruption."""

    def __init__(self) -> None:
        self.is_speaking = False
        self.speech_duration = 0.0
        self.silence_duration = 0.0
        self._frames: deque[rtc.AudioFrame] = deque(maxlen=800)

    def observe(self, frame: rtc.AudioFrame) -> tuple[bool, list[rtc.AudioFrame] | None]:
        """Observe audio frame.

        Returns:
            tuple (is_speaking_now, completed_frames_if_finished)
        """
        duration = frame_duration(frame)
        speaking_now = frame_rms(frame) >= RMS_SPEECH_THRESHOLD

        if speaking_now:
            if not self.is_speaking:
                self._frames.clear()
            self.is_speaking = True
            self.speech_duration += duration
            self.silence_duration = 0.0
            self._frames.append(copy_frame(frame))
            return True, None

        if not self.is_speaking:
            return False, None

        self.silence_duration += duration
        self._frames.append(copy_frame(frame))
        if (
            self.speech_duration >= MIN_SPEECH_SECONDS
            and self.silence_duration >= END_OF_SPEECH_SILENCE_SECONDS
        ):
            completed_frames = list(self._frames)
            self.reset()
            return False, completed_frames

        return True, None

    def reset(self) -> None:
        self.is_speaking = False
        self.speech_duration = 0.0
        self.silence_duration = 0.0
        self._frames.clear()


def create_default_providers() -> tuple[STTProvider, LLMProvider, TTSProvider]:
    """Instantiate default local providers with graceful mock fallbacks."""
    # STT
    try:
        import faster_whisper  # noqa: F401

        stt: STTProvider = FasterWhisperSTT()
    except Exception:
        logger.info("using MockSTT provider (faster-whisper not installed)")
        stt = MockSTT(transcription="Can you help me organize my priorities for today?")

    # LLM
    llm: LLMProvider = OllamaLLM()

    # TTS
    if shutil.which(settings.piper_binary_path):
        tts: TTSProvider = PiperTTS()
    else:
        logger.info("using MockTTS provider (piper binary not found on PATH)")
        tts = MockTTS()

    return stt, llm, tts


server = AgentServer()


@server.rtc_session(agent_name=settings.livekit_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    logger.info("connecting NOVA voice worker to room %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    stream = rtc.AudioStream.from_participant(
        participant=participant,
        track_source=rtc.TrackSource.SOURCE_MICROPHONE,
        sample_rate=SAMPLE_RATE,
        num_channels=NUM_CHANNELS,
    )
    source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS, queue_size_ms=200)
    track = rtc.LocalAudioTrack.create_audio_track("nova-voice-agent", source)
    await ctx.room.local_participant.publish_track(
        track,
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_UNKNOWN),
    )
    await ctx.room.local_participant.set_attributes({
        "lk.agent.state": "listening",
        "nova.agent.name": "main_assistant",
        "nova.agent.display_name": "Main Assistant",
    })

    # Prepare event dispatcher
    async def publish_event(event: dict[str, Any]) -> None:
        try:
            payload_str = json.dumps(event)
            payload_bytes = payload_str.encode("utf-8")
            # Publish structured event on nova.voice.events
            await ctx.room.local_participant.publish_data(
                payload_bytes,
                reliable=True,
                destination_identities=[participant.identity],
                topic=EVENT_TOPIC,
            )
            # If agent response is final, also publish on ACK_TOPIC for Part 2 backwards compatibility
            if event.get("type") == "agent_transcript" and event.get("text"):
                await ctx.room.local_participant.publish_data(
                    event["text"].encode("utf-8"),
                    reliable=True,
                    destination_identities=[participant.identity],
                    topic=ACK_TOPIC,
                )
            # Update LiveKit participant attributes on state changes
            if event.get("type") == "agent_state":
                state = event.get("state", "listening")
                agent_name = event.get("agent_name", "main_assistant")
                agent_display = event.get("agent_display_name", "Main Assistant")
                await ctx.room.local_participant.set_attributes({
                    "lk.agent.state": state,
                    "nova.agent.name": agent_name,
                    "nova.agent.display_name": agent_display,
                })
        except Exception:
            logger.exception("failed to publish voice event to room")

    # Audio playback callback
    async def play_audio_chunk(chunk: bytes) -> None:
        if not chunk:
            return
        frame = rtc.AudioFrame(
            data=chunk,
            sample_rate=SAMPLE_RATE,
            num_channels=NUM_CHANNELS,
            samples_per_channel=len(chunk) // 2,
        )
        await source.capture_frame(frame)

    # Initialize providers and pipeline
    stt_provider, llm_provider, tts_provider = create_default_providers()
    registry = create_default_registry()
    router = AgentRouter(registry=registry, llm=llm_provider)
    pipeline = VoicePipeline(
        stt=stt_provider,
        llm=llm_provider,
        tts=tts_provider,
        router=router,
        on_event=publish_event,
        on_audio_chunk=play_audio_chunk,
    )

    detector = SilenceDetector()
    pipeline_task: asyncio.Task[None] | None = None

    try:
        async for audio_event in stream:
            speaking_now, completed_frames = detector.observe(audio_event.frame)

            # User Interruption: if user begins speaking while agent is generating or speaking, interrupt!
            if speaking_now and pipeline_task is not None and not pipeline_task.done():
                logger.info("user started speaking; interrupting agent")
                pipeline.interrupt()
                try:
                    await pipeline_task
                except (asyncio.CancelledError, Exception):
                    pass
                pipeline_task = None
                await ctx.room.local_participant.set_attributes({"lk.agent.state": "listening"})

            if completed_frames is None:
                continue

            # Convert frames to raw 16-bit PCM bytes
            raw_pcm = b"".join(bytes(f.data) for f in completed_frames)

            # Trigger pipeline turn in background task
            pipeline_task = asyncio.create_task(
                pipeline.process_audio_turn(raw_pcm, sample_rate=SAMPLE_RATE)
            )

    finally:
        if pipeline_task is not None:
            pipeline.interrupt()
            try:
                await pipeline_task
            except (asyncio.CancelledError, Exception):
                pass
        await stream.aclose()
        await source.aclose()
        logger.info("NOVA voice worker stopped for room %s", ctx.room.name)


if __name__ == "__main__":
    cli.run_app(server)
