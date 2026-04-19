import {
  normalizePartyIdentityOrder,
  resolveFaceImageCandidates,
  resolveMemberJob,
} from "../shared_party.js";
import {
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
} from "../map_data.js";
import {
  AUTO_SAVE_SLOT_ID,
  LOCAL_MENU_STORAGE_KEY,
  deleteSaveSlotFromIndexedDB,
  getLastUsedSaveSlotId,
  listSaveSlotsFromIndexedDB,
  loadSaveEnvelopeFromIndexedDB,
  makeSaveEnvelope,
  parseSaveEnvelope,
  persistSaveEnvelopeToIndexedDB,
  restoreSaveEnvelopeFromStorageAsync,
} from "../shared_storage.js";
import { mergeMenuStateIntoSave } from "../menu_save_sync.js";
import { bindButtonHandlers, triggerAutoSaveFromEnvelope } from "./screen_shared.js";

const MENU_LABELS = ["アイテム", "まほう", "そうび", "ステータス", "ならびかえ", "ジョブ", "セーブ", "ロード"];
const MANUAL_SLOT_IDS = ["slot-1", "slot-2", "slot-3"];
const SLOT_DISPLAY_ROWS = [
  { slotId: AUTO_SAVE_SLOT_ID, label: "AUTO SAVE", kind: "auto" },
  ...MANUAL_SLOT_IDS.map((slotId, index) => ({
    slotId,
    label: `Slot ${index + 1}`,
    kind: "manual",
  })),
];
const MENU_ROUTE_BY_LABEL = {
  アイテム: "item",
  まほう: "magic",
  そうび: "equip",
  ステータス: "status",
  ジョブ: "job",
  マップ: "map",
};

function renderLayout() {
  return `
    <div class="screen narrow" data-screen="menu">
      <section class="frame">
        <div class="toolbar">
          <h1 class="title" style="margin:0;">MENU</h1>
          <div style="display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end;">
            <button id="mapBtn" class="btn" type="button">マップ</button>
            <button id="backBtn" class="btn" type="button">Location選択へ戻る</button>
          </div>
        </div>
      </section>

      <section class="frame">
        <h2 class="title">PARTY</h2>
        <div id="partyList" class="party-list"></div>
      </section>

      <section class="frame">
        <div id="menuButtons" class="menu-buttons"></div>
        <input id="menuLoadSaveInput" type="file" accept="application/json,.json" style="display:none;" />
        <div id="modeHint" class="mode-hint" aria-live="polite"></div>
      </section>

      <section class="frame">
        <div id="resourceRow" class="resource-row"></div>
      </section>

      <section class="frame">
        <div class="toolbar">
          <h2 class="title" style="margin:0;">BROWSER SLOTS</h2>
          <div id="slotStatus" class="meta"></div>
        </div>
        <div id="slotList" class="slot-list"></div>
      </section>
    </div>
  `;
}

function normalizeRow(rowValue) {
  return String(rowValue || "").toLowerCase() === "back" ? "back" : "front";
}

function toggleMemberRow(member) {
  return normalizeRow(member?.row) === "front" ? "back" : "front";
}

function levelMpText(member) {
  const mpLevels = member?.mp_levels && typeof member.mp_levels === "object" ? member.mp_levels : {};
  const chunks = [];
  for (let lv = 1; lv <= 8; lv += 1) {
    const row = mpLevels[String(lv)] || {};
    chunks.push(`${Number(row?.current ?? 0)}`);
  }
  return chunks.join("/");
}

function normalizeMenuState(raw) {
  const parsed = raw && typeof raw === "object" ? raw : {};
  const party = Array.isArray(parsed.party) ? parsed.party : [];
  const resources = parsed.resources && typeof parsed.resources === "object" ? parsed.resources : {};
  return {
    ...parsed,
    party: normalizePartyIdentityOrder(party).map((member, index) => ({
      ...member,
      index,
      row: normalizeRow(member?.row),
      job: resolveMemberJob(member, member),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
      level: Number(member?.level ?? 0),
      mp_levels: member?.mp_levels && typeof member.mp_levels === "object" ? member.mp_levels : {},
    })),
    resources: {
      cp: Number(resources.cp ?? 0),
      cp_max: Number(resources.cp_max ?? 255),
      gil: Number(resources.gil ?? 0),
    },
  };
}

