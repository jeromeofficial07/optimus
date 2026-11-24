"""
Hear the voice styles side by side, and check the effects code.
Run from the project root:   python -m tests.voice_style_cli
"""
import numpy as np
import sounddevice as sd

from app.voice.errors import VoiceError
from app.voice.styled import StyledTTS, VoiceEffects

SENTENCE = "Systems online. I am ready to assist you. Tell me what you need."


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def main():
    print("--- effects code ---")
    effects = VoiceEffects(22050, 0.88, 0.30, 0.45)
    tone = (np.sin(2 * np.pi * 200 * np.arange(22050) / 22050) * 12000).astype(np.int16)
    out = effects.process(tone)
    check("output is 16-bit audio", out.dtype == np.int16)
    check("audio is stretched to keep the speaking speed", len(out) > len(tone))
    check("no clipping", int(np.max(np.abs(out.astype(np.int32)))) <= 32767)
    check("silence stays silent", int(np.max(np.abs(effects.process(np.zeros(2000, dtype=np.int16))))) == 0)

    print("\n--- listen ---")
    variants = [
        ("plain voice (no effects)", dict(enabled=False)),
        ("commander voice (your config.py settings)", dict()),
        ("deeper and more metallic", dict(pitch=0.82, robot=0.45, echo=0.55)),
        ("deep and clean (less robotic)", dict(pitch=0.86, robot=0.12, echo=0.30)),
    ]
    for label, options in variants:
        tts = StyledTTS(**options)
        try:
            tts.load()
        except VoiceError as err:
            print(f"[{err.kind}] {err.message}")
            return
        print(f"Playing: {label}")
        with sd.OutputStream(samplerate=tts.sample_rate, channels=1, dtype="int16") as stream:
            for samples in tts.synthesize(SENTENCE):
                stream.write(samples.reshape(-1, 1))
    print("\nDone. Put the settings of your favourite into config.py (VOICE_PITCH, VOICE_ROBOT, VOICE_ECHO).")


if __name__ == "__main__":
    main()