import { resolveFaceImageCandidates } from "../shared_party.js";
import { renderMenuSubpageShell } from "./menu_subpage_shell.js";
import { bindMenuSubpageNavigation, syncMenuMemberSelection } from "./screen_shared.js";

function asNum(v, d = 0) { const n = Number(v); return Number.isFinite(n) ? n : d; }
function asNesPercent(v) { return Math.max(0, Math.min(asNum(v, 0), 99)); }

function renderLayout() {
  return renderMenuSubpageShell({
    width: "medium",
    content: `
      <section class="frame"><h1 class="title">ステータス</h1></section>
      <section class="frame">
        <div class="top">
          <div id="portraitWrap"></div>
          <div>
            <div class="name-row">
              <div id="memberName" class="name">-</div>
              <div id="memberLv" class="lv">LV 0</div>
            </div>
            <div id="statusIcons" class="status-icons"></div>
          </div>
        </div>
        <div id="statusRows" class="rows"></div>
      </section>
      <section class="frame footer">
        <button id="leftBtn" class="btn" type="button">◀</button>
        <button id="backBtn" class="btn" type="button">BACK</button>
        <button id="rightBtn" class="btn" type="button">▶</button>
      </section>
      <section class="muted">←/→ でキャラクター切替、Enter/Esc で戻る</section>
    `,
    styles: `
      .title { margin:0; font-size:1.1rem; color:#ffe588; }
      .top { display:grid; grid-template-columns:98px 1fr; gap:10px; }
      .portrait, .portrait-fallback { width:98px; height:98px; border-radius:8px; border:1px solid rgba(255,255,255,0.35); background:rgba(255,255,255,0.08); }
      .portrait { object-fit:cover; object-position:center 20%; }
      .portrait-fallback { display:grid; place-items:center; color:#acb6d7; font-size:0.65rem; }
      .name-row { display:flex; justify-content:space-between; gap:10px; align-items:baseline; }
      .name { font-size:1.5rem; font-weight:700; }
      .lv { font-size:1.1rem; }
      .status-icons { margin-top:6px; min-height:30px; display:flex; gap:6px; flex-wrap:wrap; }
      .status-icon { width:24px; height:24px; }
      .rows { margin-top:8px; display:grid; gap:4px; }
      .row { display:grid; grid-template-columns:140px 24px 1fr; font-size:0.95rem; align-items:baseline; }
      .dot { color:#acb6d7; text-align:center; }
      .footer { display:grid; grid-template-columns:1fr 1.5fr 1fr; gap:8px; }
    `,
  });
}

function resolveStatusIconCandidates(iconKey) {
  const safeKey = encodeURIComponent(String(iconKey || ""));
  if (!safeKey) return [];
  return [
    `/assets/status-icons/${safeKey}.png`,
    `/assets/images/status_icons/${safeKey}.png`,
    `../assets/images/status_icons/${safeKey}.png`,
  ];
}

function rowHtml(label, value) {
  return `<div class="row"><div>${label}</div><div class="dot">..</div><div>${value}</div></div>`;
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();
  const portraitWrap = mountNode.querySelector("#portraitWrap");
  const memberName = mountNode.querySelector("#memberName");
  const memberLv = mountNode.querySelector("#memberLv");
  const statusRows = mountNode.querySelector("#statusRows");
  const statusIcons = mountNode.querySelector("#statusIcons");
  const leftBtn = mountNode.querySelector("#leftBtn");
  const rightBtn = mountNode.querySelector("#rightBtn");
  const backBtn = mountNode.querySelector("#backBtn");

  let index = Number(store.getState().menuMemberIndex ?? 0);

  function renderPortrait(member) {
    portraitWrap.innerHTML = "";
    const fallback = document.createElement("div");
    fallback.className = "portrait-fallback";
    fallback.textContent = "NO PORTRAIT";
    const candidates = resolveFaceImageCandidates(member);
    if (!candidates.length) {
      portraitWrap.appendChild(fallback);
      return;
    }
    const img = document.createElement("img");
    img.className = "portrait";
    img.alt = "";
    let i = 0;
    img.addEventListener("error", () => {
      i += 1;
      if (i < candidates.length) img.src = candidates[i];
      else { img.remove(); portraitWrap.appendChild(fallback); }
    });
    img.src = candidates[i];
    portraitWrap.appendChild(img);
  }

  function renderStatusIcons(st) {
    const iconKeys = Array.isArray(st?.status_icons) ? st.status_icons.filter((v) => typeof v === "string" && v) : [];
    if (!iconKeys.length) {
      statusIcons.textContent = st?.status_line || "-";
      return;
    }
    statusIcons.innerHTML = "";
    iconKeys.forEach((iconKey) => {
      const candidates = resolveStatusIconCandidates(iconKey);
      if (!candidates.length) return;
      const img = document.createElement("img");
      img.className = "status-icon";
      img.alt = iconKey;
      let i = 0;
      img.addEventListener("error", () => {
        i += 1;
        if (i < candidates.length) img.src = candidates[i];
        else img.remove();
      });
      img.src = candidates[i];
      statusIcons.appendChild(img);
    });
    if (!statusIcons.childElementCount) statusIcons.textContent = st?.status_line || "-";
  }

  function render() {
    const selection = syncMenuMemberSelection(store, index);
    const party = selection.party;
    if (!party.length) {
      memberName.textContent = "No party members";
      memberLv.textContent = "LV -";
      statusRows.innerHTML = "";
      statusIcons.textContent = "-";
      portraitWrap.innerHTML = '<div class="portrait-fallback">NO DATA</div>';
      return;
    }
    index = selection.memberIndex;
    const member = selection.member || {};
    const st = member?.status && typeof member.status === "object" ? member.status : {};
    memberName.textContent = String(member?.name || "-");
    memberLv.textContent = `LV ${asNum(st.level ?? member.level)}`;
    renderPortrait(member);
    renderStatusIcons(st);
    const rows = [
      ["HP", `${asNum(st.hp ?? member.hp)} / ${asNum(st.max_hp ?? member.max_hp)}`],
      ["MP", String(st.mp_text || "0/0/0/0/0/0/0/0")],
      ["ジョブ", String(member.job || "-")],
      ["じゅくれんど", asNum(st.job_level)],
      ["けいけんち", asNum(st.exp)],
      ["つぎのレベルまで", asNum(st.exp_to_next)],
      ["ちから", asNum(st.strength)],
      ["すばやさ", asNum(st.agility)],
      ["たいりょく", asNum(st.vitality)],
      ["ちせい", asNum(st.intelligence)],
      ["せいしん", asNum(st.mind)],
      ["こうげき", `${asNum(st.atk_times)}かい ${asNum(st.atk_value)}`],
      ["めいちゅう", `${asNesPercent(st.acc_value)}%`],
      ["ぼうぎょ", `${asNum(st.def_times)}かい ${asNum(st.defense)}`],
      ["かいひりつ", `${asNesPercent(st.evasion_percent)}%`],
      ["まほうぼうぎょ", asNum(st.magic_defense)],
      ["まほうかいひりつ", `${asNesPercent(st.magic_resistance)}%`],
      ["れつ", String(st.row_label || "BACK")],
    ];
    statusRows.innerHTML = rows.map(([k, v]) => rowHtml(k, String(v))).join("");
  }

  const onLeft = () => { index -= 1; render(); };
  const onRight = () => { index += 1; render(); };
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
  return () => {
    unbindButtons();
  };
}
