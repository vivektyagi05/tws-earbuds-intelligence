"""noise_analysis.py - estimate WHAT the noise is, per frequency bin, over time.

Method: causal minimum-statistics-style tracker (Martin 2001, simplified).
 1. smooth |X|^2 over time (recursive, alpha=0.9)
 2. take the minimum over the last ~1.5 s per frequency bin
 3. multiply by a bias-compensation factor (min of smoothed noisy power
    underestimates the mean; 1.6 is an empirical constant here)
Speech is sparse in time per bin, so the running minimum mostly follows noise.
Weakness: slow to follow sudden noise increases (e.g. a passing truck).
"""
from dataclasses import dataclass
import numpy as np
from scipy.ndimage import minimum_filter1d


def estimate_noise_psd(power, hop_s, window_s=1.5, alpha=0.9, bias=1.6):
    n_bins, n_frames = power.shape
    smooth = np.empty_like(power)
    smooth[:, 0] = power[:, 0]
    for t in range(1, n_frames):
        smooth[:, t] = alpha * smooth[:, t - 1] + (1 - alpha) * power[:, t]
    w = max(3, int(window_s / hop_s)) | 1                       # odd window
    # origin=(w-1)//2 -> window covers [t-(w-1), t]: causal, streamable
    mins = minimum_filter1d(smooth, size=w, axis=1, mode="nearest", origin=(w - 1) // 2)
    return np.maximum(mins * bias, 1e-12)


# NOTE: the VAD only feeds the noise profile (speech_activity); it does NOT gate the Wiener gain.
def speech_presence(power, noise_psd, freqs, thresh_db=6.0):
    """Frame-level energy VAD: speech band must exceed noise estimate by thresh_db."""
    m = (freqs >= 300) & (freqs <= 3400)
    ratio = power[m].sum(axis=0) / (noise_psd[m].sum(axis=0) + 1e-20)
    return 10 * np.log10(ratio + 1e-12) > thresh_db


@dataclass
class NoiseProfile:
    noise_level_db: float       # estimated noise power, dB re full-scale^2
    low_freq_ratio: float       # share of noise energy below 250 Hz
    flatness: float             # 0 (tonal/coloured) .. 1 (white)
    speech_activity: float      # fraction of frames flagged as speech
    label: str                  # heuristic label, NOT a trained classifier


def profile_noise(noise_psd, power, freqs, vad):
    mean_psd = noise_psd.mean(axis=1)
    total = mean_psd.sum() + 1e-20
    low = mean_psd[freqs < 250].sum() / total
    flat = float(np.exp(np.mean(np.log(mean_psd + 1e-20))) / (np.mean(mean_psd) + 1e-20))
    if low > 0.80:
        label = "low-frequency dominated (wind / traffic-like)"
    elif flat > 0.35:
        label = "broadband (hiss / crowd / HVAC-like)"
    else:
        label = "coloured / mixed"
    level = 10 * np.log10(mean_psd.sum() + 1e-20)
    return NoiseProfile(float(level), float(low), flat, float(vad.mean()), label)
