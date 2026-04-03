const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

const modeRow = document.getElementById("modeRow");
const memberText = document.getElementById("memberText");
const atkText = document.getElementById("atkText");
const defText = document.getElementById("defText");
const equipGrid = document.getElementById("equipGrid");
const candidateTitle = document.getElementById("candidateTitle");
const candidateList = document.getElementById("candidateList");
const messageLine = document.getElementById("messageLine");
const leftBtn = document.getElementById("leftBtn");
const rightBtn = document.getElementById("rightBtn");
const backBtn = document.getElementById("backBtn");

const MODES = [
  { key: "equip", label: "そうび" },
  { key: "release", label: "かいじょ" },
];
const SLOTS = [
  { key: "main_hand", label: "みぎて" },
  { key: "off_hand", label: "ひだりて" },
  { key: "head", label: "あたま" },
  { key: "body", label: "ふく" },
  { key: "arms", label: "うで" },
];

let memberIndex = 0;
let selectedSlotKey = "main_hand";
let modeKey = "equip";

function slotLabelByKey(slotKey) {
  return SLOTS.find((row) => row.key === slotKey)?.label || slotKey;
}

function asNum(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

function parseState() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    let parsed = text ? JSON.parse(text) : {};
    if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed?.equip_candidates_by_member)) {
      const envelope = parseSaveEnvelope();
      if (envelope?.menu_state && typeof envelope.menu_state === "object") {
        parsed = envelope.menu_state;
      }
    }
    const equipmentByMember = Array.isArray(parsed?.equipment_by_member)
      ? parsed.equipment_by_member
      : [];
    const partyFromMenu = Array.isArray(parsed?.party) ? parsed.party : [];
    const party = partyFromMenu.map((member, index) => {
      if (member?.equipment && typeof member.equipment === "object") return member;
      const eq = equipmentByMember[index];
      if (eq && typeof eq === "object") {
        return { ...member, equipment: eq };
      }
      return member;
    });
    return {
      raw: parsed,
      party,
      equipCandidatesByMember: Array.isArray(parsed?.equip_candidates_by_member)
        ? parsed.equip_candidates_by_member
        : [],
    };
  } catch (_error) {
    return { party: [], equipCandidatesByMember: [] };
  }
}

function parseSaveEnvelope() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    const parsed = JSON.parse(text);
    if (parsed?.version === 1 && parsed?.save && typeof parsed.save === "object") return parsed;
    if (parsed?.party && Array.isArray(parsed.party)) {
      return { version: 1, save: parsed };
    }
    return null;
  } catch (_error) {
    return null;
  }
}

function partyFromSave(envelope) {
  const saveParty = Array.isArray(envelope?.save?.party) ? envelope.save.party : [];
  return saveParty.map((row, index) => ({
    index,
    name: String(row?.name || `Member ${index + 1}`),
    job: String(row?.job || "-"),
    status: {},
    equipment: row?.equipment && typeof row.equipment === "object" ? row.equipment : {},
  }));
}

function persistMenuState(rawState) {
  try {
    localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(rawState));
    return true;
  } catch (_error) {
    return false;
  }
}

function persistSaveEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object") return false;
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

function getMember(state) {
  const party = state.party;
  if (!party.length) return null;
  memberIndex = ((memberIndex % party.length) + party.length) % party.length;
  return party[memberIndex] || null;
}

function memberEquipment(member) {
  const eq = member?.equipment;
  return eq && typeof eq === "object"
    ? eq
    : { main_hand: null, off_hand: null, head: null, body: null, arms: null };
}

function saveInventory(envelope) {
  const inventory = envelope?.save?.inventory;
  return inventory && typeof inventory === "object" ? inventory : {};
}

function inventoryBucket(envelope, itemType) {
  const bucket = saveInventory(envelope)?.[itemType];
  return bucket && typeof bucket === "object" ? bucket : {};
}

function inventoryCount(envelope, itemType, itemName) {
  if (!itemType || !itemName) return 0;
  const count = Number(inventoryBucket(envelope, itemType)?.[itemName] ?? 0);
  return Number.isFinite(count) ? Math.max(0, count) : 0;
}

function normalizeName(value) {
  return String(value || "")
    .normalize("NFKC")
    .trim()
    .toLowerCase()
    .replace(/[^\p{L}\p{N}_\u3040-\u30ff\u4e00-\u9fff]+/gu, "");
}

