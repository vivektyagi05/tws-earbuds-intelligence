# TWS Earbuds Prototypes - Documentation

> **Status statement.** The prototypes validate algorithmic logic, measurement/decision pipelines and integration boundaries. Hardware-dependent production components are simulated or documented as migration requirements. Nothing here is claimed to be production-ready, a medical device, or a certified battery-management system.

```
tws-prototypes/
  README.md  DOCS.md  requirements.txt  run_all.sh  .gitignore
  product1_speech_isolation/  audio_input.py audio_preprocessing.py noise_analysis.py speech_enhancement.py metrics.py main.py
  product2_recovery/          device_state.py connection_manager.py separation_detector.py proximity_engine.py recovery_engine.py main.py
  product3_exposure/          session_tracker.py exposure_engine.py risk_state.py recommendation_engine.py main.py
  product4_battery/           battery_model.py health_estimator.py runtime_predictor.py degradation_detector.py main.py
  scripts/                    export_snapshot.py  verify_prototypes.py (26 stdlib unit tests)
  node-api/                   package.json src/server.js src/snapshot.js src/smoke-test.js   (data/snapshot.json is generated)
```

**Run / verify**
```bash
pip install -r requirements.txt
./run_all.sh          # prototypes -> snapshot export -> unit tests -> npm install + API smoke test
```
Each `productN/main.py` runs independently from its own folder. `python3 scripts/verify_prototypes.py` runs the unit tests alone.

---

# A. CURRENT PROTOTYPE

## A1. Speech isolation

**Current prototype: single-channel classical enhancement baseline.** Offline, file-based, one microphone channel.

Pipeline: audio input -> preprocessing/STFT -> noise estimation -> VAD/noise profiling -> Wiener gain/mask -> ISTFT -> objective metrics.

- Preprocessing: DC removal, 70 Hz causal high-pass; STFT 512-point Hann window (32 ms), 128-sample hop (8 ms) at 16 kHz.
- Noise estimation: causal minimum-statistics-style tracker (recursive smoothing alpha 0.9, 1.5 s running minimum, empirical bias factor 1.6).
- VAD/noise profiling: energy VAD and a rule-based noise label. The VAD feeds only the noise profile; it does not gate the gain.
- Enhancement: Wiener gain `G = xi/(1+xi)` with decision-directed a-priori SNR (alpha 0.98), -14 dB gain floor, 3-bin frequency smoothing. Spectral subtraction is included only as a comparison baseline.
- Metrics (need the clean reference, available only because the noisy input is simulated): input/output SNR by shadow filtering (the linear mask applied separately to speech and noise), noise and speech attenuation, SI-SDR.
- Input: `--speech clean.wav` (noise added), `--noisy noisy.wav` (no reference metrics, so no quality metric), or the built-in synthetic generator.

Measured results (default run, synthetic speech-like signal + simulated mixed noise at 0 dB; deterministic):
```
Current prototype: single-channel classical enhancement baseline (offline; not real-time, no beamforming/AEC/neural model).
[input] SIMULATED speech-like signal (synthetic, not real speech)
[input] SIMULATED 'mixed' noise mixed at 0.0 dB SNR
[waveform] 8.0s  RMS -17.0 dBFS  peak -0.6 dBFS  crest 16.4 dB
[spectrum] energy share: <250Hz (wind/traffic rumble): 40%, 250-4000Hz (speech): 60%, >4000Hz: 0%
[noise] level -24.5 dB | low-freq share 50% | flatness 0.01 | speech frames 32%
[noise] heuristic label: coloured / mixed
[latency] algorithmic ~32 ms (STFT window), offline Python RTF 0.004 (<1 = faster than real time)

=========== METRICS (reference available: simulated mix) ===========
Input  SNR            :   0.90 dB
Output SNR (shadow)   :   6.51 dB   -> improvement +5.61 dB
Noise attenuation     :   6.99 dB
Speech attenuation    :   1.37 dB  (lower = less distortion)
SI-SDR in -> out      :   0.91 ->   5.39 dB  (spectral-subtraction baseline:   3.37)

[output] wrote noisy.wav / enhanced.wav to out/
[output] wrote spectrograms.png
```
Other scenarios, same seed:
```
traffic: Output SNR (shadow)   :   6.05 dB   -> improvement +5.54 dB
traffic: SI-SDR in -> out      :   0.52 ->   5.09 dB  (spectral-subtraction baseline:   2.65)
wind: Output SNR (shadow)   :   7.36 dB   -> improvement +5.72 dB
wind: SI-SDR in -> out      :   1.47 ->   5.95 dB  (spectral-subtraction baseline:   4.09)
cafe: Output SNR (shadow)   :   0.60 dB   -> improvement +0.56 dB
cafe: SI-SDR in -> out      :  -0.01 ->   0.45 dB  (spectral-subtraction baseline:   0.17)
```
Ad-hoc robustness check (one-off, not in the test suite): 5 different random seeds per scenario, 0 dB input, SNR gain min/mean/max - mixed 5.07/5.98/6.72 dB, traffic 4.78/5.85/6.42 dB, wind 5.62/6.51/7.35 dB, cafe-babble 0.51/0.63/1.01 dB. All on synthetic signals.