function extractMenuStateFromEnvelope(envelope) {
  if (envelope?.menu_state && typeof envelope.menu_state === "object") {
    return normalizeMenuState(envelope.menu_state);
  }
  const saveParty = Array.isArray(envelope?.save?.party) ? envelope.save.party : [];
  return normalizeMenuState({
    party: saveParty.map((entry, index) => ({
      index,
      name: String(entry?.name || "Unknown"),
      portrait_key: entry?.portrait_key ?? entry?.image_name ?? null,
      image_name: entry?.image_name ?? null,
      job: String(entry?.current_job || entry?.job || "Unknown"),
      level: Number(entry?.level ?? 0),
      row: normalizeRow(entry?.row),
      hp: Number(entry?.hp ?? 0),
      max_hp: Number(entry?.max_hp ?? 0),
      mp_levels: entry?.mp_levels && typeof entry.mp_levels === "object" ? entry.mp_levels : {},
      status: {},
      status_icons: [],
      equipment: entry?.equipment && typeof entry.equipment === "object" ? entry.equipment : {},
    })),
    resources: {
      cp: Number(envelope?.save?.CP ?? 0),
      cp_max: 255,
      gil: Number(envelope?.save?.gil ?? 0),
    },
  });
}

function patchSaveWithMenuState(saveObj, menuState) {
  return mergeMenuStateIntoSave(saveObj, menuState);
}

function buildEnvelopeForCurrentState(store, state) {
  const currentState = store.getState();
  const currentEnvelope = currentState.saveEnvelope || makeSaveEnvelope({}, {});
  return {
    ...currentEnvelope,
    save: patchSaveWithMenuState(currentEnvelope.save || {}, state),
    menu_state: state,
    selected_location_group: currentState.selectedLocationGroup,
    selected_location: currentState.selectedLocation,
    saved_at: new Date().toISOString(),
  };
}