function normalizedInventoryCount(envelope, itemType, itemName) {
  const exact = inventoryCount(envelope, itemType, itemName);
  if (exact > 0) return exact;
  const bucket = inventoryBucket(envelope, itemType);
  const target = normalizeName(itemName);
  for (const [name, count] of Object.entries(bucket)) {
    if (normalizeName(name) !== target) continue;
    const num = Number(count ?? 0);
    if (Number.isFinite(num) && num > 0) return num;
  }
  return 0;
}

function candidateInventoryCount(state, envelope, row) {
  if (!row || row.kind === "none" || row.kind === "release") return null;
  const itemType = equipmentItemType(state, row.name, row.kind);
  if (itemType) {
    const invCount = normalizedInventoryCount(envelope, itemType, row.name);
    if (invCount > 0) return invCount;
  }
  const rowCount = Number(row?.count ?? NaN);
  return Number.isFinite(rowCount) && rowCount > 0 ? rowCount : null;
}

function inventoryCatalog(state) {
  const raw = state?.raw;
  return raw && typeof raw === "object" ? raw.inventory_catalog || {} : {};
}

function equipmentItemType(state, itemName, kindHint = "") {
  if (!itemName) return null;
  if (kindHint === "weapon") return "Weapon";
  if (kindHint === "armor") return "Armor";
  const catalog = inventoryCatalog(state);
  if (Array.isArray(catalog?.weapons) && catalog.weapons.includes(itemName)) return "Weapon";
  if (Array.isArray(catalog?.armors) && catalog.armors.includes(itemName)) return "Armor";
  return null;
}

function countEquippedItems(state, member) {
  const counts = new Map();
  const eq = memberEquipment(member);
  SLOTS.forEach((slot) => {
    const name = eq?.[slot.key];
    const itemType = equipmentItemType(state, name);
    if (!itemType || !name) return;
    const mapKey = `${itemType}:${name}`;
    const prev = counts.get(mapKey);
    if (prev) {
      prev.count += 1;
      return;
    }
    counts.set(mapKey, { itemType, itemName: name, count: 1 });
  });
  return counts;
}

function applyInventoryDeltaToEnvelope(envelope, beforeCounts, afterCounts) {
  if (!envelope?.save || typeof envelope.save !== "object") return;
  const inventory = saveInventory(envelope);
  if (!envelope.save.inventory || typeof envelope.save.inventory !== "object") {
    envelope.save.inventory = inventory;
  }

  beforeCounts.forEach((beforeEntry, key) => {
    const afterEntry = afterCounts.get(key);
    const delta = beforeEntry.count - (afterEntry?.count || 0);
    if (delta <= 0) return;
    const bucket = inventoryBucket(envelope, beforeEntry.itemType);
    if (!inventory[beforeEntry.itemType] || typeof inventory[beforeEntry.itemType] !== "object") {
      inventory[beforeEntry.itemType] = bucket;
    }
    const nextCount = inventoryCount(envelope, beforeEntry.itemType, beforeEntry.itemName) + delta;
    inventory[beforeEntry.itemType][beforeEntry.itemName] = nextCount;
  });

  afterCounts.forEach((afterEntry, key) => {
    const beforeEntry = beforeCounts.get(key);
    const delta = afterEntry.count - (beforeEntry?.count || 0);
    if (delta <= 0) return;
    const current = inventoryCount(envelope, afterEntry.itemType, afterEntry.itemName);
    if (current < delta) {
      throw new Error(`${afterEntry.itemName} is not available in inventory`);
    }
    const bucket = inventoryBucket(envelope, afterEntry.itemType);
    const nextCount = current - delta;
    if (nextCount <= 0) {
      delete bucket[afterEntry.itemName];
      return;
    }
    bucket[afterEntry.itemName] = nextCount;
  });
}

function modeListForSlot(mode, rows) {
  if (mode === "release") {
    return [{ name: "クリックで全装備解除", kind: "release" }];
  }
  return rows.length ? rows : [{ name: "候補なし" }];
}