Not implemented (do not read these into the results): multi-microphone beamforming, AEC, neural enhancement, earbud DSP/NPU firmware, real-time streaming.

**Privacy statement.** Raw microphone audio for the real-time enhancement path is intended to remain on-device. Processed call/uplink audio may follow the normal Bluetooth call path. The prototype/API exposes summary telemetry, not raw audio. The Node.js server performs no audio processing and never receives audio.

## A2. Recovery & separation detection

Implemented and tested: device state model (left / right / case), last-known location captured at the *last connected heartbeat*, separation detector (docked buds ignored, 20 s debounce, one-bud-connected = strong evidence, both-gone needs a 5 min timeout), RSSI filtering (median of 5, then EMA), proximity bands with +/-3 dB hysteresis (STRONG >= -66, MEDIUM >= -78 dBm), trend (CLOSER / FARTHER / STEADY), and the dead-battery degraded mode.

- **RSSI is a noisy proximity signal, not an indoor positioning system.** No distances or coordinates are produced from RSSI.
- **Warmer/colder guidance is based on filtered RSSI trend/bands.**
- **When the bud is not transmitting, live proximity is unavailable.** The prototype then shows only "Live proximity unavailable." plus the last confirmed connection and last reported battery.
- Guidance targets one bud at a time (the first confirmed separation).
- Last-known location is a place label supplied by a simulated phone-location source; GPS cannot resolve rooms and no such claim is made.

