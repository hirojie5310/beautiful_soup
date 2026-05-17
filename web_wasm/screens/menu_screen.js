import {
  normalizePartyIdentityOrder,
  resolveFaceImageCandidates,
  resolveMemberJob,
} from "../shared_party.js";
import { readCachedImageUrl, resolveCachedImageUrl } from "../image_cache.js";
import {
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
} from "../map_data.js";
import {
  AUTO_SAVE_SLOT_ID,
  getLastUsedSaveSlotId,
  parseSaveEnvelope,
} from "../shared_storage.js";
import { resolveGuestPortraitDescriptor } from "../guest_companion.js";
import { getPyodideRuntime } from "../pyodide_runtime.js";
import { saveRepository } from "../save_repository.js";
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
export function deriveMenuMapOpenRequest(state) {
  const requestedMapId = String(
    state?.menuState?.map_state?.current_map_id
    || state?.saveEnvelope?.save?.map?.map
    || DEFAULT_MAP_ID,
  );
  return {
    requestedMapId,
    resumeToCurrentMap: Boolean(
      state?.menuState?.map_return_pending
      && requestedMapId,
    ),
  };
}

export function hydrateMenuStateFromEnvelope(currentMenuState, envelope) {
  const normalizedCurrentState = normalizeMenuState(currentMenuState);
  const envelopeMenuState = envelope?.menu_state && typeof envelope.menu_state === "object"
    ? normalizeMenuState(envelope.menu_state)
    : {};
  const extractedState = extractMenuStateFromEnvelope(envelope);
  return normalizeMenuState({
    ...envelopeMenuState,
    ...extractedState,
    map_state: (
      normalizedCurrentState?.map_state
      && typeof normalizedCurrentState.map_state === "object"
    )
      ? normalizedCurrentState.map_state
      : envelopeMenuState.map_state,
    map_return_pending: Boolean(
      normalizedCurrentState?.map_return_pending
      ?? envelopeMenuState?.map_return_pending
      ?? false
    ),
  });
}

export function memberJobLevelText(member) {
  const candidates = [
    member?.job_level,
    member?.jobLevel,
    member?.status?.job_level,
    member?.status?.jobLevel,
  ];
  for (const candidate of candidates) {
    if (candidate && typeof candidate === "object") {
      const value = Number(candidate.level ?? candidate.job_level ?? candidate.jobLevel);
      if (Number.isFinite(value) && value > 0) return String(value);
      continue;
    }
    const value = Number(candidate);
    if (Number.isFinite(value) && value > 0) return String(value);
  }
  return "*";
}

export function memberStatusIconKeys(member) {
  const keys = [];
  [member?.status_icons, member?.status?.status_icons].forEach((rows) => {
    if (!Array.isArray(rows)) return;
    rows.forEach((row) => {
      const key = String(row || "").trim().toLowerCase();
      if (key && !keys.includes(key)) keys.push(key);
    });
  });
  return keys;
}

function resolveStatusIconCandidates(iconKey) {
  const safeKey = encodeURIComponent(String(iconKey || "").trim().toLowerCase());
  if (!safeKey) return [];
  return [
    `../assets/images/status_icons/${safeKey}.png`,
    new URL(`../../assets/images/status_icons/${safeKey}.png`, import.meta.url).href,
    `/assets/images/status_icons/${safeKey}.png`,
  ];
}

function applyCachedImageSource(target, candidates, { onLoad, onError } = {}) {
  if (!target) return;
  const cachedUrl = readCachedImageUrl(candidates);
  if (cachedUrl !== null) {
    if (cachedUrl) {
      target.src = cachedUrl;
      if (typeof onLoad === "function") onLoad(cachedUrl);
      return;
    }
    if (typeof onError === "function") onError();
    return;
  }
  resolveCachedImageUrl(candidates, {
    onResolved: (resolvedUrl) => {
      if (resolvedUrl) {
        target.src = resolvedUrl;
        if (typeof onLoad === "function") onLoad(resolvedUrl);
        return;
      }
      if (typeof onError === "function") onError();
    },
  });
}

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

