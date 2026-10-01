"""Runs the four Python prototypes and writes node-api/data/snapshot.json.
Architecture note: in production the phone app/earbud firmware would push real
telemetry to the service; here the Python prototypes ARE the simulated source."""
import json, subprocess, sys, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
out = root / "node-api" / "data"; out.mkdir(parents=True, exist_ok=True)
parts = {}
for key, folder in (("context", "product1_speech_isolation"), ("recovery", "product2_recovery"),
                    ("exposure", "product3_exposure"), ("battery", "product4_battery")):
    tmp = out / f"{key}.json"
    args = [sys.executable, "main.py", "--json", str(tmp)] + (["--no-plot", "--out-dir", str(out / "audio_out")] if key == "context" else [])
    r = subprocess.run(args, cwd=root / folder, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{folder} failed:\n{r.stderr}")
    parts[key] = json.loads(tmp.read_text()); tmp.unlink()
import datetime
parts["_meta"] = {"simulated": True, "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "source": "python prototypes (offline, simulated data)"}
json.dump(parts, open(out / "snapshot.json", "w"), indent=2)
print("wrote", out / "snapshot.json")
