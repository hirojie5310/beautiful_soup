const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

const modeRow = document.getElementById("modeRow");
const memberName = document.getElementById("memberName");
const memberJob = document.getElementById("memberJob");
const magicGrid = document.getElementById("magicGrid");
const candidateTitle = document.getElementById("candidateTitle");
const candidatePane = document.getElementById("candidatePane");
const messageLine = document.getElementById("messageLine");
const leftBtn = document.getElementById("leftBtn");
const rightBtn = document.getElementById("rightBtn");
const backBtn = document.getElementById("backBtn");

const MODES = [
  { key: "use", label: "つかう" },
  { key: "learn", label: "おぼえる" },
  { key: "remove", label: "はずす" },
  { key: "swap", label: "こうかん" },
];

let modeKey = "learn";
let memberIndex = 0;
let selectedLevel = 1;
let selectedSlot = 0;
const HEAL_SPELL_AMOUNT = { Cure: 50, Cura: 150, Curaga: 400, Curaja: 9999 };
const RAISE_SPELLS = new Set(["Raise", "Arise"]);
const STATUS_SPELL_CLEAR = {
  Poisona: ["poison"],
  Blindna: ["blind"],
  Stona: ["petrify", "petrification", "partial_petrify", "partial petrification"],
};
const ESUNA_CLEAR = [
  "poison",
  "blind",
  "mini",
  "silence",
  "toad",
  "petrify",
  "petrification",
  "partial_petrify",
  "partial petrification",
  "confusion",
  "sleep",
  "paralyze",
  "paralysis",
];

function asArray(v) { return Array.isArray(v) ? v : []; }
function asObj(v) { return v && typeof v === "object" ? v : {}; }

function parseState() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    const parsed = text ? JSON.parse(text) : {};
    return {
      raw: parsed,
      party: asArray(parsed?.party),
      magicSetup: asObj(parsed?.magic_setup),
      magicMetaByName: asObj(parsed?.magic_spell_meta_by_name),
      magicCandidatesByMember: asArray(parsed?.magic_candidates_by_member),
    };
  } catch (_error) {
    return { raw: {}, party: [], magicSetup: {}, magicMetaByName: {}, magicCandidatesByMember: [] };
  }
}

function parseSaveEnvelope() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    const parsed = JSON.parse(text);
    if (parsed?.version === 1 && parsed?.save && typeof parsed.save === "object") return parsed;
    if (parsed?.party && Array.isArray(parsed.party)) return { version: 1, save: parsed };
    return null;
  } catch (_error) {
    return null;
  }
}

function persistState(state) {
  try {
    localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(state));
    return true;
  } catch (_error) {
    return false;
  }
}

function persistSaveMagicSetup(setup) {
  const envelope = parseSaveEnvelope();
  const party = asArray(envelope?.save?.party);
  if (!party.length) return;
  const equippedByMember = asArray(setup?.equipped_by_member);
  party.forEach((entry, idx) => {
    const one = asObj(equippedByMember[idx]);
    const magic = {};
    for (let lv = 1; lv <= 8; lv += 1) {
      const row = asArray(one[String(lv)]).slice(0, 3).map((name) => (typeof name === "string" && name ? name : null));
      while (row.length < 3) row.push(null);
      magic[`LV${lv}`] = row;
    }
    entry.Magic = magic;
  });
  envelope.saved_at = new Date().toISOString();
  try { localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope)); } catch (_error) {}
}

function normalizeStatusText(value) {
  return String(value || "").trim().toLowerCase().replace(/[_-]/g, " ");
}

function syncPartyToSaveEnvelope(party) {
  const envelope = parseSaveEnvelope();
  const saveParty = asArray(envelope?.save?.party);
  if (!saveParty.length || !Array.isArray(party)) return;
  party.forEach((member, idx) => {
    const entry = saveParty[idx];
    if (!entry || typeof entry !== "object") return;
    entry.hp = Number(member?.hp ?? entry.hp ?? 0);
    entry.max_hp = Number(member?.max_hp ?? entry.max_hp ?? 0);
    const memberMp = asObj(member?.mp_levels);
    const mp = asObj(entry.mp);
    for (let lv = 1; lv <= 8; lv += 1) {
      const cur = Number(asObj(memberMp[String(lv)])?.current ?? mp[`L${lv}MP`] ?? 0);
      mp[`L${lv}MP`] = cur;
    }
    entry.mp = mp;
    const iconSet = new Set(asArray(member?.status_icons).map((s) => normalizeStatusText(s)));
    const statusEffects = asObj(entry.status_effects);
    Object.keys(statusEffects).forEach((label) => {
      const norm = normalizeStatusText(label);
      const hit = iconSet.has(norm)
        || (norm.includes("petrification") && (iconSet.has("petrify") || iconSet.has("petrification")))
        || (norm.includes("partial petrification") && (iconSet.has("partial petrification") || iconSet.has("partial petrify")))
        || (norm === "ko" && (iconSet.has("ko") || Number(member?.hp ?? 0) <= 0));
      statusEffects[label] = Boolean(hit);
    });
    entry.status_effects = statusEffects;
  });
  envelope.saved_at = new Date().toISOString();
  try { localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope)); } catch (_error) {}
}

