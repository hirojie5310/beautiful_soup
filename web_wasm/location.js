import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";
import {
  LOCAL_MENU_STORAGE_KEY,
  makeSaveEnvelope,
  persistSaveEnvelopeToStorage,
  restoreSaveEnvelopeFromStorage,
} from "./shared_storage.js";

const statusLine = document.getElementById("statusLine");
const locationGroupSelect = document.getElementById("locationGroupSelect");
const locationSelect = document.getElementById("locationSelect");
const startBattleBtn = document.getElementById("startBattleBtn");
const menuBtn = document.getElementById("menuBtn");
const shopMapSelect = document.getElementById("shopMapSelect");
const shopTypeSelect = document.getElementById("shopTypeSelect");
const shopGoodsSelect = document.getElementById("shopGoodsSelect");
const shopGilLine = document.getElementById("shopGilLine");
const shopStatusLine = document.getElementById("shopStatusLine");
const buyShopBtn = document.getElementById("buyShopBtn");
const stayInnBtn = document.getElementById("stayInnBtn");
const innStatusLine = document.getElementById("innStatusLine");

const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const PYTHON_BUNDLE_VERSION = "20260402b";
const INN_PRICE = 10;

let pyodide = null;
let locationGroups = [];
let shopEntries = [];
let itemTypeByName = {};
let weaponNameSet = new Set();
let armorNameSet = new Set();
let spellLevelByName = {};

