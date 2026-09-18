"""Voice conversational pipeline coordinating STT, intent routing, agent execution, and TTS."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.agents.registry import create_default_registry
from app.agents.router import AgentRouter
from app.core.config import settings
from app.memory.service import MemoryService
from app.tools.audit import audit_logger
from app.tools.base import PermissionLevel
from app.tools.registry import ToolRegistry, create_default_tool_registry
from app.voice.providers.base import (
    ChatMessage,
    LLMProvider,
    ProviderError,
    STTProvider,
    TTSProvider,
)

logger = logging.getLogger("nova.voice.pipeline")

# Affirmative keywords that indicate the user confirms a memory proposal
_CONFIRM_KEYWORDS = {"yes", "yeah", "yep", "sure", "go ahead", "do it", "please", "ok", "okay"}
_DECLINE_KEYWORDS = {"no", "cancel", "stop", "don't", "nevermind", "nope", "deny", "decline"}


class VoicePipeline:
    """End-to-end voice conversational pipeline with multi-agent routing and interruption."""

    def __init__(
        self,
        stt: STTProvider,
        llm: LLMProvider,
        tts: TTSProvider,
        router: AgentRouter | None = None,
        tool_registry: ToolRegistry | None = None,
        memory_service: MemoryService | None = None,
        user_id: str | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_audio_chunk: Callable[[bytes], Awaitable[None]] | None = None,
    ) -> None:
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.router = router or AgentRouter(registry=create_default_registry(), llm=llm)
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.memory_service = memory_service or MemoryService()
        self.on_event = on_event
        self.on_audio_chunk = on_audio_chunk

        self.context = AgentContext(
            user_id=user_id,
            tool_registry=self.tool_registry,
            on_tool_event=self._emit,
        )
        self.active_agent: BaseAgent = self.router.registry.get_default()
        self._current_turn_task: asyncio.Task[None] | None = None
        self._is_interrupted = False
        self._pending_memory_content: str | None = None
        self._pending_memory_category: str | None = None
        # Human-in-the-loop tool confirmation (Part 8)
        self._pending_tool_confirmation: dict[str, Any] | None = None

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

        # Step 1a: Check for pending tool confirmation (HITL — Part 8)
        if self._pending_tool_confirmation is not None:
            lower = transcript.lower().strip()
            tool_name = self._pending_tool_confirmation["tool_name"]
            tool_args = self._pending_tool_confirmation["arguments"]
            requested_at = self._pending_tool_confirmation["requested_at"]
            elapsed = time.monotonic() - requested_at

            if elapsed > settings.tool_confirmation_timeout_seconds:
                # Timeout — treat as declined
                await audit_logger.log_tool_call(
                    tool_name=tool_name,
                    user_id=self.context.user_id,
                    input_params=tool_args,
                    output_result=None,
                    success=False,
                    error_message="Confirmation timed out — auto-declined",
                    permission_level="HIGH",
                    requires_confirmation=True,
                    confirmed=False,
                )
                await self._emit({
                    "type": "tool_confirmation_result",
                    "tool_name": tool_name,
                    "outcome": "timed_out",
                })
                self._pending_tool_confirmation = None
                response_text = f"The action '{tool_name}' was automatically declined due to timeout."
                await self._emit({"type": "agent_transcript", "text": response_text, "is_final": True})
                self.context.conversation_history.append(ChatMessage(role="assistant", content=response_text))
                await self._set_state("speaking")
                async for audio_chunk in self.tts.synthesize(response_text):
                    if self._is_interrupted:
                        break
                    if self.on_audio_chunk is not None:
                        await self.on_audio_chunk(audio_chunk)
                if not self._is_interrupted:
                    await self._set_state("listening")
                return

            if any(kw in lower for kw in _CONFIRM_KEYWORDS):
                # User confirmed — re-execute with confirmed=True
                self.context.confirmed = True
                await self._emit({
                    "type": "tool_confirmation_result",
                    "tool_name": tool_name,
                    "outcome": "confirmed",
                })
                self._pending_tool_confirmation = None
                # Fall through to normal turn — the agent will re-attempt the tool call
                # with confirmed=True already set in context
            elif any(kw in lower for kw in _DECLINE_KEYWORDS):
                # User declined
                await audit_logger.log_tool_call(
                    tool_name=tool_name,
                    user_id=self.context.user_id,
                    input_params=tool_args,
                    output_result=None,
                    success=False,
                    error_message="User declined confirmation",
                    permission_level="HIGH",
                    requires_confirmation=True,
                    confirmed=False,
                )
                await self._emit({
                    "type": "tool_confirmation_result",
                    "tool_name": tool_name,
                    "outcome": "declined",
                })
                self._pending_tool_confirmation = None
                self.context.confirmed = False
                response_text = f"Okay, I've cancelled the '{tool_name}' action."
                await self._emit({"type": "agent_transcript", "text": response_text, "is_final": True})
                self.context.conversation_history.append(ChatMessage(role="assistant", content=response_text))
                await self._set_state("speaking")
                async for audio_chunk in self.tts.synthesize(response_text):
                    if self._is_interrupted:
                        break
                    if self.on_audio_chunk is not None:
                        await self.on_audio_chunk(audio_chunk)
                if not self._is_interrupted:
                    await self._set_state("listening")
                return
            else:
                # Unclear response — ask again
                response_text = f"Please say 'yes' to confirm or 'no' to cancel the '{tool_name}' action."
                await self._emit({"type": "agent_transcript", "text": response_text, "is_final": True})
                await self._set_state("speaking")
                async for audio_chunk in self.tts.synthesize(response_text):
                    if self._is_interrupted:
                        break
                    if self.on_audio_chunk is not None:
                        await self.on_audio_chunk(audio_chunk)
                if not self._is_interrupted:
                    await self._set_state("listening")
                return

        # Step 1b: Check for pending memory confirmation
        if self._pending_memory_content is not None:
            lower = transcript.lower().strip()
            if any(kw in lower for kw in _CONFIRM_KEYWORDS):
                try:
                    factory = self.memory_service.long_term._factory()
                    async with factory() as db:
                        stored = await self.memory_service.confirm_and_store(
                            db=db,
                            user_id=self.context.user_id or "",
                            fact_content=self._pending_memory_content,
                            category=self._pending_memory_category or "general",
                            session_id=self.context.session_id,
                        )
                    if stored:
                        await self._emit({
                            "type": "memory_saved",
                            "content": self._pending_memory_content,
                        })
                except Exception as exc:
                    logger.exception("failed to store confirmed memory: %s", exc)
                self._pending_memory_content = None
                self._pending_memory_category = None
                # Don't return — let the confirmation response flow through the pipeline
            else:
                # User didn't confirm — dismiss the proposal
                self.memory_service.session.dismiss_pending()
                self._pending_memory_content = None
                self._pending_memory_category = None

        # Step 1c: Retrieve relevant long-term memories
        self.context.memory_context = None
        if self.context.user_id:
            try:
                factory = self.memory_service.long_term._factory()
                async with factory() as db:
                    hits = await self.memory_service.retrieve_relevant_memories(
                        db=db,
                        user_id=self.context.user_id,
                        query=transcript,
                    )
                memory_text = self.memory_service.format_memory_context(hits)
                if memory_text:
                    self.context.memory_context = memory_text
                    await self._emit({
                        "type": "memory_recalled",
                        "count": len(hits),
                    })
            except Exception as exc:
                logger.warning("memory retrieval failed, continuing without: %s", exc)

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

        # Step 3a: Check if agent is requesting tool confirmation (HITL — Part 8)
        if (
            hasattr(agent_response, "metadata")
            and agent_response.metadata
            and agent_response.metadata.get("requires_confirmation")
        ):
            tool_name = agent_response.metadata.get("tool_name", "unknown")
            tool_args = agent_response.metadata.get("arguments", {})
            self._pending_tool_confirmation = {
                "tool_name": tool_name,
                "arguments": tool_args,
                "requested_at": time.monotonic(),
            }
            await self._emit({
                "type": "tool_confirmation_request",
                "tool_name": tool_name,
                "arguments": tool_args,
                "prompt": response_text,
            })
            # Reset confirmed flag so next turn can set it fresh
            self.context.confirmed = False

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

        # Step 3b: Detect memorable facts and propose for confirmation
        if self.context.user_id and self._pending_memory_content is None:
            try:
                proposals = await self.memory_service.detect_and_propose_facts(
                    user_input=transcript,
                    assistant_response=response_text,
                    llm=self.llm,
                )
                if proposals:
                    # Take the first proposal — one at a time to avoid overwhelming the user
                    proposal = proposals[0]
                    self._pending_memory_content = proposal.content
                    self._pending_memory_category = proposal.category
                    await self._emit({
                        "type": "memory_proposal",
                        "content": proposal.content,
                        "category": proposal.category,
                        "confirmation_prompt": proposal.confirmation_prompt,
                    })
            except Exception as exc:
                logger.debug("fact detection failed, continuing: %s", exc)

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
