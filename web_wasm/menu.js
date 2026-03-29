const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

const partyList = document.getElementById("partyList");
const menuButtons = document.getElementById("menuButtons");
const resourceRow = document.getElementById("resourceRow");
const backBtn = document.getElementById("backBtn");
const modeHint = document.getElementById("modeHint");
const menuLoadSaveInput = document.getElementById("menuLoadSaveInput");
const MENU_LABELS = ["アイテム", "まほう", "そうび", "ステータス", "ならびかえ", "ジョブ", "セーブ", "ロード"];
let isRowSwapMode = false;

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
      ...parsed,
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

function persistMenuState(nextState) {
  localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(nextState));
}

function parseSaveEnvelope(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw?.version === 1 && raw?.save && typeof raw.save === "object") {
    return {
      version: 1,
      saved_at: String(raw.saved_at || ""),
      selected_location_group: String(raw.selected_location_group || ""),
      selected_location: String(raw.selected_location || ""),
      save: raw.save,
      menu_state: raw?.menu_state && typeof raw.menu_state === "object"
        ? raw.menu_state
        : null,
    };
  }
  if (raw?.party && Array.isArray(raw.party)) {
    return {
      version: 1,
      saved_at: "",
      selected_location_group: "",
      selected_location: "",
      save: raw,
      menu_state: null,
    };
  }
  return null;
}

function restoreSaveEnvelopeFromStorage() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    return parseSaveEnvelope(JSON.parse(text));
  } catch (_error) {
    return null;
  }
}

function makeSaveEnvelope(saveObj, options = {}) {
  return {
    version: 1,
    saved_at: new Date().toISOString(),
    selected_location_group: String(options?.selectedLocationGroup || ""),
    selected_location: String(options?.selectedLocation || ""),
    save: saveObj,
    menu_state: options?.menuState && typeof options.menuState === "object"
      ? options.menuState
      : null,
  };
}

function patchSaveWithMenuState(saveObj, menuState) {
  const nextSave = saveObj && typeof saveObj === "object" ? { ...saveObj } : {};
  const sourceParty = Array.isArray(nextSave?.party) ? nextSave.party : [];
  const menuParty = Array.isArray(menuState?.party) ? menuState.party : [];
  const mergedParty = sourceParty.map((entry, index) => {
    const menuMember = menuParty[index];
    if (!menuMember || typeof menuMember !== "object") return entry;
    return {
      ...entry,
      row: normalizeRow(menuMember?.row),
      hp: Number(menuMember?.hp ?? entry?.hp ?? 0),
      max_hp: Number(menuMember?.max_hp ?? entry?.max_hp ?? 0),
    };
  });
  if (mergedParty.length) {
    nextSave.party = mergedParty;
  }
  if (!nextSave.party && menuParty.length) {
    nextSave.party = menuParty.map((member) => ({
      name: String(member?.name || ""),
      job: String(member?.job || ""),
      level: Number(member?.level ?? 0),
      row: normalizeRow(member?.row),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
      mp_levels: member?.mp_levels && typeof member.mp_levels === "object"
        ? member.mp_levels
        : {},
    }));
  }
  if (menuState?.resources && typeof menuState.resources === "object") {
    nextSave.CP = Number(menuState.resources?.cp ?? nextSave?.CP ?? 0);
    nextSave.gil = Number(menuState.resources?.gil ?? nextSave?.gil ?? 0);
  }
  return nextSave;
}

