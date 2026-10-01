"""audio_input.py - audio acquisition layer.

On a real earbud this module is replaced by the microphone/ADC driver delivering
fixed-size frames (e.g. 8-10 ms) from 2+ microphones. Here it (a) loads files and
(b) synthesises SIMULATED test material so the prototype runs with no assets.
"""
from math import gcd
import numpy as np
import soundfile as sf
from scipy import signal

TARGET_SR = 16000


class AudioInputError(Exception):
    pass


def load_audio(path: str, target_sr: int = TARGET_SR):
    """Load a WAV/FLAC file -> mono float32 at target_sr."""
    try:
        data, sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception as exc:  # unreadable / missing / unsupported
        raise AudioInputError(f"Cannot read '{path}': {exc}") from exc
    if data.size == 0:
        raise AudioInputError(f"'{path}' contains no samples")
    mono = data.mean(axis=1)
    if sr != target_sr:
        g = gcd(sr, target_sr)
        mono = signal.resample_poly(mono, target_sr // g, sr // g).astype(np.float32)
    return mono, target_sr


def _resonator(x, f, bw, sr):
    r = np.exp(-np.pi * bw / sr)
    a = [1.0, -2 * r * np.cos(2 * np.pi * f / sr), r * r]
    return signal.lfilter([1 - r], a, x)


def _scale_rms(x, rms):
    return x * (rms / (np.sqrt(np.mean(x ** 2)) + 1e-12))


def synth_speech_like(duration=8.0, sr=TARGET_SR, seed=0):
    """SIMULATED voiced-speech-like signal: harmonic source with moving pitch,
    shaped by vowel formant resonators, with syllable gating and pauses.
    NOT real speech - pass --speech file.wav to use real recordings."""
    rng = np.random.default_rng(seed)
    n = int(duration * sr)
    t = np.arange(n) / sr
    f0 = 115 + 25 * np.sin(2 * np.pi * 0.35 * t) + 8 * np.sin(2 * np.pi * 1.7 * t + seed)
    phase = 2 * np.pi * np.cumsum(f0) / sr
    src = np.zeros(n)
    for k in range(1, 40):
        if k * f0.max() < sr / 2 - 200:
            src += np.sin(k * phase + rng.uniform(0, 6.28)) / k
    vowels = [(700, 1200, 2600), (300, 2300, 3000), (350, 800, 2500), (550, 1800, 2600)]
    filtered = []
    for fm in vowels:
        y = src
        for f, bw in zip(fm, (90, 110, 160)):
            y = _resonator(y, f, bw, sr)
        filtered.append(y)
    gains = np.zeros((len(vowels), n))
    hop, length, pos = int(0.26 * sr), int(0.34 * sr), 0
    while pos < n:
        v = rng.integers(len(vowels))
        seg = np.hanning(length)
        end = min(n, pos + length)
        gains[v, pos:end] += seg[: end - pos]
        pos += hop
        if rng.random() < 0.18:           # pause
            pos += int(rng.uniform(0.3, 0.6) * sr)
    out = sum(g * f for g, f in zip(gains, filtered))
    return _scale_rms(out, 0.1).astype(np.float32)


def synth_noise(kind, n, sr=TARGET_SR, seed=1):
    """SIMULATED environmental noise. kind: traffic | wind | cafe | mixed"""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr
    w = rng.standard_normal(n)
    if kind == "traffic":      # engine rumble + road hiss + passing-vehicle swells
        sos = signal.butter(2, 450, "low", fs=sr, output="sos")
        rumble = signal.sosfilt(sos, w)
        sos2 = signal.butter(2, [800, 3000], "band", fs=sr, output="sos")
        hiss = 0.15 * signal.sosfilt(sos2, rng.standard_normal(n))
        swell = 1 + 1.2 * np.exp(-((t % 4.0 - 2.0) ** 2) / 0.3)
        out = (rumble + hiss) * swell
    elif kind == "wind":       # gusty, strongly low-frequency, bursty
        sos = signal.butter(3, 220, "low", fs=sr, output="sos")
        gust = 0.4 + np.abs(signal.sosfilt(signal.butter(1, 1.5, "low", fs=sr, output="sos"),
                                           rng.standard_normal(n))) * 12
        out = signal.sosfilt(sos, w) * gust
    elif kind == "cafe":       # 4-talker babble + broadband clatter floor
        out = sum(synth_speech_like(n / sr, sr, seed=100 + i) for i in range(4))
        out = out + 0.15 * _scale_rms(rng.standard_normal(n), np.sqrt(np.mean(out ** 2)))
    elif kind == "mixed":
        a = _scale_rms(synth_noise("traffic", n, sr, seed), 1)
        b = _scale_rms(synth_noise("wind", n, sr, seed + 1), 1)
        out = a + 0.8 * b
    else:
        raise ValueError(f"unknown noise kind '{kind}'")
    return out.astype(np.float32)


def mix_at_snr(speech, noise, snr_db):
    """Scale noise so that speech-to-noise power ratio == snr_db (whole-file)."""
    ps = np.mean(speech ** 2)
    pn = np.mean(noise ** 2) + 1e-20
    scaled = noise * np.sqrt(ps / (pn * 10 ** (snr_db / 10)))
    return (speech + scaled).astype(np.float32), scaled.astype(np.float32)
