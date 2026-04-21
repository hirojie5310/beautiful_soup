import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import { mergeMenuStateIntoSave } from "../menu_save_sync.js";
import { bindButtonHandlers, persistMenuEnvelope } from "./screen_shared.js";

function asObj(v) { return v && typeof v === "object" ? v : {}; }
function asArray(v) { return Array.isArray(v) ? v : []; }
function asNum(v, d = 0) { const n = Number(v); return Number.isFinite(n) ? n : d; }
function canon(text) { return String(text || "").trim().toLowerCase().replace(/[\-_]/g, " "); }
function normalizeMetaKey(text) { return String(text || "").trim().toLowerCase(); }
function clone(value) { return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value)); }

const MODES = [
  { key: "use", label: "つかう" },
  { key: "sort", label: "せいとん" },
  { key: "key_item", label: "だいじなもの" },
];
const ITEM_TYPE_ORDER = { Anywhere: 0, Field: 1, Combat: 2, Weapon: 3, Armor: 4, "Key Item": 5 };
const FIELD_USABLE_TYPES = new Set(["Anywhere", "Field"]);

function normalizeTargetScope(value) {
  return canon(value);
}

export function parseItemStatusAilments(statusAilment) {
  if (Array.isArray(statusAilment)) {
    return statusAilment.map((value) => String(value || "").trim()).filter(Boolean);
  }
  if (typeof statusAilment !== "string") return [];
  return statusAilment.split(",").map((value) => value.trim()).filter(Boolean);
}

export function getItemMeta(inventoryCatalog, itemName) {
  return asObj(asObj(inventoryCatalog)?.item_meta)?.[itemName] || null;
}

export function itemRequiresTarget(itemMeta) {
  const meta = asObj(itemMeta);
  const targetScope = normalizeTargetScope(meta.target_scope);
  const effectCategory = normalizeMetaKey(meta.effect_category);
  if (!targetScope || !["one", "single"].includes(targetScope)) return false;
  return Boolean(effectCategory || meta.default_target_side);
}

export function applyFieldItemEffect(member, itemMeta) {
  const nextMember = { ...asObj(member) };
  const meta = asObj(itemMeta);
  const effectCategory = normalizeMetaKey(meta.effect_category);
  const maxHp = Math.max(1, asNum(nextMember.max_hp, asNum(nextMember.hp, 0)));
  const hp = asNum(nextMember.hp, 0);
  let changed = false;

  if (effectCategory === "heal_hp") {
    if (hp <= 0 || hp >= maxHp) return { changed: false, member: nextMember };
    const amount = asNum(meta.value, 0);
    if (amount <= 0) return { changed: false, member: nextMember };
    nextMember.hp = Math.min(maxHp, hp + amount);
    changed = nextMember.hp !== hp;
    return { changed, member: nextMember };
  }

  if (effectCategory === "heal_full") {
    nextMember.hp = maxHp;
    changed = hp !== nextMember.hp;
    const levels = asObj(nextMember.mp_levels);
    for (let lv = 1; lv <= 8; lv += 1) {
      const key = String(lv);
      const row = asObj(levels[key]);
      const current = asNum(row.current, 0);
      const max = asNum(row.max, current);
      if (current !== max) {
        row.current = max;
        levels[key] = row;
        changed = true;
      }
    }
    nextMember.mp_levels = levels;
    return { changed, member: nextMember };
  }

  if (effectCategory === "revive") {
    if (hp > 0) return { changed: false, member: nextMember };
    nextMember.hp = Math.max(1, Math.floor(maxHp / 2));
    const beforeStatuses = asArray(nextMember.status_icons);
    const removeSet = new Set(parseItemStatusAilments(meta.status_ailment).map((key) => canon(key)));
    removeSet.add("ko");
    const nextStatuses = beforeStatuses.filter((icon) => !removeSet.has(canon(icon)));
    nextMember.status_icons = nextStatuses;
    changed = nextMember.hp !== hp || nextStatuses.length !== beforeStatuses.length;
    return { changed, member: nextMember };
  }

  if (effectCategory === "status_recovery" || effectCategory === "status_toggle") {
    const beforeStatuses = asArray(nextMember.status_icons);
    const removeSet = new Set(parseItemStatusAilments(meta.status_ailment).map((key) => canon(key)));
    if (!removeSet.size) return { changed: false, member: nextMember };
    const nextStatuses = beforeStatuses.filter((icon) => !removeSet.has(canon(icon)));
    nextMember.status_icons = nextStatuses;
    changed = nextStatuses.length !== beforeStatuses.length;
    return { changed, member: nextMember };
  }

  return { changed: false, member: nextMember };
}

