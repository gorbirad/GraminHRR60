import { calculateHrr60, classifyHrr60, normalizeHeartRateSamples } from './hrr.js';

function firstDefined(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

export function normalizeGarminActivity(activity = {}) {
  const heartRateSamples = normalizeHeartRateSamples(
    activity.heartRateSamples ?? activity.heartRateTrack ?? activity.samples ?? []
  );
  const mainSessionEndSec = firstDefined(
    activity.mainSessionEndSec,
    activity.summary?.mainSessionEndSec,
    activity.summary?.durationSec,
    activity.summaryDTO?.duration,
    heartRateSamples.at(-1)?.timeSec
  );
  const hrr60 = calculateHrr60({ heartRateSamples, mainSessionEndSec });
  const startTime = firstDefined(activity.startTimeLocal, activity.startTimeGMT, activity.startTime);

  return {
    id: String(firstDefined(activity.activityId, activity.id, 'unknown')),
    name: firstDefined(activity.activityName, activity.name, 'Trening bez nazwy'),
    activityType: firstDefined(activity.activityType?.typeKey, activity.typeKey, activity.type, 'unknown'),
    startTime,
    mainSessionEndSec,
    endHeartRate: hrr60?.endHeartRate ?? null,
    heartRateAt60Sec: hrr60?.heartRateAt60Sec ?? null,
    hrr60: hrr60?.recovery ?? null,
    classification: classifyHrr60(hrr60?.recovery),
    sampleCount: heartRateSamples.length,
    status: hrr60 ? 'calculated' : 'insufficient-data'
  };
}
