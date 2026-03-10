"""Whisper Typer — mic capture, VAD, and recording controller.

Handles three recording modes:
  - PTT: external start/stop triggers
  - Manual: toggle start/stop via button
  - VAD (always-on): Silero-VAD detects speech, auto-segments

Threading model:
  - sounddevice.InputStream runs its callback on an internal PortAudio thread.
  - The callback only copies audio into thread-safe queues (no heavy work).
  - A dedicated VAD worker thread pulls from a queue and runs Silero inference.
  - Start/stop are called from the main thread (via event queue).
  - Results are posted back to the main event queue.
"""

from __future__ import annotations

import collections
import logging
import logging.handlers
import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd

from config import (
    BLOCK_SIZE,
    CHANNELS,
    MAX_RECORD_SEC,
    SAMPLE_RATE,
    SILENCE_TIMEOUT,
    VAD_PRE_PAD_SEC,
    VAD_SILENCE_SEC,
    VAD_THRESHOLD,
    VAD_WINDOW_SAMPLES,
)

# ── VAD / stream logger ──────────────────────────────────────────────

_log = logging.getLogger("whisper_typer.audio")
_log.setLevel(logging.DEBUG)
if not _log.handlers:
    _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vad.log")
    _handler = logging.handlers.RotatingFileHandler(
        _log_path, maxBytes=1_000_000, backupCount=1, encoding="utf-8",
    )
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _log.addHandler(_handler)
    _log.propagate = False

# ── Silero VAD loader ─────────────────────────────────────────────────

_vad_model = None


def _load_vad():
    """Load Silero VAD model (cached singleton)."""
    global _vad_model
    if _vad_model is None:
        import torch
        result = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        # API returns (model, utils) tuple or just model depending on version
        if isinstance(result, tuple):
            _vad_model = result[0]
        else:
            _vad_model = result
        if _vad_model is None:
            raise RuntimeError("torch.hub.load returned None for silero_vad")
    return _vad_model


# ── Recording Controller ─────────────────────────────────────────────

