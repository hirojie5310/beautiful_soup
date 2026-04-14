import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import { mergeMenuStateIntoSave } from "../menu_save_sync.js";
import { getPyodideRuntime } from "../pyodide_runtime.js";
import {
  bindMenuSubpageNavigation,
  persistMenuEnvelope,
  stepMenuMemberSelection,
  syncMenuMemberSelection,
} from "./screen_shared.js";

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
const slotToArmorType = { head: "Helm", body: "Armor", arms: "Gloves" };
const JOB_NAME_TO_CODE = {
  "Onion Knight": "OK", Warrior: "Wa", Monk: "Mo", "White Mage": "WM", "Black Mage": "BM", "Red Mage": "RM",
  Ranger: "Ra", Knight: "Kn", Thief: "Th", Scholar: "Sc", Geomancer: "Ge", Dragoon: "Dr", Viking: "Vi",
  "Black Belt": "BB", Evoker: "Ev", Bard: "Ba", Magus: "Ma", Devout: "De", Summoner: "Su", Sage: "Sa",
  Ninja: "Ni", "Mystic Knight": "MK",
};

function asNum(v, d = 0) { const n = Number(v); return Number.isFinite(n) ? n : d; }
function asObj(v) { return v && typeof v === "object" ? v : {}; }
function clone(value) { return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value)); }
function normalizeName(value) {
  return String(value || "").normalize("NFKC").trim().toLowerCase().replace(/[^\p{L}\p{N}_\u3040-\u30ff\u4e00-\u9fff]+/gu, "");
}

