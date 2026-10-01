"""main.py - Product 1: single-channel classical enhancement baseline (offline).
Pipeline: input -> preprocess -> analysis -> enhance -> metrics."""
import argparse, json, os, sys, time
import numpy as np
import soundfile as sf

import audio_input as ai
import audio_preprocessing as pre
import noise_analysis as na
import speech_enhancement as se
import metrics as mt


def run(args):
    sr = ai.TARGET_SR
    print("Current prototype: single-channel classical enhancement baseline (offline; not real-time, no beamforming/AEC/neural model).")
    os.makedirs(args.out_dir, exist_ok=True)

    # 1. LOAD / SIMULATE ------------------------------------------------------
    if args.noisy:                                   # real noisy file: no reference
        noisy, _ = ai.load_audio(args.noisy)
        clean = noise = None
        print(f"[input] real noisy file {args.noisy} (non-intrusive metrics only)")
    else:
        if args.speech:
            clean, _ = ai.load_audio(args.speech)
            print(f"[input] speech file {args.speech}")
        else:
            clean = ai.synth_speech_like(8.0, sr)
            print("[input] SIMULATED speech-like signal (synthetic, not real speech)")
        raw_noise = ai.synth_noise(args.scenario, len(clean), sr)
        noisy, noise = ai.mix_at_snr(clean, raw_noise, args.snr)
        print(f"[input] SIMULATED '{args.scenario}' noise mixed at {args.snr} dB SNR")

    # 2. WAVEFORM ANALYSIS ----------------------------------------------------
    ws = pre.waveform_stats(noisy, sr)
    print(f"[waveform] {ws.duration_s:.1f}s  RMS {ws.rms_dbfs:.1f} dBFS  "
          f"peak {ws.peak_dbfs:.1f} dBFS  crest {ws.crest_factor_db:.1f} dB")

    # 3. PREPROCESS + STFT ----------------------------------------------------
    x = pre.preprocess(noisy, sr)
    f, t, Z = pre.stft(x, sr)
    P = np.abs(Z) ** 2
    hop_s = pre.HOP / sr
    bands = pre.band_energy_report(f, P)
    print("[spectrum] energy share: " + ", ".join(f"{k}: {v*100:.0f}%" for k, v in bands.items()))

    # 4. NOISE / SPEECH ANALYSIS ---------------------------------------------
    noise_psd = na.estimate_noise_psd(P, hop_s)
    vad = na.speech_presence(P, noise_psd, f)
    prof = na.profile_noise(noise_psd, P, f, vad)
    print(f"[noise] level {prof.noise_level_db:.1f} dB | low-freq share {prof.low_freq_ratio*100:.0f}% "
          f"| flatness {prof.flatness:.2f} | speech frames {prof.speech_activity*100:.0f}%")
    print(f"[noise] heuristic label: {prof.label}")

    # 5. ENHANCE --------------------------------------------------------------
    t0 = time.perf_counter()
    G = se.compute_gain(P, noise_psd)
    enhanced = pre.istft(se.apply_gain(Z, G), sr, len(noisy))
    proc_s = time.perf_counter() - t0
    G_ss = se.spectral_subtraction_gain(P, noise_psd)
    enhanced_ss = pre.istft(Z * G_ss, sr, len(noisy))
    rtf = proc_s / ws.duration_s
    print(f"[latency] algorithmic ~{pre.N_FFT/sr*1000:.0f} ms (STFT window), "
          f"offline Python RTF {rtf:.3f} (<1 = faster than real time)")

    # 6. METRICS --------------------------------------------------------------
    result = {"scenario": args.scenario, "noise_profile": prof.__dict__,
              "algorithmic_latency_ms": pre.N_FFT / sr * 1000}
    if clean is not None:
        ref = pre.preprocess(clean, sr)           # same HPF so comparison is fair
        nz = pre.preprocess(noise, sr)
        Zs, Zn = pre.stft(ref, sr)[2], pre.stft(nz, sr)[2]
        sp_out = pre.istft(Zs * G, sr, len(noisy))
        nz_out = pre.istft(Zn * G, sr, len(noisy))
        rep = mt.component_report(ref, nz, sp_out, nz_out, x, enhanced, ref)
        # baseline for comparison
        rep_ss = mt.si_sdr(ref, enhanced_ss)
        print("\n=========== METRICS (reference available: simulated mix) ===========")
        print(f"Input  SNR            : {rep['input_snr_db']:6.2f} dB")
        print(f"Output SNR (shadow)   : {rep['output_snr_db']:6.2f} dB   -> improvement {rep['snr_improvement_db']:+.2f} dB")
        print(f"Noise attenuation     : {rep['noise_attenuation_db']:6.2f} dB")
        print(f"Speech attenuation    : {rep['speech_attenuation_db']:6.2f} dB  (lower = less distortion)")
        print(f"SI-SDR in -> out      : {rep['si_sdr_in_db']:6.2f} -> {rep['si_sdr_out_db']:6.2f} dB  "
              f"(spectral-subtraction baseline: {rep_ss:6.2f})")
        result["metrics"] = {k: round(float(v), 2) for k, v in rep.items()}
    else:
        change = 10 * np.log10((np.mean(enhanced ** 2) + 1e-20) / (np.mean(x ** 2) + 1e-20))
        print(f"[metrics] no clean reference available; overall level change {change:+.1f} dB (not a quality metric)")

    # 7. WRITE OUTPUTS --------------------------------------------------------
    peak = max(1e-6, np.max(np.abs([noisy, enhanced]))) * 1.05
    sf.write(os.path.join(args.out_dir, "noisy.wav"), noisy / peak, sr)
    sf.write(os.path.join(args.out_dir, "enhanced.wav"), enhanced / peak, sr)
    if clean is not None:
        sf.write(os.path.join(args.out_dir, "clean_reference.wav"), clean / peak, sr)
    print(f"\n[output] wrote noisy.wav / enhanced.wav to {args.out_dir}/")

    if not args.no_plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 3, figsize=(15, 3.8), sharey=True)
            for a, sig_, title in zip(ax, (clean if clean is not None else x, x, enhanced),
                                      ("clean (reference)", "noisy input", "enhanced")):
                ff, tt, ZZ = pre.stft(sig_, sr)
                a.pcolormesh(tt, ff, 20 * np.log10(np.abs(ZZ) + 1e-6), vmin=-90, vmax=-20, shading="auto")
                a.set_title(title); a.set_xlabel("s")
            ax[0].set_ylabel("Hz")
            fig.tight_layout(); fig.savefig(os.path.join(args.out_dir, "spectrograms.png"), dpi=90)
            print("[output] wrote spectrograms.png")
        except ImportError:
            print("[output] matplotlib not installed; skipping spectrogram plot")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=2)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Speech isolation prototype")
    ap.add_argument("--speech", help="clean speech wav/flac (else simulated)")
    ap.add_argument("--noisy", help="already-noisy file (no reference metrics)")
    ap.add_argument("--scenario", default="mixed", choices=["traffic", "wind", "cafe", "mixed"])
    ap.add_argument("--snr", type=float, default=0.0, help="input SNR dB for simulated mix")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--json", help="write summary JSON here")
    ap.add_argument("--no-plot", action="store_true")
    try:
        run(ap.parse_args())
    except ai.AudioInputError as e:
        sys.exit(f"ERROR: {e}")
