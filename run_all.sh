#!/usr/bin/env bash
# Runs all four prototypes, exports the snapshot, runs the unit tests, then the Node API smoke test.
set -e
cd "$(dirname "$0")"
for p in product1_speech_isolation product2_recovery product3_exposure product4_battery; do
  echo; echo "################ $p ################"
  (cd "$p" && python3 main.py)
done
echo; echo "################ snapshot export ################"
python3 scripts/export_snapshot.py
echo; echo "################ unit tests ################"
python3 scripts/verify_prototypes.py
echo; echo "################ node api smoke test ################"
(cd node-api && npm install --silent && npm test)