function renderLayout() {
  return renderMenuSubpageShell({
    content: `
      <section class="frame toolbar">
        <h1 class="title">ITEM</h1>
        <button class="btn" type="button" id="backBtn">BACK</button>
        <div id="memberName" class="desc">-</div>
      </section>
      <section class="frame mode-row" id="modeRow"></section>
      <section class="frame">
        <div id="itemTitle" class="desc">所持アイテム</div>
        <div class="item-list" id="itemList"></div>
      </section>
      <section class="frame">
        <div class="desc">対象キャラクター</div>
        <div class="target-list" id="targetList"></div>
      </section>
      <section class="frame desc" id="messageLine">モードを選んで操作してください。</section>
      <section class="frame footer">
        <div class="desc" id="sortLine">A→Z</div>
      </section>
    `,
    styles: `
      .toolbar { display:grid; grid-template-columns: 1fr auto auto; gap:8px; align-items:center; }
      .title { margin:0; color:#ffe588; font-size:1rem; }
      .mode-row { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:6px; }
      .item-list { display:grid; gap:6px; max-height:35vh; overflow:auto; }
      .item-row, .target-row {
        border:1px solid rgba(255,255,255,0.32); border-radius:6px; background:rgba(0,0,0,0.2);
        color:#eef2ff; min-height:36px; padding:6px 8px; cursor:pointer;
      }
      .item-row { display:grid; grid-template-columns:1fr auto; align-items:center; }
      .item-row.sel { box-shadow: inset 0 0 0 2px rgba(255,227,127,0.6); }
      .target-list { display:grid; gap:6px; }
      .target-row { display:grid; grid-template-columns:1fr auto; align-items:center; background:rgba(22,36,95,0.94); }
      .name { font-weight:700; }
      .hp { color:#89f0ac; font-size:0.86rem; }
      .icon-row { display:flex; gap:4px; justify-content:flex-end; min-height:16px; }
      .status-icon { width:16px; height:16px; image-rendering:pixelated; }
      .desc { color:#acb6d7; font-size:0.84rem; }
      .footer { display:grid; grid-template-columns:1fr; gap:8px; }
      .empty { color:#acb6d7; border:1px dashed rgba(255,255,255,0.3); border-radius:6px; padding:8px; }
    `,
  });
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

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const modeRow = mountNode.querySelector("#modeRow");
  const itemTitle = mountNode.querySelector("#itemTitle");
  const itemList = mountNode.querySelector("#itemList");
  const targetList = mountNode.querySelector("#targetList");
  const messageLine = mountNode.querySelector("#messageLine");
  const memberName = mountNode.querySelector("#memberName");
  const sortLine = mountNode.querySelector("#sortLine");
  const backBtn = mountNode.querySelector("#backBtn");

  let modeKey = "use";
  let selectedItemName = "";
  let sortAscending = true;

  function getState() {
    return store.getState();
  }

  function inventoryRows() {
    const envelope = getState().saveEnvelope;
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
      ? rows.filter((row) => row.itemType === "Key Item")
      : rows.filter((row) => row.itemType !== "Key Item");
    filtered.sort((a, b) => {
      const typeCmp = (ITEM_TYPE_ORDER[a.itemType] ?? 99) - (ITEM_TYPE_ORDER[b.itemType] ?? 99);
      if (typeCmp !== 0) return typeCmp;
      return sortAscending ? a.name.localeCompare(b.name, "ja") : b.name.localeCompare(a.name, "ja");
    });
    return filtered;
  }

  function persist(nextMenuState, nextEnvelope) {
    persistMenuEnvelope(store, nextMenuState, nextEnvelope);
  }

  function consumeInventory(envelope, itemName) {
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
      return true;
    }
    return false;
  }

  function useItem(itemName, targetIdx) {
    const appState = getState();
    const rawMenuState = asObj(appState.menuState);
    const party = asArray(rawMenuState.party).map((member) => ({ ...member }));
    if (!party.length || targetIdx < 0 || targetIdx >= party.length) return { ok: false, message: "対象が不正です。" };
    const itemType = inventoryRows().find((row) => row.name === itemName)?.itemType || "";
    if (!FIELD_USABLE_TYPES.has(itemType)) return { ok: false, message: "このアイテムはフィールドでは使えません。" };

    const itemMeta = getItemMeta(rawMenuState.inventory_catalog, itemName);
    const effectCategory = normalizeMetaKey(itemMeta?.effect_category);
    if (!effectCategory) {
      return { ok: false, message: "未実装のアイテムです。" };
    }
    const result = applyFieldItemEffect(party[targetIdx], itemMeta);
    if (!result.changed) return { ok: false, message: "効果がありません。" };

    const nextEnvelope = clone(appState.saveEnvelope || store.createDefaultEnvelope());
    if (!consumeInventory(nextEnvelope, itemName)) return { ok: false, message: "在庫がありません。" };
    party[targetIdx] = result.member;
    const nextMenuState = { ...rawMenuState, party };
    nextEnvelope.menu_state = nextMenuState;
    if (nextEnvelope?.save && typeof nextEnvelope.save === "object") {
      nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextMenuState);
    }
    persist(nextMenuState, nextEnvelope);
    return { ok: true, message: `${itemName} を ${target.name || "target"} に使用しました。` };
  }

  function renderModeButtons() {
    modeRow.innerHTML = "";
    MODES.forEach((mode) => {
      const btn = document.createElement("button");
      btn.className = `btn${modeKey === mode.key ? " active" : ""}`;
      btn.type = "button";
      btn.textContent = mode.label;
      btn.addEventListener("click", () => {
        if (mode.key === "sort") sortAscending = !sortAscending;
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
      button.innerHTML = `<div>${row.name} <span class="desc">[${row.itemType}]</span></div><div>×${row.count}</div>`;
      button.addEventListener("click", () => {
        selectedItemName = row.name;
        if (modeKey === "sort") sortAscending = !sortAscending;
        render();
      });
      itemList.appendChild(button);
    });
  }

  function renderTargetRows() {
    const party = asArray(getState().menuState?.party);
    memberName.textContent = party.length ? "全キャラクター" : "-";
    targetList.innerHTML = "";
    if (!party.length) {
      targetList.innerHTML = '<div class="empty">キャラクター情報がありません。</div>';
      return;
    }
    const selectedRequiresTarget = itemRequiresTarget(getItemMeta(getState().menuState?.inventory_catalog, selectedItemName));
    party.forEach((member, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "target-row";
      btn.innerHTML = `<div><div class="name">${String(member?.name || `member ${idx + 1}`)}</div><div class="hp">${asNum(member?.hp)} / ${asNum(member?.max_hp)}</div></div><div class="icon-row"></div>`;
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

  function render() {
    renderModeButtons();
    renderItemRows();
    renderTargetRows();
    sortLine.textContent = sortAscending ? "A→Z" : "Z→A";
  }

  const handleBack = () => navigate("menu");
  const unbindButtons = bindButtonHandlers([{ target: backBtn, handler: handleBack }]);
  render();
  return () => unbindButtons();
}