function modeLabel() {
  return MODES.find((m) => m.key === modeKey)?.label || modeKey;
}

function ensureMagicSetup(state) {
  const setup = asObj(state.magicSetup);
  const stocked = asObj(setup.stock_by_level);
  const equipped = asArray(setup.equipped_by_member);
  if (Object.keys(stocked).length && equipped.length) return;

  const nextStock = {};
  for (let lv = 1; lv <= 8; lv += 1) {
    const rows = asArray(state.magicCandidatesByMember[memberIndex]).filter((row) => Number(row?.level || 0) === lv);
    nextStock[String(lv)] = rows.map((row) => String(row?.name || "")).filter(Boolean);
  }
  const nextEquipped = state.party.map(() => {
    const one = {};
    for (let lv = 1; lv <= 8; lv += 1) one[String(lv)] = [null, null, null];
    return one;
  });
  state.magicSetup = { stock_by_level: nextStock, equipped_by_member: nextEquipped };
}

function equippedRow(state, mIdx, lv) {
  return asArray(asObj(asArray(state.magicSetup?.equipped_by_member)[mIdx])[String(lv)]).slice(0, 3);
}

function stockRow(state, lv) {
  return asArray(asObj(state.magicSetup?.stock_by_level)[String(lv)]);
}

function mpText(member, lv) {
  const mp = asObj(asObj(member?.mp_levels)[String(lv)]);
  const cur = Number(mp?.current ?? 0);
  const max = Number(mp?.max ?? 0);
  return `(${cur}/${max})`;
}

function spellTypeSymbol(meta) {
  const type = String(meta?.type || "");
  if (type.includes("Black")) return "●";
  if (type.includes("White")) return "〇";
  if (type.includes("Summon")) return "◎";
  return "◇";
}

function spellNameWithSymbol(state, spellName) {
  const raw = String(spellName || "");
  if (!raw) return "（空）";
  const meta = state.magicMetaByName?.[raw] || {};
  return `${spellTypeSymbol(meta)}${raw}`;
}

