"""
Voice styling: turns a normal Piper voice into a deep, authoritative, slightly robotic
"commander" voice. It is an original effect chain in plain numpy (no extra packages):

  1. deeper pitch     - speak faster, then stretch (lower pitch, same speaking speed)
  2. chest resonance  - boost the low frequencies, soften the harsh highs
  3. metallic edge    - a very short echo (comb filter) plus a touch of ring modulation
  4. warmth           - gentle saturation
  5. hall echo        - a few fading echoes

It shapes the STYLE of a speech voice. It does not copy any real person's voice.
"""
import numpy as np

from app.config import PIPER_LENGTH_SCALE, VOICE_ECHO, VOICE_PITCH, VOICE_ROBOT, VOICE_STYLE
from app.voice.multilingual import MultilingualTTS
from app.voice.tts_engine import clean_for_speech


class VoiceEffects:
    def __init__(self, sample_rate: int, pitch: float, robot: float, echo: float):
        self.sr = sample_rate
        self.pitch = min(1.0, max(0.7, pitch))     # Limits keep the voice understandable
        self.robot = min(0.6, max(0.0, robot))
        self.echo = min(1.0, max(0.0, echo))

    def process(self, samples: np.ndarray) -> np.ndarray:
        """Takes 16-bit audio from Piper and returns 16-bit styled audio."""
        if len(samples) < 256:
            return samples
        x = samples.astype(np.float32) / 32768.0
        sr = self.sr

        # 1. Pitch: the audio was synthesised faster by 'pitch', so stretching it restores the
        #    original speed while lowering the pitch by the same factor.
        if self.pitch < 1.0:
            length = int(len(x) / self.pitch)
            x = np.interp(np.linspace(0, len(x) - 1, length), np.arange(len(x)), x).astype(np.float32)

        # 2. Chest resonance and softer highs, shaped in the frequency domain
        spectrum = np.fft.rfft(x)
        freq = np.fft.rfftfreq(len(x), 1.0 / sr)
        gain = 1.0 + 1.4 * np.exp(-((freq - 140.0) / 110.0) ** 2)   # A bump around 140 Hz
        gain *= 1.0 / (1.0 + (freq / 6500.0) ** 4)                  # Gentle roll-off above ~6.5 kHz
        x = np.fft.irfft(spectrum * gain, n=len(x)).astype(np.float32)

        # 3. Metallic edge: a very short echo plus a little ring modulation
        if self.robot > 0:
            delay = max(1, int(sr * 0.0042))
            metal = x.copy()
            metal[delay:] += self.robot * 0.9 * x[:-delay]
            t = np.arange(len(x), dtype=np.float32) / sr
            ring = x * np.sin(2 * np.pi * 95.0 * t).astype(np.float32)
            x = metal + self.robot * 0.25 * ring

        # 4. Warmth: normalise, then saturate softly
        peak = float(np.max(np.abs(x)))
        if peak <= 0:
            return np.zeros(len(x), dtype=np.int16)
        x = np.tanh(1.4 * (x / peak)).astype(np.float32)

        # 5. Hall echo (a silent tail is added so the echoes can ring out)
        if self.echo > 0:
            tail = int(sr * 0.12)
            padded = np.concatenate([x, np.zeros(tail, dtype=np.float32)])
            out = padded.copy()
            for delay_s, level in ((0.032, 0.50), (0.061, 0.33), (0.097, 0.20)):
                k = int(sr * delay_s)
                out[k:] += self.echo * level * padded[:-k]
            x = out

        peak = float(np.max(np.abs(x)))
        return (x * (0.9 / peak) * 32767).astype(np.int16)


class StyledTTS(MultilingualTTS):
    """The multilingual voice engine with the commander effects applied to every sentence."""

    def __init__(self, pitch=None, robot=None, echo=None, enabled=None):
        super().__init__()
        self._pitch = VOICE_PITCH if pitch is None else pitch
        self._robot = VOICE_ROBOT if robot is None else robot
        self._echo = VOICE_ECHO if echo is None else echo
        self._enabled = (VOICE_STYLE == "prime") if enabled is None else enabled
        self._effects: dict[int, VoiceEffects] = {}

    def synthesize(self, text: str):
        if not self._enabled:
            yield from super().synthesize(text)     # The plain voice
            return
        voice = self._current_voice()
        cleaned = clean_for_speech(text)
        if not cleaned:
            return
        from piper import SynthesisConfig
        pitch = min(1.0, max(0.7, self._pitch))
        config = SynthesisConfig(length_scale=PIPER_LENGTH_SCALE * pitch)   # Faster now, stretched later
        rate = voice.config.sample_rate
        effects = self._effects.get(rate)
        if effects is None:
            effects = self._effects[rate] = VoiceEffects(rate, pitch, self._robot, self._echo)
        for chunk in voice.synthesize(cleaned, syn_config=config):
            yield effects.process(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))