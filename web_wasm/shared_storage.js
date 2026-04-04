export const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
export const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";

export function parseSaveEnvelope(raw) {
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

export function restoreSaveEnvelopeFromStorage() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    return parseSaveEnvelope(JSON.parse(text));
  } catch (_error) {
    return null;
  }
}

export function parseMenuStateFromStorage() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    if (!text) return {};
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

export function makeSaveEnvelope(saveObj, options = {}) {
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

export function persistSaveEnvelopeToStorage(envelope) {
  if (!envelope) return false;
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

export function syncRuntimeSaveToStorage({
  pyodide,
  buildEnvelopeOptions,
}) {
  if (!pyodide) return false;
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return false;
  try {
    const saveObj = JSON.parse(saveJson);
    const envelope = makeSaveEnvelope(saveObj, buildEnvelopeOptions(saveObj));
    return persistSaveEnvelopeToStorage(envelope);
  } catch (_error) {
    return false;
  }
}