function renderModeButtons() {
  modeRow.innerHTML = "";
  MODES.forEach((mode) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn${modeKey === mode.key ? " active" : ""}`;
    btn.textContent = mode.label;
    btn.addEventListener("click", () => {
      modeKey = mode.key;
      render();
    });
    modeRow.appendChild(btn);
  });
}

function renderGrid(state, member) {
  let html = '<div class="grid-head"><div>LV</div><div>セット1</div><div>セット2</div><div>セット3</div></div>';
  for (let lv = 1; lv <= 8; lv += 1) {
    const row = equippedRow(state, memberIndex, lv);
    html += `<div class="grid-row"><div class="lv ${selectedLevel === lv ? "sel" : ""}" data-lv="${lv}">LV${lv} ${mpText(member, lv)}</div>`;
    for (let i = 0; i < 3; i += 1) {
      const name = spellNameWithSymbol(state, row[i]);
      html += `<div class="slot ${selectedLevel === lv && selectedSlot === i ? "sel" : ""}" data-lv="${lv}" data-slot="${i}">${name}</div>`;
    }
    html += "</div>";
  }
  magicGrid.innerHTML = html;
}

function candidateRowsForMode(state) {
  if (modeKey === "learn") {
    return stockRow(state, selectedLevel).map((name) => ({ kind: "stock", name }));
  }
  if (modeKey === "swap") {
    return state.party
      .map((m, idx) => ({ kind: "member", member_index: idx, name: String(m?.name || "-") }))
      .filter((row) => row.member_index !== memberIndex);
  }
  if (modeKey === "use") {
    return state.party.map((m, idx) => ({ kind: "member", member_index: idx, name: String(m?.name || "-") }));
  }
  return [{ kind: "remove", name: "スロットから外す" }];
}

function renderCandidates(state) {
  candidateTitle.textContent = `${modeLabel()} / LV${selectedLevel}`;
  const rows = candidateRowsForMode(state);
  candidatePane.innerHTML = "";
  if (!rows.length) {
    candidatePane.innerHTML = '<div class="empty">候補がありません。</div>';
    return;
  }
  rows.forEach((row, index) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "candidate";
    if (row.kind === "stock") {
      const meta = state.magicMetaByName?.[row.name] || {};
      btn.textContent = `${spellTypeSymbol(meta)}${row.name}`;
    } else {
      btn.textContent = row.name;
    }
    btn.addEventListener("click", () => executeModeAction(state, row, index));
    candidatePane.appendChild(btn);
  });
}

function selectedSpellName(state) {
  const row = equippedRow(state, memberIndex, selectedLevel);
  return String(row[selectedSlot] || "");
}

function removeStatuses(member, keys) {
  const normalized = new Set(keys.map((k) => normalizeStatusText(k)));
  const before = asArray(member?.status_icons);
  const after = before.filter((value) => !normalized.has(normalizeStatusText(value)));
  return { changed: after.length !== before.length, icons: after };
}

function applyFieldSpell(caster, target, spellName) {
  const s = String(spellName || "");
  if (!s || !caster || !target) return { ok: false, message: "対象を選んでください。" };

  const lvRow = asObj(asObj(caster?.mp_levels)[String(selectedLevel)]);
  const mpCurrent = Number(lvRow?.current ?? 0);
  if (mpCurrent < 1) return { ok: false, message: "MPがたりません。" };

  const targetHp = Number(target?.hp ?? 0);
  const targetMax = Number(target?.max_hp ?? 0);
  const targetIcons = asArray(target?.status_icons).map((row) => String(row));

  let nextTarget = { ...target };
  let changed = false;

  if (Object.prototype.hasOwnProperty.call(HEAL_SPELL_AMOUNT, s)) {
    if (targetHp <= 0 || targetHp >= targetMax) return { ok: false, message: "この対象にはこうかがありません。" };
    const heal = Number(HEAL_SPELL_AMOUNT[s] || 0);
    nextTarget.hp = heal >= 9999 ? targetMax : Math.min(targetMax, targetHp + heal);
    changed = nextTarget.hp !== targetHp;
  } else if (RAISE_SPELLS.has(s)) {
    const isKo = targetHp <= 0 || targetIcons.some((v) => normalizeStatusText(v) === "ko");
    if (!isKo) return { ok: false, message: "この対象にはこうかがありません。" };
    nextTarget.hp = s === "Arise" ? targetMax : Math.max(1, Math.floor(targetMax / 2));
    const clean = removeStatuses(nextTarget, ["ko"]);
    nextTarget.status_icons = clean.icons;
    changed = true;
  } else if (Object.prototype.hasOwnProperty.call(STATUS_SPELL_CLEAR, s)) {
    const clean = removeStatuses(nextTarget, STATUS_SPELL_CLEAR[s]);
    if (!clean.changed) return { ok: false, message: "この対象にはこうかがありません。" };
    nextTarget.status_icons = clean.icons;
    changed = true;
  } else if (s === "Esuna") {
    const clean = removeStatuses(nextTarget, ESUNA_CLEAR);
    if (!clean.changed) return { ok: false, message: "この対象にはこうかがありません。" };
    nextTarget.status_icons = clean.icons;
    changed = true;
  } else {
    return { ok: false, message: "フィールドではつかえないまほうです。" };
  }

  if (!changed) return { ok: false, message: "この対象にはこうかがありません。" };
  const nextCaster = { ...caster };
  const nextLvRow = { ...lvRow, current: mpCurrent - 1 };
  nextCaster.mp_levels = { ...asObj(caster?.mp_levels), [String(selectedLevel)]: nextLvRow };
  return { ok: true, caster: nextCaster, target: nextTarget, message: `${s} をつかいました。` };
}

function executeModeAction(state, row) {
  const setup = asObj(state.magicSetup);
  const stock = asObj(setup.stock_by_level);
  const equippedByMember = asArray(setup.equipped_by_member);
  const lvKey = String(selectedLevel);
  const me = asObj(equippedByMember[memberIndex]);
  const myRow = asArray(me[lvKey]).slice(0, 3);
  while (myRow.length < 3) myRow.push(null);

  if (modeKey === "learn") {
    const spell = String(row?.name || "");
    if (!spell) return;
    const stockList = stockRow(state, selectedLevel);
    if (!stockList.includes(spell)) return;
    const old = myRow[selectedSlot];
    if (typeof old === "string" && old) stockList.push(old);
    myRow[selectedSlot] = spell;
    stock[lvKey] = stockList.filter((name) => name !== spell).sort();
    me[lvKey] = myRow;
    equippedByMember[memberIndex] = me;
    messageLine.textContent = `LV${selectedLevel} スロット${selectedSlot + 1}に ${spell} をセットしました。`;
  } else if (modeKey === "remove") {
    const old = myRow[selectedSlot];
    if (!old) return;
    myRow[selectedSlot] = null;
    const stockList = stockRow(state, selectedLevel);
    stockList.push(old);
    stock[lvKey] = stockList.sort();
    me[lvKey] = myRow;
    equippedByMember[memberIndex] = me;
    messageLine.textContent = `${old} を外してストックに戻しました。`;
  } else if (modeKey === "swap") {
    const otherIndex = Number(row?.member_index ?? -1);
    if (otherIndex < 0 || otherIndex >= equippedByMember.length || otherIndex === memberIndex) return;
    const other = asObj(equippedByMember[otherIndex]);
    const otherRow = asArray(other[lvKey]).slice(0, 3);
    while (otherRow.length < 3) otherRow.push(null);
    [myRow[selectedSlot], otherRow[selectedSlot]] = [otherRow[selectedSlot], myRow[selectedSlot]];
    me[lvKey] = myRow;
    other[lvKey] = otherRow;
    equippedByMember[memberIndex] = me;
    equippedByMember[otherIndex] = other;
    messageLine.textContent = `${row?.name || "-"} と交換しました。`;
  } else if (modeKey === "use") {
    const spell = selectedSpellName(state);
    if (!spell) return;
    const targetIndex = Number(row?.member_index ?? -1);
    if (targetIndex < 0 || targetIndex >= state.party.length) return;
    const caster = state.party[memberIndex];
    const target = state.party[targetIndex];
    const useResult = applyFieldSpell(caster, target, spell);
    if (!useResult.ok) {
      messageLine.textContent = useResult.message;
      return;
    }
    const nextParty = state.party.map((member, idx) => {
      if (idx === memberIndex) return useResult.caster;
      if (idx === targetIndex) return useResult.target;
      return member;
    });
    state.party = nextParty;
    messageLine.textContent = `${useResult.message}（${String(target?.name || "-")}）`;
  }

  const nextRaw = {
    ...(state.raw && typeof state.raw === "object" ? state.raw : {}),
    party: state.party,
    magic_setup: {
      stock_by_level: stock,
      equipped_by_member: equippedByMember,
    },
  };
  persistState(nextRaw);
  persistSaveMagicSetup(nextRaw.magic_setup);
  syncPartyToSaveEnvelope(state.party);
  render();
}

function render() {
  const state = parseState();
  if (!state.party.length) {
    memberName.textContent = "No party members";
    memberJob.textContent = "-";
    magicGrid.innerHTML = "";
    candidatePane.innerHTML = '<div class="empty">パーティ情報がありません。</div>';
    return;
  }
  memberIndex = ((memberIndex % state.party.length) + state.party.length) % state.party.length;
  selectedLevel = Math.max(1, Math.min(8, selectedLevel));
  selectedSlot = Math.max(0, Math.min(2, selectedSlot));

  ensureMagicSetup(state);
  memberName.textContent = String(state.party[memberIndex]?.name || "-");
  memberJob.textContent = String(state.party[memberIndex]?.job || "-");

  renderModeButtons();
  renderGrid(state, state.party[memberIndex]);
  renderCandidates(state);
}

magicGrid.addEventListener("click", (event) => {
  const slot = event.target.closest("[data-slot]");
  if (slot) {
    selectedLevel = Number(slot.dataset.lv || selectedLevel);
    selectedSlot = Number(slot.dataset.slot || selectedSlot);
    render();
    return;
  }
  const lv = event.target.closest("[data-lv]");
  if (lv) {
    selectedLevel = Number(lv.dataset.lv || selectedLevel);
    render();
  }
});

leftBtn?.addEventListener("click", () => {
  memberIndex -= 1;
  render();
});
rightBtn?.addEventListener("click", () => {
  memberIndex += 1;
  render();
});
backBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    memberIndex -= 1;
    render();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    memberIndex += 1;
    render();
  }
});

render();
