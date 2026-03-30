const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

const modeRow = document.getElementById("modeRow");
const itemTitle = document.getElementById("itemTitle");
const itemList = document.getElementById("itemList");
const targetList = document.getElementById("targetList");
const messageLine = document.getElementById("messageLine");
const memberName = document.getElementById("memberName");
const sortLine = document.getElementById("sortLine");
const backBtn = document.getElementById("backBtn");

const MODES = [
  { key: "use", label: "つかう" },
  { key: "sort", label: "せいとん" },
  { key: "key_item", label: "だいじなもの" },
];

const ITEM_TYPE_ORDER = {
  Anywhere: 0,
  Field: 1,
  Combat: 2,
  Weapon: 3,
  Armor: 4,
  "Key Item": 5,
};
const FIELD_USABLE_TYPES = new Set(["Anywhere", "Field"]);
const TARGET_REQUIRED = new Set([
  "potion", "hi potion", "elixir", "antidote", "echo herbs", "mallet", "maiden's kiss",
  "gold needle", "eye drops", "phoenix down",
]);
const HEAL_AMOUNT = { potion: 90, "hi potion": 360 };
const STATUS_CLEAR = {
  antidote: ["poison"],
  "eye drops": ["blind"],
  "echo herbs": ["silence"],
  "maiden's kiss": ["toad"],
  mallet: ["mini"],
  "gold needle": ["petrify", "petrification", "partial_petrify", "partial petrification"],
};

let modeKey = "use";
let selectedItemName = "";
let sortAscending = true;
let itemTypeByItemName = {};
let weaponNames = new Set();
let armorNames = new Set();
let itemTypeByCanonName = {};
let weaponCanonNames = new Set();
let armorCanonNames = new Set();

function isEquipmentLabelItem(name) {
  const rawName = String(name || "");
  const key = canon(rawName);
  return weaponNames.has(rawName) || armorNames.has(rawName) || weaponCanonNames.has(key) || armorCanonNames.has(key);
}

function asObj(v) { return v && typeof v === "object" ? v : {}; }
function asArray(v) { return Array.isArray(v) ? v : []; }
function asNum(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}
function canon(text) {
  return String(text || "").trim().toLowerCase().replace(/[\-_]/g, " ");
}

function parseMenuState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LOCAL_MENU_STORAGE_KEY) || "{}");
    return { raw: parsed, party: asArray(parsed?.party) };
  } catch (_error) {
    return { raw: {}, party: [] };
  }
}

function parseSaveEnvelope() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LOCAL_SAVE_STORAGE_KEY) || "{}");
    if (parsed?.version === 1 && parsed?.save && typeof parsed.save === "object") return parsed;
    if (parsed?.party && Array.isArray(parsed.party)) return { version: 1, save: parsed };
    return null;
  } catch (_error) {
    return null;
  }
}

function persistMenuState(raw) {
  try { localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(raw)); return true; } catch (_error) { return false; }
}

function persistSaveEnvelope(envelope) {
  try { localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope)); return true; } catch (_error) { return false; }
}

function resolveStatusIconCandidates(iconKey) {
  const safe = encodeURIComponent(String(iconKey || ""));
  if (!safe) return [];
  return [
    `/assets/images/status_icons/${safe}.png`,
    `../assets/images/status_icons/${safe}.png`,
    `/assets/status-icons/${safe}.png`,
  ];
}

function itemTypeForRow(row) {
  const itemName = String(row?.name || "");
  const canonName = canon(itemName);
  if (weaponNames.has(itemName) || weaponCanonNames.has(canonName)) return "Weapon";
  if (armorNames.has(itemName) || armorCanonNames.has(canonName)) return "Armor";

  const inferEquipmentTypeFromName = (nameKey) => {
    const weaponHints = [
      "sword", "blade", "knife", "dagger", "staff", "rod", "bow", "axe",
      "spear", "hammer", "whip", "nunchaku", "bell", "harp", "boomerang",
      "shuriken", "book", "tome", "claw", "katana", "lance",
    ];
    const armorHints = [
      "helm", "helmet", "cap", "hat", "armor", "mail", "robe", "vest",
      "garb", "gi", "shield", "gauntlet", "gauntlets", "glove", "gloves", "armlet", "bracer",
      "ribbon", "cowl", "band",
    ];
    const hasWholeToken = (hints) => {
      const normalized = ` ${String(nameKey || "").replace(/[^a-z0-9]+/g, " ")} `;
      return hints.some((token) => normalized.includes(` ${token} `));
    };
    if (hasWholeToken(weaponHints)) return "Weapon";
    if (hasWholeToken(armorHints)) return "Armor";
    return "";
  };

  const fromInv = String(row?.itemType || "");
  const inferredByName = inferEquipmentTypeFromName(canonName);
  if (inferredByName) return inferredByName;
  if (fromInv && ITEM_TYPE_ORDER[fromInv] != null) return fromInv;
  const fromMeta = String(itemTypeByItemName?.[itemName] || itemTypeByCanonName?.[canonName] || "");
  return ITEM_TYPE_ORDER[fromMeta] != null ? fromMeta : "Combat";
}