async function rebuildEnvelopeMenuStateFromRuntime(envelope) {
  const pyodide = await getPyodideRuntime();
  const normalizedEnvelope = envelope && typeof envelope === "object" ? envelope : null;
  if (!pyodide || !normalizedEnvelope?.save || typeof normalizedEnvelope.save !== "object") {
    return {
      envelope: normalizedEnvelope,
      menuState: extractMenuStateFromEnvelope(normalizedEnvelope),
    };
  }

  const selectedLocationGroup = String(normalizedEnvelope.selected_location_group || "");
  const selectedLocation = String(normalizedEnvelope.selected_location || "");
  if (!selectedLocationGroup || !selectedLocation) {
    return {
      envelope: normalizedEnvelope,
      menuState: extractMenuStateFromEnvelope(normalizedEnvelope),
    };
  }

  try {
    const bootWithSave = pyodide.globals.get("boot_engine_for_location_with_save_json");
    const getMenuStateJson = pyodide.globals.get("get_menu_state_json");
    const exportRuntimeSaveJson = pyodide.globals.get("export_runtime_save_json");
    if (!bootWithSave || !getMenuStateJson || !exportRuntimeSaveJson) {
      return {
        envelope: normalizedEnvelope,
        menuState: extractMenuStateFromEnvelope(normalizedEnvelope),
      };
    }

    bootWithSave(
      selectedLocationGroup,
      selectedLocation,
      JSON.stringify(normalizedEnvelope.save),
      7,
    );

    const runtimeSave = JSON.parse(String(exportRuntimeSaveJson() || "{}"));
    const runtimeMenuState = normalizeMenuState(
      JSON.parse(String(getMenuStateJson() || "{}")),
    );
    const nextEnvelope = {
      ...normalizedEnvelope,
      save: runtimeSave,
      menu_state: runtimeMenuState,
      saved_at: new Date().toISOString(),
    };
    return { envelope: nextEnvelope, menuState: runtimeMenuState };
  } catch (_error) {
    return {
      envelope: normalizedEnvelope,
      menuState: extractMenuStateFromEnvelope(normalizedEnvelope),
    };
  }
}

