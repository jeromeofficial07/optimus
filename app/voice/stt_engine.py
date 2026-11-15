"""
STTEngine - speech-to-text with Faster-Whisper (offline, runs on the CPU).

Input : a numpy array of float32 samples, 16 kHz, mono (what MicRecorder produces)
Output: the recognised text
"""
import threading

import numpy as np

from app.config import (WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_DIR,
                        WHISPER_LANGUAGE, WHISPER_MODEL)
from app.voice.errors import VoiceError


class STTEngine:
    def __init__(self, model_name: str = WHISPER_MODEL):
        self.model_name = model_name
        self._model = None
        self._lock = threading.Lock()  # load() may be called from more than one thread

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self):
        """Load the model into RAM (a few seconds). Safe to call repeatedly."""
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise VoiceError(
                    "stt_lib",
                    "The speech recognition library is missing. Run:  "
                    "python -m pip install faster-whisper",
                ) from exc

            # First try the local copy only (fast, works offline); if the model has
            # never been downloaded, try again allowing a download.
            last_error = None
            for local_only in (True, False):
                try:
                    self._model = WhisperModel(
                        self.model_name,
                        device=WHISPER_DEVICE,
                        compute_type=WHISPER_COMPUTE_TYPE,
                        download_root=str(WHISPER_DIR),
                        local_files_only=local_only,
                    )
                    return
                except Exception as exc:
                    last_error = exc
            raise VoiceError(
                "stt_model",
                f"Could not load the speech model '{self.model_name}': {last_error}. "
                "The first run needs an internet connection to download it.",
            )

    def transcribe(self, audio: np.ndarray) -> str:
        """Convert recorded audio into text. Returns an empty string if no speech was found."""
        self.load()
        try:
            segments, _info = self._model.transcribe(
                audio,
                language=WHISPER_LANGUAGE,
                beam_size=1,                       # Fastest decoding
                vad_filter=True,                   # Ignore silence and background noise
                condition_on_previous_text=False,  # Avoids repeated phrases
            )
            # 'segments' is a lazy generator: the real work happens as we loop over it
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise VoiceError("stt_failed", f"Speech recognition failed: {exc}") from exc