function inventoryRows() {
  const envelope = parseSaveEnvelope();
  const inv = asObj(envelope?.save?.inventory);
  const rows = [];
  Object.entries(inv).forEach(([itemType, bucket]) => {
    if (!bucket || typeof bucket !== "object") return;
    Object.entries(bucket).forEach(([name, count]) => {
      const qty = asNum(count, 0);
      if (qty <= 0) return;
      rows.push({ name: String(name), count: qty, itemType: String(itemType) });
    });
  });
  const filtered = modeKey === "key_item"
    ? rows.filter((row) => itemTypeForRow(row) === "Key Item")
    : rows.filter((row) => itemTypeForRow(row) !== "Key Item");

  filtered.sort((a, b) => {
    const aEquip = isEquipmentLabelItem(a.name);
    const bEquip = isEquipmentLabelItem(b.name);
    if (aEquip !== bEquip) return aEquip ? 1 : -1;

    const typeCmp = ITEM_TYPE_ORDER[itemTypeForRow(a)] - ITEM_TYPE_ORDER[itemTypeForRow(b)];
    if (typeCmp !== 0) return typeCmp;
    return sortAscending
      ? a.name.localeCompare(b.name, "ja")
      : b.name.localeCompare(a.name, "ja");
  });
  return filtered;
}

function itemTypeByName(itemName) {
  const row = inventoryRows().find((entry) => entry.name === itemName);
  return row ? itemTypeForRow(row) : "";
}

function consumeInventory(itemName) {
  const envelope = parseSaveEnvelope();
  if (!envelope) return false;
  const inv = asObj(envelope?.save?.inventory);
  const buckets = ["Anywhere", "Field", "Combat", "Key Item"];
  for (const bucketName of buckets) {
    const bucket = asObj(inv[bucketName]);
    const cur = asNum(bucket[itemName], 0);
    if (cur <= 0) continue;
    if (cur === 1) delete bucket[itemName];
    else bucket[itemName] = cur - 1;
    inv[bucketName] = bucket;
    envelope.save.inventory = inv;
    envelope.saved_at = new Date().toISOString();
    return persistSaveEnvelope(envelope);
  }
  return false;
}

function clearStatuses(member, keys) {
  const before = asArray(member?.status_icons);
  const removeSet = new Set(keys.map((key) => canon(key)));
  const next = before.filter((icon) => !removeSet.has(canon(icon)));
  if (next.length === before.length) return false;
  member.status_icons = next;
  return true;
}

function useItem(itemName, targetIdx) {
  const itemType = itemTypeByName(itemName);
  if (!FIELD_USABLE_TYPES.has(itemType)) {
    return { ok: false, message: "このアイテムはフィールドでは使えません。" };
  }

  const state = parseMenuState();
  const party = state.party;
  if (!party.length || targetIdx < 0 || targetIdx >= party.length) return { ok: false, message: "対象が不正です。" };
  const target = asObj(party[targetIdx]);
  const normalized = canon(itemName);
  let changed = false;

  if (normalized === "phoenix down") {
    const hp = asNum(target.hp, 0);
    const maxHp = Math.max(1, asNum(target.max_hp, hp));
    if (hp > 0) return { ok: false, message: "効果がありません。" };
    target.hp = Math.max(1, Math.floor(maxHp / 2));
    changed = true;
    clearStatuses(target, ["ko"]);
  } else if (normalized === "elixir") {
    const maxHp = Math.max(1, asNum(target.max_hp, 1));
    const beforeHp = asNum(target.hp, 0);
    target.hp = maxHp;
    changed = beforeHp !== target.hp;
    const levels = asObj(target.mp_levels);
    for (let lv = 1; lv <= 8; lv += 1) {
      const row = asObj(levels[String(lv)]);
      const cur = asNum(row.current, 0);
      const max = asNum(row.max, cur);
      if (cur !== max) {
        row.current = max;
        levels[String(lv)] = row;
        changed = true;
      }
    }
    target.mp_levels = levels;
  } else if (HEAL_AMOUNT[normalized]) {
    const hp = asNum(target.hp, 0);
    const maxHp = Math.max(1, asNum(target.max_hp, hp));
    if (hp <= 0 || hp >= maxHp) return { ok: false, message: "効果がありません。" };
    target.hp = Math.min(maxHp, hp + HEAL_AMOUNT[normalized]);
    changed = target.hp !== hp;
  } else if (STATUS_CLEAR[normalized]) {
    changed = clearStatuses(target, STATUS_CLEAR[normalized]);
  } else {
    return { ok: false, message: "未実装のアイテムです。" };
  }

  if (!changed) return { ok: false, message: "効果がありません。" };
  if (!consumeInventory(itemName)) return { ok: false, message: "在庫がありません。" };

  state.party[targetIdx] = target;
  const ok = persistMenuState({ ...state.raw, party: state.party });
  return ok
    ? { ok: true, message: `${itemName} を ${target.name || "target"} に使用しました。` }
    : { ok: false, message: "保存に失敗しました。" };
}