State machine:
```
NOT_NEEDED --disconnect (not docked)--> SEPARATION_SUSPECTED --20 s debounce--> SEPARATED
SEPARATED --user taps Find + advertisements seen--> SEARCHING --reconnect/docked--> NOT_NEEDED
SEPARATED | SEARCHING --battery 0 / no advertisements--> LIVE_UNAVAILABLE --charged, advertises again--> SEPARATED
Per device: CONNECTED <-> DISCONNECTED.   Proximity: UNKNOWN / WEAK / MEDIUM / STRONG
```
Example run:
```
===== SCENARIO A: lost right bud, found via BLE proximity =====
22:42 both earbuds connected.
[22:48:15] status: state=SEPARATION_SUSPECTED proximity=UNKNOWN
            Checking the right bud connection...
[22:48:35] status: state=SEPARATED proximity=UNKNOWN
            Right bud disconnected.
            Last confirmed connection: Bedroom, 10:48 PM.
            Last reported battery: 34% (as of 10:48 PM).
            Tap 'Find' and walk toward it to see live signal strength.

-- 23:02 user taps 'Find' and starts walking (BLE scan every 2 s) --
t= 0s true_dist=14.0m rssi=-85.1 band=WEAK    trend=UNKNOWN | Searching for the right bud...
t= 2s true_dist=12.9m rssi=-81.6 band=WEAK    trend=UNKNOWN | Searching for the right bud...
t= 4s true_dist=11.8m rssi=-83.4 band=WEAK    trend=UNKNOWN | Searching for the right bud...
t= 6s true_dist=10.7m rssi=-82.7 band=WEAK    trend=STEADY  | Signal steady - try moving to a different spot.
t= 8s true_dist= 9.6m rssi=-83.9 band=WEAK    trend=STEADY  | Signal steady - try moving to a different spot.
t=10s true_dist= 8.5m rssi=-80.2 band=WEAK    trend=STEADY  | Signal steady - try moving to a different spot.
t=12s true_dist= 7.4m rssi=-74.2 band=WEAK    trend=STEADY  | Signal steady - try moving to a different spot.
t=14s true_dist= 6.3m rssi=-75.1 band=WEAK    trend=STEADY  | Signal steady - try moving to a different spot.
t=16s true_dist= 5.2m rssi=-71.1 band=WEAK    trend=CLOSER  | You are getting closer to the right bud.
t=18s true_dist= 4.1m rssi=-71.6 band=WEAK    trend=CLOSER  | You are getting closer to the right bud.
t=20s true_dist= 3.0m rssi=-68.1 band=MEDIUM  trend=CLOSER  | You are getting closer to the right bud.
t=22s true_dist= 1.9m rssi=-64.5 band=MEDIUM  trend=CLOSER  | You are getting closer to the right bud.
t=24s true_dist= 0.8m rssi=-62.7 band=MEDIUM  trend=CLOSER  | You are getting closer to the right bud.
t=26s true_dist= 0.5m rssi=-49.4 band=MEDIUM  trend=CLOSER  | You are getting closer to the right bud.
t=28s true_dist= 0.5m rssi=-50.6 band=MEDIUM  trend=CLOSER  | You are getting closer to the right bud.
t=30s true_dist= 0.5m rssi=-50.6 band=STRONG  trend=CLOSER  | You are getting closer to the right bud.
t=32s true_dist= 0.5m rssi=-58.3 band=STRONG  trend=CLOSER  | You are getting closer to the right bud.

Event log:
  22:42:00 LEFT_BUD  CONNECTED batt=62%
  22:42:00 RIGHT_BUD CONNECTED batt=34%
  22:42:00 CASE      CONNECTED batt=80%
  22:48:00 RIGHT_BUD HEARTBEAT batt=34%
  22:48:00 LEFT_BUD  HEARTBEAT batt=60%
  22:48:10 RIGHT_BUD DISCONNECTED (LINK_LOSS)
  22:48:40 LEFT_BUD  HEARTBEAT batt=60%

===== SCENARIO B: right bud battery depleted =====
[23:42:00] status: state=LIVE_UNAVAILABLE proximity=UNKNOWN
            Live proximity unavailable.
            Last confirmed connection: Bedroom, 10:48 PM.
            Last reported battery: 34% (as of 10:48 PM).
            The earbud is not transmitting. Search where you last used it; live guidance resumes if it is charged or placed in its case.
```

## A3. Listening exposure

**Prototype engineering exposure simulation.** Configurable model, verified by unit tests:

- `allowed_hours(L) = 8 h / 2^((L - 85)/3)` (85 dBA reference, 8 h reference duration, 3 dB exchange rate)
- `dose% = 100 * sum(t_i / allowed_hours(L_i))`, per ear, worst ear reported; rolling 24 h window by session end time (a session straddling the window start is counted whole - conservative); levels below 70 dBA contribute nothing (a prototype choice, configurable)
- `LEX,8h = 85 + 10*log10(dose/100)` is derived from the dose, so it is consistent with the dose by construction (the exact energy-equivalent exchange rate would be 3.01 dB)
- States: NORMAL < 50%, ELEVATED 50-100%, HIGH >= 100%, with 10% hysteresis on the way down
- Alerts: notify on escalation; repeat only after a cooldown (ELEVATED 3 h, HIGH 1 h); NORMAL never notifies; wording is advisory
- Invalid input is rejected: duration <= 0, NaN/inf duration, level outside 20-130 dBA, NaN level
- Layers are separate: RAW INPUT -> EXPOSURE CALCULATION -> EXPOSURE STATE -> USER RECOMMENDATION

