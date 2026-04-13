import {
  LOCAL_MENU_STORAGE_KEY,
  makeSaveEnvelope,
  persistSaveEnvelopeToStorage,
  restoreSaveEnvelopeFromStorage,
  restoreSaveEnvelopeFromStorageAsync,
} from "./shared_storage.js";
import { findPartyMemberIndex } from "./shared_party.js";

export const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";
export const PYTHON_BUNDLE_VERSION = "20260414a";
export const INN_PRICE = 10;

export function asObj(value) {
  return value && typeof value === "object" ? value : {};
}

export function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export function asNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function clone(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

export function readStoredEnvelope() {
  const envelope = restoreSaveEnvelopeFromStorage();
  if (envelope?.save && typeof envelope.save === "object") return envelope;
  try {
    const raw = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed?.save && typeof parsed.save === "object") return parsed;
    if (parsed && typeof parsed === "object") return makeSaveEnvelope(parsed, {});
  } catch (_error) {
    return null;
  }
  return null;
}

export async function readStoredEnvelopeAsync() {
  const envelope = await restoreSaveEnvelopeFromStorageAsync();
  if (envelope?.save && typeof envelope.save === "object") return envelope;
  return readStoredEnvelope();
}

export function currentGil(envelope = null) {
  const source = envelope?.save ? envelope : readStoredEnvelope();
  const menuGil = asNumber(source?.menu_state?.resources?.gil, NaN);
  if (Number.isFinite(menuGil)) return menuGil;
  return asNumber(source?.save?.gil, 0);
}

export function getStoredLocationSelection() {
  const envelope = readStoredEnvelope();
  return {
    selected_location_group: String(envelope?.selected_location_group || ""),
    selected_location: String(envelope?.selected_location || ""),
  };
}

export async function getStoredLocationSelectionAsync() {
  const envelope = await readStoredEnvelopeAsync();
  return {
    selected_location_group: String(envelope?.selected_location_group || ""),
    selected_location: String(envelope?.selected_location || ""),
  };
}

export function syncStoredLocationSelection(selectedLocationGroup, selectedLocation) {
  const originalEnvelope = readStoredEnvelope();
  const nextEnvelope = originalEnvelope
    ? clone(originalEnvelope)
    : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  nextEnvelope.selected_location_group = String(selectedLocationGroup || "");
  nextEnvelope.selected_location = String(selectedLocation || "");
  nextEnvelope.saved_at = new Date().toISOString();
  return persistSaveEnvelopeToStorage(nextEnvelope);
}

export async function syncStoredLocationSelectionAsync(selectedLocationGroup, selectedLocation) {
  const originalEnvelope = await readStoredEnvelopeAsync();
  const nextEnvelope = originalEnvelope
    ? clone(originalEnvelope)
    : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  nextEnvelope.selected_location_group = String(selectedLocationGroup || "");
  nextEnvelope.selected_location = String(selectedLocation || "");
  nextEnvelope.saved_at = new Date().toISOString();
  return persistSaveEnvelopeToStorage(nextEnvelope);
}

export function persistMenuStateFromEnvelope(envelope) {
  if (!envelope?.menu_state || typeof envelope.menu_state !== "object") return;
  try {
    localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(envelope.menu_state));
  } catch (_error) {
    // noop
  }
}

export async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} fetch failed: ${response.status}`);
  return response.json();
}

export async function preparePythonBundle(instance) {
  const response = await fetch(`./python_bundle.zip?v=${PYTHON_BUNDLE_VERSION}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`python_bundle.zip fetch failed: ${response.status}`);
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/python_bundle.zip", bytes);
  await instance.runPythonAsync(`
import sys
import zipfile

with zipfile.ZipFile('/tmp/python_bundle.zip', 'r') as bundle:
    bundle.extractall('/')
if '/' not in sys.path:
    sys.path.insert(0, '/')
`);
}

