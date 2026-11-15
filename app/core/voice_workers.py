"""
Background threads for voice, so the GUI never freezes.

MicRecorder     - records the microphone while the push-to-talk key is held
TranscribeWorker- converts a recording into text (Faster-Whisper)
SpeechWorker    - a long-lived thread that speaks queued sentences (Piper)
VoiceInitWorker - loads the speech models at startup
"""
import queue
import threading
import time

import numpy as np
from PySide6.QtCore import QThread, Signal

from app.config import MAX_RECORD_SECONDS, SAMPLE_RATE
from app.voice.errors import VoiceError
from app.voice.stt_engine import STTEngine
from app.voice.tts_engine import TTSEngine


def _to_16k(audio: np.ndarray, rate: int) -> np.ndarray:
    """Convert audio recorded at another sample rate to the 16 kHz that Whisper needs."""
    if rate == SAMPLE_RATE:
        return audio
    if rate % SAMPLE_RATE == 0:  # e.g. 48000 -> 16000: average every 3 samples
        factor = rate // SAMPLE_RATE
        usable = len(audio) - len(audio) % factor
        return audio[:usable].reshape(-1, factor).mean(axis=1).astype(np.float32)
    target_length = int(len(audio) * SAMPLE_RATE / rate)  # Otherwise interpolate
    positions = np.linspace(0, len(audio) - 1, target_length)
    return np.interp(positions, np.arange(len(audio)), audio).astype(np.float32)


# ====================================================================== recording
class MicRecorder(QThread):
    level = Signal(float)       # Current loudness 0..1 (drives the level meter)
    recorded = Signal(object)   # numpy float32 array, 16 kHz mono
    failed = Signal(str, str)   # (error kind, friendly message)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_requested = False
        self._chunks: list[np.ndarray] = []
        self._level = 0.0

    def stop_recording(self):
        """Called from the GUI when the push-to-talk key/button is released."""
        self._stop_requested = True

    def _callback(self, indata, frames, time_info, status):
        """Called by the audio driver (on its own thread) with each block of microphone data."""
        mono = indata[:, 0].copy()
        self._chunks.append(mono)
        rms = float(np.sqrt(np.mean(mono * mono)))
        self._level = min(1.0, rms * 12.0)

    def _open_stream(self):
        """Open the default microphone. Tries 16 kHz first, then the device's own rate."""
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise VoiceError("audio_lib", "The audio library is missing. Run:  "
                                          "python -m pip install sounddevice") from exc
        try:
            device = sd.query_devices(kind="input")
        except Exception as exc:
            raise VoiceError(
                "no_mic",
                "No microphone was found. Plug one in or enable it in Windows Sound "
                "settings, then try again.",
            ) from exc

        rates = [SAMPLE_RATE]
        default_rate = int(device["default_samplerate"])
        if default_rate != SAMPLE_RATE:
            rates.append(default_rate)

        last_error = None
        for rate in rates:
            try:
                stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                        callback=self._callback)
                return stream, rate
            except Exception as exc:
                last_error = exc
        raise VoiceError("mic_open", f"Could not open the microphone: {last_error}")

    def run(self):
        try:
            stream, rate = self._open_stream()
        except VoiceError as err:
            self.failed.emit(err.kind, err.message)
            return

        try:
            with stream:  # Starts capturing; stops and closes when the block ends
                started = time.monotonic()
                while not self._stop_requested and time.monotonic() - started < MAX_RECORD_SECONDS:
                    self.msleep(40)
                    self.level.emit(self._level)
        except Exception as exc:
            self.failed.emit("mic_open", f"The microphone stopped working: {exc}")
            return

        if not self._chunks:
            self.recorded.emit(np.zeros(0, dtype=np.float32))
            return
        audio = np.concatenate(self._chunks)

        # A completely flat signal usually means Windows is blocking microphone access
        if len(audio) > rate * 0.3 and float(np.max(np.abs(audio))) == 0.0:
            self.failed.emit(
                "mic_silent",
                "The microphone is only giving silence. Open Windows Settings > Privacy & "
                "security > Microphone and make sure microphone access is on, including "
                "'Let desktop apps access your microphone'.",
            )
            return
        self.recorded.emit(_to_16k(audio, rate))


# ====================================================================== transcription
class TranscribeWorker(QThread):
    transcribed = Signal(str)
    failed = Signal(str, str)

    def __init__(self, stt: STTEngine, audio: np.ndarray, parent=None):
        super().__init__(parent)
        self._stt = stt
        self._audio = audio

    def run(self):
        try:
            text = self._stt.transcribe(self._audio)
        except VoiceError as err:
            self.failed.emit(err.kind, err.message)
            return
        except Exception as exc:
            self.failed.emit("stt_failed", f"Speech recognition failed: {exc}")
            return
        self.transcribed.emit(text)


