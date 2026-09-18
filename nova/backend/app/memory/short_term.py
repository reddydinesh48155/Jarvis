"""Short-term memory: current conversation turns held in-process.

This is a lightweight wrapper around a bounded list of ChatMessage objects.
No database persistence — data lives only for the duration of the voice session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.voice.providers.base import ChatMessage


DEFAULT_MAX_TURNS = 10  # 10 turns = 20 messages (user + assistant)


@dataclass
class ShortTermMemory:
    """In-process conversation turn buffer with configurable window size."""

    max_turns: int = DEFAULT_MAX_TURNS
    _messages: list[ChatMessage] = field(default_factory=list)

    @property
    def messages(self) -> list[ChatMessage]:
        """Return the current message buffer (read-only view)."""
        return list(self._messages)

    @property
    def turn_count(self) -> int:
        """Number of complete user+assistant turns."""
        return len(self._messages) // 2

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        """Append a completed conversational turn."""
        self._messages.append(ChatMessage(role="user", content=user_message))
        self._messages.append(ChatMessage(role="assistant", content=assistant_message))
        self._trim()

    def add_message(self, role: str, content: str) -> None:
        """Append a single message."""
        self._messages.append(ChatMessage(role=role, content=content))
        self._trim()

    def get_recent(self, n_turns: int | None = None) -> list[ChatMessage]:
        """Return the most recent n turns (2n messages). None = all."""
        if n_turns is None:
            return list(self._messages)
        count = n_turns * 2
        return list(self._messages[-count:]) if count < len(self._messages) else list(self._messages)

    def clear(self) -> None:
        """Wipe the short-term buffer."""
        self._messages.clear()

    def _trim(self) -> None:
        """Keep the buffer within max_turns."""
        max_messages = self.max_turns * 2
        if len(self._messages) > max_messages:
            self._messages = self._messages[-max_messages:]

