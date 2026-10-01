"""metrics.py - measurable comparison. Intrusive metrics need the clean reference,
which we have only because the noisy input is SIMULATED by us."""
import numpy as np


def snr_db(clean, other_noise):
    return 10 * np.log10((np.sum(clean ** 2) + 1e-20) / (np.sum(other_noise ** 2) + 1e-20))


def si_sdr(ref, est):
    """Scale-invariant SDR (Le Roux 2019). Higher is better."""
    ref, est = ref - ref.mean(), est - est.mean()
    alpha = np.dot(est, ref) / (np.dot(ref, ref) + 1e-20)
    target = alpha * ref
    noise = est - target
    return 10 * np.log10((np.sum(target ** 2) + 1e-20) / (np.sum(noise ** 2) + 1e-20))


def component_report(speech_in, noise_in, speech_out, noise_out, noisy, enhanced, clean):
    """Because the mask is linear, push speech and noise through it separately
    ('shadow filtering') to separate suppression from speech distortion."""
    return {
        "input_snr_db": snr_db(speech_in, noise_in),
        "output_snr_db": snr_db(speech_out, noise_out),
        "snr_improvement_db": snr_db(speech_out, noise_out) - snr_db(speech_in, noise_in),
        "noise_attenuation_db": 10 * np.log10(np.sum(noise_in ** 2) / (np.sum(noise_out ** 2) + 1e-20)),
        "speech_attenuation_db": 10 * np.log10(np.sum(speech_in ** 2) / (np.sum(speech_out ** 2) + 1e-20)),
        "si_sdr_in_db": si_sdr(clean, noisy),
        "si_sdr_out_db": si_sdr(clean, enhanced),
    }
