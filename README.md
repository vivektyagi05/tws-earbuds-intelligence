# TWS Earbuds - Four Software Prototypes

Honest, runnable prototypes for four earbud software concepts plus a small Node.js API layer.

> The prototypes validate algorithmic logic, measurement/decision pipelines and integration boundaries. Hardware-dependent production components are simulated or documented as migration requirements.

| # | Prototype | What it actually is |
|---|---|---|
| 1 | Speech isolation | Current prototype: single-channel classical enhancement baseline (offline, synthetic/test audio) |
| 2 | Recovery & separation | State machine + simulated BLE RSSI. RSSI is a noisy proximity signal, not an indoor positioning system |
| 3 | Listening exposure | Prototype engineering exposure simulation (dose model). Not a medical device |
| 4 | Battery intelligence | Prototype SOH estimate from simulated software-level telemetry. Not a certified BMS/SOH |
| 5 | Node.js API | BFF serving a snapshot of the simulated prototype outputs. No audio/DSP processing |

```bash
pip install -r requirements.txt     # numpy, scipy, soundfile (+ matplotlib optional)
./run_all.sh                        # 4 prototypes -> snapshot export -> 26 unit tests -> Node smoke test
```
Each prototype also runs on its own: `cd product2_recovery && python3 main.py`.
Start the API: `python3 scripts/export_snapshot.py && cd node-api && npm install && npm start` (port 3000).

Full documentation, limitations and the feature traceability table: **[DOCS.md](DOCS.md)**.
Requirements: Python 3.10+, Node 18+.
