'use strict';
const express = require('express');
const { load } = require('./snapshot');

const app = express();
// generatedAt = response time; snapshotGeneratedAt = when the Python prototypes produced the data.
const meta = (snap) => ({ simulated: true, generatedAt: new Date().toISOString(),
  snapshotGeneratedAt: (snap && snap._meta && snap._meta.generatedAt) || null, apiVersion: 'v1' });
const handler = (fn) => (req, res, next) => {
  try { const snap = load(); res.set('Cache-Control', 'no-store').json({ ...fn(snap), meta: meta(snap) }); }
  catch (e) { next(e); }
};

// Device + connection state of left bud, right bud, case
app.get('/api/earbuds/status', handler((s) => s.recovery.status));
// Recovery guidance (last-known location, proximity band, dead-battery handling)
app.get('/api/earbuds/recovery', handler((s) => ({
  active: s.recovery.recovery, deadBatteryCase: s.recovery.recoveryDeadBattery })));
// Battery health, runtime, degradation warnings
app.get('/api/earbuds/battery', handler((s) => s.battery));
// Cumulative listening exposure estimate (not a medical measurement)
app.get('/api/earbuds/exposure', handler((s) => s.exposure));
// Summary of the OFFLINE speech-enhancement prototype run (summary only - never raw audio;
// this server performs no audio processing)
app.get('/api/earbuds/context', handler((s) => ({
  noiseLabel: s.context.noise_profile.label,
  noiseLevelDb: round(s.context.noise_profile.noise_level_db),
  lowFrequencyShare: round(s.context.noise_profile.low_freq_ratio),
  speechActivity: round(s.context.noise_profile.speech_activity),
  snrImprovementDb: s.context.metrics ? s.context.metrics.snr_improvement_db : null,
  algorithmicLatencyMs: s.context.algorithmic_latency_ms,
  processedOn: 'offline prototype run (simulated; not on-device, not real-time)' })));

function round(v) { return Math.round(v * 100) / 100; }

app.get('/healthz', (req, res) => res.json({ ok: true }));
app.use((req, res) => res.status(404).json({ error: 'not_found' }));
app.use((err, req, res, next) => {            // central error handler
  res.status(err.status || 500).json({ error: err.message, meta: meta(null) });
});

if (require.main === module) {
  const port = process.env.PORT || 3000;
  app.listen(port, () => console.log(`TWS earbuds API (simulated data) on :${port}`));
}
module.exports = app;
