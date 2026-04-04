function asNum(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function cloneJobProgress(progress, fallbackLevel = 1, fallbackSkillPoint = 0) {
  if (progress && typeof progress === "object") {
    return {
      level: Math.max(1, asNum(progress.level, fallbackLevel)),
      skill_point: Math.max(0, asNum(progress.skill_point, fallbackSkillPoint)),
    };
  }
  return {
    level: Math.max(1, asNum(fallbackLevel, 1)),
    skill_point: Math.max(0, asNum(fallbackSkillPoint, 0)),
  };
}

export function applyJobChangeToSaveEntry(saveEntry, options = {}) {
  const entry = saveEntry && typeof saveEntry === "object" ? { ...saveEntry } : {};
  const currentJob = String(options.currentJob || entry.job || "").trim();
  const nextJob = String(options.nextJob || "").trim();
  if (!nextJob) return entry;

  const jobLevels = entry.job_levels && typeof entry.job_levels === "object"
    ? { ...entry.job_levels }
    : {};

  const currentProgress = cloneJobProgress(
    jobLevels[currentJob],
    options.currentJobLevel ?? entry?.job_level?.level ?? 1,
    options.currentJobSkillPoint ?? entry?.job_level?.skill_point ?? 0,
  );
  if (currentJob) {
    jobLevels[currentJob] = currentProgress;
  }

  const nextProgress = cloneJobProgress(
    jobLevels[nextJob],
    options.nextJobLevel ?? 1,
    options.nextJobSkillPoint ?? 0,
  );
  jobLevels[nextJob] = nextProgress;

  entry.job = nextJob;
  entry.current_job = nextJob;
  entry.job_levels = jobLevels;
  entry.job_level = { ...nextProgress };
  return entry;
}
