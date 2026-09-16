"""
Generates the sound effects used by the program (assets/sounds/*.wav).

You normally don't need to run this -- the .wav files are already committed
with the project. This script only exists in case someone wants to
regenerate or tweak the tones later (it uses no external dependency, only
the Python standard library).

Usage: python tools/generate_sounds.py
"""
import math
import struct
import wave
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds"
SAMPLE_RATE = 44100


def _tone(freq: float, duration: float, volume: float = 0.3, fade_ms: float = 15) -> list[int]:
    n_samples = int(SAMPLE_RATE * duration)
    fade_samples = int(SAMPLE_RATE * fade_ms / 1000)
    samples = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        value = math.sin(2 * math.pi * freq * t)
        # simple fade-in/out to avoid "clicks" at the start/end of the sound
        if i < fade_samples:
            value *= i / fade_samples
        elif i > n_samples - fade_samples:
            value *= (n_samples - i) / fade_samples
        samples.append(int(value * volume * 32767))
    return samples


def _write_wav(path: Path, samples: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"".join(struct.pack("<h", s) for s in samples))


def main() -> None:
    # Success: two short rising tones (like a "positive confirmation")
    success = _tone(660, 0.09) + _tone(0, 0.02) + _tone(990, 0.12)
    _write_wav(OUTPUT_DIR / "success.wav", success)

    # Error: one short, low tone
    error = _tone(220, 0.18, volume=0.35)
    _write_wav(OUTPUT_DIR / "error.wav", error)

    # Info/neutral: a single short beep
    info = _tone(520, 0.1, volume=0.25)
    _write_wav(OUTPUT_DIR / "info.wav", info)

    print(f"Sounds written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
