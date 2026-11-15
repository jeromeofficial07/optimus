"""
Text-to-speech with Piper (offline, runs on the CPU).

TTSEngine        - turns text into audio samples
SentenceSplitter - cuts a streaming answer into sentences so speech can start early
clean_for_speech - removes Markdown symbols so they are not read aloud
"""
import re
import threading
from collections.abc import Iterator

import numpy as np

from app.config import PIPER_LENGTH_SCALE, PIPER_MODEL_PATH, PIPER_VOICE
from app.voice.errors import VoiceError

_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")       # [text](url) -> text
_MD_SYMBOLS = re.compile(r"[*`#>~|]+")                # bold, code, headings, quotes
_LIST_MARKER = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+")  # "- item" / "1. item"


def clean_for_speech(text: str) -> str:
    """Strip Markdown so Piper reads words, not symbols. Returns '' if nothing is speakable."""
    text = _MD_LINK.sub(r"\1", text)
    text = _LIST_MARKER.sub("", text)
    text = _MD_SYMBOLS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if re.search(r"\w", text) else ""


class SentenceSplitter:
    """
    Feed it the answer piece by piece with feed(); it returns complete sentences as soon
    as they are ready. Call flush() at the end for whatever is left over.
    """

    _BOUNDARY = re.compile(r"(?<=[.!?:])\s+|\n+")
    _MIN_LENGTH = 25  # Very short fragments ("1.", "Yes.") are merged into the next sentence

    def __init__(self):
        self._buffer = ""
        self._carry = ""

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        parts = self._BOUNDARY.split(self._buffer)
        self._buffer = parts.pop()  # The last piece may be an unfinished sentence
        sentences = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if self._carry:
                part = f"{self._carry} {part}"
                self._carry = ""
            if len(part) < self._MIN_LENGTH:
                self._carry = part
            else:
                sentences.append(part)
        return sentences

    def flush(self) -> list[str]:
        rest = f"{self._carry} {self._buffer}".strip()
        self._buffer = ""
        self._carry = ""
        return [rest] if rest else []


class TTSEngine:
    def __init__(self):
        self._voice = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._voice is not None

    @property
    def sample_rate(self) -> int:
        """Sample rate of the loaded voice (needed to open the audio output)."""
        self.load()
        return self._voice.config.sample_rate

    def load(self):
        """Load the Piper voice. Safe to call repeatedly."""
        with self._lock:
            if self._voice is not None:
                return
            if not PIPER_MODEL_PATH.exists():
                raise VoiceError(
                    "tts_model",
                    f"The voice file '{PIPER_VOICE}' was not found in models\\piper. "
                    "Download it with the Phase 4 Step 5 command.",
                )
            try:
                from piper import PiperVoice
            except ImportError as exc:
                raise VoiceError(
                    "tts_lib",
                    "The speech synthesis library is missing. Run:  python -m pip install piper-tts",
                ) from exc
            try:
                self._voice = PiperVoice.load(str(PIPER_MODEL_PATH))
            except Exception as exc:
                raise VoiceError("tts_model", f"Could not load the voice: {exc}") from exc

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        """
        Turn text into audio. Yields numpy int16 arrays (one per sentence Piper detects),
        so playback can begin before the whole text is synthesised.
        """
        self.load()
        cleaned = clean_for_speech(text)
        if not cleaned:
            return
        from piper import SynthesisConfig
        config = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE)
        for chunk in self._voice.synthesize(cleaned, syn_config=config):
            yield np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)