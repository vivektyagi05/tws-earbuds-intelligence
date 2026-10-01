"""speech_enhancement.py - single-microphone statistical speech enhancement.

Algorithm: Wiener gain  G = xi / (1 + xi)  per time-frequency bin, where
  gamma = |X|^2 / noise_psd                       (a-posteriori SNR)
  xi    = a*G_prev^2*gamma_prev + (1-a)*max(gamma-1,0)   (decision-directed, Ephraim-Malah)
Then: gain floor (limits musical noise/over-suppression) + 3-bin frequency smoothing.

This is classical DSP, not AI: input = noisy STFT + noise PSD, output = mask.
A production system would replace compute_gain() with a neural mask estimator
(e.g. small GRU/CRN) and keep everything around it.
"""
import numpy as np


def compute_gain(power, noise_psd, alpha=0.98, floor_db=-14.0, xi_min_db=-25.0):
    floor = 10 ** (floor_db / 20)
    xi_min = 10 ** (xi_min_db / 10)
    gamma = np.maximum(power / noise_psd, 1e-6)
    G = np.empty_like(power)
    G_prev = np.ones(power.shape[0])
    gamma_prev = np.ones(power.shape[0])
    for t in range(power.shape[1]):
        xi = alpha * (G_prev ** 2) * gamma_prev + (1 - alpha) * np.maximum(gamma[:, t] - 1, 0)
        xi = np.maximum(xi, xi_min)
        g = np.maximum(xi / (1 + xi), floor)
        G[:, t] = g
        G_prev, gamma_prev = g, gamma[:, t]
    kernel = np.array([0.25, 0.5, 0.25])               # smooth across frequency
    G = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="same"), 0, G)
    return np.clip(G, floor, 1.0)


def spectral_subtraction_gain(power, noise_psd, over=1.5, floor_db=-14.0):
    """Baseline for comparison: classic power spectral subtraction."""
    floor = 10 ** (floor_db / 20)
    g = np.sqrt(np.maximum(1 - over * noise_psd / np.maximum(power, 1e-12), 0))
    return np.clip(g, floor, 1.0)


def apply_gain(Z, G):
    return Z * G
