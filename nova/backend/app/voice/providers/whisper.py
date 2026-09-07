"""faster-whisper local STT provider implementation."""

from __future__ import annotations

import asyncio
import io
import logging
import wave
from typing import Any

import numpy as np

from app.core.config import settings
from app.voice.providers.base import ProviderError, STTProvider

logger = logging.getLogger("nova.voice.providers.whisper")


class FasterWhisperSTT(STTProvider):
    """Local Speech-to-Text provider powered by faster-whisper."""

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str = "default",
    ) -> None:
        self.model_size = model_size or settings.whisper_model_size
        self.device = device or settings.whisper_device
        self.compute_type = compute_type
        self._model: Any = None
        self._lock = asyncio.Lock()

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ProviderError(
                "faster-whisper is not installed. Install with: pip install faster-whisper"
            ) from exc

        try:
            logger.info(
                "loading faster-whisper model '%s' on %s (%s)",
                self.model_size,
                self.device,
                self.compute_type,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            return self._model
        except Exception as exc:
            logger.exception("failed to initialize faster-whisper model '%s'", self.model_size)
            raise ProviderError(f"Failed to load Whisper model '{self.model_size}': {exc}") from exc

    def _transcribe_sync(self, audio_data: bytes, sample_rate: int) -> str:
        model = self._get_model()

        # Convert raw 16-bit PCM bytes to float32 numpy array
        try:
            audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
            if audio_int16.size == 0:
                return ""
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
        except Exception as exc:
            logger.warning("invalid audio data for transcription: %s", exc)
            return ""

        segments, _ = model.transcribe(
            audio_float32,
            language="en",
            beam_size=1,
            vad_filter=True,
        )

        texts = [segment.text.strip() for segment in segments if segment.text.strip()]
        return " ".join(texts)

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        if not audio_data:
            return ""

        async with self._lock:
            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(
                    None, self._transcribe_sync, audio_data, sample_rate
                )
            except ProviderError:
                raise
            except Exception as exc:
                logger.exception("transcription failed")
                raise ProviderError(f"STT transcription error: {exc}") from exc