Production implementation requires per-model acoustic calibration and validation against the selected applicable safe-listening standard. This prototype is not a medical device and does not provide hearing-loss diagnosis or certified hearing protection.

Why volume percentage alone is insufficient: the same setting yields different dBA across sources, earbud models, fit/seal and EQ, and exposure also depends on time. No microphone recording is needed for this concept: inputs are only level, time and duration.

Example run (levels are SIMULATED; "moderate" = 82 dBA and "higher" = 92 dBA are assumed mappings):
```
########## SCENARIO A: moderate / higher / moderate ##########
(Prototype engineering exposure simulation - not a medical device; levels are SIMULATED)

RAW INPUT      : Session 1 - moderate: 60 min, L=82 dBA / R=80 dBA [SIMULATED]
EXPOSURE       : L dose   6.2% | R dose   3.9% | worst=left | LEX,8h 73.0 dBA | this session adds 6.2%
STATE          : NORMAL
RECOMMENDATION : "Continue monitoring."  notify=False  (normal: no alert)

RAW INPUT      : Session 2 - higher: 45 min, L=92 dBA / R=93 dBA [SIMULATED]
EXPOSURE       : L dose  53.5% | R dose  63.5% | worst=right | LEX,8h 83.0 dBA | this session adds 59.5%
STATE          : ELEVATED
RECOMMENDATION : "Consider lowering volume."  notify=True  (escalation)

RAW INPUT      : Session 3 - moderate: 90 min, L=82 dBA / R=81 dBA [SIMULATED]
EXPOSURE       : L dose  62.9% | R dose  70.9% | worst=right | LEX,8h 83.5 dBA | this session adds 9.4%
STATE          : ELEVATED
RECOMMENDATION : "Consider lowering volume."  notify=True  (cooldown elapsed)

10 min later, still ELEVATED: notify=False (suppressed (cooldown, 170 min left))

########## SCENARIO B: heavy day (escalation to HIGH) ##########
(Prototype engineering exposure simulation - not a medical device; levels are SIMULATED)

RAW INPUT      : Session 1 - moderate: 60 min, L=82 dBA / R=80 dBA [SIMULATED]
EXPOSURE       : L dose   6.2% | R dose   3.9% | worst=left | LEX,8h 73.0 dBA | this session adds 6.2%
STATE          : NORMAL
RECOMMENDATION : "Continue monitoring."  notify=False  (normal: no alert)

RAW INPUT      : Session 2 - higher: 45 min, L=92 dBA / R=93 dBA [SIMULATED]
EXPOSURE       : L dose  53.5% | R dose  63.5% | worst=right | LEX,8h 83.0 dBA | this session adds 59.5%
STATE          : ELEVATED
RECOMMENDATION : "Consider lowering volume."  notify=True  (escalation)

RAW INPUT      : Session 3 - loud: 60 min, L=95 dBA / R=95 dBA [SIMULATED]
EXPOSURE       : L dose 179.5% | R dose 189.5% | worst=right | LEX,8h 87.8 dBA | this session adds 126.0%
STATE          : HIGH
RECOMMENDATION : "Consider taking a listening break."  notify=True  (escalation)

10 min later, still HIGH: notify=False (suppressed (cooldown, 50 min left))

########## SCENARIO C: invalid input handling ##########
(Prototype engineering exposure simulation - not a medical device; levels are SIMULATED)

RAW INPUT      : bad sensor value: 30 min, L=150 dBA / R=80 dBA [SIMULATED]
REJECTED       : implausible level 150 dBA

RAW INPUT      : Session 1 - moderate: 60 min, L=82 dBA / R=80 dBA [SIMULATED]
EXPOSURE       : L dose   6.2% | R dose   3.9% | worst=left | LEX,8h 73.0 dBA | this session adds 6.2%
STATE          : NORMAL
RECOMMENDATION : "Continue monitoring."  notify=False  (normal: no alert)

10 min later, still NORMAL: notify=False (normal: no alert)
```

## A4. Battery intelligence

**Prototype SOH estimate** from software-level simulated telemetry and statistical estimation (not a validated or laboratory SOH).

