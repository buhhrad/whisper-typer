"""Whisper Typer — faster-whisper transcription wrapper.

Loads the model once on first use (lazy singleton) and transcribes
numpy audio arrays directly without writing temp WAV files.
"""

from __future__ import annotations

import numpy as np

from config import (
    WHISPER_BEAM_SIZE,
    WHISPER_COMPUTE,
    WHISPER_DEVICE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
)

_model = None
_model_size_loaded: str | None = None


def _get_model(model_size: str | None = None):
    """Load the faster-whisper model (cached singleton). Reloads if size changed."""
    global _model, _model_size_loaded
    size = model_size or WHISPER_MODEL
    if _model is None or (_model_size_loaded is not None and size != _model_size_loaded):
        from faster_whisper import WhisperModel
        _model = WhisperModel(size, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE)
        _model_size_loaded = size
    return _model


def transcribe(audio: np.ndarray, model_size: str | None = None) -> str:
    """Transcribe a numpy float32 audio array to text.

    Args:
        audio: float32 numpy array, 16kHz mono.
        model_size: Override model size (tiny/base/small/medium/large-v3).

    Returns:
        Transcribed text string (empty string if no speech detected).
    """
    if audio is None or len(audio) == 0:
        return ""

    model = _get_model(model_size)

    segments, info = model.transcribe(
        audio,
        beam_size=WHISPER_BEAM_SIZE,
        language=WHISPER_LANGUAGE,
        vad_filter=True,           # use Silero VAD to filter non-speech
        vad_parameters=dict(
            min_silence_duration_ms=500,
        ),
    )

    # Collect all segment texts
    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    return " ".join(text_parts).strip()


def preload(model_size: str | None = None) -> None:
    """Pre-load the model (call from background thread at startup)."""
    _get_model(model_size)