class Recorder:
    """Manages mic capture with optional VAD.

    Posts events to the main event queue:
      ("recording_done", np.ndarray)  — finished recording
      ("recording_empty",)            — no audio captured
      ("vad_speech_start",)           — VAD detected speech start
      ("vad_speech_end",)             — VAD detected speech end
      ("audio_error", str)            — error message
    """

    def __init__(self, event_queue: queue.Queue, device_index: int | None = None):
        self._queue = event_queue
        self._device_index = device_index
        self._stream: sd.InputStream | None = None
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._lock = threading.Lock()
        self._start_time: float = 0
        self._silence_start: float | None = None

        # VAD state (protected by _vad_lock)
        self._vad_enabled = False
        self._vad_model = None
        self._vad_speaking = False
        self._vad_silence_start: float | None = None
        self._vad_lock = threading.Lock()
        self._vad_buffer = collections.deque()  # ring buffer for pre-pad
        self._vad_pre_pad_samples = int(SAMPLE_RATE * VAD_PRE_PAD_SEC)
        self._vad_chunk = bytearray()  # accumulate raw bytes for VAD window
        # VAD worker thread and queue — keeps inference off the PortAudio thread
        self._vad_queue: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=500)
        self._vad_thread: threading.Thread | None = None

        # Stream error recovery
        self._stream_retry_count = 0
        self._stream_last_retry: float = 0.0
        self._stream_max_retries = 3
        self._stream_retry_backoff = 2.0  # seconds, doubles each attempt

    # ── Stream lifecycle ──────────────────────────────────────────

    def set_device(self, device_index: int | None) -> None:
        """Change the input device. Restarts the stream if open."""
        was_open = self._stream is not None
        if was_open:
            self.close_stream()
        self._device_index = device_index
        if was_open:
            self.open_stream()

    def open_stream(self) -> None:
        """Open the mic stream (doesn't start recording yet)."""
        if self._stream is not None:
            return
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                device=self._device_index,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._stream_retry_count = 0
            _log.info("Audio stream opened (device=%s)", self._device_index)
        except Exception as e:
            _log.error("Failed to open audio stream: %s: %s", type(e).__name__, e)
            self._queue.put(("audio_error", str(e)))
            self._schedule_stream_retry()

    def close_stream(self) -> None:
        """Close the mic stream."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            _log.info("Audio stream closed")

    # ── Recording control (PTT / Manual) ──────────────────────────

    def start_recording(self) -> None:
        """Begin capturing audio frames."""
        with self._lock:
            self._frames = []
            self._recording = True
            self._start_time = time.monotonic()
            self._silence_start = None

    def stop_recording(self) -> None:
        """Stop capturing and post the result."""
        with self._lock:
            self._recording = False
            frames = self._frames.copy()
            self._frames = []

        if frames:
            audio = np.concatenate(frames, axis=0).flatten()
            # Skip if too short (<0.3s)
            if len(audio) >= int(SAMPLE_RATE * 0.3):
                self._queue.put(("recording_done", audio))
                return
        self._queue.put(("recording_empty",))

    # ── VAD mode ──────────────────────────────────────────────────

    def enable_vad(self) -> None:
        """Enable always-on VAD mode."""
        _log.info("VAD enabled")
        if not self._vad_model:
            self._vad_model = _load_vad()
        with self._vad_lock:
            self._vad_enabled = True
            self._vad_speaking = False
            self._vad_silence_start = None
            self._vad_buffer.clear()
            self._vad_chunk = bytearray()
        # Start the VAD worker thread
        if self._vad_thread is None or not self._vad_thread.is_alive():
            self._vad_thread = threading.Thread(target=self._vad_worker, daemon=True)
            self._vad_thread.start()
        self.open_stream()

    def disable_vad(self) -> None:
        """Disable VAD mode and stop the worker thread."""
        _log.info("VAD disabled")
        with self._vad_lock:
            self._vad_enabled = False
            self._vad_speaking = False
            self._vad_buffer.clear()
            self._vad_chunk = bytearray()
        # Signal worker to exit
        self._vad_queue.put(None)

    @property
    def vad_active(self) -> bool:
        return self._vad_enabled

    # ── Audio callback ────────────────────────────────────────────

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Called by sounddevice for each block of audio data.

        MUST be lightweight — no model inference here. Just copy data and
        enqueue for the VAD worker thread.
        """
        if status:
            _log.warning("Audio stream status error: %s", status)
            self._queue.put(("audio_error", f"Stream: {status}"))

        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.flatten().copy()

        # Direct recording mode (PTT / Manual)
        with self._lock:
            if self._recording:
                self._frames.append(mono.copy())
                # Check max duration
                elapsed = time.monotonic() - self._start_time
                if elapsed >= MAX_RECORD_SEC:
                    threading.Thread(target=self.stop_recording, daemon=True).start()
                    return
                # Silence detection for non-VAD recording
                rms = float(np.sqrt(np.dot(mono, mono) / len(mono)))
                if rms < 0.01:
                    if self._silence_start is None:
                        self._silence_start = time.monotonic()
                    elif time.monotonic() - self._silence_start >= SILENCE_TIMEOUT:
                        threading.Thread(target=self.stop_recording, daemon=True).start()
                        return
                else:
                    self._silence_start = None

        # VAD mode — enqueue audio for the worker thread (non-blocking)
        if self._vad_enabled and self._vad_model:
            try:
                self._vad_queue.put_nowait(mono)
            except queue.Full:
                pass  # drop frame rather than block the PortAudio thread

    # ── VAD worker thread ──────────────────────────────────────────

    def _vad_worker(self) -> None:
        """Dedicated thread that runs Silero VAD inference off the PortAudio thread."""
        import torch

        _log.info("VAD worker thread started")
        chunks_since_health_check = 0
        # ~5 seconds of audio at 32ms per VAD window = ~156 chunks
        health_check_interval = int(5.0 / (VAD_WINDOW_SAMPLES / SAMPLE_RATE))

        while True:
            mono = self._vad_queue.get()
            if mono is None:
                # Shutdown signal
                _log.info("VAD worker thread stopping (shutdown signal)")
                break
            if not self._vad_enabled:
                continue
            try:
                self._process_vad(mono, torch)
                chunks_since_health_check += 1
                if chunks_since_health_check >= health_check_interval:
                    chunks_since_health_check = 0
                    self._check_stream_health()
            except Exception as exc:
                _log.error("VAD worker exception: %s: %s", type(exc).__name__, exc)

    # ── Stream error recovery ─────────────────────────────────────────

    def _check_stream_health(self) -> None:
        """Verify the audio stream is still active; attempt recovery if not."""
        if self._stream is None:
            _log.warning("Stream health check: stream is None, attempting recovery")
            self._attempt_stream_recovery()
            return
        try:
            if not self._stream.active:
                _log.warning("Stream health check: stream inactive, attempting recovery")
                self._attempt_stream_recovery()
        except Exception as exc:
            _log.error("Stream health check error: %s: %s", type(exc).__name__, exc)
            self._attempt_stream_recovery()

    def _attempt_stream_recovery(self) -> None:
        """Try to reopen the stream with backoff."""
        now = time.monotonic()
        backoff = self._stream_retry_backoff * (2 ** self._stream_retry_count)
        if now - self._stream_last_retry < backoff:
            return  # too soon, wait for backoff

        if self._stream_retry_count >= self._stream_max_retries:
            _log.error(
                "Stream recovery: max retries (%d) exceeded, giving up",
                self._stream_max_retries,
            )
            self._queue.put(("audio_error", "Mic stream lost — max retries exceeded"))
            return

        self._stream_retry_count += 1
        self._stream_last_retry = now
        _log.info(
            "Stream recovery: attempt %d/%d (backoff %.1fs)",
            self._stream_retry_count, self._stream_max_retries, backoff,
        )

        # Close whatever is left, then reopen
        self.close_stream()
        self.open_stream()

    def _schedule_stream_retry(self) -> None:
        """Schedule a deferred stream retry on a background thread."""
        if self._stream_retry_count >= self._stream_max_retries:
            _log.error(
                "Stream retry: max retries (%d) exceeded, not scheduling another",
                self._stream_max_retries,
            )
            return
        backoff = self._stream_retry_backoff * (2 ** self._stream_retry_count)
        _log.info("Scheduling stream retry in %.1fs", backoff)

        def _retry():
            time.sleep(backoff)
            if self._stream is None and self._vad_enabled:
                _log.info("Executing scheduled stream retry")
                self._attempt_stream_recovery()

        threading.Thread(target=_retry, daemon=True).start()

    def _process_vad(self, mono: np.ndarray, torch) -> None:
        """Feed audio to Silero VAD and manage speech segments.

        Called from the VAD worker thread only. Uses _vad_lock for shared state.
        """
        # Accumulate into VAD-sized chunks (using raw bytes for thread safety)
        raw = mono.tobytes()
        with self._vad_lock:
            self._vad_chunk.extend(raw)

        bytes_per_window = VAD_WINDOW_SAMPLES * 4  # float32 = 4 bytes

        while True:
            with self._vad_lock:
                if len(self._vad_chunk) < bytes_per_window:
                    break
                chunk_bytes = bytes(self._vad_chunk[:bytes_per_window])
                del self._vad_chunk[:bytes_per_window]

            chunk = np.frombuffer(chunk_bytes, dtype=np.float32)

            # Run VAD inference (safe — we're on the worker thread)
            tensor = torch.from_numpy(chunk)
            prob = float(self._vad_model(tensor, SAMPLE_RATE))
            is_speech = prob >= VAD_THRESHOLD

            with self._vad_lock:
                if not self._vad_speaking:
                    # Buffer audio for pre-pad
                    self._vad_buffer.append(chunk.copy())
                    total = sum(len(c) for c in self._vad_buffer)
                    while total > self._vad_pre_pad_samples and len(self._vad_buffer) > 1:
                        total -= len(self._vad_buffer[0])
                        self._vad_buffer.popleft()

                    if is_speech:
                        self._vad_speaking = True
                        self._vad_silence_start = None
                        self._queue.put(("vad_speech_start",))

                        # Start recording with pre-pad buffer
                        with self._lock:
                            pre_pad = np.concatenate(list(self._vad_buffer)) if self._vad_buffer else np.array([], dtype=np.float32)
                            self._frames = [pre_pad] if len(pre_pad) > 0 else []
                            self._recording = True
                            self._start_time = time.monotonic()
                            self._silence_start = None
                else:
                    # Currently speaking — accumulate frames
                    with self._lock:
                        if self._recording:
                            self._frames.append(chunk.copy())

                    if not is_speech:
                        if self._vad_silence_start is None:
                            self._vad_silence_start = time.monotonic()
                        elif time.monotonic() - self._vad_silence_start >= VAD_SILENCE_SEC:
                            self._vad_speaking = False
                            self._vad_silence_start = None
                            self._vad_buffer.clear()
                            self._queue.put(("vad_speech_end",))

                            with self._lock:
                                self._recording = False
                                frames = self._frames.copy()
                                self._frames = []

                            if frames:
                                audio = np.concatenate(frames, axis=0).flatten()
                                if len(audio) >= int(SAMPLE_RATE * 0.3):
                                    self._queue.put(("recording_done", audio))
                                else:
                                    self._queue.put(("recording_empty",))
                    else:
                        self._vad_silence_start = None