function renderLayout() {
  return renderMenuSubpageShell({
    content: `
      <section class="frame mode-row" id="modeRow"></section>
      <section class="frame">
        <div class="summary"><div id="memberText">-</div><div><span id="atkText">こうげき 0</span> <span id="defText">ぼうぎょ 0</span></div></div>
        <div id="equipGrid" class="equip-grid"></div>
      </section>
      <section class="frame"><div id="candidateTitle" class="candidate-title">そうび</div><div id="candidateList" class="candidate-list"></div></section>
      <section class="frame"><div id="messageLine" class="hint">候補を選ぶと装備が確定します。</div></section>
      <section class="frame footer">
        <button id="leftBtn" class="btn" type="button">◀</button>
        <button id="backBtn" class="btn" type="button">BACK</button>
        <button id="rightBtn" class="btn" type="button">▶</button>
      </section>
      <section class="hint">モードをタップして切替 / 装備行をタップして候補表示 / ←→でキャラ切替</section>
    `,
    styles: `
      .mode-row { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
      .summary { display:flex; justify-content:space-between; gap:8px; font-size:1rem; font-weight:700; }
      .equip-grid { margin-top:8px; border-top:1px solid rgba(255,255,255,0.35); padding-top:8px; display:grid; gap:4px; }
      .equip-row { display:grid; grid-template-columns:74px 1fr; gap:8px; align-items:baseline; }
      .slot { color:#acb6d7; }
      .item.selected::before { content:"▶ "; color:#ffe588; }
      .candidate-title { color:#ffe588; margin-bottom:8px; font-weight:700; }
      .candidate-list { display:grid; gap:4px; max-height:34vh; overflow:auto; }
      .candidate { border:1px solid rgba(255,255,255,0.3); border-radius:6px; background:rgba(0,0,0,0.2); padding:7px; cursor:pointer; text-align:left; color:#eef2ff; }
      .candidate .meta { color:#acb6d7; font-size:0.8rem; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .footer { display:grid; grid-template-columns:1fr 1.6fr 1fr; gap:8px; }
      .hint { color:#acb6d7; font-size:0.85rem; margin-top:6px; }
    `,
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  const modeRow = mountNode.querySelector("#modeRow");
  const memberText = mountNode.querySelector("#memberText");
  const atkText = mountNode.querySelector("#atkText");
  const defText = mountNode.querySelector("#defText");
  const equipGrid = mountNode.querySelector("#equipGrid");
  const candidateTitle = mountNode.querySelector("#candidateTitle");
  const candidateList = mountNode.querySelector("#candidateList");
  const messageLine = mountNode.querySelector("#messageLine");
  const leftBtn = mountNode.querySelector("#leftBtn");
  const rightBtn = mountNode.querySelector("#rightBtn");
  const backBtn = mountNode.querySelector("#backBtn");

  let memberIndex = Number(store.getState().menuMemberIndex ?? 0);
  let selectedSlotKey = "main_hand";
  let modeKey = "equip";
  let equipmentMaster = { weapons: [], armors: [] };
  let equipmentMasterReady = false;
  let pyodide = null;

  function slotLabelByKey(slotKey) {
    return SLOTS.find((row) => row.key === slotKey)?.label || slotKey;
  }
  function memberEquipment(member) {
    const eq = member?.equipment;
    return eq && typeof eq === "object" ? eq : { main_hand: null, off_hand: null, head: null, body: null, arms: null };
  }
  function getMenuState() { return store.getState().menuState || {}; }
  function getEnvelope() { return store.getState().saveEnvelope || store.createDefaultEnvelope(); }
  function saveInventory(envelope) { return envelope?.save?.inventory && typeof envelope.save.inventory === "object" ? envelope.save.inventory : {}; }
  function inventoryBucket(envelope, itemType) { const bucket = saveInventory(envelope)?.[itemType]; return bucket && typeof bucket === "object" ? bucket : {}; }
  function inventoryCount(envelope, itemType, itemName) { const count = Number(inventoryBucket(envelope, itemType)?.[itemName] ?? 0); return Number.isFinite(count) ? Math.max(0, count) : 0; }
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
  function equipmentItemType(itemName, kindHint = "") {
    if (!itemName) return null;
    if (kindHint === "weapon") return "Weapon";
    if (kindHint === "armor") return "Armor";
    if (equipmentMasterReady) {
      if (equipmentMaster.weapons.some((row) => String(row?.name || "") === String(itemName))) return "Weapon";
      if (equipmentMaster.armors.some((row) => String(row?.name || "") === String(itemName))) return "Armor";
    }
    return null;
  }
  function normalizeJobCode(value) { return String(value || "").trim().toLowerCase().replace(/[\s_-]+/g, ""); }
  function memberJobCode(member, envelope, targetMemberIndex) {
    const saveParty = Array.isArray(envelope?.save?.party) ? envelope.save.party : [];
    const saveEntry = saveParty[targetMemberIndex];
    const jobName = String(saveEntry?.job || member?.job || "").trim();
    if (jobName && JOB_NAME_TO_CODE[jobName]) return JOB_NAME_TO_CODE[jobName];
    return jobName;
  }
  function itemAllowedForMember(member, envelope, itemRaw, targetMemberIndex) {
    const equippedBy = Array.isArray(itemRaw?.EquippedBy) ? itemRaw.EquippedBy : [];
    if (!equippedBy.length) return true;
    const allow = new Set(equippedBy.map((code) => normalizeJobCode(code)));
    const currentJob = normalizeJobCode(memberJobCode(member, envelope, targetMemberIndex));
    return currentJob ? allow.has(currentJob) : true;
  }
  function isTwoHandedWeapon(itemRaw) {
    if (!itemRaw || typeof itemRaw !== "object") return false;
    if ("Two-Handed" in itemRaw) return true;
    const hands = itemRaw?.Hands;
    if (typeof hands === "number") return hands >= 2;
    if (typeof hands === "string" && /^\d+$/.test(hands)) return Number(hands) >= 2;
    return Boolean(itemRaw?.TwoHanded);
  }
  function compactBonusLabel(bonusRaw) {
    if (!bonusRaw || typeof bonusRaw !== "object") return "";
    const keyMap = {
      Strength: "STR",
      Agility: "AGI",
      Vitality: "VIT",
      Intelligence: "INT",
      Mind: "MND",
      Fire: "FIR",
      Ice: "ICE",
      Lightning: "LIT",
      Earth: "ERT",
      Air: "AIR",
      Holy: "HLY",
    };
    const parts = [];
    Object.entries(bonusRaw).forEach(([key, value]) => {
      const short = keyMap[String(key)] || String(key).slice(0, 3).toUpperCase();
      if (typeof value === "string" && value.trim().toLowerCase() === "up") {
        parts.push(`${short}↑`);
        return;
      }
      const amount = asNum(value, 0);
      if (amount === 0) return;
      parts.push(`${short}${amount >= 0 ? `+${amount}` : amount}`);
    });
    return parts.length ? `BON:${parts.join("/")}` : "";
  }
  function buildDynamicCandidateRows(member, targetMemberIndex, slotKey) {
    const envelope = getEnvelope();
    if (!equipmentMasterReady || !member) return null;
    if (slotKey === "main_hand" || slotKey === "off_hand") {
      const rows = [{ kind: "none", name: null }];
      equipmentMaster.weapons.forEach((raw) => {
        const name = String(raw?.name || "");
        if (!name) return;
        const stockCount = normalizedInventoryCount(envelope, "Weapon", name);
        if (stockCount <= 0) return;
        if (!itemAllowedForMember(member, envelope, raw, targetMemberIndex)) return;
        if (slotKey === "off_hand" && isTwoHandedWeapon(raw)) return;
        rows.push({
          kind: "weapon",
          name,
          count: stockCount,
          atk: asNum(raw?.BasePower ?? raw?.AttackPower),
          acc: raw?.BaseAccuracy != null ? Math.round(Number(raw.BaseAccuracy || 0) * 100) : asNum(raw?.HitRate),
          bonus_label: compactBonusLabel(raw?.Bonus),
        });
      });
      if (slotKey === "off_hand") {
        equipmentMaster.armors.forEach((raw) => {
          const name = String(raw?.name || "");
          if (!name || String(raw?.ArmorType || "") !== "Shield") return;
          const stockCount = normalizedInventoryCount(envelope, "Armor", name);
          if (stockCount <= 0) return;
          if (!itemAllowedForMember(member, envelope, raw, targetMemberIndex)) return;
          rows.push({
            kind: "armor",
            name,
            count: stockCount,
            def: asNum(raw?.Defense),
            eva: raw?.Evasion != null ? Math.round(Number(raw.Evasion || 0) * 100) : asNum(raw?.EvasionPenalty),
            bonus_label: compactBonusLabel(raw?.Bonus),
          });
        });
      }
      return rows;
    }
    const armorType = slotToArmorType[slotKey];
    if (!armorType) return null;
    const rows = [{ kind: "none", name: null }];
    equipmentMaster.armors.forEach((raw) => {
      const name = String(raw?.name || "");
      if (!name || String(raw?.ArmorType || "") !== armorType) return;
      const stockCount = normalizedInventoryCount(envelope, "Armor", name);
      if (stockCount <= 0) return;
      if (!itemAllowedForMember(member, envelope, raw, targetMemberIndex)) return;
      rows.push({
        kind: "armor",
        name,
        count: stockCount,
        def: asNum(raw?.Defense),
        eva: raw?.Evasion != null ? Math.round(Number(raw.Evasion || 0) * 100) : asNum(raw?.EvasionPenalty),
        bonus_label: compactBonusLabel(raw?.Bonus),
      });
    });
    return rows;
  }
  function findEquippedItemRow(member, targetMemberIndex, slotKey) {
    if (!equipmentMasterReady || !member) return null;
    const equippedName = String(memberEquipment(member)?.[slotKey] || "");
    if (!equippedName) return null;
    if (slotKey === "main_hand" || slotKey === "off_hand") {
      const weaponRow = equipmentMaster.weapons.find((raw) => String(raw?.name || "") === equippedName);
      if (weaponRow) {
        if (slotKey === "off_hand" && isTwoHandedWeapon(weaponRow)) return null;
        return {
          kind: "weapon",
          name: equippedName,
          atk: asNum(weaponRow?.BasePower ?? weaponRow?.AttackPower),
          acc: weaponRow?.BaseAccuracy != null
            ? Math.round(Number(weaponRow.BaseAccuracy || 0) * 100)
            : asNum(weaponRow?.HitRate),
          bonus_label: compactBonusLabel(weaponRow?.Bonus),
        };
      }
      if (slotKey === "off_hand") {
        const shieldRow = equipmentMaster.armors.find((raw) => (
          String(raw?.name || "") === equippedName
          && String(raw?.ArmorType || "") === "Shield"
        ));
        if (shieldRow) {
          return {
            kind: "armor",
            name: equippedName,
            def: asNum(shieldRow?.Defense),
            eva: shieldRow?.Evasion != null
              ? Math.round(Number(shieldRow.Evasion || 0) * 100)
              : asNum(shieldRow?.EvasionPenalty),
            bonus_label: compactBonusLabel(shieldRow?.Bonus),
          };
        }
      }
      return null;
    }
    const armorType = slotToArmorType[slotKey];
    if (!armorType) return null;
    const armorRow = equipmentMaster.armors.find((raw) => (
      String(raw?.name || "") === equippedName
      && String(raw?.ArmorType || "") === armorType
    ));
    if (!armorRow) return null;
    return {
      kind: "armor",
      name: equippedName,
      def: asNum(armorRow?.Defense),
      eva: armorRow?.Evasion != null
        ? Math.round(Number(armorRow.Evasion || 0) * 100)
        : asNum(armorRow?.EvasionPenalty),
      bonus_label: compactBonusLabel(armorRow?.Bonus),
    };
  }
  function countEquippedItems(member) {
    const counts = new Map();
    const eq = memberEquipment(member);
    SLOTS.forEach((slot) => {
      const name = eq?.[slot.key];
      const itemType = equipmentItemType(name);
      if (!itemType || !name) return;
      const key = `${itemType}:${name}`;
      counts.set(key, { itemType, itemName: name, count: (counts.get(key)?.count || 0) + 1 });
    });
    return counts;
  }
  function applyInventoryDeltaToEnvelope(envelope, beforeCounts, afterCounts) {
    const inventory = saveInventory(envelope);
    if (!envelope.save.inventory || typeof envelope.save.inventory !== "object") envelope.save.inventory = inventory;
    beforeCounts.forEach((beforeEntry, key) => {
      const delta = beforeEntry.count - (afterCounts.get(key)?.count || 0);
      if (delta <= 0) return;
      if (!inventory[beforeEntry.itemType] || typeof inventory[beforeEntry.itemType] !== "object") inventory[beforeEntry.itemType] = {};
      inventory[beforeEntry.itemType][beforeEntry.itemName] = inventoryCount(envelope, beforeEntry.itemType, beforeEntry.itemName) + delta;
    });
    afterCounts.forEach((afterEntry, key) => {
      const delta = afterEntry.count - (beforeCounts.get(key)?.count || 0);
      if (delta <= 0) return;
      const current = inventoryCount(envelope, afterEntry.itemType, afterEntry.itemName);
      if (current < delta) throw new Error(`${afterEntry.itemName} is not available in inventory`);
      const bucket = inventoryBucket(envelope, afterEntry.itemType);
      const nextCount = current - delta;
      if (nextCount <= 0) delete bucket[afterEntry.itemName];
      else bucket[afterEntry.itemName] = nextCount;
    });
  }
  function modeListForSlot(rows) {
    if (modeKey === "release") return [{ name: "クリックで全装備解除", kind: "release" }];
    return rows.length ? rows : [{ name: "候補なし" }];
  }
  function formatCandidateMeta(row) {
    const parts = [];
    if (row?.atk != null) {
      parts.push(`ATK:${asNum(row?.atk)} ACC:${asNum(row?.acc)}%`);
    } else if (row?.def != null) {
      parts.push(`DEF:${asNum(row?.def)} EVA:${asNum(row?.eva)}`);
    }
    if (row?.bonus_label) {
      parts.push(String(row.bonus_label));
    }
    return parts.join(" ");
  }
  function computeSummaryStats(member) {
    const baseAtk = asNum(member?.status?.atk_value);
    const baseDef = asNum(member?.status?.defense);
    const attackRows = ["main_hand", "off_hand"]
      .map((slotKey) => findEquippedItemRow(member, memberIndex, slotKey))
      .filter((row) => row && row.kind === "weapon");
    const defenseRows = ["off_hand", "head", "body", "arms"]
      .map((slotKey) => findEquippedItemRow(member, memberIndex, slotKey))
      .filter((row) => row && row.kind === "armor");
    return {
      atk: attackRows.length
        ? Math.round(attackRows.reduce((sum, row) => sum + asNum(row?.atk), 0) / attackRows.length)
        : baseAtk,
      def: defenseRows.length
        ? defenseRows.reduce((sum, row) => sum + asNum(row?.def), 0)
        : baseDef,
    };
  }
  function applyEquipmentChange(member, selectedRow, forceMode = null) {
    const activeMode = forceMode || modeKey;
    const nextMember = { ...member };
    const nextEq = { ...memberEquipment(member) };
    if (activeMode === "release") {
      SLOTS.forEach((slot) => { nextEq[slot.key] = null; });
      nextMember.equipment = nextEq;
      return { member: nextMember, message: "全装備を解除しました。" };
    }
    nextEq[selectedSlotKey] = selectedRow?.kind === "none" ? null : (selectedRow?.name || null);
    nextMember.equipment = nextEq;
    return { member: nextMember, message: `${slotLabelByKey(selectedSlotKey)} に ${nextEq[selectedSlotKey] || "はずす"} を設定しました。` };
  }
  async function rebuildMenuStateFromRuntime(nextEnvelope, fallbackParty) {
    const state = store.getState();
    const locationGroup = String(state.selectedLocationGroup || "");
    const location = String(state.selectedLocation || "");
    if (!pyodide || !locationGroup || !location) {
      return {
        ...(store.getState().menuState && typeof store.getState().menuState === "object"
          ? store.getState().menuState
          : {}),
        party: fallbackParty,
      };
    }
    try {
      const bootForLocation = pyodide.globals.get("boot_engine_for_location_with_save_json");
      const getMenuStateJson = pyodide.globals.get("get_menu_state_json");
      const getSessionStatusJson = pyodide.globals.get("get_session_status_json");
      if (!bootForLocation || !getMenuStateJson || !getSessionStatusJson) {
        return {
          ...(store.getState().menuState && typeof store.getState().menuState === "object"
            ? store.getState().menuState
            : {}),
          party: fallbackParty,
        };
      }
      bootForLocation(locationGroup, location, JSON.stringify(nextEnvelope.save), 7);
      const rebuiltMenuState = JSON.parse(String(getMenuStateJson() || "{}"));
      const rebuiltSessionStatusPayload = JSON.parse(String(getSessionStatusJson() || "{}"));
      const rebuiltPartyStatus = Array.isArray(rebuiltSessionStatusPayload?.session_status?.party)
        ? rebuiltSessionStatusPayload.session_status.party
        : [];
      const mergedParty = fallbackParty.map((member, index) => {
        const runtimeMember = rebuiltPartyStatus[index];
        if (!runtimeMember || typeof runtimeMember !== "object") return member;
        return {
          ...member,
          hp: Number(runtimeMember?.hp ?? member?.hp ?? 0),
          max_hp: Number(runtimeMember?.max_hp ?? member?.max_hp ?? 0),
          mp_levels: runtimeMember?.mp_levels && typeof runtimeMember.mp_levels === "object"
            ? runtimeMember.mp_levels
            : member?.mp_levels,
          status_icons: Array.isArray(runtimeMember?.status_icons)
            ? runtimeMember.status_icons
            : member?.status_icons,
          status: runtimeMember?.status && typeof runtimeMember.status === "object"
            ? runtimeMember.status
            : member?.status,
          row: runtimeMember?.row ?? member?.row,
          job: runtimeMember?.job ?? member?.job,
        };
      });
      return {
        ...(rebuiltMenuState && typeof rebuiltMenuState === "object" ? rebuiltMenuState : {}),
        party: mergedParty,
      };
    } catch (_error) {
      return {
        ...(store.getState().menuState && typeof store.getState().menuState === "object"
          ? store.getState().menuState
          : {}),
        party: fallbackParty,
      };
    }
  }
  async function commitEquipmentChange(selectedRow, forceMode = null) {
    const menuState = getMenuState();
    const party = Array.isArray(menuState?.party) ? menuState.party : [];
    const member = party[memberIndex];
    if (!member) return;
    const changed = applyEquipmentChange(member, selectedRow, forceMode);
    const nextEnvelope = clone(getEnvelope());
    if (nextEnvelope?.save) {
      const beforeCounts = countEquippedItems(member);
      const afterCounts = countEquippedItems(changed.member);
      try {
        applyInventoryDeltaToEnvelope(nextEnvelope, beforeCounts, afterCounts);
      } catch (_error) {
        messageLine.textContent = "在庫がないため装備できません。";
        return;
      }
    }
    const nextParty = party.map((row, idx) => {
      if (idx !== memberIndex) return row;
      const summary = computeSummaryStats(changed.member);
      return {
        ...changed.member,
        status: {
          ...(row?.status || {}),
          atk_value: summary.atk,
          defense: summary.def,
        },
      };
    });
    if (nextEnvelope?.save && typeof nextEnvelope.save === "object") {
      nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, {
        ...(menuState && typeof menuState === "object" ? menuState : {}),
        party: nextParty,
      });
    }
    const rebuiltMenuState = await rebuildMenuStateFromRuntime(nextEnvelope, nextParty);
    const nextMenuState = {
      ...(menuState && typeof menuState === "object" ? menuState : {}),
      ...(rebuiltMenuState && typeof rebuiltMenuState === "object" ? rebuiltMenuState : {}),
      party: Array.isArray(rebuiltMenuState?.party) ? rebuiltMenuState.party : nextParty,
      equipment_by_member: (Array.isArray(rebuiltMenuState?.party) ? rebuiltMenuState.party : nextParty)
        .map((row) => memberEquipment(row)),
    };
    persistMenuEnvelope(store, nextMenuState, nextEnvelope);
    messageLine.textContent = changed.message;
    if (forceMode === "release") modeKey = "equip";
    render();
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
          if (window.confirm("このキャラクターの装備をすべて解除しますか？")) {
            void commitEquipmentChange({ kind: "release", name: null }, "release");
          }
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
      row.innerHTML = `<div class="slot">${slot.label}</div><div class="item ${selectedSlotKey === slot.key ? "selected" : ""}">${String(eq?.[slot.key] || "-")}</div>`;
      row.addEventListener("click", () => { selectedSlotKey = slot.key; render(); });
      equipGrid.appendChild(row);
    });
  }
  function renderCandidates(member) {
    const rows = (buildDynamicCandidateRows(member, memberIndex, selectedSlotKey) || []).filter((row) => !row || row.kind === "none" || (row.count ?? 1) > 0);
    const viewRows = modeListForSlot(rows);
    candidateTitle.textContent = `${MODES.find((mode) => mode.key === modeKey)?.label || "そうび"} / ${slotLabelByKey(selectedSlotKey)}`;
    candidateList.innerHTML = "";
    viewRows.forEach((row) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "candidate";
      const name = row?.name ? String(row.name) : "はずす";
      const stockLabel = row?.count ? ` x${row.count}` : "";
      const equippedName = String(memberEquipment(member)?.[selectedSlotKey] || "");
      const equippedMark = modeKey === "equip" && equippedName && equippedName === name ? " [E]" : "";
      const meta = formatCandidateMeta(row);
      button.innerHTML = `<div>${name}${stockLabel}${equippedMark}</div><div class="meta">${meta}</div>`;
      button.addEventListener("click", () => {
        void commitEquipmentChange(row);
      });
      candidateList.appendChild(button);
    });
  }
  function render() {
    const menuState = getMenuState();
    const selection = syncMenuMemberSelection(store, memberIndex);
    const party = selection.party;
    renderModeButtons();
    if (!party.length) {
      memberText.textContent = "No party members";
      atkText.textContent = "こうげき 0";
      defText.textContent = "ぼうぎょ 0";
      equipGrid.innerHTML = "";
      candidateList.innerHTML = "";
      return;
    }
    memberIndex = selection.memberIndex;
    const member = selection.member;
    const st = member?.status && typeof member.status === "object" ? member.status : {};
    memberText.textContent = String(member?.name || "-");
    atkText.textContent = `こうげき ${asNum(st?.atk_value)}`;
    defText.textContent = `ぼうぎょ ${asNum(st?.defense)}`;
    renderEquipRows(member);
    renderCandidates(member);
  }
  async function loadEquipmentMaster() {
    try {
      const [weaponsResponse, armorsResponse] = await Promise.all([
        fetch("../assets/data/ffiii_weapons.json", { cache: "no-store" }),
        fetch("../assets/data/ffiii_armors.json", { cache: "no-store" }),
      ]);
      if (!weaponsResponse.ok || !armorsResponse.ok) return;
      const [weaponsJson, armorsJson] = await Promise.all([weaponsResponse.json(), armorsResponse.json()]);
      equipmentMaster = {
        weapons: Array.isArray(weaponsJson?.weapons) ? weaponsJson.weapons : [],
        armors: Array.isArray(armorsJson?.armors) ? armorsJson.armors : [],
      };
      equipmentMasterReady = true;
      render();
    } catch (_error) {
      equipmentMasterReady = false;
    }
  }
  const onLeft = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, -1); render(); };
  const onRight = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, 1); render(); };
  const onBack = () => navigate("menu");
  const unbindButtons = bindMenuSubpageNavigation({
    leftBtn,
    rightBtn,
    backBtn,
    onLeft,
    onRight,
    onBack,
  });
  render();
  try {
    pyodide = await getPyodideRuntime();
  } catch (_error) {
    pyodide = null;
  }
  await loadEquipmentMaster();
  return () => {
    unbindButtons();
  };
}
