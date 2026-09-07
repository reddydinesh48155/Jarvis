"""Voice conversational pipeline coordinating STT, intent routing, agent execution, and TTS."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import create_default_registry
from app.agents.router import AgentRouter
from app.voice.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderError,
    STTProvider,
    TTSProvider,
)

logger = logging.getLogger("nova.voice.pipeline")


class VoicePipeline:
    """End-to-end voice conversational pipeline with multi-agent routing and interruption."""

    def __init__(
        self,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        router: AgentRouter | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_audio_chunk: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.router = router or AgentRouter(registry=create_default_registry(), llm=llm)
        self.on_event = on_event
        self.on_audio_chunk = on_audio_chunk

        self.context = AgentContext()
        self.active_agent: BaseAgent = self.router.registry.get_default()
        self._current_turn_task: asyncio.Task[None] | None = None
        self._is_interrupted = False

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            try:
                await self.on_event(event)
            except Exception as exc:
                logger.warning("failed to emit pipeline event %s: %s", event, exc)

    async def _set_state(self, state: str) -> None:
        """State can be 'listening', 'thinking', or 'speaking'."""
        await self._emit({
            "type": "agent_state",
            "state": state,
            "agent_name": self.active_agent.name,
            "agent_display_name": self.active_agent.display_name,
        })

    def interrupt(self) -> None:
        """Interrupt any ongoing agent generation or TTS audio playback."""
        logger.info("interrupt requested; canceling active turn")
        self._is_interrupted = True
        if self._current_turn_task is not None and not self._current_turn_task.done():
            self._current_turn_task.cancel()

    async def process_audio_turn(self, audio_data: bytes, sample_rate: int = 16000) -> None:
        """Coordinate a complete speech-in -> agent -> speech-out turn with cancellation support."""
        # Cancel any previous turn that might still be running
        self.interrupt()
        self._is_interrupted = False

        self._current_turn_task = asyncio.create_task(
            self._run_turn(audio_data, sample_rate)
        )
        try:
            await self._current_turn_task
        except asyncio.CancelledError:
            logger.info("audio turn was canceled due to interruption")
            await self._set_state("listening")
        finally:
            self._current_turn_task = None

    async def _run_turn(self, audio_data: bytes, sample_rate: int) -> None:
        # Step 1: STT
        await self._set_state("thinking")

        try:
            transcript = await self.stt.transcribe(audio_data, sample_rate=sample_rate)
            transcript = transcript.strip()
        except Exception as exc:
            logger.exception("STT failure during voice turn")
            await self._emit({
                "type": "error",
                "stage": "stt",
                "message": "Sorry, I had trouble transcribing your audio.",
            })
            await self._set_state("listening")
            return

        if not transcript:
            logger.debug("no transcript recognized from audio chunk")
            await self._set_state("listening")
            return

        # Emit user transcript
        await self._emit({
            "type": "user_transcript",
            "text": transcript,
            "is_final": True,
        })

        if self._is_interrupted:
            return

        # Step 2: Intent classification & multi-agent routing
        selected_agent, routing_reason = await self.router.route(
            user_input=transcript,
            context=self.context,
        )
        self.active_agent = selected_agent

        await self._emit({
            "type": "active_agent",
            "name": selected_agent.name,
            "display_name": selected_agent.display_name,
            "reason": routing_reason,
        })

        if self._is_interrupted:
            return

        # Step 3: Agent reasoning & response generation
        try:
            agent_response = await selected_agent.handle(
                user_input=transcript,
                context=self.context,
                llm=self.llm,
            )
            response_text = agent_response.content.strip()
        except Exception as exc:
            logger.exception("agent reasoning failure (%s)", exc)
            response_text = "I encountered an error while processing your request. Please try again."
            await self._emit({
                "type": "error",
                "stage": "llm",
                "message": str(exc),
            })

        if self._is_interrupted:
            return

        # Emit final agent transcript
        await self._emit({
            "type": "agent_transcript",
            "text": response_text,
            "agent_name": selected_agent.name,
            "agent_display_name": selected_agent.display_name,
            "is_final": True,
        })

        # Update conversation history
        self.context.conversation_history.append(ChatMessage(role="user", content=transcript))
        self.context.conversation_history.append(
            ChatMessage(role="assistant", content=response_text)
        )
        # Keep conversation history window bounded to recent 10 turns
        if len(self.context.conversation_history) > 20:
            self.context.conversation_history = self.context.conversation_history[-20:]

        if self._is_interrupted:
            return

        # Step 4: TTS synthesis & streaming playback
        await self._set_state("speaking")
        try:
            async for audio_chunk in self.tts.synthesize(response_text):
                if self._is_interrupted:
                    logger.info("interrupted during TTS audio streaming")
                    break
                if self.on_audio_chunk is not None:
                    await self.on_audio_chunk(audio_chunk)
        except Exception as exc:
            logger.exception("TTS synthesis failure (%s)", exc)
            await self._emit({
                "type": "error",
                "stage": "tts",
                "message": "Speech synthesis failed.",
            })

        # Final state
        if not self._is_interrupted:
            await self._set_state("listening")
