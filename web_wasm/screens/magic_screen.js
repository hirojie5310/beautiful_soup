import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import { memberIdentityKeys } from "../shared_party.js";
import {
  bindMenuSubpageNavigation,
  persistMenuEnvelope,
  stepMenuMemberSelection,
  syncMenuMemberSelection,
} from "./screen_shared.js";

const MODES = [
  { key: "use", label: "つかう" },
  { key: "learn", label: "おぼえる" },
  { key: "remove", label: "はずす" },
  { key: "swap", label: "こうかん" },
];
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
  "partial petrify": "Partial Petrification",
  partial_petrify: "Partial Petrification",
};
const TARGETED_FIELD_EFFECT_CATEGORIES = new Set(["heal_hp", "revive", "status_recovery"]);
const TARGETLESS_FIELD_EFFECT_CATEGORIES = new Set(["teleport", "field_utility"]);
const FIELD_USABLE_EFFECT_CATEGORIES = new Set([
  ...TARGETED_FIELD_EFFECT_CATEGORIES,
  ...TARGETLESS_FIELD_EFFECT_CATEGORIES,
]);

function asArray(v) { return Array.isArray(v) ? v : []; }
function asObj(v) { return v && typeof v === "object" ? v : {}; }
function normalizeStatusText(value) { return String(value || "").trim().toLowerCase().replace(/[_-]/g, " "); }
function normalizeMetaKey(value) { return String(value || "").trim().toLowerCase(); }
function clone(value) { return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value)); }

function canonicalStatusKey(value) {
  const normalized = normalizeStatusText(value);
  const mapped = STATUS_EFFECT_KEY_BY_ICON[normalized];
  return normalizeStatusText(mapped || normalized);
}

export function parseSpellStatusAilments(statusAilment) {
  if (Array.isArray(statusAilment)) {
    return statusAilment.map((value) => String(value || "").trim()).filter(Boolean);
  }
  if (typeof statusAilment !== "string") return [];
  return statusAilment.split(",").map((value) => value.trim()).filter(Boolean);
}

