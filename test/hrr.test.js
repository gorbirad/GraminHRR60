import test from 'node:test';
import assert from 'node:assert/strict';
import { calculateHrr60, classifyHrr60 } from '../src/hrr.js';

test('calculateHrr60 uses end-of-session heart rate and the first sample at or after +60s', () => {
  const result = calculateHrr60({
    mainSessionEndSec: 600,
    heartRateSamples: [
      { timeSec: 570, heartRate: 168 },
      { timeSec: 600, heartRate: 164 },
      { timeSec: 655, heartRate: 150 },
      { timeSec: 661, heartRate: 142 }
    ]
  });

  assert.deepEqual(result, {
    mainSessionEndSec: 600,
    endHeartRate: 164,
    heartRateAt60Sec: 142,
    recovery: 22
  });
});

test('calculateHrr60 returns null when there is no sample after +60s', () => {
  const result = calculateHrr60({
    mainSessionEndSec: 300,
    heartRateSamples: [
      { timeSec: 300, heartRate: 155 },
      { timeSec: 350, heartRate: 146 }
    ]
  });

  assert.equal(result, null);
});

test('classifyHrr60 maps recovery ranges into readable labels', () => {
  assert.equal(classifyHrr60(35), 'bardzo dobry');
  assert.equal(classifyHrr60(24), 'dobry');
  assert.equal(classifyHrr60(15), 'umiarkowany');
  assert.equal(classifyHrr60(8), 'niski');
});
