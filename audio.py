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
        self._vad_queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._vad_thread: threading.Thread | None = None

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
        except Exception as e:
            self._queue.put(("audio_error", str(e)))

    def close_stream(self) -> None:
        """Close the mic stream."""
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

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
        mono = indata[:, 0].copy() if indata.ndim > 1 else indata.flatten().copy()

        # Direct recording mode (PTT / Manual)
        with self._lock:
            if self._recording:
                self._frames.append(mono)
                # Check max duration
                elapsed = time.monotonic() - self._start_time
                if elapsed >= MAX_RECORD_SEC:
                    threading.Thread(target=self.stop_recording, daemon=True).start()
                    return
                # Silence detection for non-VAD recording
                rms = float(np.sqrt(np.mean(mono ** 2)))
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

        while True:
            mono = self._vad_queue.get()
            if mono is None:
                # Shutdown signal
                break
            if not self._vad_enabled:
                continue
            self._process_vad(mono, torch)

    def _process_vad(self, mono: np.ndarray, torch) -> None:
        """Feed audio to Silero VAD and manage speech segments.

        Called from the VAD worker thread only. Uses _vad_lock for shared state.
        """
        # Accumulate into VAD-sized chunks (using raw bytes for thread safety)
        raw = mono.astype(np.float32).tobytes()
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
                    self._vad_buffer.extend(chunk.tolist())
                    while len(self._vad_buffer) > self._vad_pre_pad_samples:
                        self._vad_buffer.popleft()

                    if is_speech:
                        self._vad_speaking = True
                        self._vad_silence_start = None
                        self._queue.put(("vad_speech_start",))

                        # Start recording with pre-pad buffer
                        with self._lock:
                            pre_pad = np.array(list(self._vad_buffer), dtype=np.float32)
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