function buildEnvelopeForCurrentState(store, state) {
  const currentState = store.getState();
  const currentEnvelope = currentState.saveEnvelope || saveRepository.makeEnvelope({}, {});
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

  const initialEnvelope = store.getState().saveEnvelope;
  if (initialEnvelope?.save) {
    const rebuilt = await rebuildEnvelopeMenuStateFromRuntime(initialEnvelope);
    if (rebuilt.envelope?.save && rebuilt.menuState) {
      const hydratedMenuState = hydrateMenuStateFromEnvelope(state, {
        ...(rebuilt.envelope && typeof rebuilt.envelope === "object" ? rebuilt.envelope : {}),
        menu_state: rebuilt.menuState,
      });
      state = hydratedMenuState;
      store.updateMenuState(hydratedMenuState);
      store.updateSaveEnvelope({
        ...rebuilt.envelope,
        menu_state: hydratedMenuState,
      }, { reason: "session_restored" });
    }
  }

  if (!Array.isArray(state.party) || !state.party.length) {
    const currentEnvelope = store.getState().saveEnvelope;
    if (currentEnvelope?.save) {
      state = hydrateMenuStateFromEnvelope(state, currentEnvelope);
      store.updateMenuState(state);
      store.updateSaveEnvelope({
        ...currentEnvelope,
        menu_state: state,
      }, { reason: "session_restored" });
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
    const persisted = store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" });
    if (persisted) {
      triggerAutoSaveFromEnvelope(nextEnvelope);
    }
    return persisted;
  }

  async function refreshSlotList() {
    const slots = await saveRepository.listSlots();
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
    if (!store.updateSaveEnvelope(nextEnvelope, { reason: "manual_save" })) {
      setSlotStatus("保存失敗: 現在セーブの更新に失敗しました。");
      return false;
    }
    const saveResult = await saveRepository.commit({
      reason: "manual_save",
      envelope: nextEnvelope,
      slotId,
      alreadyMirrored: true,
    });
    const saved = saveResult.persisted;
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
      card.classList.add(`row-${normalizeRow(member?.row)}`);
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
      const imageCandidates = resolveFaceImageCandidates(member, index);
      if (imageCandidates.length) {
        const img = document.createElement("img");
        img.className = "portrait";
        img.alt = "";
        applyCachedImageSource(img, imageCandidates, {
          onLoad: () => fallback.remove(),
          onError: () => {
            img.remove();
            if (!card.contains(fallback)) card.insertBefore(fallback, card.firstChild);
          },
        });
        card.appendChild(img);
      } else {
        card.appendChild(fallback);
      }

      const main = document.createElement("div");
      main.className = "member-main";
      main.innerHTML = `
        <div class="line-strong">${String(member?.name || "Unknown")} / Lv ${Number(member?.level ?? 0)}</div>
        <div class="muted">Job: ${String(member?.job || "Unknown")} / Lv ${memberJobLevelText(member)}</div>
        <div class="hp"><span>HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}</span><span class="menu-status-icons" aria-label="status icons"></span></div>
        <div class="mp">MP(1-8): ${levelMpText(member)}</div>
      `;
      const statusIconRow = main.querySelector(".menu-status-icons");
      memberStatusIconKeys(member).forEach((iconKey) => {
        const candidates = resolveStatusIconCandidates(iconKey);
        if (!candidates.length) return;
        const icon = document.createElement("img");
        icon.className = "menu-status-icon";
        icon.alt = iconKey;
        icon.loading = "lazy";
        icon.decoding = "async";
        applyCachedImageSource(icon, candidates, {
          onError: () => {
            icon.remove();
          },
        });
        statusIconRow.appendChild(icon);
      });
      card.appendChild(main);
      partyList.appendChild(card);
    });
  }

  function renderResources() {
    resourceRow.innerHTML = "";
    const statsPanel = document.createElement("div");
    statsPanel.className = "resource-panel resource-stats";
    const cp = document.createElement("div");
    cp.textContent = `CP ${Number(state.resources?.cp ?? 0)}/${Number(state.resources?.cp_max ?? 255)}`;
    const gil = document.createElement("div");
    gil.textContent = `GIL ${Number(state.resources?.gil ?? 0)}`;
    statsPanel.append(cp, gil);
    resourceRow.append(statsPanel);

    const guestPortrait = resolveGuestPortraitDescriptor(store.getState().saveEnvelope);
    if (!guestPortrait) return;

    const guestPanel = document.createElement("div");
    guestPanel.className = "resource-panel resource-guest";
    const label = document.createElement("div");
    label.className = "resource-guest-label";
    label.textContent = guestPortrait.label;
    const fallback = document.createElement("div");
    fallback.className = "portrait-fallback";
    fallback.textContent = guestPortrait.fallbackText;
    const img = document.createElement("img");
    img.className = "portrait";
    img.alt = guestPortrait.alt;
    applyCachedImageSource(img, [guestPortrait.imageUrl], {
      onLoad: () => fallback.remove(),
      onError: () => {
        img.remove();
        if (!guestPanel.contains(fallback)) guestPanel.appendChild(fallback);
      },
    });
    guestPanel.append(label, img);
    if (!img.getAttribute("src")) {
      guestPanel.appendChild(fallback);
    }
    resourceRow.append(guestPanel);
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
        const envelope = await saveRepository.loadSlot(slotId);
        if (!envelope?.save) {
          setSlotStatus(`${label} の読込に失敗しました。`);
          return;
        }
        highlightedSlotId = slotId;
        exitSaveSlotSelectionMode();
        const rebuilt = await rebuildEnvelopeMenuStateFromRuntime(envelope);
        const loadedMenuState = rebuilt.menuState;
        state = loadedMenuState;
        store.updateMenuState(loadedMenuState);
        store.updateSaveEnvelope(rebuilt.envelope || { ...envelope, menu_state: loadedMenuState }, { reason: "session_restored" });
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
        const removed = await saveRepository.deleteSlot(slotId);
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
            const rebuilt = await rebuildEnvelopeMenuStateFromRuntime(envelope);
            const loadedMenuState = rebuilt.menuState;
            persistMenuState(loadedMenuState);
            store.updateSaveEnvelope(rebuilt.envelope || { ...envelope, menu_state: loadedMenuState }, { reason: "save_imported" });
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
      const { requestedMapId, resumeToCurrentMap } = deriveMenuMapOpenRequest(currentState);
      if (resumeToCurrentMap) {
        navigate("map");
        return;
      }
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