export function getSpellMeta(metaByName, spellName) {
  return asObj(metaByName)?.[spellName] || null;
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

export function usableSpellNames(menuState, mIdx) {
  const candidateNames = asArray(
    (menuState?.magic_candidates_by_member || menuState?.magicCandidatesByMember)?.[mIdx],
  )
    .map((row) => String(row?.name || ""))
    .filter(Boolean);
  const candidateSet = new Set(candidateNames);

  const member = asObj(asArray(menuState?.party)[mIdx]);
  const currentJob = String(member?.current_job || member?.job || "").trim();
  if (!currentJob) return candidateSet;

  const allowedNames = asArray(asObj(menuState?.job_magic_allowed_names_by_job)[currentJob])
    .map((name) => String(name || ""))
    .filter(Boolean);
  if (!allowedNames.length) return candidateSet;
  const merged = new Set(allowedNames);
  candidateSet.forEach((name) => merged.add(name));
  return merged;
}

export function applyFieldSpellEffect(caster, target, spellMeta, selectedLevel) {
  const meta = asObj(spellMeta);
  const effectCategory = normalizeMetaKey(meta.effect_category);
  const lvKey = String(selectedLevel);
  const lvRow = asObj(asObj(caster?.mp_levels)[lvKey]);
  const mpCurrent = Number(lvRow?.current ?? 0);
  if (mpCurrent < 1) return { ok: false, message: "MPがたりません。" };

  const targetHp = Number(target?.hp ?? 0);
  const targetMax = Number(target?.max_hp ?? 0);
  const targetIcons = asArray(target?.status_icons).map((row) => String(row));
  let nextTarget = { ...target };
  let changed = false;

  if (!FIELD_USABLE_EFFECT_CATEGORIES.has(effectCategory)) {
    return { ok: false, message: "フィールドではつかえないまほうです。" };
  }

  if (effectCategory === "heal_hp") {
    if (targetHp <= 0 || targetHp >= targetMax) return { ok: false, message: "この対象にはこうかがありません。" };
    const heal = Number(meta.field_heal_hp || 0);
    if (heal <= 0) return { ok: false, message: "フィールドではつかえないまほうです。" };
    nextTarget.hp = heal >= 9999 ? targetMax : Math.min(targetMax, targetHp + heal);
    changed = true;
  } else if (effectCategory === "revive") {
    const isKo = targetHp <= 0 || targetIcons.some((v) => normalizeStatusText(v) === "ko");
    if (!isKo) return { ok: false, message: "この対象にはこうかがありません。" };
    nextTarget.hp = normalizeMetaKey(meta.field_revive_hp) === "full"
      ? targetMax
      : Math.max(1, Math.floor(targetMax / 2));
    const removeSet = new Set(parseSpellStatusAilments(meta.status_ailment).map((key) => canonicalStatusKey(key)));
    removeSet.add("ko");
    nextTarget.status_icons = targetIcons.filter((value) => !removeSet.has(canonicalStatusKey(value)));
    changed = true;
  } else if (effectCategory === "status_recovery") {
    const removeSet = new Set(parseSpellStatusAilments(meta.status_ailment).map((key) => canonicalStatusKey(key)));
    if (!removeSet.size) return { ok: false, message: "フィールドではつかえないまほうです。" };
    const nextIcons = targetIcons.filter((value) => !removeSet.has(canonicalStatusKey(value)));
    if (nextIcons.length === targetIcons.length) return { ok: false, message: "この対象にはこうかがありません。" };
    nextTarget.status_icons = nextIcons;
    changed = true;
  } else if (TARGETLESS_FIELD_EFFECT_CATEGORIES.has(effectCategory)) {
    changed = true;
  }

  if (!changed) return { ok: false, message: "この対象にはこうかがありません。" };
  const nextCaster = { ...caster, mp_levels: { ...asObj(caster?.mp_levels), [lvKey]: { ...lvRow, current: mpCurrent - 1 } } };
  return {
    ok: true,
    caster: nextCaster,
    target: nextTarget,
    usesTarget: TARGETED_FIELD_EFFECT_CATEGORIES.has(effectCategory),
  };
}

function findSavePartyIndex(saveParty, member, fallbackIndex) {
  const wanted = memberIdentityKeys(member, fallbackIndex);
  if (!wanted.length) return fallbackIndex;
  const wantedSet = new Set(wanted);
  const matchedIndex = asArray(saveParty).findIndex((entry, index) => (
    memberIdentityKeys(entry, index).some((key) => wantedSet.has(key))
  ));
  return matchedIndex >= 0 ? matchedIndex : fallbackIndex;
}

export function applyMagicSetupToSaveParty(saveParty, equippedByMember, partyMembers = []) {
  const party = asArray(saveParty);
  const equipped = asArray(equippedByMember);
  const members = asArray(partyMembers).length ? asArray(partyMembers) : party;
  members.forEach((member, memberIndex) => {
    const saveIndex = findSavePartyIndex(party, member, memberIndex);
    const entry = party[saveIndex];
    if (!entry || typeof entry !== "object") return;
    const memberSetup = asObj(equipped[memberIndex]);
    const magic = {};
    for (let lv = 1; lv <= 8; lv += 1) {
      const row = asArray(memberSetup[String(lv)]).slice(0, 3).map((name) => (
        typeof name === "string" && name ? name : null
      ));
      while (row.length < 3) row.push(null);
      magic[`LV${lv}`] = row;
    }
    entry.Magic = magic;
    if ("magic" in entry) delete entry.magic;
  });
}

function syncSavePartyVitalsAndStatuses(saveParty, party) {
  const saveRows = asArray(saveParty);
  const partyRows = asArray(party);
  partyRows.forEach((member, index) => {
    const saveIndex = findSavePartyIndex(saveRows, member, index);
    const saveEntry = saveRows[saveIndex];
    if (!saveEntry || typeof saveEntry !== "object") return;
    const mpLevels = asObj(member?.mp_levels);
    const nextStatusEffects = saveEntry.status_effects && typeof saveEntry.status_effects === "object"
      ? { ...saveEntry.status_effects }
      : {};
    Object.keys(nextStatusEffects).forEach((key) => {
      nextStatusEffects[key] = false;
    });
    asArray(member?.status_icons).forEach((icon) => {
      const statusKey = STATUS_EFFECT_KEY_BY_ICON[normalizeStatusText(icon)];
      if (statusKey) nextStatusEffects[statusKey] = true;
    });
    saveEntry.hp = Number(member?.hp ?? saveEntry.hp ?? 0);
    saveEntry.max_hp = Number(member?.max_hp ?? saveEntry.max_hp ?? 0);
    saveEntry.mp_levels = mpLevels;
    saveEntry.mp = Object.fromEntries(
      Array.from({ length: 8 }, (_unused, offset) => {
        const level = String(offset + 1);
        return [`L${level}MP`, Number(asObj(mpLevels[level]).current ?? 0)];
      }),
    );
    saveEntry.status_effects = nextStatusEffects;
    saveEntry.status_icons = asArray(member?.status_icons);
  });
}

function renderLayout() {
  return renderMenuSubpageShell({
    content: `
      <section class="frame mode-row" id="modeRow"></section>
      <section class="frame member"><div id="memberName">-</div><div id="memberJob">-</div></section>
      <section class="frame grid" id="magicGrid"></section>
      <section class="frame"><div id="candidateTitle">候補</div><div class="candidate-pane" id="candidatePane"></div></section>
      <section class="frame"><div id="messageLine" class="desc">モードを選び、スロットや候補をタップして操作します。</div></section>
      <section class="frame footer">
        <button class="btn" type="button" id="leftBtn">◀</button>
        <button class="btn" type="button" id="backBtn">BACK</button>
        <button class="btn" type="button" id="rightBtn">▶</button>
      </section>
      <section class="muted">←→でキャラ変更 / LV行・スロット行をタップ / 候補をタップで決定</section>
    `,
    styles: `
      .mode-row { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:6px; }
      .member { display:flex; justify-content:space-between; gap:8px; font-weight:700; }
      .grid { background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(0,0,0,0.22)), rgba(22, 36, 95, 0.94); }
      .grid-head, .grid-row { display:grid; grid-template-columns:96px repeat(3, 1fr); }
      .grid-head > div, .grid-row > div { min-height:40px; display:flex; align-items:center; padding:0 8px; border-right:1px solid rgba(255,255,255,0.25); border-bottom:1px solid rgba(255,255,255,0.25); font-size:0.8rem; }
      .grid-head > div:last-child, .grid-row > div:last-child { border-right:0; }
      .lv, .slot, .candidate { cursor:pointer; }
      .sel { box-shadow: inset 0 0 0 2px rgba(255,227,127,0.6); }
      .candidate-pane { display:grid; gap:6px; max-height:20vh; overflow:auto; }
      .candidate { border:1px solid rgba(255,255,255,0.3); border-radius:6px; background:rgba(0,0,0,0.2); color:#eef2ff; padding:7px; text-align:left; }
      .candidate.target-candidate { display:grid; grid-template-columns:1fr auto; align-items:center; gap:8px; }
      .candidate .name { font-weight:700; }
      .candidate .hp { color:#89f0ac; font-size:0.86rem; }
      .candidate .icon-row { display:flex; gap:4px; justify-content:flex-end; min-height:16px; }
      .candidate .status-icon { width:16px; height:16px; image-rendering:pixelated; }
      .desc { color:#acb6d7; font-size:0.85rem; }
      .footer { display:grid; grid-template-columns:1fr 1.6fr 1fr; gap:8px; }
      .empty { color:#acb6d7; }
    `,
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  const modeRow = mountNode.querySelector("#modeRow");
  const memberName = mountNode.querySelector("#memberName");
  const memberJob = mountNode.querySelector("#memberJob");
  const magicGrid = mountNode.querySelector("#magicGrid");
  const candidateTitle = mountNode.querySelector("#candidateTitle");
  const candidatePane = mountNode.querySelector("#candidatePane");
  const messageLine = mountNode.querySelector("#messageLine");
  const leftBtn = mountNode.querySelector("#leftBtn");
  const rightBtn = mountNode.querySelector("#rightBtn");
  const backBtn = mountNode.querySelector("#backBtn");

  let modeKey = "use";
  let memberIndex = Number(store.getState().menuMemberIndex ?? 0);
  let selectedLevel = 1;
  let selectedSlot = 0;

  function persist(nextMenuState, nextEnvelope) {
    persistMenuEnvelope(store, nextMenuState, nextEnvelope);
  }

  function modeLabel() {
    return MODES.find((m) => m.key === modeKey)?.label || modeKey;
  }

  function ensureMagicSetup(state) {
    const setup = asObj(state.magic_setup || state.magicSetup);
    const stocked = asObj(setup.stock_by_level);
    const equipped = asArray(setup.equipped_by_member);
    if (Object.keys(stocked).length && equipped.length) return setup;
    const nextStock = {};
    for (let lv = 1; lv <= 8; lv += 1) {
      const rows = asArray((state.magic_candidates_by_member || state.magicCandidatesByMember)?.[memberIndex]).filter((row) => Number(row?.level || 0) === lv);
      nextStock[String(lv)] = rows.map((row) => String(row?.name || "")).filter(Boolean);
    }
    const nextEquipped = asArray(state.party).map(() => {
      const one = {};
      for (let lv = 1; lv <= 8; lv += 1) one[String(lv)] = [null, null, null];
      return one;
    });
    return { stock_by_level: nextStock, equipped_by_member: nextEquipped };
  }

  function equippedRow(setup, mIdx, lv) {
    return asArray(asObj(asArray(setup?.equipped_by_member)[mIdx])[String(lv)]).slice(0, 3);
  }
  function stockRow(setup, lv) { return asArray(asObj(setup?.stock_by_level)[String(lv)]); }
  function mpText(member, lv) {
    const mp = asObj(asObj(member?.mp_levels)[String(lv)]);
    return `(${Number(mp?.current ?? 0)}/${Number(mp?.max ?? 0)})`;
  }
  function spellTypeSymbol(meta) {
    const type = String(meta?.type || "");
    if (type.includes("Black")) return "●";
    if (type.includes("White")) return "〇";
    if (type.includes("Summon")) return "◎";
    return "◇";
  }
  function spellNameWithSymbol(metaByName, spellName) {
    const raw = String(spellName || "");
    if (!raw) return "（空）";
    return `${spellTypeSymbol(metaByName?.[raw] || {})}${raw}`;
  }
  function applyFieldSpell(caster, target, spellName) {
    const s = String(spellName || "");
    if (!s || !caster || !target) return { ok: false, message: "対象を選んでください。" };
    const metaByName = store.getState().menuState?.magic_spell_meta_by_name || store.getState().menuState?.magicMetaByName;
    const spellMeta = getSpellMeta(metaByName, s);
    const result = applyFieldSpellEffect(caster, target, spellMeta, selectedLevel);
    if (!result.ok) return result;
    return { ...result, message: `${s} をつかいました。` };
  }

  function executeModeAction(row) {
    const state = store.getState();
    const menuState = state.menuState;
    const setup = ensureMagicSetup(menuState);
    const stock = asObj(setup.stock_by_level);
    const equippedByMember = asArray(setup.equipped_by_member).map((one) => clone(one));
    const lvKey = String(selectedLevel);
    const me = asObj(equippedByMember[memberIndex]);
    const myRow = asArray(me[lvKey]).slice(0, 3);
    while (myRow.length < 3) myRow.push(null);
    const party = asArray(menuState.party).map((member) => clone(member));

    if (modeKey === "learn") {
      const spell = String(row?.name || "");
      if (!spell) return;
      const stockList = stockRow(setup, selectedLevel);
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
      const stockList = stockRow(setup, selectedLevel);
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
      const spell = String(myRow[selectedSlot] || "");
      if (!spell) return;
      if (!usableSpellNames(menuState, memberIndex).has(spell)) {
        messageLine.textContent = "現在のジョブではその魔法は使えません。";
        return;
      }
      const targetIndex = Number(row?.member_index ?? -1);
      if (targetIndex < 0 || targetIndex >= party.length) return;
      const useResult = applyFieldSpell(party[memberIndex], party[targetIndex], spell);
      if (!useResult.ok) {
        messageLine.textContent = useResult.message;
        return;
      }
      party[memberIndex] = useResult.caster;
      party[targetIndex] = useResult.target;
      messageLine.textContent = useResult.usesTarget
        ? `${useResult.message}（${String(party[targetIndex]?.name || "-")}）`
        : useResult.message;
    }

    const nextMenuState = {
      ...(menuState && typeof menuState === "object" ? menuState : {}),
      party,
      magic_setup: { stock_by_level: stock, equipped_by_member: equippedByMember },
    };
    const nextEnvelope = clone(state.saveEnvelope || store.createDefaultEnvelope());
    nextEnvelope.menu_state = nextMenuState;
    if (Array.isArray(nextEnvelope?.save?.party)) {
      applyMagicSetupToSaveParty(nextEnvelope.save.party, equippedByMember, party);
      syncSavePartyVitalsAndStatuses(nextEnvelope.save.party, party);
    }
    persist(nextMenuState, nextEnvelope);
    render();
  }

  function renderModeButtons() {
    modeRow.innerHTML = "";
    MODES.forEach((mode) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `btn${modeKey === mode.key ? " active" : ""}`;
      btn.textContent = mode.label;
      btn.addEventListener("click", () => { modeKey = mode.key; render(); });
      modeRow.appendChild(btn);
    });
  }

  function renderGrid(menuState, setup, member) {
    let html = '<div class="grid-head"><div>LV</div><div>セット1</div><div>セット2</div><div>セット3</div></div>';
    for (let lv = 1; lv <= 8; lv += 1) {
      const row = equippedRow(setup, memberIndex, lv);
      html += `<div class="grid-row"><div class="lv ${selectedLevel === lv ? "sel" : ""}" data-lv="${lv}">LV${lv} ${mpText(member, lv)}</div>`;
      for (let i = 0; i < 3; i += 1) {
        html += `<div class="slot ${selectedLevel === lv && selectedSlot === i ? "sel" : ""}" data-lv="${lv}" data-slot="${i}">${spellNameWithSymbol(menuState.magic_spell_meta_by_name || menuState.magicMetaByName, row[i])}</div>`;
      }
      html += "</div>";
    }
    magicGrid.innerHTML = html;
  }

  function candidateRowsForMode(menuState, setup) {
    if (modeKey === "learn") return stockRow(setup, selectedLevel).map((name) => ({ kind: "stock", name }));
    if (modeKey === "swap") return asArray(menuState.party).map((m, idx) => ({ kind: "member", member_index: idx, name: String(m?.name || "-") })).filter((row) => row.member_index !== memberIndex);
    if (modeKey === "use") return asArray(menuState.party).map((m, idx) => ({ kind: "member", member_index: idx, name: String(m?.name || "-") }));
    return [{ kind: "remove", name: "スロットから外す" }];
  }

  function renderCandidates(menuState, setup) {
    candidateTitle.textContent = `${modeLabel()} / LV${selectedLevel}`;
    const rows = candidateRowsForMode(menuState, setup);
    candidatePane.innerHTML = "";
    if (!rows.length) {
      candidatePane.innerHTML = '<div class="empty">候補がありません。</div>';
      return;
    }
    rows.forEach((row) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "candidate";
      if (row.kind === "stock") {
        const meta = (menuState.magic_spell_meta_by_name || menuState.magicMetaByName)?.[row.name] || {};
        btn.textContent = `${spellTypeSymbol(meta)}${row.name}`;
      } else if (modeKey === "use") {
        const member = asObj(asArray(menuState.party)[Number(row.member_index ?? -1)]);
        btn.classList.add("target-candidate");
        btn.innerHTML = `<div><div class="name">${row.name}</div><div class="hp">${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}</div></div><div class="icon-row"></div>`;
        const iconRow = btn.querySelector(".icon-row");
        asArray(member?.status_icons).forEach((iconKey) => {
          const candidates = resolveStatusIconCandidates(iconKey);
          if (!candidates.length) return;
          const img = document.createElement("img");
          img.className = "status-icon";
          img.alt = String(iconKey || "");
          let iconIndex = 0;
          img.addEventListener("error", () => {
            iconIndex += 1;
            if (iconIndex < candidates.length) img.src = candidates[iconIndex];
            else img.remove();
          });
          img.src = candidates[iconIndex];
          iconRow?.appendChild(img);
        });
      } else {
        btn.textContent = row.name;
      }
      btn.addEventListener("click", () => executeModeAction(row));
      candidatePane.appendChild(btn);
    });
  }

  function render() {
    const menuState = store.getState().menuState;
    const selection = syncMenuMemberSelection(store, memberIndex);
    const party = asArray(selection.party);
    if (!party.length) {
      memberName.textContent = "No party members";
      memberJob.textContent = "-";
      magicGrid.innerHTML = "";
      candidatePane.innerHTML = '<div class="empty">パーティ情報がありません。</div>';
      return;
    }
    memberIndex = selection.memberIndex;
    selectedLevel = Math.max(1, Math.min(8, selectedLevel));
    selectedSlot = Math.max(0, Math.min(2, selectedSlot));
    const setup = ensureMagicSetup(menuState);
    memberName.textContent = String(party[memberIndex]?.name || "-");
    memberJob.textContent = String(party[memberIndex]?.job || "-");
    renderModeButtons();
    renderGrid(menuState, setup, party[memberIndex]);
    renderCandidates(menuState, setup);
  }

  const onGridClick = (event) => {
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
  };
  const onLeft = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, -1); render(); };
  const onRight = () => { memberIndex = stepMenuMemberSelection(store, memberIndex, 1); render(); };
  const onBack = () => navigate("menu");
  magicGrid.addEventListener("click", onGridClick);
  const unbindButtons = bindMenuSubpageNavigation({
    leftBtn,
    rightBtn,
    backBtn,
    onLeft,
    onRight,
    onBack,
  });
  render();
  return () => {
    magicGrid.removeEventListener("click", onGridClick);
    unbindButtons();
  };
}
