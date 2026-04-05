import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";
import {
  INN_PRICE,
  buildRecoveredPartySnapshot,
  clone,
  currentGil,
  getStoredLocationSelection,
  persistMenuStateFromEnvelope,
  prepareExplicitGroups,
  preparePythonBundle,
  readStoredEnvelope,
  syncMenuPartyRecovery,
  syncSavePartyRecovery,
} from "./location_shared.js";
import { makeSaveEnvelope, persistSaveEnvelopeToStorage } from "./shared_storage.js";

const statusLine = document.getElementById("statusLine");
const selectedLocationLine = document.getElementById("selectedLocationLine");
const gilLine = document.getElementById("gilLine");
const stayInnBtn = document.getElementById("stayInnBtn");
const innStatusLine = document.getElementById("innStatusLine");
const backBtn = document.getElementById("backBtn");
const menuBtn = document.getElementById("menuBtn");

let pyodide = null;
let defaultSelection = {
  selected_location_group: "",
  selected_location: "",
};

function renderGilDisplay() {
  if (!gilLine) return;
  gilLine.textContent = `GIL ${currentGil().toLocaleString()}`;
}

function resolvedSelection() {
  const stored = getStoredLocationSelection();
  return {
    selected_location_group: String(stored.selected_location_group || defaultSelection.selected_location_group || ""),
    selected_location: String(stored.selected_location || defaultSelection.selected_location || ""),
  };
}

function renderSelection() {
  if (!selectedLocationLine) return;
  const selection = resolvedSelection();
  if (selection.selected_location_group || selection.selected_location) {
    selectedLocationLine.textContent = `現在のLocation: ${selection.selected_location_group || "-"} / ${selection.selected_location || "-"}`;
    return;
  }
  selectedLocationLine.textContent = "現在のLocationは未選択です。";
}

async function stayAtInn() {
  const gil = currentGil();
  if (gil < INN_PRICE) {
    if (innStatusLine) {
      innStatusLine.textContent = `GIL が足りません。必要: ${INN_PRICE.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
    }
    return;
  }

  const selection = resolvedSelection();
  const originalEnvelope = readStoredEnvelope();
  const nextEnvelope = originalEnvelope ? clone(originalEnvelope) : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
  }

  const recoveredParty = await buildRecoveredPartySnapshot(
    pyodide,
    nextEnvelope.save,
    selection.selected_location_group,
    selection.selected_location,
  );
  if (!recoveredParty.length) {
    if (innStatusLine) {
      innStatusLine.textContent = "宿屋の回復処理に失敗しました。";
    }
    return;
  }

  nextEnvelope.save.gil = Math.max(0, gil - INN_PRICE);
  syncSavePartyRecovery(nextEnvelope.save, recoveredParty);
  if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
    nextEnvelope.menu_state = { party: [], resources: { cp: 0, cp_max: 255, gil: nextEnvelope.save.gil } };
  }
  if (!nextEnvelope.menu_state.resources || typeof nextEnvelope.menu_state.resources !== "object") {
    nextEnvelope.menu_state.resources = {};
  }
  nextEnvelope.menu_state.resources.gil = nextEnvelope.save.gil;
  syncMenuPartyRecovery(nextEnvelope.menu_state, recoveredParty);
  nextEnvelope.saved_at = new Date().toISOString();
  nextEnvelope.selected_location_group = selection.selected_location_group;
  nextEnvelope.selected_location = selection.selected_location;

  if (!persistSaveEnvelopeToStorage(nextEnvelope)) {
    if (innStatusLine) {
      innStatusLine.textContent = "宿泊内容の保存に失敗しました。";
    }
    return;
  }

  persistMenuStateFromEnvelope(nextEnvelope);
  renderGilDisplay();
  if (innStatusLine) {
    innStatusLine.textContent = `宿に泊まりました。HP・MP・状態異常が全快しました。-${INN_PRICE.toLocaleString()} GIL`;
  }
}

async function bootInnScreen() {
  statusLine.textContent = "Inn を起動中...";
  pyodide = await loadPyodide();
  await pyodide.loadPackage("typing-extensions");
  await preparePythonBundle(pyodide);
  await prepareExplicitGroups(pyodide);

  const bootstrapResponse = await fetch("./bootstrap_runtime.py");
  if (!bootstrapResponse.ok) throw new Error(`bootstrap_runtime.py fetch failed: ${bootstrapResponse.status}`);
  const bootstrapPython = await bootstrapResponse.text();
  await pyodide.runPythonAsync(bootstrapPython);

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  defaultSelection = {
    selected_location_group: String(selectionPayload?.selected_group || ""),
    selected_location: String(selectionPayload?.selected_location || ""),
  };

  renderSelection();
  renderGilDisplay();
  if (stayInnBtn) stayInnBtn.disabled = false;
  statusLine.textContent = "宿泊できます。";
}

stayInnBtn?.addEventListener("click", () => {
  stayAtInn().catch((_error) => {
    if (innStatusLine) {
      innStatusLine.textContent = "宿屋処理でエラーが発生しました。";
    }
  });
});
backBtn?.addEventListener("click", () => {
  window.location.href = "./index.html";
});
menuBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

bootInnScreen().catch((error) => {
  statusLine.textContent = `起動失敗: ${String(error)}`;
});
