import { saveRepository } from "./save_repository.js";

export const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
export const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";

export function readBattleStartSelectionFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_START_SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return {
        selected_location_group: String(parsed.selected_location_group || ""),
        selected_location: String(parsed.selected_location || ""),
        enemy_names: Array.isArray(parsed.enemy_names)
          ? parsed.enemy_names.map((name) => String(name || "")).filter((name) => Boolean(name))
          : [],
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}

export function readBattleReturnContextFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_RETURN_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

export function writeBattleReturnContextToSession(nextContext) {
  try {
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify(nextContext || {}));
    return nextContext && typeof nextContext === "object" ? nextContext : null;
  } catch (_error) {
    return null;
  }
}

export function compactSaveEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object") return null;
  if (!envelope.save || typeof envelope.save !== "object") return null;
  return {
    version: 1,
    saved_at: String(envelope.saved_at || ""),
    selected_location_group: String(envelope.selected_location_group || ""),
    selected_location: String(envelope.selected_location || ""),
    save: envelope.save,
    menu_state: null,
  };
}

export function downloadSaveEnvelope(envelope) {
  const exportEnvelope = compactSaveEnvelope(envelope);
  if (!exportEnvelope) return false;
  const payload = JSON.stringify(exportEnvelope, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  anchor.href = url;
  anchor.download = `ffiii_savedata_${stamp}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

export function buildRuntimeSaveEnvelope({
  saveObj,
  currentBattleSelection,
  storedEnvelope = null,
  menuState,
  selectedLocationGroup = "",
  selectedLocation = "",
}) {
  return saveRepository.makeEnvelope(saveObj, {
    selectedLocationGroup: selectedLocationGroup
      || currentBattleSelection?.selected_location_group
      || storedEnvelope?.selected_location_group
      || "",
    selectedLocation: selectedLocation
      || currentBattleSelection?.selected_location
      || storedEnvelope?.selected_location
      || "",
    menuState,
  });
}

export function syncRuntimeSaveToBrowser({
  pyodide,
  appStore = null,
  cachedStoredEnvelope = null,
  currentBattleSelection,
  menuState,
}) {
  if (!pyodide) return { persisted: false, envelope: null };
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return { persisted: false, envelope: null };
  try {
    const saveObj = JSON.parse(saveJson);
    const storedEnvelope = appStore?.getState()?.saveEnvelope || cachedStoredEnvelope || saveRepository.loadLocalMirror();
    const envelope = buildRuntimeSaveEnvelope({
      saveObj,
      currentBattleSelection,
      storedEnvelope,
      menuState,
    });
    const persisted = appStore
      ? appStore.updateSaveEnvelope(envelope)
      : saveRepository.saveLocalMirror(envelope);
    return { persisted, envelope };
  } catch (_error) {
    return { persisted: false, envelope: null };
  }
}

export async function persistFinishedBattleSave({
  pyodide,
  appStore = null,
  result,
  menuState,
}) {
  if (!pyodide) return { persisted: false, autosaved: false, envelope: null };
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return { persisted: false, autosaved: false, envelope: null };
  try {
    const saveObj = JSON.parse(saveJson);
    const envelope = saveRepository.makeEnvelope(saveObj, {
      selectedLocationGroup: result?.selected_location_group,
      selectedLocation: result?.selected_location,
      menuState,
    });
    const persisted = appStore
      ? appStore.updateSaveEnvelope(envelope)
      : saveRepository.saveLocalMirror(envelope);
    const autosaved = await saveRepository.saveAuto(envelope);
    return { persisted, autosaved, envelope };
  } catch (_error) {
    return { persisted: false, autosaved: false, envelope: null };
  }
}