async function preparePythonBundle(instance) {
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

async function prepareExplicitGroups(instance) {
  const response = await fetch("../assets/data/explicit_groups.json");
  if (!response.ok) {
    instance.FS.writeFile("/tmp/explicit_groups.json", new Uint8Array());
    return;
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/explicit_groups.json", bytes);
}

function asObj(value) {
  return value && typeof value === "object" ? value : {};
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function asNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function clone(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function readStoredEnvelope() {
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

function currentGil() {
  const envelope = readStoredEnvelope();
  const menuGil = asNumber(envelope?.menu_state?.resources?.gil, NaN);
  if (Number.isFinite(menuGil)) return menuGil;
  return asNumber(envelope?.save?.gil, 0);
}

function updateGilDisplay() {
  if (shopGilLine) {
    shopGilLine.textContent = `GIL ${currentGil().toLocaleString()}`;
  }
}

function parseStoredSelection() {
  try {
    const raw = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return {
      selected_location_group: String(parsed.selected_location_group || ""),
      selected_location: String(parsed.selected_location || ""),
    };
  } catch (_error) {
    return null;
  }
}

function setSelectOptions(select, values, selectedValue = "") {
  if (!select) return;
  const wanted = String(selectedValue || "");
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    if (String(value) === wanted) option.selected = true;
    select.appendChild(option);
  });
  if (values.length && !select.value) {
    select.value = String(values[0]);
  }
}

function renderLocationSelectors() {
  const selectedGroupName = locationGroupSelect.value;
  locationGroupSelect.innerHTML = "";
  locationGroups.forEach((group) => {
    const option = document.createElement("option");
    option.value = group.group_name;
    option.textContent = group.group_name;
    if (group.group_name === selectedGroupName) option.selected = true;
    locationGroupSelect.appendChild(option);
  });

  const currentGroup = locationGroups.find((g) => g.group_name === locationGroupSelect.value) || locationGroups[0];
  const locations = Array.isArray(currentGroup?.locations) ? currentGroup.locations : [];
  const selectedLocation = locationSelect.value;
  locationSelect.innerHTML = "";
  locations.forEach((loc) => {
    const option = document.createElement("option");
    option.value = loc;
    option.textContent = loc;
    if (loc === selectedLocation) option.selected = true;
    locationSelect.appendChild(option);
  });
  if (locations.length && !locationSelect.value) locationSelect.value = locations[0];
}

function saveAndGoBattle() {
  const payload = {
    selected_location_group: String(locationGroupSelect.value || ""),
    selected_location: String(locationSelect.value || ""),
  };
  sessionStorage.setItem(BATTLE_START_SELECTION_KEY, JSON.stringify(payload));
  window.location.href = "./battle.html";
}

async function loadJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} fetch failed: ${response.status}`);
  return response.json();
}

async function loadShopMasterData() {
  const [shopsRaw, itemsRaw, weaponsRaw, armorsRaw, spellsRaw] = await Promise.all([
    loadJson("../assets/data/ffiii_shops.json"),
    loadJson("../assets/data/ffiii_items.json"),
    loadJson("../assets/data/ffiii_weapons.json"),
    loadJson("../assets/data/ffiii_armors.json"),
    loadJson("../assets/data/ffiii_spells.json"),
  ]);

  shopEntries = asArray(shopsRaw);
  itemTypeByName = {};
  asArray(itemsRaw?.items).forEach((item) => {
    const name = String(item?.Name || "");
    if (!name) return;
    itemTypeByName[name] = String(item?.ItemType || "");
  });

  weaponNameSet = new Set(asArray(weaponsRaw?.weapons).map((row) => String(row?.name || "")).filter(Boolean));
  armorNameSet = new Set(asArray(armorsRaw?.armors).map((row) => String(row?.name || "")).filter(Boolean));
  spellLevelByName = {};
  asArray(spellsRaw?.spells).forEach((spell) => {
    const name = String(spell?.name || "");
    const level = asNumber(spell?.Level, 0);
    if (name && level > 0) spellLevelByName[name] = level;
  });
}

function selectedShopEntry() {
  return shopEntries.find((entry) => String(entry?.map || "") === String(shopMapSelect?.value || "")) || null;
}

function selectedShopTypeRow() {
  const entry = selectedShopEntry();
  return asArray(entry?.shops).find((row) => String(row?.type || "") === String(shopTypeSelect?.value || "")) || null;
}

function selectedGoodsRow() {
  const row = selectedShopTypeRow();
  return asArray(row?.goods).find((good) => String(good?.name || "") === String(shopGoodsSelect?.value || "")) || null;
}

function renderShopGoods() {
  const row = selectedShopTypeRow();
  const goods = asArray(row?.goods);
  setSelectOptions(shopGoodsSelect, goods.map((good) => String(good?.name || "")).filter(Boolean), shopGoodsSelect?.value || "");
  const selectedGood = selectedGoodsRow();
  const price = asNumber(selectedGood?.price, 0);
  if (shopStatusLine) {
    shopStatusLine.textContent = selectedGood
      ? `${selectedGood.name} / ${price.toLocaleString()} GIL`
      : "購入する商品を選択してください。";
  }
  if (buyShopBtn) {
    buyShopBtn.disabled = !selectedGood;
  }
}

function renderShopTypes() {
  const entry = selectedShopEntry();
  const shops = asArray(entry?.shops);
  setSelectOptions(shopTypeSelect, shops.map((row) => String(row?.type || "")).filter(Boolean), shopTypeSelect?.value || "");
  renderShopGoods();
}

function renderShopSelectors() {
  const maps = shopEntries.map((entry) => String(entry?.map || "")).filter(Boolean);
  const currentMap = String(shopMapSelect?.value || locationSelect?.value || "");
  const preferredMap = maps.includes(currentMap) ? currentMap : maps[0] || "";
  setSelectOptions(shopMapSelect, maps, preferredMap);
  renderShopTypes();
  updateGilDisplay();
}

function normalizeShopTypeToInventoryBucket(type, itemName) {
  const rawType = String(type || "");
  if (rawType === "Armor") return "Armor";
  if (rawType === "Weapons") return "Weapon";
  if (rawType === "Weapons & Armor") {
    if (weaponNameSet.has(itemName)) return "Weapon";
    if (armorNameSet.has(itemName)) return "Armor";
  }
  if (rawType === "Magic" || rawType === "Summon Magic") return "Magic";
  const itemType = String(itemTypeByName[itemName] || "");
  if (itemType) return itemType;
  if (weaponNameSet.has(itemName)) return "Weapon";
  if (armorNameSet.has(itemName)) return "Armor";
  return "Anywhere";
}

function addPurchasedItemToInventory(save, bucketName, itemName, quantity = 1) {
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

function syncMenuStateAfterPurchase(envelope, itemName, bucketName) {
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

function persistMenuStateFromEnvelope(envelope) {
  if (!envelope?.menu_state || typeof envelope.menu_state !== "object") return;
  try {
    localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(envelope.menu_state));
  } catch (_error) {
    // noop
  }
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

function syncSavePartyRecovery(save, recoveredParty) {
  const saveParty = asArray(save?.party);
  recoveredParty.forEach((member, index) => {
    const saveEntry = saveParty[index];
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

function syncMenuPartyRecovery(menuState, recoveredParty) {
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

async function buildRecoveredPartySnapshot(save) {
  if (!pyodide || !save || typeof save !== "object") return [];
  const bootForLocation = pyodide.globals.get("boot_engine_for_location_with_save_json");
  if (!bootForLocation) return [];
  const payloadText = String(
    bootForLocation(
      String(locationGroupSelect?.value || ""),
      String(locationSelect?.value || ""),
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

async function stayAtInn() {
  const gil = currentGil();
  if (gil < INN_PRICE) {
    if (innStatusLine) {
      innStatusLine.textContent = `GIL が足りません。必要: ${INN_PRICE.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
    }
    return;
  }

  const originalEnvelope = readStoredEnvelope();
  const nextEnvelope = originalEnvelope ? clone(originalEnvelope) : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
  }

  const recoveredParty = await buildRecoveredPartySnapshot(nextEnvelope.save);
  if (!recoveredParty.length) {
    if (innStatusLine) {
      innStatusLine.textContent = "宿屋の回復処理に失敗しました。";
    }
    return;
  }

  nextEnvelope.save.gil = Math.max(0, gil - INN_PRICE);
  syncSavePartyRecovery(nextEnvelope.save, recoveredParty);
  if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
    nextEnvelope.menu_state = { party: [], resources: { cp: 0, cp_max: 255, gil: nextEnvelope.save.gil } };
  }
  if (!nextEnvelope.menu_state.resources || typeof nextEnvelope.menu_state.resources !== "object") {
    nextEnvelope.menu_state.resources = {};
  }
  nextEnvelope.menu_state.resources.gil = nextEnvelope.save.gil;
  syncMenuPartyRecovery(nextEnvelope.menu_state, recoveredParty);
  nextEnvelope.saved_at = new Date().toISOString();
  nextEnvelope.selected_location_group = String(locationGroupSelect?.value || nextEnvelope.selected_location_group || "");
  nextEnvelope.selected_location = String(locationSelect?.value || nextEnvelope.selected_location || "");

  if (!persistSaveEnvelopeToStorage(nextEnvelope)) {
    if (innStatusLine) {
      innStatusLine.textContent = "宿泊内容の保存に失敗しました。";
    }
    return;
  }

  persistMenuStateFromEnvelope(nextEnvelope);
  updateGilDisplay();
  if (innStatusLine) {
    innStatusLine.textContent = `宿に泊まりました。HP・MP・状態異常が全快しました。-${INN_PRICE.toLocaleString()} GIL`;
  }
}

