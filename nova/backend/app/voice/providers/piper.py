"""Piper local TTS provider implementation."""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import AsyncIterator

from app.core.config import settings
from app.voice.providers.base import ProviderError, TTSProvider

logger = logging.getLogger("nova.voice.providers.piper")


class PiperTTS(TTSProvider):
    """Local fast TTS provider using Piper binary and voice models."""

    def __init__(
        self,
        voice: str | None = None,
        binary_path: str | None = None,
        chunk_size: int = 4096,
    ) -> None:
        self.voice = voice or settings.piper_voice
        self.binary_path = binary_path or settings.piper_binary_path
        self.chunk_size = chunk_size

    def _check_binary(self) -> None:
        if not shutil.which(self.binary_path):
            raise ProviderError(
                f"Piper binary '{self.binary_path}' not found on PATH. "
                "Download Piper from https://github.com/rhasspy/piper/releases."
            )

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        clean_text = text.strip()
        if not clean_text:
            return

        self._check_binary()

        cmd = [
            self.binary_path,
            "--model",
            self.voice,
            "--output-raw",
        ]

        logger.debug("running Piper TTS for text: %s", clean_text[:40])
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            logger.exception("failed to spawn piper process")
            raise ProviderError(f"Failed to start Piper TTS: {exc}") from exc

        try:
            # Write input text to piper stdin
            if process.stdin:
                process.stdin.write(clean_text.encode("utf-8"))
                await process.stdin.drain()
                process.stdin.close()

            # Stream stdout raw PCM bytes
            if process.stdout:
                while True:
                    chunk = await process.stdout.read(self.chunk_size)
                    if not chunk:
                        break
                    yield chunk

            await process.wait()
            if process.returncode != 0:
                stderr_output = ""
                if process.stderr:
                    stderr_output = (await process.stderr.read()).decode(errors="ignore")
                logger.warning("Piper exited with code %s: %s", process.returncode, stderr_output)
                raise ProviderError(f"Piper TTS synthesis failed: {stderr_output}")

        except asyncio.CancelledError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            raise
        except ProviderError:
            raise
        except Exception as exc:
            logger.exception("unexpected error during Piper TTS streaming")
            raise ProviderError(f"TTS streaming error: {exc}") from exc
