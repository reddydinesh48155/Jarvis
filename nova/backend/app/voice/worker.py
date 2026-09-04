"""LiveKit Agents worker for transport-only NOVA voice sessions.

This worker deliberately avoids STT, LLM, and TTS. It uses a small RMS-based
silence detector, replays the captured PCM as an audio echo, and publishes the
scripted acknowledgement as reliable room data. Part 3 can replace the echo
publisher with a real response pipeline without changing room plumbing.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from collections.abc import Iterable

from livekit import rtc
from livekit.agents import AgentServer, AutoSubscribe, JobContext, cli

from app.core.config import settings


logger = logging.getLogger("nova.voice.worker")

SAMPLE_RATE = 48_000
NUM_CHANNELS = 1
RMS_SPEECH_THRESHOLD = 500.0
MIN_SPEECH_SECONDS = 0.15
END_OF_SPEECH_SILENCE_SECONDS = 0.60
ACKNOWLEDGEMENT = "I heard you"
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
    """Detect one speech segment without STT or an inference model."""

    def __init__(self) -> None:
        self.is_speaking = False
        self.speech_duration = 0.0
        self.silence_duration = 0.0
        self._frames: deque[rtc.AudioFrame] = deque(maxlen=500)

    def observe(self, frame: rtc.AudioFrame) -> list[rtc.AudioFrame] | None:
        duration = frame_duration(frame)
        speaking_now = frame_rms(frame) >= RMS_SPEECH_THRESHOLD

        if speaking_now:
            if not self.is_speaking:
                self._frames.clear()
            self.is_speaking = True
            self.speech_duration += duration
            self.silence_duration = 0.0
            self._frames.append(copy_frame(frame))
            return None

        if not self.is_speaking:
            return None

        self.silence_duration += duration
        self._frames.append(copy_frame(frame))
        if (
            self.speech_duration >= MIN_SPEECH_SECONDS
            and self.silence_duration >= END_OF_SPEECH_SILENCE_SECONDS
        ):
            completed_frames = list(self._frames)
            self.reset()
            return completed_frames
        return None

    def reset(self) -> None:
        self.is_speaking = False
        self.speech_duration = 0.0
        self.silence_duration = 0.0
        self._frames.clear()


async def publish_acknowledgement(
    room: rtc.Room,
    source: rtc.AudioSource,
    frames: Iterable[rtc.AudioFrame],
    participant_identity: str,
) -> None:
    """Echo captured audio and publish the scripted acknowledgement event."""
    try:
        for frame in frames:
            await source.capture_frame(frame)
        await source.wait_for_playout()
        await room.local_participant.publish_data(
            ACKNOWLEDGEMENT,
            reliable=True,
            destination_identities=[participant_identity],
            topic=ACK_TOPIC,
        )
    except Exception:
        logger.exception("failed to publish voice acknowledgement")


server = AgentServer()


@server.rtc_session(agent_name=settings.livekit_agent_name)
async def entrypoint(ctx: JobContext) -> None:
    logger.info("connecting voice worker to room %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    stream = rtc.AudioStream.from_participant(
        participant=participant,
        track_source=rtc.TrackSource.SOURCE_MICROPHONE,
        sample_rate=SAMPLE_RATE,
        num_channels=NUM_CHANNELS,
    )
    source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS, queue_size_ms=200)
    track = rtc.LocalAudioTrack.create_audio_track("nova-voice-echo", source)
    await ctx.room.local_participant.publish_track(
        track,
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_UNKNOWN),
    )
    await ctx.room.local_participant.set_attributes({"lk.agent.state": "listening"})

    detector = SilenceDetector()
    acknowledgement_task: asyncio.Task[None] | None = None
    try:
        async for audio_event in stream:
            if acknowledgement_task is not None and acknowledgement_task.done():
                await acknowledgement_task
                await ctx.room.local_participant.set_attributes({"lk.agent.state": "listening"})
                acknowledgement_task = None

            completed_frames = detector.observe(audio_event.frame)
            if completed_frames is None or acknowledgement_task is not None:
                continue

            await ctx.room.local_participant.set_attributes({"lk.agent.state": "speaking"})
            acknowledgement_task = asyncio.create_task(
                publish_acknowledgement(
                    ctx.room,
                    source,
                    completed_frames,
                    participant.identity,
                )
            )
    finally:
        if acknowledgement_task is not None:
            await acknowledgement_task
            await ctx.room.local_participant.set_attributes({"lk.agent.state": "listening"})
        await stream.aclose()
        await source.aclose()
        logger.info("voice worker stopped for room %s", ctx.room.name)


if __name__ == "__main__":
    cli.run_app(server)