function purchaseSelectedGoods() {
  const goods = selectedGoodsRow();
  const typeRow = selectedShopTypeRow();
  if (!goods || !typeRow) {
    if (shopStatusLine) shopStatusLine.textContent = "購入する商品を選択してください。";
    return;
  }

  const price = asNumber(goods.price, 0);
  const gil = currentGil();
  if (gil < price) {
    if (shopStatusLine) {
      shopStatusLine.textContent = `GIL が足りません。必要: ${price.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
    }
    return;
  }

  const originalEnvelope = readStoredEnvelope();
  const nextEnvelope = originalEnvelope ? clone(originalEnvelope) : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
  }
  const bucketName = normalizeShopTypeToInventoryBucket(typeRow.type, goods.name);
  const nextGil = Math.max(0, gil - price);
  nextEnvelope.save.gil = nextGil;
  if (!addPurchasedItemToInventory(nextEnvelope.save, bucketName, goods.name, 1)) {
    if (shopStatusLine) {
      shopStatusLine.textContent = `${goods.name} の保存先を解決できませんでした。`;
    }
    return;
  }

  syncMenuStateAfterPurchase(nextEnvelope, goods.name, bucketName);
  nextEnvelope.saved_at = new Date().toISOString();
  nextEnvelope.selected_location_group = String(locationGroupSelect?.value || nextEnvelope.selected_location_group || "");
  nextEnvelope.selected_location = String(locationSelect?.value || nextEnvelope.selected_location || "");

  if (!persistSaveEnvelopeToStorage(nextEnvelope)) {
    if (shopStatusLine) {
      shopStatusLine.textContent = "購入内容の保存に失敗しました。";
    }
    return;
  }

  persistMenuStateFromEnvelope(nextEnvelope);
  updateGilDisplay();
  if (shopStatusLine) {
    shopStatusLine.textContent = `${goods.name} を購入しました。-${price.toLocaleString()} GIL`;
  }
}

async function bootLocationScreen() {
  statusLine.textContent = "Pyodide 起動中...";
  pyodide = await loadPyodide();
  await pyodide.loadPackage("typing-extensions");
  await preparePythonBundle(pyodide);
  await prepareExplicitGroups(pyodide);

  const bootstrapResponse = await fetch("./bootstrap_runtime.py");
  if (!bootstrapResponse.ok) throw new Error(`bootstrap_runtime.py fetch failed: ${bootstrapResponse.status}`);
  const bootstrapPython = await bootstrapResponse.text();
  await pyodide.runPythonAsync(bootstrapPython);
  await loadShopMasterData();

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];
  renderLocationSelectors();

  const stored = parseStoredSelection();
  if (stored?.selected_location_group) {
    locationGroupSelect.value = stored.selected_location_group;
    renderLocationSelectors();
  } else if (selectionPayload?.selected_group) {
    locationGroupSelect.value = selectionPayload.selected_group;
    renderLocationSelectors();
  }

  if (stored?.selected_location) {
    locationSelect.value = stored.selected_location;
  } else if (selectionPayload?.selected_location) {
    locationSelect.value = selectionPayload.selected_location;
  }

  renderShopSelectors();
  if (shopMapSelect && shopEntries.some((entry) => String(entry?.map || "") === String(locationSelect?.value || ""))) {
    shopMapSelect.value = String(locationSelect.value || "");
    renderShopTypes();
  }

  startBattleBtn.disabled = false;
  statusLine.textContent = "Locationを選択して「戦闘開始」を押してください。";
}

locationGroupSelect?.addEventListener("change", () => renderLocationSelectors());
locationSelect?.addEventListener("change", () => {
  const locationName = String(locationSelect.value || "");
  if (shopEntries.some((entry) => String(entry?.map || "") === locationName)) {
    shopMapSelect.value = locationName;
    renderShopTypes();
  }
});
shopMapSelect?.addEventListener("change", () => renderShopTypes());
shopTypeSelect?.addEventListener("change", () => renderShopGoods());
shopGoodsSelect?.addEventListener("change", () => renderShopGoods());
buyShopBtn?.addEventListener("click", () => purchaseSelectedGoods());
stayInnBtn?.addEventListener("click", () => {
  stayAtInn().catch((_error) => {
    if (innStatusLine) {
      innStatusLine.textContent = "宿屋処理でエラーが発生しました。";
    }
  });
});
startBattleBtn?.addEventListener("click", () => saveAndGoBattle());
menuBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

bootLocationScreen().catch((error) => {
  statusLine.textContent = `起動失敗: ${String(error)}`;
});