function formatSavedAt(value) {
  if (!value) return "未保存";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ja-JP", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function saveEnvelopeToLocalFile(envelope) {
  const payload = JSON.stringify(envelope, null, 2);
  const fileName = `ffiii_savedata_${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
  if (window.showSaveFilePicker) {
    const handle = await window.showSaveFilePicker({
      suggestedName: fileName,
      types: [{ description: "JSON save data", accept: { "application/json": [".json"] } }],
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

async function pickSaveFileText(input) {
  if (window.showOpenFilePicker) {
    const [handle] = await window.showOpenFilePicker({
      multiple: false,
      types: [{ description: "JSON save data", accept: { "application/json": [".json"] } }],
      excludeAcceptAllOption: false,
    });
    if (!handle) return "";
    const file = await handle.getFile();
    return file.text();
  }
  return new Promise((resolve, reject) => {
    const onChange = async (event) => {
      input.removeEventListener("change", onChange);
      const file = event?.target?.files?.[0];
      if (!file) {
        reject(new Error("file not selected"));
        return;
      }
      try {
        resolve(await file.text());
      } catch (error) {
        reject(error);
      }
    };
    input.value = "";
    input.addEventListener("change", onChange, { once: true });
    input.click();
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const partyList = mountNode.querySelector("#partyList");
  const menuButtons = mountNode.querySelector("#menuButtons");
  const resourceRow = mountNode.querySelector("#resourceRow");
  const slotList = mountNode.querySelector("#slotList");
  const slotStatus = mountNode.querySelector("#slotStatus");
  const mapBtn = mountNode.querySelector("#mapBtn");
  const backBtn = mountNode.querySelector("#backBtn");
  const modeHint = mountNode.querySelector("#modeHint");
  const menuLoadSaveInput = mountNode.querySelector("#menuLoadSaveInput");

  let isRowSwapMode = false;
  let state = normalizeMenuState(store.getState().menuState);
  let slotSummariesById = {};
  let highlightedSlotId = getLastUsedSaveSlotId() || MANUAL_SLOT_IDS[0];
  let isSaveSlotSelectionMode = false;
  let pendingLocalFileExport = false;

  if (!Array.isArray(state.party) || !state.party.length) {
    const stored = await restoreSaveEnvelopeFromStorageAsync();
    if (stored?.save) {
      state = extractMenuStateFromEnvelope(stored);
      store.updateMenuState(state);
      store.updateSaveEnvelope({
        ...stored,
        menu_state: state,
      });
    }
  }

  function persistMenuState(nextState) {
    state = normalizeMenuState(nextState);
    store.updateMenuState(state);
    const currentEnvelope = store.getState().saveEnvelope;
    if (!currentEnvelope?.save || typeof currentEnvelope.save !== "object") return true;
    const nextEnvelope = {
      ...currentEnvelope,
      save: patchSaveWithMenuState(currentEnvelope.save, state),
      menu_state: state,
      saved_at: new Date().toISOString(),
    };
    const persisted = store.updateSaveEnvelope(nextEnvelope);
    if (persisted) {
      triggerAutoSaveFromEnvelope(nextEnvelope);
    }
    return persisted;
  }

  async function refreshSlotList() {
    const slots = await listSaveSlotsFromIndexedDB();
    slotSummariesById = Object.fromEntries(
      slots.map((row) => [String(row.slot_id || ""), row]),
    );
    renderSlots();
  }

  function setSlotStatus(message) {
    if (!slotStatus) return;
    slotStatus.textContent = String(message || "");
  }

  function exitSaveSlotSelectionMode() {
    isSaveSlotSelectionMode = false;
    pendingLocalFileExport = false;
    highlightedSlotId = getLastUsedSaveSlotId() || highlightedSlotId || MANUAL_SLOT_IDS[0];
    updateModeHint();
  }

  async function saveToSlot(slotId, { exportLocalFile = false } = {}) {
    persistMenuState(state);
    const nextEnvelope = buildEnvelopeForCurrentState(store, state);
    if (!store.updateSaveEnvelope(nextEnvelope)) {
      setSlotStatus("保存失敗: 現在セーブの更新に失敗しました。");
      return false;
    }
    const saved = await persistSaveEnvelopeToIndexedDB(nextEnvelope, {
      slotId,
      kind: "manual",
      rememberSelection: true,
    });
    if (!saved) {
      setSlotStatus(`${slotId} への保存に失敗しました。`);
      return false;
    }
    highlightedSlotId = slotId;
    exitSaveSlotSelectionMode();
    await refreshSlotList();
    setSlotStatus(`${SLOT_DISPLAY_ROWS.find((row) => row.slotId === slotId)?.label || slotId} に保存しました。`);

    if (exportLocalFile) {
      try {
        await saveEnvelopeToLocalFile(nextEnvelope);
        setSlotStatus(`${SLOT_DISPLAY_ROWS.find((row) => row.slotId === slotId)?.label || slotId} に保存し、ローカルファイルにも出力しました。`);
      } catch (_error) {
        setSlotStatus(`${SLOT_DISPLAY_ROWS.find((row) => row.slotId === slotId)?.label || slotId} に保存しました。ローカルファイル保存はキャンセルまたは失敗しました。`);
      }
    }
    return true;
  }

  function enterSaveSlotSelectionMode() {
    isSaveSlotSelectionMode = true;
    pendingLocalFileExport = true;
    highlightedSlotId = (
      MANUAL_SLOT_IDS.includes(getLastUsedSaveSlotId())
        ? getLastUsedSaveSlotId()
        : MANUAL_SLOT_IDS[0]
    );
    updateModeHint();
    renderSlots();
    setSlotStatus("保存先スロットを選択してください。保存後にローカルファイルにも出力します。");
  }

  function updateModeHint() {
    if (isSaveSlotSelectionMode) {
      modeHint.textContent = "保存先選択モード: 保存したい Slot をクリックしてください。もう一度「セーブ」でキャンセルできます。";
      modeHint.classList.add("active");
      return;
    }
    if (isRowSwapMode) {
      modeHint.textContent = "ならびかえモード: キャラクターをクリックで front/back を切り替え";
      modeHint.classList.add("active");
      return;
    }
    modeHint.textContent = "";
    modeHint.classList.remove("active");
  }

  function renderParty() {
    partyList.innerHTML = "";
    if (!state.party.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "表示できるパーティ情報がありません。バトル画面を起動後にメニューを開いてください。";
      partyList.appendChild(empty);
      return;
    }

    state.party.forEach((member, index) => {
      const card = document.createElement("article");
      card.className = "member-card";
      if (isRowSwapMode) {
        card.classList.add("row-mode");
        card.tabIndex = 0;
        const handleToggle = () => {
          const nextParty = state.party.map((entry, entryIndex) => (
            entryIndex === index ? { ...entry, row: toggleMemberRow(entry) } : entry
          ));
          persistMenuState({ ...state, party: nextParty });
          renderParty();
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
        img.addEventListener("load", () => fallback.remove());
        img.addEventListener("error", () => {
          imageIndex += 1;
          if (imageIndex < imageCandidates.length) {
            img.src = imageCandidates[imageIndex];
            return;
          }
          img.remove();
          if (!card.contains(fallback)) card.insertBefore(fallback, card.firstChild);
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

  function renderResources() {
    resourceRow.innerHTML = "";
    const cp = document.createElement("div");
    cp.textContent = `CP ${Number(state.resources?.cp ?? 0)}/${Number(state.resources?.cp_max ?? 255)}`;
    const gil = document.createElement("div");
    gil.textContent = `GIL ${Number(state.resources?.gil ?? 0)}`;
    resourceRow.append(cp, gil);
  }

  function renderSlots() {
    if (!slotList) return;
    slotList.innerHTML = "";

    SLOT_DISPLAY_ROWS.forEach((slotRow) => {
      const { slotId, label, kind } = slotRow;
      const summaryRow = slotSummariesById[slotId];
      const summary = summaryRow?.summary && typeof summaryRow.summary === "object"
        ? summaryRow.summary
        : {};

      const card = document.createElement("article");
      card.className = "slot-card";
      if (kind === "auto") {
        card.classList.add("slot-card-auto");
      }
      if (highlightedSlotId === slotId) {
        card.classList.add("is-selected");
      }
      if (isSaveSlotSelectionMode && kind === "manual") {
        card.classList.add("is-save-target");
        card.tabIndex = 0;
        const handleSelect = async () => {
          highlightedSlotId = slotId;
          renderSlots();
          await saveToSlot(slotId, { exportLocalFile: pendingLocalFileExport });
        };
        card.addEventListener("click", handleSelect);
        card.addEventListener("keydown", (event) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          void handleSelect();
        });
      }

      const title = document.createElement("div");
      title.className = "slot-title";
      title.textContent = label;

      const meta = document.createElement("div");
      meta.className = "slot-meta";
      if (summaryRow) {
        meta.innerHTML = [
          `保存日時: ${formatSavedAt(summaryRow.saved_at)}`,
          `先頭: ${String(summary.lead_name || "-")} Lv ${Number(summary.lead_level || 0)}`,
          `GIL: ${Number(summary.gil || 0)}`,
          `場所: ${String(summary.location_group || summary.location || "-")}`,
        ].join("<br>");
      } else {
        meta.textContent = kind === "auto"
          ? "まだオートセーブはありません。"
          : "このスロットは空です。";
      }

      const actions = document.createElement("div");
      actions.className = "slot-actions";

      if (kind === "manual") {
        const saveBtn = document.createElement("button");
        saveBtn.className = "btn";
        saveBtn.type = "button";
        saveBtn.textContent = isSaveSlotSelectionMode && highlightedSlotId === slotId ? "ここに保存" : "保存";
        saveBtn.addEventListener("click", async (event) => {
          event.stopPropagation();
          highlightedSlotId = slotId;
          renderSlots();
          await saveToSlot(slotId, { exportLocalFile: pendingLocalFileExport });
        });
        actions.append(saveBtn);
      }

      const loadBtn = document.createElement("button");
      loadBtn.className = "btn";
      loadBtn.type = "button";
      loadBtn.textContent = "読込";
      loadBtn.disabled = !summaryRow;
      loadBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        const envelope = await loadSaveEnvelopeFromIndexedDB(slotId);
        if (!envelope?.save) {
          setSlotStatus(`${label} の読込に失敗しました。`);
          return;
        }
        highlightedSlotId = slotId;
        exitSaveSlotSelectionMode();
        const loadedMenuState = extractMenuStateFromEnvelope(envelope);
        state = loadedMenuState;
        store.updateMenuState(loadedMenuState);
        store.updateSaveEnvelope({ ...envelope, menu_state: loadedMenuState });
        renderParty();
        renderResources();
        await refreshSlotList();
        setSlotStatus(`${label} を読み込みました。`);
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.className = "btn";
      deleteBtn.type = "button";
      deleteBtn.textContent = "削除";
      deleteBtn.disabled = !summaryRow || kind === "auto";
      deleteBtn.addEventListener("click", async (event) => {
        event.stopPropagation();
        if (kind === "auto") return;
        const removed = await deleteSaveSlotFromIndexedDB(slotId);
        if (!removed) {
          setSlotStatus(`${label} の削除に失敗しました。`);
          return;
        }
        if (highlightedSlotId === slotId) {
          highlightedSlotId = MANUAL_SLOT_IDS[0];
        }
        await refreshSlotList();
        setSlotStatus(`${label} を削除しました。`);
      });

      actions.append(loadBtn);
      if (kind !== "auto") {
        actions.append(deleteBtn);
      }
      card.append(title, meta, actions);
      slotList.appendChild(card);
    });
  }

  function renderButtons() {
    menuButtons.innerHTML = "";
    MENU_LABELS.forEach((label) => {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.textContent = label;
      button.addEventListener("click", async () => {
        if (label === "ならびかえ") {
          isRowSwapMode = !isRowSwapMode;
          updateModeHint();
          renderParty();
          return;
        }
        isRowSwapMode = false;
        updateModeHint();
        renderParty();

        if (label === "セーブ") {
          if (isSaveSlotSelectionMode) {
            exitSaveSlotSelectionMode();
            renderSlots();
            setSlotStatus("保存先選択をキャンセルしました。");
            return;
          }
          enterSaveSlotSelectionMode();
          return;
        }

        if (label === "ロード") {
          try {
            const text = await pickSaveFileText(menuLoadSaveInput);
            const envelope = parseSaveEnvelope(JSON.parse(text));
            if (!envelope?.save) {
              window.alert("ロード失敗: セーブデータ形式が不正です。");
              return;
            }
            const loadedMenuState = extractMenuStateFromEnvelope(envelope);
            persistMenuState(loadedMenuState);
            store.updateSaveEnvelope({ ...envelope, menu_state: loadedMenuState });
            renderParty();
            renderResources();
            window.alert("ロード完了: セーブデータを復元しました。");
          } catch (_error) {
            window.alert("ロード失敗: ファイル選択がキャンセルされたか、読み込みに失敗しました。");
          }
          return;
        }

        const routeName = MENU_ROUTE_BY_LABEL[label];
        if (routeName) navigate(routeName);
      });
      menuButtons.appendChild(button);
    });
  }

  const handleMapOpen = async () => {
    try {
      const currentState = store.getState();
      const requestedMapId = String(
        currentState.menuState?.map_state?.current_map_id
        || currentState.saveEnvelope?.save?.map?.map
        || DEFAULT_MAP_ID,
      );
      const mapDefinition = await loadMapDefinition(requestedMapId);
      const selection = {
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
      };
      if (!isMapSelectionCompatible(mapDefinition, selection)) {
        setSlotStatus("現在のLocationでは対応するマップへ移動できません。");
        return;
      }
      navigate("map");
    } catch (error) {
      setSlotStatus(`マップ確認失敗: ${String(error)}`);
    }
  };
  const handleBack = () => navigate("location");
  const unbindButtons = bindButtonHandlers([
    { target: mapBtn, handler: handleMapOpen },
    { target: backBtn, handler: handleBack },
  ]);

  updateModeHint();
  renderParty();
  renderButtons();
  renderResources();
  await refreshSlotList();

  return () => {
    unbindButtons();
  };
}
