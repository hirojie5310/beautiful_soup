export const FIXED_PARTY_SLOT_KEYS = ["runeth", "arc", "refia", "ingus"];
export const FIXED_PARTY_SLOT_LABELS = ["Runeth", "Arc", "Refia", "Ingus"];

export function normalizeFaceKey(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/^ch_/, "")
    .replace(/\.(png|jpg|jpeg|webp)$/i, "")
    .replace(/\s+/g, "_")
    .replace(/-/g, "_");
}

export function resolveFaceImageCandidates(member, memberIndex = -1) {
  const portraitKey = normalizeFaceKey(member?.portrait_key);
  const nameKey = normalizeFaceKey(member?.name);
  const imageNameKey = normalizeFaceKey(member?.image_name);
  const slotKey = FIXED_PARTY_SLOT_KEYS[memberIndex] || "";
  const aliasMap = { luneth: "runeth" };
  const keys = [portraitKey, imageNameKey, nameKey, slotKey]
    .map((key) => aliasMap[key] || key)
    .filter((value, index, arr) => value && arr.indexOf(value) === index);
  if (!keys.length) return [];
  const exts = ["png", "webp", "jpg", "jpeg"];
  const paths = [];
  keys.forEach((key) => {
    const variants = [key, key.charAt(0).toUpperCase() + key.slice(1)];
    variants.forEach((variantKey) => {
      const safeKey = encodeURIComponent(variantKey);
      exts.forEach((ext) => {
        paths.push(`/web_wasm/portraits/${safeKey}.${ext}`);
        paths.push(`/web_wasm/faces/${safeKey}.${ext}`);
        paths.push(`./portraits/${safeKey}.${ext}`);
        paths.push(`../assets/images/portraits/${safeKey}.${ext}`);
        paths.push(new URL(`../assets/images/portraits/${safeKey}.${ext}`, import.meta.url).href);
        paths.push(`/assets/images/portraits/${safeKey}.${ext}`);
        paths.push(`../assets/images/motions/${safeKey}.${ext}`);
        paths.push(new URL(`../assets/images/motions/${safeKey}.${ext}`, import.meta.url).href);
        paths.push(`/assets/images/motions/${safeKey}.${ext}`);
      });
    });
  });
  return paths.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

export function memberIdentityKeys(member, fallbackIndex = -1) {
  const keys = [];
  [
    normalizeFaceKey(member?.portrait_key),
    normalizeFaceKey(member?.image_name),
    normalizeFaceKey(member?.name),
  ].forEach((rawKey) => {
    const key = rawKey === "luneth" ? "runeth" : rawKey;
    if (key && !keys.includes(key)) keys.push(key);
  });
  const slotIndex = Number(member?.index ?? fallbackIndex);
  if (Number.isInteger(slotIndex) && slotIndex >= 0 && slotIndex < FIXED_PARTY_SLOT_KEYS.length) {
    const slotKey = FIXED_PARTY_SLOT_KEYS[slotIndex];
    if (!keys.includes(slotKey)) keys.push(slotKey);
  }
  return keys;
}

function explicitMemberIdentityKeys(member) {
  if (!member || typeof member !== "object") return [];
  const keys = [];
  [
    normalizeFaceKey(member?.portrait_key),
    normalizeFaceKey(member?.image_name),
    normalizeFaceKey(member?.name),
  ].forEach((rawKey) => {
    const key = rawKey === "luneth" ? "runeth" : rawKey;
    if (key && !keys.includes(key)) keys.push(key);
  });
  return keys;
}

export function normalizePartyIdentityOrder(party) {
  const source = Array.isArray(party) ? party.filter((member) => member && typeof member === "object") : [];
  if (!source.length) return [];
  const unused = new Set(source.map((_, index) => index));
  const normalized = [];
  const slotCount = Math.max(source.length, FIXED_PARTY_SLOT_KEYS.length);
  for (let slotIndex = 0; slotIndex < slotCount; slotIndex += 1) {
    let matchIndex = -1;
    const slotKey = FIXED_PARTY_SLOT_KEYS[slotIndex] || "";
    if (slotKey) {
      matchIndex = source.findIndex((member, index) => unused.has(index) && memberIdentityKeys(member, index).includes(slotKey));
    }
    if (matchIndex < 0 && unused.has(slotIndex)) {
      matchIndex = slotIndex;
    }
    if (matchIndex < 0) {
      matchIndex = source.findIndex((_member, index) => unused.has(index));
    }
    if (matchIndex < 0) break;
    unused.delete(matchIndex);
    const member = source[matchIndex];
    normalized.push({
      ...member,
      index: slotIndex,
      name: FIXED_PARTY_SLOT_LABELS[slotIndex] || String(member?.name || "Unknown"),
      portrait_key: member?.portrait_key ?? FIXED_PARTY_SLOT_KEYS[slotIndex] ?? null,
    });
  }
  return normalized;
}

export function normalizeMemberIndexedRows(sourceParty, rows) {
  const source = Array.isArray(sourceParty)
    ? sourceParty.filter((member) => member && typeof member === "object")
    : [];
  const sourceRows = Array.isArray(rows) ? rows : [];
  if (!source.length || !sourceRows.length) return sourceRows.slice();
  const unused = new Set(source.map((_, index) => index));
  const normalizedRows = [];
  const slotCount = Math.max(source.length, FIXED_PARTY_SLOT_KEYS.length);
  for (let slotIndex = 0; slotIndex < slotCount; slotIndex += 1) {
    let matchIndex = -1;
    const slotKey = FIXED_PARTY_SLOT_KEYS[slotIndex] || "";
    if (slotKey) {
      matchIndex = source.findIndex((member, index) => (
        unused.has(index) && memberIdentityKeys(member, index).includes(slotKey)
      ));
    }
    if (matchIndex < 0 && unused.has(slotIndex)) {
      matchIndex = slotIndex;
    }
    if (matchIndex < 0) {
      matchIndex = source.findIndex((_member, index) => unused.has(index));
    }
    if (matchIndex < 0) break;
    unused.delete(matchIndex);
    normalizedRows.push(sourceRows[matchIndex]);
  }
  return normalizedRows;
}

export function findPartyMemberIndex(party, member, fallbackIndex = -1) {
  const sourceParty = Array.isArray(party) ? party : [];
  const explicitWanted = explicitMemberIdentityKeys(member);
  if (explicitWanted.length) {
    const explicitWantedSet = new Set(explicitWanted);
    const explicitMatchIndex = sourceParty.findIndex((entry) => (
      explicitMemberIdentityKeys(entry).some((key) => explicitWantedSet.has(key))
    ));
    if (explicitMatchIndex >= 0) return explicitMatchIndex;
  }

  const wanted = memberIdentityKeys(member, fallbackIndex);
  if (!wanted.length) return fallbackIndex;
  const wantedSet = new Set(wanted);
  const matchedIndex = sourceParty.findIndex((entry, index) => (
    memberIdentityKeys(entry, index).some((key) => wantedSet.has(key))
  ));
  return matchedIndex >= 0 ? matchedIndex : fallbackIndex;
}

export function jobLevelRows(entry) {
  return entry?.job_levels && typeof entry.job_levels === "object" ? entry.job_levels : {};
}

export function highestJobLevelName(jobLevels) {
  let bestName = "";
  let bestLevel = -1;
  Object.entries(jobLevels || {}).forEach(([jobName, row]) => {
    const level = typeof row === "object" && row !== null
      ? Number(row?.level ?? 0)
      : Number(row ?? 0);
    if (!jobName || !Number.isFinite(level) || level <= bestLevel) return;
    bestName = String(jobName);
    bestLevel = level;
  });
  return bestName;
}

export function resolveMemberJob(member, saveEntry = null) {
  const memberJob = String(member?.job || "").trim();
  const saveJob = String(saveEntry?.job || "").trim();
  const jobLevels = jobLevelRows(saveEntry);
  if (memberJob && (!Object.keys(jobLevels).length || jobLevels[memberJob])) return memberJob;
  if (saveJob && (!Object.keys(jobLevels).length || jobLevels[saveJob])) return saveJob;
  return highestJobLevelName(jobLevels) || memberJob || saveJob || "Unknown";
}

export function normalizeSavePartyAgainstTemplate(saveParty, templateParty, mergeSaveData) {
  const sourceParty = Array.isArray(saveParty) ? saveParty : [];
  const normalizedParty = normalizePartyIdentityOrder(sourceParty);
  return normalizedParty.map((member, index) => {
    const templateEntry = Array.isArray(templateParty) ? templateParty[index] : null;
    const merged = templateEntry && typeof templateEntry === "object"
      ? mergeSaveData(templateEntry, member)
      : { ...member };
    return {
      ...merged,
      index,
      name: FIXED_PARTY_SLOT_LABELS[index] || String(merged?.name || member?.name || "Unknown"),
      portrait_key: merged?.portrait_key ?? FIXED_PARTY_SLOT_KEYS[index] ?? null,
      job: resolveMemberJob(merged, merged),
    };
  });
}