function renderModeButtons() {
  modeRow.innerHTML = "";
  MODES.forEach((mode) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn${mode.key === modeKey ? " active" : ""}`;
    button.textContent = mode.label;
    button.addEventListener("click", () => {
      if (mode.key === "release") {
        const ok = window.confirm("このキャラクターの装備をすべて解除しますか？");
        if (!ok) return;
        const state = parseState();
        commitEquipmentChange(state, { kind: "release", name: null }, { forceMode: "release" });
        return;
      }
      modeKey = mode.key;
      render();
    });
    modeRow.appendChild(button);
  });
}

function renderEquipRows(member) {
  const eq = memberEquipment(member);
  equipGrid.innerHTML = "";
  SLOTS.forEach((slot) => {
    const row = document.createElement("div");
    row.className = "equip-row";
    row.innerHTML = `
      <div class="slot">${slot.label}</div>
      <div class="item ${selectedSlotKey === slot.key ? "selected" : ""}">${String(eq?.[slot.key] || "-")}</div>
    `;
    row.addEventListener("click", () => {
      selectedSlotKey = slot.key;
      render();
    });
    equipGrid.appendChild(row);
  });
}

function renderCandidates(state) {
  const member = getMember(state);
  const envelope = parseSaveEnvelope();
  const rowsBySlot = state.equipCandidatesByMember?.[memberIndex];
  const slotRowsRaw = rowsBySlot && typeof rowsBySlot === "object" ? rowsBySlot[selectedSlotKey] : [];
  const slotRows = Array.isArray(slotRowsRaw)
    ? slotRowsRaw.filter((row) => {
      if (!row || typeof row !== "object") return false;
      if (row.kind === "none") return true;
      return candidateInventoryCount(state, envelope, row) != null;
    })
    : [];
  const viewRows = modeListForSlot(modeKey, slotRows);

  const modeLabel = MODES.find((mode) => mode.key === modeKey)?.label || "そうび";
  candidateTitle.textContent = `${modeLabel} / ${slotLabelByKey(selectedSlotKey)}`;
  candidateList.innerHTML = "";
  viewRows.forEach((row) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "candidate";
    const name = row?.name ? String(row.name) : "はずす";
    const stock = candidateInventoryCount(state, envelope, row);
    const stockLabel = stock != null ? ` x${stock}` : "";
    const equippedName = String(memberEquipment(member)?.[selectedSlotKey] || "");
    const equippedMark = modeKey === "equip" && equippedName && equippedName === name ? " [E]" : "";
    const meta = row?.kind === "release"
      ? "確認後、全装備を解除"
      : row?.atk != null
      ? `ATK:${asNum(row?.atk)} ACC:${asNum(row?.acc)}%`
      : `DEF:${asNum(row?.def)} EVA:${asNum(row?.eva)}`;
    button.innerHTML = `<div>${name}${stockLabel}${equippedMark}</div><div class="meta">${meta}</div>`;
    button.addEventListener("click", () => {
      commitEquipmentChange(state, row);
    });
    candidateList.appendChild(button);
  });
}

function findCandidateRow(state, targetMemberIndex, slotKey, itemName) {
  const rowsBySlot = state.equipCandidatesByMember?.[targetMemberIndex];
  const rows = rowsBySlot && typeof rowsBySlot === "object" ? rowsBySlot[slotKey] : [];
  if (!Array.isArray(rows)) return null;
  return rows.find((row) => String(row?.name || "") === String(itemName || "")) || null;
}

function computeSummaryStats(state, targetMemberIndex, member) {
  const eq = memberEquipment(member);
  const baseAtk = asNum(member?.status?.atk_value);
  const baseDef = asNum(member?.status?.defense);
  const attackRows = ["main_hand", "off_hand"]
    .map((slotKey) => findCandidateRow(state, targetMemberIndex, slotKey, eq?.[slotKey]))
    .filter((row) => row && row.kind === "weapon");
  const atk = attackRows.length
    ? Math.round(attackRows.reduce((sum, row) => sum + asNum(row?.atk), 0) / attackRows.length)
    : baseAtk;

  const defenseRows = ["off_hand", "head", "body", "arms"]
    .map((slotKey) => findCandidateRow(state, targetMemberIndex, slotKey, eq?.[slotKey]))
    .filter((row) => row && row.kind === "armor");
  const def = defenseRows.length
    ? defenseRows.reduce((sum, row) => sum + asNum(row?.def), 0)
    : baseDef;
  return { atk, def };
}

function applyEquipmentChange(member, selectedRow, options = {}) {
  const activeMode = options?.forceMode || modeKey;
  const nextMember = { ...member };
  const nextEq = { ...memberEquipment(member) };
  if (activeMode === "release") {
    nextEq.main_hand = null;
    nextEq.off_hand = null;
    nextEq.head = null;
    nextEq.body = null;
    nextEq.arms = null;
    nextMember.equipment = nextEq;
    return { member: nextMember, message: "全装備を解除しました。" };
  }
  const itemName = selectedRow?.kind === "none" ? null : (selectedRow?.name || null);
  nextEq[selectedSlotKey] = itemName;
  nextMember.equipment = nextEq;
  return { member: nextMember, message: `${slotLabelByKey(selectedSlotKey)} に ${itemName || "はずす"} を設定しました。` };
}

function commitEquipmentChange(state, selectedRow, options = {}) {
  const member = getMember(state);
  if (!member) return;
  const changed = applyEquipmentChange(member, selectedRow, options);
  const envelope = parseSaveEnvelope();
  if (envelope?.save) {
    const beforeCounts = countEquippedItems(state, member);
    const afterCounts = countEquippedItems(state, changed.member);
    try {
      applyInventoryDeltaToEnvelope(envelope, beforeCounts, afterCounts);
    } catch (_error) {
      if (messageLine) {
        messageLine.textContent = "在庫がないため装備できません。";
      }
      return;
    }
  }
  const nextPartyRaw = state.party.map((row, idx) => (idx === memberIndex ? changed.member : row));
  const nextState = { ...state, party: nextPartyRaw };
  const nextParty = nextPartyRaw.map((row, idx) => {
    if (idx !== memberIndex) return row;
    const summary = computeSummaryStats(nextState, idx, row);
    const status = row?.status && typeof row.status === "object" ? row.status : {};
    return {
      ...row,
      status: {
        ...status,
        atk_value: summary.atk,
        defense: summary.def,
      },
    };
  });

  const nextRaw = {
    ...(state.raw && typeof state.raw === "object" ? state.raw : {}),
    party: nextParty,
    equipment_by_member: nextParty.map((row) => memberEquipment(row)),
  };
  const okMenu = persistMenuState(nextRaw);

  if (envelope?.save && Array.isArray(envelope.save.party) && envelope.save.party[memberIndex]) {
    const saveEntry = envelope.save.party[memberIndex];
    saveEntry.equipment = {
      ...memberEquipment(changed.member),
    };
    envelope.menu_state = nextRaw;
    envelope.saved_at = new Date().toISOString();
    persistSaveEnvelope(envelope);
  }

  if (messageLine) {
    messageLine.textContent = okMenu
      ? changed.message
      : "装備の保存に失敗しました。";
  }
  if (options?.forceMode === "release") {
    modeKey = "equip";
  }
  render();
}

function render() {
  const state = parseState();
  const envelope = parseSaveEnvelope();
  if (!state.party.length && envelope?.save) {
    state.party = partyFromSave(envelope);
  }
  if (
    state.party.length
    && envelope?.save
    && Array.isArray(envelope.save.party)
  ) {
    state.party = state.party.map((member, index) => {
      if (member?.equipment && Object.keys(member.equipment).length) return member;
      const saveMember = envelope.save.party[index];
      const eq = saveMember?.equipment && typeof saveMember.equipment === "object"
        ? saveMember.equipment
        : null;
      return eq ? { ...member, equipment: eq } : member;
    });
  }

  const member = getMember(state);
  renderModeButtons();
  if (!member) {
    memberText.textContent = "No party members";
    atkText.textContent = "こうげき 0";
    defText.textContent = "ぼうぎょ 0";
    equipGrid.innerHTML = "";
    candidateList.innerHTML = "";
    return;
  }

  const st = member?.status && typeof member.status === "object" ? member.status : {};
  memberText.textContent = String(member?.name || "-");
  atkText.textContent = `こうげき ${asNum(st?.atk_value)}`;
  defText.textContent = `ぼうぎょ ${asNum(st?.defense)}`;

  renderEquipRows(member);
  renderCandidates(state);
}

function goBack() {
  window.location.href = "./menu.html";
}

leftBtn?.addEventListener("click", () => {
  memberIndex -= 1;
  render();
});
rightBtn?.addEventListener("click", () => {
  memberIndex += 1;
  render();
});
backBtn?.addEventListener("click", goBack);

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    memberIndex -= 1;
    render();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    memberIndex += 1;
    render();
  } else if (event.key === "Escape" || event.key === "Enter" || event.key === "Backspace") {
    event.preventDefault();
    goBack();
  }
});

render();
