"""
MultilingualSTT - Whisper with language detection (falls back to the English model if the
                  multilingual one is missing, so voice input never breaks)
MultilingualTTS - one Piper voice per language, loaded on demand; at most two extra voices
                  are kept in memory

With MULTILINGUAL_ENABLED = False both behave like the English-only versions.
"""
import gc
import threading
import time
from collections import OrderedDict

import numpy as np

from app.config import (LANGUAGES, MULTILINGUAL_ENABLED, PIPER_LENGTH_SCALE, WHISPER_COMPUTE_TYPE,
                        WHISPER_CPU_THREADS, WHISPER_DEVICE, WHISPER_DIR, WHISPER_MODEL,
                        WHISPER_MULTILINGUAL_MODEL)
from app.voice.errors import VoiceError
from app.voice.languages import LANG, voice_installed, voice_path
from app.voice.stt_engine import STTEngine
from app.voice.tts_engine import TTSEngine, clean_for_speech


class MultilingualSTT(STTEngine):
    def __init__(self):
        super().__init__(WHISPER_MULTILINGUAL_MODEL if MULTILINGUAL_ENABLED else WHISPER_MODEL)
        self.active_model = self.model_name   # The model that really loaded (may be the fallback)
        self.last_language = "en"             # Language of the most recent recording
        self.last_used = time.monotonic()

    @property
    def multilingual(self) -> bool:
        return not self.active_model.endswith(".en")

    def load(self):
        with self._lock:
            if self._model is not None:
                return
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise VoiceError("stt_lib", "The speech recognition library is missing. Run:  "
                                            "python -m pip install faster-whisper") from exc
            names = [self.model_name] + ([WHISPER_MODEL] if self.model_name != WHISPER_MODEL else [])
            last_error = None
            for name in names:                       # Preferred model first, English model as the fallback
                for local_only in (True, False):     # Offline copy first, then allow a download
                    try:
                        self._model = WhisperModel(
                            name, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE,
                            cpu_threads=WHISPER_CPU_THREADS, download_root=str(WHISPER_DIR),
                            local_files_only=local_only)
                        self.active_model = name
                        self.last_used = time.monotonic()
                        return
                    except Exception as exc:
                        last_error = exc
            raise VoiceError("stt_model", f"Could not load a speech model: {last_error}. "
                                          "The first run needs an internet connection to download it.")

    def transcribe(self, audio: np.ndarray) -> str:
        self.load()
        self.last_used = time.monotonic()
        preference = LANG.preference if MULTILINGUAL_ENABLED and self.multilingual else "en"
        language = None if preference == "auto" else preference    # None = let Whisper detect it
        try:
            segments, info = self._model.transcribe(
                audio, language=language, beam_size=1, vad_filter=True, condition_on_previous_text=False)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise VoiceError("stt_failed", f"Speech recognition failed: {exc}") from exc

        detected = getattr(info, "language", None) or "en"
        confident = float(getattr(info, "language_probability", 0.0) or 0.0) >= 0.6
        # A fixed preference is trusted; a detection must be confident and a configured language
        self.last_language = language or (detected if confident and detected in LANGUAGES else "en")
        return text

    def unload(self):
        """Free the model's memory (it reloads automatically the next time you speak)."""
        with self._lock:
            self._model = None
        gc.collect()


class MultilingualTTS(TTSEngine):
    MAX_EXTRA_VOICES = 2

    def __init__(self):
        super().__init__()
        self._language = "en"
        self._extra: OrderedDict = OrderedDict()   # Extra voices, least recently used first
        self._extra_lock = threading.Lock()

    def has_voice(self, code: str) -> bool:
        return voice_installed(code)

    def set_language(self, code: str):
        """Choose the voice for the next reply. An unknown or uninstalled language keeps English."""
        self._language = code if MULTILINGUAL_ENABLED and code in LANGUAGES and voice_installed(code) else "en"

    def _current_voice(self):
        if self._language == "en":
            self.load()
            return self._voice
        with self._extra_lock:
            if self._language in self._extra:
                self._extra.move_to_end(self._language)
                return self._extra[self._language]
            try:
                from piper import PiperVoice
                voice = PiperVoice.load(str(voice_path(self._language)))
            except Exception as exc:
                raise VoiceError("tts_model", f"Could not load the {self._language} voice: {exc}") from exc
            self._extra[self._language] = voice
            while len(self._extra) > self.MAX_EXTRA_VOICES:
                self._extra.popitem(last=False)      # Drop the least recently used voice
            return voice

    @property
    def sample_rate(self) -> int:
        return self._current_voice().config.sample_rate

    def synthesize(self, text: str):
        voice = self._current_voice()
        cleaned = clean_for_speech(text)
        if not cleaned:
            return
        from piper import SynthesisConfig
        config = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)
        for chunk in voice.synthesize(cleaned, syn_config=config):
            yield np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)