- `capacity_est = (P_avg * listen_h) / (dSOC/100)` per session, only sessions with dSOC >= 30 pp
- `Prototype SOH% = median(capacity_est, last 20 sessions) / reference_capacity * 100` (reference 185 mWh = 50 mAh x 3.7 V, assumed)
- `runtime_h = ((SOC - 5%)/100 * capacity_est) / P_recent`, `P_recent` = EWMA (alpha 0.25) of recent average power; range from the capacity IQR and power std-dev
- Trend: capacity binned per 10 cycles -> Theil-Sen slope (points per 100 cycles); acceleration = late-half minus early-half slope; cycles to 80% (a configurable convention)
- Left/right comparison and warnings: health gap >= 10 points; slope >= 2x the other bud and >= 2 points/100 cycles; acceleration >= 3 points (set above the ~1.5-2 point noise floor of this estimate); median temperature > 40 C
- Telemetry fields `voltage` and `charge_duration` are generated and stored but not used by any estimator; temperature is used only for the warm-running flag.
- Output is deterministic (seeded generator; verified by a unit test).

Example run:
```
==================================================================
  EARBUD BATTERY DASHBOARD   (prototype SOH estimates, SIMULATED data)
==================================================================

LEFT BUD   cycles=299  sessions=300  confidence=high
  Prototype SOH est.  :  91.3%   [capacity 169 mWh, IQR 165-172]
  Runtime on full chg :  4.9 h   (new reference cell, same cutoff & load: ~5.4 h)
  Runtime now (95% ) :  4.7 h   range 4.3-5.1 h   [recent load 32.5 mW]
  Degradation trend   : -2.35 pts/100 cycles, acceleration -1.63
  Cycles to 80% health: ~486

RIGHT BUD   cycles=299  sessions=300  confidence=high
  Prototype SOH est.  :  77.9%   [capacity 144 mWh, IQR 140-147]
  Runtime on full chg :  3.6 h   (new reference cell, same cutoff & load: ~4.6 h)
  Runtime now (62% ) :  2.2 h   range 2.0-2.4 h   [recent load 37.9 mW]
  Degradation trend   : -8.48 pts/100 cycles, acceleration -2.01
  Cycles to 80% health: n/a (already at/below 80% or not degrading)

FINDINGS
  [WARNING] Right earbud degradation is significantly higher (health gap 13 points).
  [WARNING] Right earbud is fading 3.6x faster (8.5 vs 2.4 points per 100 cycles).

NOTE: Prototype SOH estimate from simulated software-level telemetry; not a validated or laboratory-certified battery-health measurement.
```
Prototype vs production: the prototype infers capacity from SOC readings that are themselves estimates, with an assumed reference capacity, no impedance data and no temperature compensation. It indicates a trend; it is not certified SOH.

## A5. Node.js API (BFF / snapshot layer)

Node.js is used only as an API/BFF that serves a **snapshot of simulated prototype outputs** produced by `scripts/export_snapshot.py`. It does no real-time audio DSP, no raw audio handling and no earbud signal processing. Every response has `meta.simulated: true`; `meta.generatedAt` is the response time and `meta.snapshotGeneratedAt` is when the Python prototypes produced the data. Missing snapshot -> `503`; unknown route -> `404` (both covered by the smoke test).

| Endpoint | Returns |
|---|---|
| `GET /api/earbuds/status` | `{left, right, case}`, each `{connection, batteryPct}` |
| `GET /api/earbuds/recovery` | `{active: {state, device, proximity, liveTracking, guidance[]}, deadBatteryCase: {...}}` |
| `GET /api/earbuds/battery` | `{left: {health, estimatedRuntimeHours, ...}, right: {...}, warning, estimateType, findings[]}` (`health` = prototype SOH estimate) |
| `GET /api/earbuds/exposure` | `{doseLeftPct, doseRightPct, state, recommendation, totalListeningMinutes, disclaimer}` |
| `GET /api/earbuds/context` | summary of the offline speech-enhancement run `{noiseLabel, noiseLevelDb, lowFrequencyShare, speechActivity, snrImprovementDb, algorithmicLatencyMs, processedOn}`; never raw audio |
| `GET /healthz` | `{ok: true}` |

