import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import {
  bindMenuSubpageNavigation,
  persistMenuEnvelope,
  syncMenuMemberSelection,
} from "./screen_shared.js";

const MODES = [
  { key: "use", label: "つかう" },
  { key: "learn", label: "おぼえる" },
  { key: "remove", label: "はずす" },
  { key: "swap", label: "こうかん" },
];
const HEAL_SPELL_AMOUNT = { Cure: 50, Cura: 150, Curaga: 400, Curaja: 9999 };
const RAISE_SPELLS = new Set(["Raise", "Arise"]);
const STATUS_SPELL_CLEAR = {
  Poisona: ["poison"],
  Blindna: ["blind"],
  Stona: ["petrify", "petrification", "partial_petrify", "partial petrification"],
};
const ESUNA_CLEAR = [
  "poison", "blind", "mini", "silence", "toad", "petrify", "petrification",
  "partial_petrify", "partial petrification", "confusion", "sleep", "paralyze", "paralysis",
];

function asArray(v) { return Array.isArray(v) ? v : []; }
function asObj(v) { return v && typeof v === "object" ? v : {}; }
function normalizeStatusText(value) { return String(value || "").trim().toLowerCase().replace(/[_-]/g, " "); }
function clone(value) { return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value)); }

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

  let modeKey = "learn";
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
      changed = true;
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
    const nextCaster = { ...caster, mp_levels: { ...asObj(caster?.mp_levels), [String(selectedLevel)]: { ...lvRow, current: mpCurrent - 1 } } };
    return { ok: true, caster: nextCaster, target: nextTarget, message: `${s} をつかいました。` };
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
      const targetIndex = Number(row?.member_index ?? -1);
      if (targetIndex < 0 || targetIndex >= party.length) return;
      const useResult = applyFieldSpell(party[memberIndex], party[targetIndex], spell);
      if (!useResult.ok) {
        messageLine.textContent = useResult.message;
        return;
      }
      party[memberIndex] = useResult.caster;
      party[targetIndex] = useResult.target;
      messageLine.textContent = `${useResult.message}（${String(party[targetIndex]?.name || "-")}）`;
    }

    const nextMenuState = {
      ...(menuState && typeof menuState === "object" ? menuState : {}),
      party,
      magic_setup: { stock_by_level: stock, equipped_by_member: equippedByMember },
    };
    const nextEnvelope = clone(state.saveEnvelope || store.createDefaultEnvelope());
    nextEnvelope.menu_state = nextMenuState;
    if (Array.isArray(nextEnvelope?.save?.party)) {
      party.forEach((member, idx) => {
        if (!nextEnvelope.save.party[idx]) return;
        nextEnvelope.save.party[idx].hp = Number(member?.hp ?? nextEnvelope.save.party[idx].hp ?? 0);
        nextEnvelope.save.party[idx].max_hp = Number(member?.max_hp ?? nextEnvelope.save.party[idx].max_hp ?? 0);
        const mp = asObj(nextEnvelope.save.party[idx].mp);
        const memberMp = asObj(member?.mp_levels);
        for (let lv = 1; lv <= 8; lv += 1) {
          mp[`L${lv}MP`] = Number(asObj(memberMp[String(lv)])?.current ?? mp[`L${lv}MP`] ?? 0);
        }
        nextEnvelope.save.party[idx].mp = mp;
      });
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
  const onLeft = () => { memberIndex -= 1; render(); };
  const onRight = () => { memberIndex += 1; render(); };
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
