"""audio_preprocessing.py - conditioning + time/frequency analysis.

Production equivalent: fixed-point DC-block/high-pass biquads and a streaming
STFT (or filterbank) in the DSP, run frame-by-frame.
"""
from dataclasses import dataclass
import numpy as np
from scipy import signal

N_FFT = 512      # 32 ms @16 kHz
HOP = 128        # 8 ms


def preprocess(x, sr, hp_hz=70.0):
    """Remove DC and sub-70 Hz rumble (mic handling noise / wind thump)."""
    x = x - np.mean(x)
    sos = signal.butter(2, hp_hz, "high", fs=sr, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)   # causal -> streamable


def stft(x, sr, n_fft=N_FFT, hop=HOP):
    f, t, Z = signal.stft(x, fs=sr, window="hann", nperseg=n_fft,
                          noverlap=n_fft - hop, boundary="zeros", padded=True)
    return f, t, Z


def istft(Z, sr, length, n_fft=N_FFT, hop=HOP):
    _, x = signal.istft(Z, fs=sr, window="hann", nperseg=n_fft,
                        noverlap=n_fft - hop, boundary=True)
    x = x[:length]
    if len(x) < length:
        x = np.pad(x, (0, length - len(x)))
    return x.astype(np.float32)


@dataclass
class WaveformStats:
    duration_s: float
    rms_dbfs: float
    peak_dbfs: float
    crest_factor_db: float


def waveform_stats(x, sr) -> WaveformStats:
    rms = np.sqrt(np.mean(x ** 2)) + 1e-12
    pk = np.max(np.abs(x)) + 1e-12
    return WaveformStats(len(x) / sr, 20 * np.log10(rms), 20 * np.log10(pk),
                         20 * np.log10(pk / rms))


def band_energy_report(freqs, power):
    """Share of long-term energy in three bands (low / speech / high)."""
    mean_p = power.mean(axis=1)
    total = mean_p.sum() + 1e-20
    bands = {"<250Hz (wind/traffic rumble)": (0, 250),
             "250-4000Hz (speech)": (250, 4000),
             ">4000Hz": (4000, 1e9)}
    return {k: float(mean_p[(freqs >= lo) & (freqs < hi)].sum() / total)
            for k, (lo, hi) in bands.items()}
