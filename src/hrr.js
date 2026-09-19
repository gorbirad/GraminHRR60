function toFiniteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function normalizeHeartRateSamples(samples = []) {
  return samples
    .map((sample, index) => {
      if (typeof sample === 'number') {
        return { timeSec: index, heartRate: sample };
      }

      return {
        timeSec: toFiniteNumber(sample?.timeSec ?? sample?.seconds ?? sample?.t ?? sample?.offsetSec),
        heartRate: toFiniteNumber(sample?.heartRate ?? sample?.bpm ?? sample?.value)
      };
    })
    .filter((sample) => sample.timeSec !== null && sample.heartRate !== null)
    .sort((left, right) => left.timeSec - right.timeSec);
}

export function calculateHrr60({ heartRateSamples = [], mainSessionEndSec } = {}) {
  const samples = normalizeHeartRateSamples(heartRateSamples);

  if (samples.length === 0) {
    return null;
  }

  const fallbackEndSec = samples.at(-1)?.timeSec;
  const sessionEndSec = toFiniteNumber(mainSessionEndSec) ?? fallbackEndSec;

  if (sessionEndSec === null) {
    return null;
  }

  let endSample = null;

  for (let index = samples.length - 1; index >= 0; index -= 1) {
    if (samples[index].timeSec <= sessionEndSec) {
      endSample = samples[index];
      break;
    }
  }

  const recoverySample = samples.find((sample) => sample.timeSec >= sessionEndSec + 60);

  if (!endSample || !recoverySample) {
    return null;
  }

  return {
    mainSessionEndSec: sessionEndSec,
    endHeartRate: endSample.heartRate,
    heartRateAt60Sec: recoverySample.heartRate,
    recovery: endSample.heartRate - recoverySample.heartRate
  };
}

export function classifyHrr60(recovery) {
  if (!Number.isFinite(recovery)) {
    return 'brak danych';
  }

  if (recovery >= 30) {
    return 'bardzo dobry';
  }

  if (recovery >= 20) {
    return 'dobry';
  }

  if (recovery >= 12) {
    return 'umiarkowany';
  }

  return 'niski';
}
