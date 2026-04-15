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

function emptyEquipmentSet() {
  return {
    main_hand: null,
    off_hand: null,
    head: null,
    body: null,
    arms: null,
  };
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asObject(value) {
  return value && typeof value === "object" ? value : {};
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
  entry.equipment = emptyEquipmentSet();
  return entry;
}

export function returnEquipmentToInventory(saveData, equipment, inventoryCatalog = {}) {
  if (!saveData || typeof saveData !== "object") return false;

  const eq = asObject(equipment);
  const weaponNames = new Set(asArray(inventoryCatalog.weapons).map((name) => String(name || "")));
  const armorNames = new Set(asArray(inventoryCatalog.armors).map((name) => String(name || "")));

  if (!saveData.inventory || typeof saveData.inventory !== "object") {
    saveData.inventory = {};
  }

  let changed = false;
  ["main_hand", "off_hand", "head", "body", "arms"].forEach((slotKey) => {
    const itemName = String(eq[slotKey] || "").trim();
    if (!itemName) return;

    let bucketName = null;
    if (weaponNames.has(itemName)) bucketName = "Weapon";
    else if (armorNames.has(itemName)) bucketName = "Armor";
    if (!bucketName) return;

    if (!saveData.inventory[bucketName] || typeof saveData.inventory[bucketName] !== "object") {
      saveData.inventory[bucketName] = {};
    }
    const current = asNum(saveData.inventory[bucketName][itemName], 0);
    saveData.inventory[bucketName][itemName] = current + 1;
    changed = true;
  });

  return changed;
}