# ====================================================================== speaking
_END = object()   # Marks "the reply is complete" in the queue
_QUIT = object()  # Tells the thread to exit


class SpeechWorker(QThread):
    """
    One long-lived thread that speaks sentences in the order they are queued.
    The GUI calls speak() for each sentence and end_of_reply() when the answer is
    complete. For every end_of_reply()/stop_speaking() call, exactly one
    speaking_finished signal comes back.
    """
    speaking_started = Signal()
    speaking_finished = Signal()
    failed = Signal(str, str)

    def __init__(self, tts: TTSEngine, parent=None):
        super().__init__(parent)
        self._tts = tts
        self._queue: queue.Queue = queue.Queue()
        self._abort = threading.Event()  # Set = stop talking right now

    # ----- called from the GUI thread -----
    def speak(self, text: str):
        self._queue.put(text)

    def end_of_reply(self):
        self._queue.put(_END)

    def stop_speaking(self):
        """Cut off the current sentence and discard everything still waiting."""
        self._abort.set()
        ends = 0
        quit_seen = False
        try:
            while True:
                item = self._queue.get_nowait()
                if item is _END:
                    ends += 1          # Keep these so every reply still gets its signal
                elif item is _QUIT:
                    quit_seen = True
        except queue.Empty:
            pass
        for _ in range(ends + 1):      # +1 for this stop request
            self._queue.put(_END)
        if quit_seen:
            self._queue.put(_QUIT)

    def shutdown(self):
        """Ask the thread to exit (used when the window closes)."""
        self._abort.set()
        self._queue.put(_QUIT)

    # ----- runs on the worker thread -----
    def run(self):
        stream = None
        started = False
        while True:
            item = self._queue.get()
            if item is _QUIT:
                break
            if item is _END:
                stream = self._close_stream(stream, drain=not self._abort.is_set())
                self._abort.clear()
                started = False
                self.speaking_finished.emit()
                continue
            if self._abort.is_set():
                continue  # A stop was requested: throw away sentences queued before it
            try:
                if not started:
                    started = True
                    self.speaking_started.emit()
                if stream is None:
                    stream = self._open_stream()
                self._play(stream, item)
            except VoiceError as err:
                self._abort.set()
                self.failed.emit(err.kind, err.message)
            except Exception as exc:
                self._abort.set()
                self.failed.emit("audio_out", f"Audio playback failed: {exc}")
        self._close_stream(stream, drain=False)

    def _open_stream(self):
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise VoiceError("audio_lib", "The audio library is missing. Run:  "
                                          "python -m pip install sounddevice") from exc
        try:
            stream = sd.OutputStream(samplerate=self._tts.sample_rate, channels=1, dtype="int16")
            stream.start()
            return stream
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError("audio_out", f"Could not open the speakers: {exc}") from exc

    def _play(self, stream, text: str):
        """Synthesize one sentence and play it in 0.1 second blocks so a stop is instant."""
        block = max(1, self._tts.sample_rate // 10)
        for samples in self._tts.synthesize(text):
            for start in range(0, len(samples), block):
                if self._abort.is_set():
                    return
                stream.write(samples[start:start + block].reshape(-1, 1))

    @staticmethod
    def _close_stream(stream, drain: bool):
        """Close the speakers. drain=True lets the last audio finish; False cuts it off."""
        if stream is not None:
            try:
                stream.stop() if drain else stream.abort()
                stream.close()
            except Exception:
                pass
        return None


# ====================================================================== startup loading
class VoiceInitWorker(QThread):
    loaded = Signal(str, str)  # (speech-recognition error, speech-synthesis error); "" = OK

    def __init__(self, stt: STTEngine, tts: TTSEngine, parent=None):
        super().__init__(parent)
        self._stt = stt
        self._tts = tts

    def run(self):
        stt_error = ""
        tts_error = ""
        try:
            self._stt.load()
        except VoiceError as err:
            stt_error = f"Voice input is unavailable. {err.message}"
        except Exception as exc:
            stt_error = f"Voice input is unavailable. {exc}"
        try:
            self._tts.load()
        except VoiceError as err:
            tts_error = f"Spoken replies are unavailable. {err.message}"
        except Exception as exc:
            tts_error = f"Spoken replies are unavailable. {exc}"
        self.loaded.emit(stt_error, tts_error)