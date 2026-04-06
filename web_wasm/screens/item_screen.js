import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import { bindButtonHandlers, persistMenuEnvelope } from "./screen_shared.js";

function asObj(v) { return v && typeof v === "object" ? v : {}; }
function asArray(v) { return Array.isArray(v) ? v : []; }
function asNum(v, d = 0) { const n = Number(v); return Number.isFinite(n) ? n : d; }
function canon(text) { return String(text || "").trim().toLowerCase().replace(/[\-_]/g, " "); }
function clone(value) { return typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value)); }
function cloneObj(value) { return value && typeof value === "object" ? { ...value } : {}; }

const MODES = [
  { key: "use", label: "つかう" },
  { key: "sort", label: "せいとん" },
  { key: "key_item", label: "だいじなもの" },
];
const ITEM_TYPE_ORDER = { Anywhere: 0, Field: 1, Combat: 2, Weapon: 3, Armor: 4, "Key Item": 5 };
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
  partial_petrify: "Partial Petrification",
};

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

  function clearStatuses(member, keys) {
    const before = asArray(member?.status_icons);
    const removeSet = new Set(keys.map((key) => canon(key)));
    const next = before.filter((icon) => !removeSet.has(canon(icon)));
    if (next.length === before.length) return false;
    member.status_icons = next;
    return true;
  }

  function syncSaveEntryFromMember(saveEntry, member) {
    if (!saveEntry || typeof saveEntry !== "object") return;
    const mpLevels = asObj(member?.mp_levels);
    const nextStatusEffects = cloneObj(saveEntry.status_effects);
    Object.keys(nextStatusEffects).forEach((key) => {
      nextStatusEffects[key] = false;
    });
    asArray(member?.status_icons).forEach((icon) => {
      const statusKey = STATUS_EFFECT_KEY_BY_ICON[canon(icon)];
      if (statusKey) nextStatusEffects[statusKey] = true;
    });
    saveEntry.hp = Number(member?.hp ?? saveEntry.hp ?? 0);
    saveEntry.max_hp = Number(member?.max_hp ?? saveEntry.max_hp ?? 0);
    saveEntry.mp_levels = mpLevels;
    saveEntry.mp = Object.fromEntries(
      Array.from({ length: 8 }, (_unused, index) => {
        const level = String(index + 1);
        return [`L${level}MP`, asNum(asObj(mpLevels[level]).current, 0)];
      }),
    );
    saveEntry.status_effects = nextStatusEffects;
    saveEntry.status_icons = asArray(member?.status_icons);
  }

  function useItem(itemName, targetIdx) {
    const appState = getState();
    const rawMenuState = asObj(appState.menuState);
    const party = asArray(rawMenuState.party).map((member) => ({ ...member }));
    if (!party.length || targetIdx < 0 || targetIdx >= party.length) return { ok: false, message: "対象が不正です。" };
    const itemType = inventoryRows().find((row) => row.name === itemName)?.itemType || "";
    if (!FIELD_USABLE_TYPES.has(itemType)) return { ok: false, message: "このアイテムはフィールドでは使えません。" };

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
        if (cur !== max) { row.current = max; levels[String(lv)] = row; changed = true; }
      }
      target.mp_levels = levels;
    } else if (HEAL_AMOUNT[normalized]) {
      const hp = asNum(target.hp, 0);
      const maxHp = Math.max(1, asNum(target.max_hp, hp));
      if (hp <= 0 || hp >= maxHp) return { ok: false, message: "効果がありません。" };
      target.hp = Math.min(maxHp, hp + HEAL_AMOUNT[normalized]);
      changed = true;
    } else if (STATUS_CLEAR[normalized]) {
      changed = clearStatuses(target, STATUS_CLEAR[normalized]);
    } else {
      return { ok: false, message: "未実装のアイテムです。" };
    }

    if (!changed) return { ok: false, message: "効果がありません。" };
    const nextEnvelope = clone(appState.saveEnvelope || store.createDefaultEnvelope());
    if (!consumeInventory(nextEnvelope, itemName)) return { ok: false, message: "在庫がありません。" };
    party[targetIdx] = target;
    const nextMenuState = { ...rawMenuState, party };
    nextEnvelope.menu_state = nextMenuState;
    if (Array.isArray(nextEnvelope?.save?.party) && nextEnvelope.save.party[targetIdx]) {
      syncSaveEntryFromMember(nextEnvelope.save.party[targetIdx], target);
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
    const selectedRequiresTarget = TARGET_REQUIRED.has(canon(selectedItemName));
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
