import { memberIdentityKeys } from "./shared_party.js";

const STATUS_EFFECT_KEY_BY_ICON = {
  poison: "Poison",
  blind: "Blind",
  mini: "Mini",
  silence: "Silence",
  toad: "Toad",
  petrify: "Petrification",
  petrification: "Petrification",
  ko: "KO",
  confusion: "Confusion",
  sleep: "Sleep",
  paralysis: "Paralysis",
  paralyze: "Paralysis",
  "partial petrification": "Partial Petrification",
  partial_petrify: "Partial Petrification",
};

function cloneJsonValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function asArrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function asPlainObject(value) {
  return value && typeof value === "object" ? value : {};
}

function normalizeStatusIconText(value) {
  return String(value || "").trim().toLowerCase().replace(/[_-]/g, " ");
}

function findSavePartyIndex(saveParty, member, fallbackIndex) {
  const wanted = memberIdentityKeys(member, fallbackIndex);
  if (!wanted.length) return fallbackIndex;
  const wantedSet = new Set(wanted);
  const matchedIndex = asArrayValue(saveParty).findIndex((entry, index) => (
    memberIdentityKeys(entry, index).some((key) => wantedSet.has(key))
  ));
  return matchedIndex >= 0 ? matchedIndex : fallbackIndex;
}

export function mergeMenuStateIntoSave(saveData, menuState) {
  const nextSave = cloneJsonValue(saveData || {});
  const nextMenuState = menuState && typeof menuState === "object" ? menuState : {};
  const saveParty = asArrayValue(nextSave.party);
  const menuParty = asArrayValue(nextMenuState.party);
  const magicSetup = asPlainObject(nextMenuState.magic_setup);
  const equippedByMember = asArrayValue(magicSetup.equipped_by_member);

  menuParty.forEach((member, index) => {
    const saveIndex = findSavePartyIndex(saveParty, member, index);
    const saveEntry = {
      ...asPlainObject(saveParty[saveIndex]),
      ...asPlainObject(member),
    };
    const mpLevels = asPlainObject(member?.mp_levels);
    const nextStatusEffects = asPlainObject(saveEntry.status_effects);
    const nextJob = String(
      member?.current_job || member?.job || saveEntry.current_job || saveEntry.job || "",
    ).trim();
    const jobLevels = asPlainObject(saveEntry.job_levels);

    Object.keys(nextStatusEffects).forEach((key) => {
      nextStatusEffects[key] = false;
    });
    asArrayValue(member?.status_icons).forEach((icon) => {
      const statusKey = STATUS_EFFECT_KEY_BY_ICON[normalizeStatusIconText(icon)];
      if (statusKey) nextStatusEffects[statusKey] = true;
    });

    saveEntry.job = nextJob;
    saveEntry.current_job = nextJob;
    saveEntry.row = String(member?.row || saveEntry.row || "front");
    saveEntry.hp = Number(member?.hp ?? saveEntry.hp ?? 0);
    saveEntry.max_hp = Number(member?.max_hp ?? saveEntry.max_hp ?? 0);
    saveEntry.mp_levels = mpLevels;
    saveEntry.mp = Object.fromEntries(
      Array.from({ length: 8 }, (_unused, offset) => {
        const level = String(offset + 1);
        return [`L${level}MP`, Number(asPlainObject(mpLevels[level]).current ?? 0)];
      }),
    );
    saveEntry.status_effects = nextStatusEffects;
    saveEntry.status_icons = asArrayValue(member?.status_icons);
    if (member?.equipment && typeof member.equipment === "object") {
      saveEntry.equipment = cloneJsonValue(member.equipment);
    }
    if (nextJob) {
      const currentJobLevel = asPlainObject(saveEntry.job_level);
      const nextJobProgress = jobLevels[nextJob] && typeof jobLevels[nextJob] === "object"
        ? { ...jobLevels[nextJob] }
        : {
          level: Number(currentJobLevel.level ?? 1) || 1,
          skill_point: Number(currentJobLevel.skill_point ?? 0) || 0,
        };
      nextJobProgress.level = Math.max(1, Number(nextJobProgress.level ?? 1) || 1);
      nextJobProgress.skill_point = Math.max(0, Number(nextJobProgress.skill_point ?? 0) || 0);
      jobLevels[nextJob] = nextJobProgress;
      saveEntry.job_levels = jobLevels;
      saveEntry.job_level = nextJobProgress;
    }

    const memberSetup = asPlainObject(equippedByMember[index]);
    if (Object.keys(memberSetup).length) {
      const magic = {};
      for (let lv = 1; lv <= 8; lv += 1) {
        const row = asArrayValue(memberSetup[String(lv)]).slice(0, 3).map((name) => (
          typeof name === "string" && name ? name : null
        ));
        while (row.length < 3) row.push(null);
        magic[`LV${lv}`] = row;
      }
      saveEntry.Magic = magic;
      delete saveEntry.magic;
    }

    saveParty[saveIndex] = saveEntry;
  });

  nextSave.party = saveParty;
  nextSave.CP = Number(nextMenuState?.resources?.cp ?? nextSave.CP ?? 0);
  nextSave.gil = Number(nextMenuState?.resources?.gil ?? nextSave.gil ?? 0);
  return nextSave;
}