function persistSaveEnvelopeToStorage(envelope) {
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

function normalizeMenuState(raw) {
  const parsed = raw && typeof raw === "object" ? raw : {};
  const party = Array.isArray(raw?.party) ? raw.party : [];
  const resources = raw?.resources && typeof raw.resources === "object" ? raw.resources : {};
  return {
    ...parsed,
    party: party.map((member) => ({
      ...member,
      name: String(member?.name || "Unknown"),
      portrait_key: member?.portrait_key ?? null,
      image_name: member?.image_name ?? null,
      job: String(member?.job || "Unknown"),
      level: Number(member?.level ?? 0),
      row: normalizeRow(member?.row),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
      mp_levels: member?.mp_levels && typeof member.mp_levels === "object"
        ? member.mp_levels
        : {},
      status: member?.status && typeof member.status === "object"
        ? member.status
        : {},
      status_icons: Array.isArray(member?.status_icons) ? member.status_icons : [],
      equipment: member?.equipment && typeof member.equipment === "object"
        ? member.equipment
        : {},
    })),
    resources: {
      cp: Number(resources?.cp ?? 0),
      cp_max: Number(resources?.cp_max ?? 255),
      gil: Number(resources?.gil ?? 0),
    },
  };
}

function extractMenuStateFromEnvelope(envelope) {
  if (envelope?.menu_state && typeof envelope.menu_state === "object") {
    return normalizeMenuState(envelope.menu_state);
  }
  const saveParty = Array.isArray(envelope?.save?.party) ? envelope.save.party : [];
  const fallbackParty = saveParty.map((entry) => ({
    name: String(entry?.name || "Unknown"),
    portrait_key: entry?.portrait_key ?? entry?.image_name ?? null,
    image_name: entry?.image_name ?? null,
    job: String(entry?.current_job || entry?.job || "Unknown"),
    level: Number(entry?.level ?? 0),
    row: normalizeRow(entry?.row),
    hp: Number(entry?.hp ?? 0),
    max_hp: Number(entry?.max_hp ?? 0),
    mp_levels: entry?.mp_levels && typeof entry.mp_levels === "object"
      ? entry.mp_levels
      : {},
    status: {},
    status_icons: [],
    equipment: entry?.equipment && typeof entry.equipment === "object"
      ? entry.equipment
      : {},
  }));
  return normalizeMenuState({
    party: fallbackParty,
    resources: {
      cp: Number(envelope?.save?.CP ?? 0),
      cp_max: 255,
      gil: Number(envelope?.save?.gil ?? 0),
    },
  });
}

async function saveEnvelopeToLocalFile(envelope) {
  const payload = JSON.stringify(envelope, null, 2);
  const fileName = `ffiii_savedata_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  if (window.showSaveFilePicker) {
    const handle = await window.showSaveFilePicker({
      suggestedName: fileName,
      types: [
        {
          description: "JSON save data",
          accept: { "application/json": [".json"] },
        },
      ],
    });
    const writable = await handle.createWritable();
    await writable.write(payload);
    await writable.close();
    return true;
  }
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

async function pickSaveFileText() {
  if (window.showOpenFilePicker) {
    const [handle] = await window.showOpenFilePicker({
      multiple: false,
      types: [
        {
          description: "JSON save data",
          accept: { "application/json": [".json"] },
        },
      ],
      excludeAcceptAllOption: false,
    });
    if (!handle) return "";
    const file = await handle.getFile();
    return file.text();
  }
  return new Promise((resolve, reject) => {
    if (!menuLoadSaveInput) {
      reject(new Error("file input not found"));
      return;
    }
    const onChange = async (event) => {
      menuLoadSaveInput.removeEventListener("change", onChange);
      const file = event?.target?.files?.[0];
      if (!file) {
        reject(new Error("file not selected"));
        return;
      }
      try {
        const text = await file.text();
        resolve(text);
      } catch (error) {
        reject(error);
      }
    };
    menuLoadSaveInput.value = "";
    menuLoadSaveInput.addEventListener("change", onChange, { once: true });
    menuLoadSaveInput.click();
  });
}

function normalizeRow(rowValue) {
  return String(rowValue || "").toLowerCase() === "back" ? "back" : "front";
}

function toggleMemberRow(member) {
  const current = normalizeRow(member?.row);
  return current === "front" ? "back" : "front";
}

function updateModeHint() {
  if (!modeHint) return;
  if (isRowSwapMode) {
    modeHint.textContent = "ならびかえモード: キャラクターをクリックで front/back を切り替え";
    modeHint.classList.add("active");
    return;
  }
  modeHint.textContent = "";
  modeHint.classList.remove("active");
}

function disableRowSwapMode() {
  isRowSwapMode = false;
  updateModeHint();
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

  party.forEach((member, index) => {
    const card = document.createElement("article");
    card.className = "member-card";
    if (isRowSwapMode) {
      card.classList.add("row-mode");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.setAttribute("aria-label", `${String(member?.name || "Unknown")}のrowを切り替え`);
      const handleToggle = () => {
        const nextParty = state.party.map((entry, entryIndex) => {
          if (entryIndex !== index) return entry;
          return { ...entry, row: toggleMemberRow(entry) };
        });
        state.party = nextParty;
        persistMenuState(state);
        renderParty(state.party);
      };
      card.addEventListener("click", handleToggle);
      card.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        handleToggle();
      });
    }

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
      if (label === "ならびかえ") {
        isRowSwapMode = !isRowSwapMode;
        updateModeHint();
        renderParty(state.party);
        return;
      }
      disableRowSwapMode();
      renderParty(state.party);
      if (label === "アイテム") {
        window.location.href = "./item.html";
        return;
      }
      if (label === "そうび") {
        window.location.href = "./equip.html";
        return;
      }
      if (label === "まほう") {
        window.location.href = "./magic.html";
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
      if (label === "セーブ") {
        persistMenuState(state);
        const stored = restoreSaveEnvelopeFromStorage();
        const currentSave = stored?.save && typeof stored.save === "object" ? stored.save : {};
        const nextSave = patchSaveWithMenuState(currentSave, state);
        const nextEnvelope = makeSaveEnvelope(nextSave, {
          selectedLocationGroup: stored?.selected_location_group || "",
          selectedLocation: stored?.selected_location || "",
          menuState: state,
        });
        if (!persistSaveEnvelopeToStorage(nextEnvelope)) {
          window.alert("セーブ失敗: ブラウザ保存に失敗しました。");
          return;
        }
        saveEnvelopeToLocalFile(nextEnvelope)
          .then(() => {
            window.alert("セーブ完了: ブラウザとローカルファイルに保存しました。");
          })
          .catch((_error) => {
            window.alert("ブラウザ保存は完了しました。ローカルファイル保存はキャンセルまたは失敗しました。");
          });
        return;
      }
      if (label === "ロード") {
        pickSaveFileText()
          .then((text) => {
            const envelope = parseSaveEnvelope(JSON.parse(text));
            if (!envelope?.save) {
              window.alert("ロード失敗: セーブデータ形式が不正です。");
              return;
            }
            const loadedMenuState = extractMenuStateFromEnvelope(envelope);
            state.party = loadedMenuState.party;
            state.resources = loadedMenuState.resources;
            persistMenuState(state);
            persistSaveEnvelopeToStorage({
              ...envelope,
              menu_state: state,
            });
            renderParty(state.party);
            renderResources(state.resources);
            window.alert("ロード完了: セーブデータを復元しました。");
          })
          .catch((_error) => {
            window.alert("ロード失敗: ファイル選択がキャンセルされたか、読み込みに失敗しました。");
          });
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
updateModeHint();
renderParty(state.party);
renderButtons();
renderResources(state.resources);
