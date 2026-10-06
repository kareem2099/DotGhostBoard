"""
scripts/generate_sounds.py
──────────────────────────
Generates custom synthesized UI sound presets for DotGhostBoard
using standard library `wave` and `math` (zero external dependencies).
"""

import math
import os
import struct
import wave

SAMPLE_RATE = 44100


def save_wav(filename: str, samples: list[float]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with wave.open(filename, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        raw = bytearray()
        for s in samples:
            # Clamp to -1.0 .. 1.0 and scale to 16-bit signed integer
            clamped = max(-1.0, min(1.0, s))
            val = int(clamped * 32767)
            raw.extend(struct.pack("<h", val))
        w.writeframes(raw)
    print(f"✓ Generated: {filename} ({len(samples)} samples, {len(samples)/SAMPLE_RATE*1000:.1f}ms)")


def generate_pop(filename: str) -> None:
    """Soft warm bubble pop (downward pitch sweep)."""
    duration = 0.075  # 75 ms
    num_samples = int(duration * SAMPLE_RATE)
    samples = []
    phase = 0.0

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        progress = t / duration

        # Frequency sweeps down smoothly from 540Hz to 260Hz
        freq = 540.0 - 280.0 * (progress ** 1.3)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE

        # Sine wave with a touch of 2nd harmonic warmth
        wave_val = math.sin(phase) + 0.22 * math.sin(2.0 * phase)

        # Attack and exponential decay envelope
        attack = min(1.0, progress / 0.08)
        decay = math.exp(-6.5 * progress)
        volume = 0.45 * attack * decay

        samples.append(volume * wave_val)

    save_wav(filename, samples)


def generate_chime(filename: str) -> None:
    """Crystal marimba chime (A5 + E6 harmonic bell)."""
    duration = 0.090  # 90 ms
    num_samples = int(duration * SAMPLE_RATE)
    samples = []

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        progress = t / duration

        # Two pure harmonic tones
        f1 = 880.0  # A5
        f2 = 1320.0  # E6
        tone1 = math.sin(2.0 * math.pi * f1 * t)
        tone2 = math.sin(2.0 * math.pi * f2 * t)
        combined = 0.65 * tone1 + 0.35 * tone2

        # Fast attack (3ms) and exponential decay
        attack = min(1.0, progress / 0.05)
        decay = math.exp(-5.5 * progress)
        volume = 0.40 * attack * decay

        samples.append(volume * combined)

    save_wav(filename, samples)


def generate_click(filename: str) -> None:
    """Crisp tactile mechanical switch click (fast snappy 32ms transient)."""
    duration = 0.035  # 35 ms
    num_samples = int(duration * SAMPLE_RATE)
    samples = []
    phase = 0.0

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        progress = t / duration

        # Fast sweep downward
        freq = 2400.0 * (1.0 - 0.7 * progress)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        wave_val = math.sin(phase)

        attack = min(1.0, progress / 0.04)
        decay = math.exp(-12.0 * progress)
        volume = 0.50 * attack * decay

        samples.append(volume * wave_val)

    save_wav(filename, samples)


def generate_beam(filename: str) -> None:
    """Subtle futuristic soft ping (C6 + G6)."""
    duration = 0.080  # 80 ms
    num_samples = int(duration * SAMPLE_RATE)
    samples = []

    for i in range(num_samples):
        t = i / SAMPLE_RATE
        progress = t / duration

        f1 = 1046.5  # C6
        f2 = 1567.98  # G6
        tone = 0.7 * math.sin(2.0 * math.pi * f1 * t) + 0.3 * math.sin(2.0 * math.pi * f2 * t)

        attack = min(1.0, progress / 0.06)
        decay = math.exp(-6.0 * progress)
        volume = 0.38 * attack * decay

        samples.append(volume * tone)

    save_wav(filename, samples)


def main():
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "assets", "sounds")
    generate_pop(os.path.join(base_dir, "ghost_pop.wav"))
    generate_chime(os.path.join(base_dir, "ghost_chime.wav"))
    generate_click(os.path.join(base_dir, "ghost_click.wav"))
    generate_beam(os.path.join(base_dir, "ghost_beam.wav"))


if __name__ == "__main__":
    main()
