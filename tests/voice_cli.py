"""
Voice test without the GUI.
Run from the project root with:   python -m tests.voice_cli
"""
import time

import numpy as np
import sounddevice as sd

from app.config import SAMPLE_RATE
from app.voice.errors import VoiceError
from app.voice.stt_engine import STTEngine
from app.voice.tts_engine import TTSEngine


def main():
    print("Microphone:", sd.query_devices(kind="input")["name"])
    print("Speakers  :", sd.query_devices(kind="output")["name"])

    stt, tts = STTEngine(), TTSEngine()
    try:
        print("\nLoading speech recognition (a few seconds)...")
        stt.load()
        print("Loading voice...")
        tts.load()
    except VoiceError as err:
        print(f"[{err.kind}] {err.message}")
        return

    input("\nPress Enter, then speak for 4 seconds...")
    audio = sd.rec(int(4 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    audio = audio[:, 0]
    print(f"Peak level: {np.abs(audio).max():.3f}  (should be clearly above 0.01 while you speak)")

    started = time.time()
    text = stt.transcribe(audio)
    print(f"Heard ({time.time() - started:.1f}s): {text!r}")
    if not text:
        print("Nothing recognised. Try again, closer to the microphone.")
        return

    print("Speaking...")
    with sd.OutputStream(samplerate=tts.sample_rate, channels=1, dtype="int16") as out:
        for samples in tts.synthesize(f"You said: {text}"):
            out.write(samples.reshape(-1, 1))
    print("Done.")


if __name__ == "__main__":
    main()