Sample `GET /api/earbuds/battery` (findings omitted):
```json
{
  "left": {
    "health": 91,
    "estimatedRuntimeHours": 4.7,
    "fullChargeRuntimeHours": 4.9,
    "confidence": "high",
    "trendPointsPer100Cycles": -2.35
  },
  "right": {
    "health": 78,
    "estimatedRuntimeHours": 2.2,
    "fullChargeRuntimeHours": 3.6,
    "confidence": "high",
    "trendPointsPer100Cycles": -8.48
  },
  "warning": "Right earbud degradation is significantly higher (health gap 13 points).",
  "estimateType": "prototype_soh_estimate",
  "meta": {
    "simulated": true,
    "generatedAt": "2026-10-01T05:09:47.070Z",
    "snapshotGeneratedAt": "2026-10-01T05:09:19.488286+00:00",
    "apiVersion": "v1"
  }
}
```

## A6. Tests actually run by `./run_all.sh`

All four prototypes; snapshot export; 26 unit tests (exposure maths, boundaries, hysteresis, cooldown, invalid-input rejection and an all-invalid regression; recovery debounce / docked / last-known-location / dead-battery; battery formulas, Theil-Sen slope recovery, determinism; speech metrics, end-to-end metrics, determinism, missing-file error, documented babble limitation; each prototype standalone; snapshot contents); Node smoke test (5 endpoints 200 + `meta.simulated`, 404, 503).

---

# B. PRODUCTION MIGRATION

| Area | Production architecture |
|---|---|
| Speech | **Production architecture: multi-microphone DSP/beamforming with optional quantized neural enhancement on earbud hardware**, with AEC for call/hear-through paths, wind detection from inter-mic coherence, fixed-point streaming frames (8-10 ms) on the bud DSP/NPU, frame sizes and filterbanks chosen for a low-tens-of-ms latency budget, acoustic tuning on a head-and-torso simulator, perceptual evaluation (e.g. PESQ/STOI and listening tests) |
| Recovery | Android `BluetoothLeScanner` / iOS CoreBluetooth scanning with bud-firmware advertising and a GATT service or LE Audio; platform location + user-defined places; foreground/background restrictions handled per OS; optional cloud registry and push |
| Exposure | Per-model acoustic calibration (digital level, EQ, content loudness -> SPL at the ear, with fit estimation); validation against the selected applicable safe-listening standard; accumulation that survives switching phones; reviewed wording and user-adjustable limits |
| Battery | Validated fuel-gauge/BMS data, coulomb counting, temperature compensation, cell characterisation, impedance tracking, laboratory validation of the SOH estimator, hardware safety cut-offs; ML only with real fleet data, keeping the formula model as a baseline |
| API | Authentication, device-specific routes (`/devices/{id}/...`), persistence and history, rate limiting, input validation on writes, TLS, push notifications, data-retention policy |

# C. HARDWARE-DEPENDENT FEATURES (not implemented; simulated or documented only)

Multi-mic capture and beamforming; AEC; neural enhancement on a bud NPU; real-time streaming and measured on-device latency/power; real BLE scanning, RSSI and connection callbacks; bud advertising when out of the case; case-detect sensor; calibrated acoustic output level; battery fuel gauge, voltage/current sensing and thermal sensing. UWB and Bluetooth Channel Sounding are not implemented or claimed.

# D. SIMULATED DATA

| Data | Where | Note |
|---|---|---|
| Speech signal | `audio_input.synth_speech_like` | Synthetic harmonic/formant signal, not real speech |
| Noise (traffic, wind, babble) | `audio_input.synth_noise` | Synthetic generators |
| Device events, battery %, case state | `product2_recovery/main.py` | Hand-written scenario |
| Phone location / room label | `product2_recovery/main.py` | Simulated place labels |
| BLE RSSI | `proximity_engine.SimulatedBleScanner` | Log-distance model + Gaussian shadowing; includes the "bud is advertising" assumption |
| Dead-battery condition | `product2_recovery/main.py` | Set by the scenario; production infers it from silence + low last battery, with uncertainty |
| Listening levels (dBA) | `product3_exposure/main.py` | Assumed mappings, no calibration |
| Battery telemetry | `battery_model.simulate_telemetry` | Seeded; the generator's ground-truth fade is hidden from the estimators |
| API data | `node-api/data/snapshot.json` | Generated by the prototypes; ignored by git |

