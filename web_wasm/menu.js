const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";

const partyList = document.getElementById("partyList");
const menuButtons = document.getElementById("menuButtons");
const resourceRow = document.getElementById("resourceRow");
const backBtn = document.getElementById("backBtn");
const MENU_LABELS = ["アイテム", "まほう", "そうび", "ステータス", "ならびかえ", "ジョブ", "セーブ"];

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
    .filter((value, index, arr) => value && arr.indexOf(value) === index);
  if (!keys.length) return [];
  const exts = ["png", "webp", "jpg", "jpeg"];
  const paths = [];
  keys.forEach((key) => {
    exts.forEach((ext) => {
      const safeKey = encodeURIComponent(key);
      paths.push(`/web_wasm/faces/${safeKey}.${ext}`);
      paths.push(`../assets/images/faces/${safeKey}.${ext}`);
      paths.push(`/assets/images/faces/${safeKey}.${ext}`);
    });
  });
  return paths.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

function parseMenuState() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    if (!text) return { party: [], resources: { cp: 0, cp_max: 255, gil: 0 } };
    const parsed = JSON.parse(text);
    return {
      party: Array.isArray(parsed?.party) ? parsed.party : [],
      resources: {
        cp: Number(parsed?.resources?.cp ?? 0),
        cp_max: Number(parsed?.resources?.cp_max ?? 255),
        gil: Number(parsed?.resources?.gil ?? 0),
      },
    };
  } catch (_error) {
    return { party: [], resources: { cp: 0, cp_max: 255, gil: 0 } };
  }
}

function levelMpText(member) {
  const mpLevels = member?.mp_levels && typeof member.mp_levels === "object" ? member.mp_levels : {};
  const chunks = [];
  for (let lv = 1; lv <= 8; lv += 1) {
    const row = mpLevels[String(lv)] || {};
    const cur = Number(row?.current ?? 0);
    chunks.push(`${cur}`);
  }
  return chunks.join("/");
}

function renderParty(party) {
  partyList.innerHTML = "";
  if (!party.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "表示できるパーティ情報がありません。バトル画面を起動後にメニューを開いてください。";
    partyList.appendChild(empty);
    return;
  }

  party.forEach((member) => {
    const card = document.createElement("article");
    card.className = "member-card";

    const fallback = document.createElement("div");
    fallback.className = "portrait-fallback";
    fallback.textContent = "NO PORTRAIT";

    const imageCandidates = resolveFaceImageCandidates(member);
    if (imageCandidates.length) {
      const img = document.createElement("img");
      img.className = "portrait";
      img.alt = "";
      let imageIndex = 0;
      img.addEventListener("load", () => {
        fallback.remove();
      });
      img.addEventListener("error", () => {
        imageIndex += 1;
        if (imageIndex < imageCandidates.length) {
          img.src = imageCandidates[imageIndex];
          return;
        }
        img.remove();
        if (!card.contains(fallback)) {
          card.insertBefore(fallback, card.firstChild);
        }
      });
      img.src = imageCandidates[imageIndex];
      card.appendChild(img);
    } else {
      card.appendChild(fallback);
    }

    const main = document.createElement("div");
    main.className = "member-main";
    main.innerHTML = `
      <div class="line-strong">${String(member?.name || "Unknown")}</div>
      <div class="muted">Job: ${String(member?.job || "Unknown")} / Lv ${Number(member?.level ?? 0)}</div>
      <div class="muted">row: ${String(member?.row || "front")}</div>
      <div class="hp">HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}</div>
      <div class="mp">MP(1-8): ${levelMpText(member)}</div>
    `;
    card.appendChild(main);
    partyList.appendChild(card);
  });
}

function renderButtons() {
  if (!menuButtons) return;
  menuButtons.innerHTML = "";
  MENU_LABELS.forEach((label) => {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => {
      if (label === "そうび") {
        window.location.href = "./equip.html";
        return;
      }
      if (label === "ステータス") {
        window.location.href = "./status.html";
        return;
      }
      if (label === "ジョブ") {
        window.location.href = "./job.html";
        return;
      }
      window.alert(`${label} は現在準備中です。`);
    });
    menuButtons.appendChild(button);
  });
}

function renderResources(resources) {
  if (!resourceRow) return;
  resourceRow.innerHTML = "";
  const cp = document.createElement("div");
  cp.textContent = `CP ${Number(resources?.cp ?? 0)}/${Number(resources?.cp_max ?? 255)}`;
  const gil = document.createElement("div");
  gil.textContent = `GIL ${Number(resources?.gil ?? 0)}`;
  resourceRow.append(cp, gil);
}

if (backBtn) {
  backBtn.addEventListener("click", () => {
    window.location.href = "./index.html";
  });
}

const state = parseMenuState();
renderParty(state.party);
renderButtons();
renderResources(state.resources);