function renderModeButtons() {
  modeRow.innerHTML = "";
  MODES.forEach((mode) => {
    const btn = document.createElement("button");
    btn.className = `btn${modeKey === mode.key ? " active" : ""}`;
    btn.type = "button";
    btn.textContent = mode.label;
    btn.addEventListener("click", () => {
      if (mode.key === "sort") {
        sortAscending = !sortAscending;
      }
      modeKey = mode.key;
      render();
    });
    modeRow.appendChild(btn);
  });
}

function renderItemRows() {
  itemList.innerHTML = "";
  itemTitle.textContent = "所持アイテム";
  const rows = inventoryRows();
  if (!rows.length) {
    itemList.innerHTML = '<div class="empty">表示できるアイテムがありません。</div>';
    return;
  }
  if (!rows.some((row) => row.name === selectedItemName)) selectedItemName = rows[0]?.name || "";

  rows.forEach((row) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `item-row${selectedItemName === row.name ? " sel" : ""}`;
    const equipmentSuffix = "";
    const typeSuffix = ` <span class="desc">[${itemTypeForRow(row)}]</span>`;
    button.innerHTML = `<div>${row.name}${equipmentSuffix}${typeSuffix}</div><div>×${row.count}</div>`;
    button.addEventListener("click", () => {
      selectedItemName = row.name;
      if (modeKey === "sort") sortAscending = !sortAscending;
      render();
    });
    itemList.appendChild(button);
  });
}

function renderTargetRows(state) {
  const party = state.party;
  memberName.textContent = party.length ? "全キャラクター" : "-";
  targetList.innerHTML = "";

  if (!party.length) {
    targetList.innerHTML = '<div class="empty">キャラクター情報がありません。</div>';
    return;
  }

  const selectedRequiresTarget = TARGET_REQUIRED.has(canon(selectedItemName));
  party.forEach((member, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "target-row";
    btn.innerHTML = `
      <div>
        <div class="name">${String(member?.name || `member ${idx + 1}`)}</div>
        <div class="hp">${asNum(member?.hp)} / ${asNum(member?.max_hp)}</div>
      </div>
      <div class="icon-row"></div>
    `;

    const iconRow = btn.querySelector(".icon-row");
    asArray(member?.status_icons).forEach((iconKey) => {
      const candidates = resolveStatusIconCandidates(iconKey);
      if (!candidates.length) return;
      const img = document.createElement("img");
      img.className = "status-icon";
      img.alt = iconKey;
      let iconIndex = 0;
      img.addEventListener("error", () => {
        iconIndex += 1;
        if (iconIndex < candidates.length) img.src = candidates[iconIndex];
        else img.remove();
      });
      img.src = candidates[iconIndex];
      iconRow.appendChild(img);
    });

    btn.addEventListener("click", () => {
      if (modeKey !== "use") {
        messageLine.textContent = "つかうモードで対象を選んでください。";
        return;
      }
      if (!selectedItemName) {
        messageLine.textContent = "アイテムを選択してください。";
        return;
      }
      if (!selectedRequiresTarget) {
        messageLine.textContent = "対象選択が不要なアイテムです。";
        return;
      }
      const result = useItem(selectedItemName, idx);
      messageLine.textContent = result.message;
      render();
    });
    targetList.appendChild(btn);
  });
}

function readInventoryCatalogFromStorage() {
  const menuState = parseMenuState().raw;
  const envelope = parseSaveEnvelope();
  const fromMenuState = asObj(menuState?.inventory_catalog);
  const fromEnvelope = asObj(envelope?.menu_state?.inventory_catalog);
  const catalog = Object.keys(fromMenuState).length ? fromMenuState : fromEnvelope;

  const toNameSet = (value) => {
    const rows = Array.isArray(value) ? value : [];
    return new Set(rows.map((name) => String(name || "")).filter((name) => name));
  };
  const toCanonSet = (nameSet) => new Set(Array.from(nameSet).map((name) => canon(name)).filter((name) => name));
  const itemTypes = asObj(catalog?.item_types);
  const nextItemTypeByName = {};
  const nextItemTypeByCanon = {};
  Object.entries(itemTypes).forEach(([name, itemType]) => {
    const itemName = String(name || "");
    if (!itemName) return;
    const normalizedItemType = String(itemType || "");
    nextItemTypeByName[itemName] = normalizedItemType;
    const key = canon(itemName);
    if (key) {
      nextItemTypeByCanon[key] = normalizedItemType;
    }
  });

  itemTypeByItemName = nextItemTypeByName;
  itemTypeByCanonName = nextItemTypeByCanon;
  weaponNames = toNameSet(catalog?.weapons);
  weaponCanonNames = toCanonSet(weaponNames);
  armorNames = toNameSet(catalog?.armors);
  armorCanonNames = toCanonSet(armorNames);
}

function render() {
  const state = parseMenuState();
  renderModeButtons();
  renderItemRows();
  renderTargetRows(state);
  sortLine.textContent = sortAscending ? "A→Z" : "Z→A";
}

backBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

readInventoryCatalogFromStorage();
render();