export async function prepareExplicitGroups(instance) {
  const response = await fetch("../assets/data/explicit_groups.json");
  if (!response.ok) {
    instance.FS.writeFile("/tmp/explicit_groups.json", new Uint8Array());
    return;
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/explicit_groups.json", bytes);
}

export async function loadShopMasterData() {
  const [shopsRaw, itemsRaw, weaponsRaw, armorsRaw, spellsRaw] = await Promise.all([
    loadJson("../assets/data/ffiii_shops.json"),
    loadJson("../assets/data/ffiii_items.json"),
    loadJson("../assets/data/ffiii_weapons.json"),
    loadJson("../assets/data/ffiii_armors.json"),
    loadJson("../assets/data/ffiii_spells.json"),
  ]);

  const itemTypeByName = {};
  asArray(itemsRaw?.items).forEach((item) => {
    const name = String(item?.Name || "");
    if (!name) return;
    itemTypeByName[name] = String(item?.ItemType || "");
  });

  const spellLevelByName = {};
  asArray(spellsRaw?.spells).forEach((spell) => {
    const name = String(spell?.name || "");
    const level = asNumber(spell?.Level, 0);
    if (name && level > 0) spellLevelByName[name] = level;
  });

  return {
    shopEntries: asArray(shopsRaw),
    itemTypeByName,
    weaponNameSet: new Set(asArray(weaponsRaw?.weapons).map((row) => String(row?.name || "")).filter(Boolean)),
    armorNameSet: new Set(asArray(armorsRaw?.armors).map((row) => String(row?.name || "")).filter(Boolean)),
    spellLevelByName,
  };
}

export function normalizeShopTypeToInventoryBucket(masterData, type, itemName) {
  const rawType = String(type || "");
  if (rawType === "Armor") return "Armor";
  if (rawType === "Weapons") return "Weapon";
  if (rawType === "Weapons & Armor") {
    if (masterData.weaponNameSet.has(itemName)) return "Weapon";
    if (masterData.armorNameSet.has(itemName)) return "Armor";
  }
  if (rawType === "Magic" || rawType === "Summon Magic") return "Magic";
  const itemType = String(masterData.itemTypeByName[itemName] || "");
  if (itemType) return itemType;
  if (masterData.weaponNameSet.has(itemName)) return "Weapon";
  if (masterData.armorNameSet.has(itemName)) return "Armor";
  return "Anywhere";
}

export function addPurchasedItemToInventory(save, spellLevelByName, bucketName, itemName, quantity = 1) {
  if (!save || typeof save !== "object") return false;
  if (!save.inventory || typeof save.inventory !== "object") {
    save.inventory = {};
  }
  if (bucketName === "Magic") {
    const spellLevel = asNumber(spellLevelByName[itemName], 0);
    if (spellLevel <= 0) return false;
    const levelKey = `LV${spellLevel}`;
    if (!save.inventory.Magic || typeof save.inventory.Magic !== "object") {
      save.inventory.Magic = {};
    }
    if (!save.inventory.Magic[levelKey] || typeof save.inventory.Magic[levelKey] !== "object") {
      save.inventory.Magic[levelKey] = {};
    }
    const current = asNumber(save.inventory.Magic[levelKey][itemName], 0);
    save.inventory.Magic[levelKey][itemName] = current + quantity;
    return true;
  }
  if (!save.inventory[bucketName] || typeof save.inventory[bucketName] !== "object") {
    save.inventory[bucketName] = {};
  }
  const current = asNumber(save.inventory[bucketName][itemName], 0);
  save.inventory[bucketName][itemName] = current + quantity;
  return true;
}

export function syncMenuStateAfterPurchase(envelope, spellLevelByName, itemName, bucketName) {
  if (!envelope?.menu_state || typeof envelope.menu_state !== "object") return;
  if (!envelope.menu_state.resources || typeof envelope.menu_state.resources !== "object") {
    envelope.menu_state.resources = {};
  }
  envelope.menu_state.resources.gil = asNumber(envelope.save?.gil, 0);
  if (bucketName !== "Magic") return;
  const level = asNumber(spellLevelByName[itemName], 0);
  if (level <= 0) return;
  if (!envelope.menu_state.magic_setup || typeof envelope.menu_state.magic_setup !== "object") {
    envelope.menu_state.magic_setup = {};
  }
  const magicSetup = envelope.menu_state.magic_setup;
  if (!magicSetup.stock_by_level || typeof magicSetup.stock_by_level !== "object") {
    magicSetup.stock_by_level = {};
  }
  const key = String(level);
  const row = asArray(magicSetup.stock_by_level[key]);
  row.push(itemName);
  magicSetup.stock_by_level[key] = row;
}

function clearedStatusEffects(statusEffects) {
  const next = {};
  Object.entries(asObj(statusEffects)).forEach(([key]) => {
    next[key] = false;
  });
  return next;
}

function mpLevelsToSaveMp(mpLevels) {
  const mp = {};
  for (let level = 1; level <= 8; level += 1) {
    const row = asObj(asObj(mpLevels)[String(level)]);
    mp[`L${level}MP`] = asNumber(row.current, 0);
  }
  return mp;
}

export function syncSavePartyRecovery(save, recoveredParty) {
  const saveParty = asArray(save?.party);
  recoveredParty.forEach((member, index) => {
    const saveIndex = findPartyMemberIndex(saveParty, member, index);
    const saveEntry = saveParty[saveIndex];
    if (!saveEntry || typeof saveEntry !== "object") return;
    const hp = asNumber(member?.hp, asNumber(saveEntry.max_hp, asNumber(saveEntry.hp, 0)));
    const maxHp = asNumber(member?.max_hp, asNumber(saveEntry.max_hp, hp));
    const mpLevels = asObj(member?.mp_levels);
    saveEntry.hp = hp;
    saveEntry.max_hp = maxHp;
    saveEntry.mp_levels = mpLevels;
    saveEntry.mp = mpLevelsToSaveMp(mpLevels);
    saveEntry.status_effects = clearedStatusEffects(saveEntry.status_effects);
    if ("status_icons" in saveEntry) {
      saveEntry.status_icons = [];
    }
  });
  save.party = saveParty;
}

export function syncMenuPartyRecovery(menuState, recoveredParty) {
  if (!menuState || typeof menuState !== "object") return;
  const party = asArray(menuState.party);
  recoveredParty.forEach((member, index) => {
    const row = party[index];
    if (!row || typeof row !== "object") return;
    const hp = asNumber(member?.hp, asNumber(row.max_hp, asNumber(row.hp, 0)));
    const maxHp = asNumber(member?.max_hp, asNumber(row.max_hp, hp));
    const mpLevels = asObj(member?.mp_levels);
    row.hp = hp;
    row.max_hp = maxHp;
    row.mp_levels = mpLevels;
    row.status_icons = [];
    if (row.status && typeof row.status === "object") {
      row.status = {
        ...row.status,
        hp,
        max_hp: maxHp,
        mp_text: Array.from({ length: 8 }, (_v, idx) => {
          const level = String(idx + 1);
          return String(asNumber(asObj(mpLevels[level]).current, 0)).padStart(2, " ");
        }).join("/"),
        status_line: "-",
        status_icons: [],
      };
    }
  });
  menuState.party = party;
}

export async function buildRecoveredPartySnapshot(pyodide, save, selectedLocationGroup, selectedLocation) {
  if (!pyodide || !save || typeof save !== "object") return [];
  const bootForLocation = pyodide.globals.get("boot_engine_for_location_with_save_json");
  if (!bootForLocation) return [];
  const payloadText = String(
    bootForLocation(
      String(selectedLocationGroup || ""),
      String(selectedLocation || ""),
      JSON.stringify(save),
      7,
    ) || "",
  );
  if (!payloadText) return [];
  try {
    const payload = JSON.parse(payloadText);
    return asArray(payload?.session_status?.party);
  } catch (_error) {
    return [];
  }
}
