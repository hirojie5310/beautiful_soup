const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";

const portraitWrap = document.getElementById("portraitWrap");
const memberName = document.getElementById("memberName");
const memberLv = document.getElementById("memberLv");
const statusRows = document.getElementById("statusRows");
const statusIcons = document.getElementById("statusIcons");
const leftBtn = document.getElementById("leftBtn");
const rightBtn = document.getElementById("rightBtn");
const backBtn = document.getElementById("backBtn");

let index = 0;

function normalizeFaceKey(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/^ch_/, "")
    .replace(/\.(png|jpg|jpeg|webp)$/i, "")
    .replace(/\s+/g, "_")
    .replace(/-/g, "_");
}

function resolveFaceImageCandidates(member) {
  const portraitKey = normalizeFaceKey(member?.portrait_key);
  const nameKey = normalizeFaceKey(member?.name);
  const aliasMap = { luneth: "runeth" };
  const keys = [portraitKey, nameKey]
    .map((key) => aliasMap[key] || key)
    .filter((value, i, arr) => value && arr.indexOf(value) === i);
  const exts = ["png", "webp", "jpg", "jpeg"];
  return keys.flatMap((key) => {
    const safeKey = encodeURIComponent(key);
    return exts.flatMap((ext) => [
      `/web_wasm/faces/${safeKey}.${ext}`,
      `../assets/images/faces/${safeKey}.${ext}`,
      `/assets/images/faces/${safeKey}.${ext}`,
    ]);
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

function parseState() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    const parsed = text ? JSON.parse(text) : {};
    return Array.isArray(parsed?.party) ? parsed.party : [];
  } catch (_error) {
    return [];
  }
}

function rowHtml(label, value) {
  return `<div class="row"><div>${label}</div><div class="dot">..</div><div>${value}</div></div>`;
}

function asNum(v, d = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : d;
}

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
    if (i < candidates.length) {
      img.src = candidates[i];
      return;
    }
    img.remove();
    portraitWrap.appendChild(fallback);
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
      if (i < candidates.length) {
        img.src = candidates[i];
        return;
      }
      img.remove();
    });
    img.src = candidates[i];
    statusIcons.appendChild(img);
  });
  if (!statusIcons.childElementCount) {
    statusIcons.textContent = st?.status_line || "-";
  }
}

function render() {
  const party = parseState();
  if (!party.length) {
    memberName.textContent = "No party members";
    memberLv.textContent = "LV -";
    statusRows.innerHTML = "";
    statusIcons.textContent = "-";
    portraitWrap.innerHTML = '<div class="portrait-fallback">NO DATA</div>';
    return;
  }

  index = ((index % party.length) + party.length) % party.length;
  const member = party[index] || {};
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
    ["めいちゅう", `${asNum(st.acc_value)}%`],
    ["ぼうぎょ", `${asNum(st.def_times)}かい ${asNum(st.defense)}`],
    ["かいひりつ", `${asNum(st.evasion_percent)}%`],
    ["まほうぼうぎょ", asNum(st.magic_defense)],
    ["まほうかいひりつ", `${asNum(st.magic_resistance)}%`],
    ["れつ", String(st.row_label || "BACK")],
  ];
  statusRows.innerHTML = rows.map(([k, v]) => rowHtml(k, String(v))).join("");
}

function goBack() {
  window.location.href = "./menu.html";
}

leftBtn?.addEventListener("click", () => {
  index -= 1;
  render();
});
rightBtn?.addEventListener("click", () => {
  index += 1;
  render();
});
backBtn?.addEventListener("click", goBack);

window.addEventListener("keydown", (event) => {
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    index -= 1;
    render();
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    index += 1;
    render();
  } else if (event.key === "Escape" || event.key === "Enter" || event.key === "Backspace") {
    event.preventDefault();
    goBack();
  }
});

render();
