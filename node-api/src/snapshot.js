'use strict';
// Loads the snapshot produced by scripts/export_snapshot.py (SIMULATED data).
// In production this module becomes a repository over a database / device-state
// service fed by the phone app (BLE events) and earbud telemetry uploads.
const fs = require('fs');
const path = require('path');
const DEFAULT_FILE = path.join(__dirname, '..', 'data', 'snapshot.json');
const file = () => process.env.TWS_SNAPSHOT || DEFAULT_FILE;   // env override used by the 503 test

function load() {
  try {
    return JSON.parse(fs.readFileSync(file(), 'utf8'));
  } catch (err) {
    const e = new Error('Snapshot unavailable. Run: python3 scripts/export_snapshot.py');
    e.status = 503;
    throw e;
  }
}
module.exports = { load };