# E. LIMITATIONS

- Speech: synthetic speech is not real speech; the implementation is offline; real-time earbud feasibility is not proven; noise tracking lags sudden changes; a single mic cannot separate a talker from babble (about +0.6 dB on the babble scenario - a real limitation); no perceptual metrics or listening tests; results are on simulated mixes.
- Recovery: RSSI is noisy and affected by bodies, pockets and furniture, so only coarse bands/trends are reported; no indoor positioning; one bud guided at a time.
- Exposure: no calibration, so absolute dose is only as meaningful as the assumed levels; ambient noise and individual susceptibility are not modelled; not a medical device.
- Battery: simulated data; gauge error propagates into capacity; reference capacity assumed; the acceleration estimate is noisy; 80% end-of-life is a convention; voltage and charge duration are unused.
- API: serves static simulated snapshots; no auth, persistence, rate limiting or TLS.

---

# TRACEABILITY

| Feature | Current Prototype | Production Requirement | Status |
|---|---|---|---|
| Noise suppression | Single-channel Wiener mask, offline | Multi-mic beamforming + optional quantized NN on bud DSP/NPU | Prototype only |
| Real-time operation | Not implemented (offline file processing) | Streaming fixed-point frames on bud hardware | Hardware-dependent |
| Echo cancellation | Not implemented | AEC in the call path | Not implemented |
| Speech privacy | Local Python run; API serves summaries only | On-device raw-audio processing; call audio over the normal BT path | Documented |
| Last-known location | Location captured at last connected heartbeat (simulated source) | Phone location APIs + user-defined places | Prototype logic validated |
| Separation detection | Debounce + docked/other-bud rules (unit-tested) | Real BLE connection events, tuned on field data | Prototype logic validated |
| Proximity guidance | Filtered simulated RSSI bands + trend | Real BLE RSSI; bud advertising firmware | Simulated |
| Dead-battery behaviour | "Live proximity unavailable" + last confirmed info | Same behaviour, inferred from real silence | Prototype logic validated |
| Exposure dose | Configurable 85 dBA / 8 h / 3 dB model, hysteresis, cooldown (unit-tested) | Per-model calibration + validation against the applicable standard | Prototype simulation |
| Exposure privacy | Level/time/duration only | Same, local-first | Documented |
| Battery SOH | Median capacity estimate vs assumed reference | Validated fuel gauge/BMS + lab validation | Prototype estimate |
| Runtime prediction | Formula with EWMA power | BMS-grade model with temperature/aging | Prototype estimate |
| Degradation / L-R imbalance | Theil-Sen trend + threshold rules | Fleet-validated thresholds | Prototype logic validated |
| API | Express serving simulated snapshot, 404/503 | Auth, per-device routes, persistence, rate limit, TLS, retention | Prototype only |

# COMPARISON

| Product | Core Technology | Main Input | Main Algorithm | Where It Runs (production) | User Output | Company Value |
|---|---|---|---|---|---|---|
| 1 Speech isolation | Classical DSP baseline; production adds mic arrays + optional NN | Microphone audio | STFT + noise tracking + Wiener mask | On-earbud DSP/NPU, never a remote server | Clearer speech | Call-quality differentiation |
| 2 Recovery | BLE + state machine | Connection events, RSSI, phone location | Debounced rules + filtered RSSI bands | Phone app + bud advertising firmware | Last confirmed location + warmer/colder hints | Retention, trust |
| 3 Exposure | Dose accumulation | Estimated level (dBA), duration | Exchange-rate dose model + hysteresis + cooldown | Bud firmware / phone, local first | Calm advisory states | Safe-listening positioning |
| 4 Battery | Statistical estimation | SOC, power, cycles, temperature | Median capacity, EWMA runtime, Theil-Sen trend | Firmware logging + phone/cloud analytics | SOH estimate, runtime, warnings | Warranty/quality insight |
