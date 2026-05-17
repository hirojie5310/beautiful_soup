export const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
export const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";
export const LOCAL_LAST_USED_SAVE_SLOT_KEY = "ff3_wasm_last_used_save_slot_v1";
export const SAVE_DB_NAME = "ff3_wasm_save_db";
export const SAVE_DB_VERSION = 1;
export const SAVE_STORE_NAME = "save_slots";
export const DEFAULT_SAVE_SLOT_ID = "default";
export const AUTO_SAVE_SLOT_ID = "auto-1";
const indexedDbWriteQueue = new Map();

function asNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function migrateLegacyGilInventory(save, menuState) {
  if (!save || typeof save !== "object") {
    return { save, menuState };
  }
  const inventory = save.inventory;
  if (!inventory || typeof inventory !== "object") {
    return { save, menuState };
  }
  let migratedGil = 0;
  const nextInventory = cloneValue(inventory);
  Object.entries(nextInventory).forEach(([bucketName, bucketValue]) => {
    if (!bucketValue || typeof bucketValue !== "object" || bucketName === "Magic") return;
    const gilQuantity = asNumber(bucketValue.GIL, 0);
    if (gilQuantity > 0) {
      migratedGil += gilQuantity;
      delete bucketValue.GIL;
    }
    if (!Object.keys(bucketValue).length) {
      delete nextInventory[bucketName];
    }
  });
  if (migratedGil <= 0) {
    return { save, menuState };
  }
  const nextSave = {
    ...cloneValue(save),
    gil: Math.max(0, asNumber(save.gil, 0)) + migratedGil,
    inventory: nextInventory,
  };
  let nextMenuState = menuState && typeof menuState === "object"
    ? cloneValue(menuState)
    : null;
  if (!nextMenuState || typeof nextMenuState !== "object") {
    nextMenuState = {};
  }
  if (!nextMenuState.resources || typeof nextMenuState.resources !== "object") {
    nextMenuState.resources = {};
  }
  nextMenuState.resources.gil = Math.max(
    0,
    asNumber(nextMenuState.resources.gil, asNumber(save.gil, 0)),
  ) + migratedGil;
  return {
    save: nextSave,
    menuState: nextMenuState,
  };
}

function resolveCatalogItemTypes(menuState) {
  const inventoryCatalog = menuState?.inventory_catalog;
  const itemTypes = inventoryCatalog?.item_types && typeof inventoryCatalog.item_types === "object"
    ? { ...inventoryCatalog.item_types }
    : {};
  const itemMeta = inventoryCatalog?.item_meta && typeof inventoryCatalog.item_meta === "object"
    ? inventoryCatalog.item_meta
    : {};
  Object.entries(itemMeta).forEach(([name, meta]) => {
    const itemType = String(meta?.item_type || "");
    if (!itemType || itemTypes[name]) return;
    itemTypes[name] = itemType;
  });
  return itemTypes;
}

function migrateLegacyInventoryBuckets(save, menuState) {
  if (!save || typeof save !== "object") {
    return { save, menuState };
  }
  const inventory = save.inventory;
  if (!inventory || typeof inventory !== "object") {
    return { save, menuState };
  }
  const itemTypes = resolveCatalogItemTypes(menuState);
  if (!Object.keys(itemTypes).length) {
    return { save, menuState };
  }
  const nextInventory = cloneValue(inventory);
  let changed = false;
  Object.entries(nextInventory).forEach(([bucketName, bucketValue]) => {
    if (!bucketValue || typeof bucketValue !== "object" || bucketName === "Magic") return;
    Object.entries(bucketValue).forEach(([itemName, rawCount]) => {
      const targetBucket = String(itemTypes[itemName] || "");
      const count = asNumber(rawCount, 0);
      if (!targetBucket || targetBucket === bucketName || count <= 0) return;
      if (!nextInventory[targetBucket] || typeof nextInventory[targetBucket] !== "object") {
        nextInventory[targetBucket] = {};
      }
      nextInventory[targetBucket][itemName] = asNumber(nextInventory[targetBucket][itemName], 0) + count;
      delete bucketValue[itemName];
      changed = true;
    });
    if (!Object.keys(bucketValue).length) {
      delete nextInventory[bucketName];
    }
  });
  if (!changed) {
    return { save, menuState };
  }
  return {
    save: {
      ...cloneValue(save),
      inventory: nextInventory,
    },
    menuState,
  };
}

function hasIndexedDb() {
  return typeof indexedDB !== "undefined" && indexedDB !== null;
}

function openSaveDb() {
  if (!hasIndexedDb()) {
    return Promise.resolve(null);
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(SAVE_DB_NAME, SAVE_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(SAVE_STORE_NAME)) {
        const store = db.createObjectStore(SAVE_STORE_NAME, { keyPath: "slot_id" });
        store.createIndex("saved_at", "saved_at", { unique: false });
        store.createIndex("kind", "kind", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("indexedDB open failed"));
  });
}

function runStoreRequest(mode, runner) {
  return openSaveDb().then((db) => new Promise((resolve, reject) => {
    if (!db) {
      resolve(null);
      return;
    }
    const tx = db.transaction(SAVE_STORE_NAME, mode);
    const store = tx.objectStore(SAVE_STORE_NAME);
    let request;
    try {
      request = runner(store);
    } catch (error) {
      reject(error);
      return;
    }
    tx.oncomplete = () => {
      resolve(request?.result ?? null);
      if (typeof db.close === "function") {
        db.close();
      }
    };
    tx.onerror = () => {
      reject(tx.error || request?.error || new Error("indexedDB transaction failed"));
      if (typeof db.close === "function") {
        db.close();
      }
    };
    tx.onabort = () => {
      reject(tx.error || new Error("indexedDB transaction aborted"));
      if (typeof db.close === "function") {
        db.close();
      }
    };
  }));
}

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function persistEnvelopeToLocalMirror(envelope) {
  if (!envelope) return false;
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

export function getLastUsedSaveSlotId() {
  try {
    return String(localStorage.getItem(LOCAL_LAST_USED_SAVE_SLOT_KEY) || "");
  } catch (_error) {
    return "";
  }
}

export function setLastUsedSaveSlotId(slotId) {
  try {
    if (!slotId) {
      localStorage.removeItem(LOCAL_LAST_USED_SAVE_SLOT_KEY);
      return true;
    }
    localStorage.setItem(LOCAL_LAST_USED_SAVE_SLOT_KEY, String(slotId));
    return true;
  } catch (_error) {
    return false;
  }
}

function buildSlotRecord(slotId, envelope, options = {}) {
  const parsed = parseSaveEnvelope(envelope);
  if (!parsed) return null;
  const save = parsed.save && typeof parsed.save === "object" ? parsed.save : {};
  const party = Array.isArray(save.party) ? save.party : [];
  return {
    slot_id: String(slotId || DEFAULT_SAVE_SLOT_ID),
    kind: String(options?.kind || "manual"),
    saved_at: String(parsed.saved_at || new Date().toISOString()),
    summary: {
      party_count: party.length,
      lead_name: String(party[0]?.name || ""),
      lead_level: Number(party[0]?.level || 0),
      gil: Number(save.gil || 0),
      location_group: String(parsed.selected_location_group || ""),
      location: String(parsed.selected_location || ""),
    },
    envelope: cloneValue(parsed),
  };
}

function enqueueIndexedDbSave(slotId, record, rememberSelection) {
  const key = String(slotId || DEFAULT_SAVE_SLOT_ID);
  return new Promise((resolve) => {
    const current = indexedDbWriteQueue.get(key);
    if (current?.pending) {
      current.pending.record = record;
      current.pending.rememberSelection = current.pending.rememberSelection || Boolean(rememberSelection);
      current.pending.resolvers.push(resolve);
      return;
    }
    const state = current || {
      inFlight: false,
      pending: null,
    };
    state.pending = {
      record,
      rememberSelection: Boolean(rememberSelection),
      resolvers: [resolve],
    };
    indexedDbWriteQueue.set(key, state);
    if (!state.inFlight) {
      void flushIndexedDbSaveQueue(key);
    }
  });
}

async function flushIndexedDbSaveQueue(slotId) {
  const key = String(slotId || DEFAULT_SAVE_SLOT_ID);
  const state = indexedDbWriteQueue.get(key);
  if (!state || state.inFlight || !state.pending) return;
  state.inFlight = true;
  const pending = state.pending;
  state.pending = null;
  let stored = null;
  let succeeded = false;
  try {
    stored = await runStoreRequest("readwrite", (store) => store.put(pending.record));
    if (stored !== null && pending.rememberSelection) {
      setLastUsedSaveSlotId(key);
    }
    succeeded = stored !== null || !hasIndexedDb();
  } catch (_error) {
    succeeded = false;
  } finally {
    pending.resolvers.forEach((resolver) => resolver(succeeded));
    state.inFlight = false;
    if (state.pending) {
      void flushIndexedDbSaveQueue(key);
    } else {
      indexedDbWriteQueue.delete(key);
    }
  }
}

export function parseSaveEnvelope(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw?.version === 1 && raw?.save && typeof raw.save === "object") {
    const gilMigrated = migrateLegacyGilInventory(
      raw.save,
      raw?.menu_state && typeof raw.menu_state === "object"
        ? raw.menu_state
        : null,
    );
    const migrated = migrateLegacyInventoryBuckets(gilMigrated.save, gilMigrated.menuState);
    return {
      version: 1,
      saved_at: String(raw.saved_at || ""),
      selected_location_group: String(raw.selected_location_group || ""),
      selected_location: String(raw.selected_location || ""),
      save: migrated.save,
      menu_state: migrated.menuState,
    };
  }
  if (raw?.party && Array.isArray(raw.party)) {
    const gilMigrated = migrateLegacyGilInventory(raw, null);
    const migrated = migrateLegacyInventoryBuckets(gilMigrated.save, gilMigrated.menuState);
    return {
      version: 1,
      saved_at: "",
      selected_location_group: "",
      selected_location: "",
      save: migrated.save,
      menu_state: migrated.menuState,
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

export function clearSaveEnvelopeFromStorage() {
  try {
    localStorage.removeItem(LOCAL_SAVE_STORAGE_KEY);
    return true;
  } catch (_error) {
    return false;
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

export function clearMenuStateFromStorage() {
  try {
    localStorage.removeItem(LOCAL_MENU_STORAGE_KEY);
    return true;
  } catch (_error) {
    return false;
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
  const parsed = parseSaveEnvelope(envelope);
  if (!parsed) return false;
  const mirrored = persistEnvelopeToLocalMirror(parsed);
  void persistSaveEnvelopeToIndexedDB(parsed, {
    slotId: DEFAULT_SAVE_SLOT_ID,
    kind: "mirror",
    rememberSelection: false,
  });
  return mirrored;
}

export async function loadSaveEnvelopeFromIndexedDB(slotId = DEFAULT_SAVE_SLOT_ID) {
  const record = await runStoreRequest("readonly", (store) => store.get(String(slotId)));
  if (!record || typeof record !== "object") return null;
  return parseSaveEnvelope(record.envelope);
}

export async function persistSaveEnvelopeToIndexedDB(
  envelope,
  { slotId = DEFAULT_SAVE_SLOT_ID, kind = "manual", rememberSelection = kind !== "auto" } = {},
) {
  const record = buildSlotRecord(slotId, envelope, { kind });
  if (!record) return false;
  return enqueueIndexedDbSave(slotId, record, rememberSelection);
}

export async function persistAutoSaveEnvelope(envelope) {
  return persistSaveEnvelopeToIndexedDB(envelope, {
    slotId: AUTO_SAVE_SLOT_ID,
    kind: "auto",
    rememberSelection: false,
  });
}

export async function deleteSaveSlotFromIndexedDB(slotId = DEFAULT_SAVE_SLOT_ID) {
  try {
    await runStoreRequest("readwrite", (store) => store.delete(String(slotId)));
    if (getLastUsedSaveSlotId() === String(slotId)) {
      setLastUsedSaveSlotId("");
    }
    return true;
  } catch (_error) {
    return false;
  }
}

export async function listSaveSlotsFromIndexedDB() {
  const rows = await runStoreRequest("readonly", (store) => store.getAll());
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((row) => row && typeof row === "object")
    .map((row) => ({
      slot_id: String(row.slot_id || ""),
      kind: String(row.kind || "manual"),
      saved_at: String(row.saved_at || ""),
      summary: row.summary && typeof row.summary === "object" ? row.summary : {},
    }))
    .sort((a, b) => String(b.saved_at).localeCompare(String(a.saved_at)));
}

export async function migrateLegacyLocalStorageSaveToIndexedDB(
  slotId = DEFAULT_SAVE_SLOT_ID,
) {
  const mirrored = restoreSaveEnvelopeFromStorage();
  if (!mirrored) return null;
  await persistSaveEnvelopeToIndexedDB(mirrored, { slotId });
  return mirrored;
}

export async function restoreSaveEnvelopeFromStorageAsync(
  slotId = DEFAULT_SAVE_SLOT_ID,
) {
  const indexed = await loadSaveEnvelopeFromIndexedDB(slotId);
  if (indexed) {
    persistEnvelopeToLocalMirror(indexed);
    return indexed;
  }
  return migrateLegacyLocalStorageSaveToIndexedDB(slotId);
}

export async function syncRuntimeSaveToStorage({
  pyodide,
  buildEnvelopeOptions,
  slotId = DEFAULT_SAVE_SLOT_ID,
  kind = "manual",
}) {
  if (!pyodide) return false;
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return false;
  try {
    const saveObj = JSON.parse(saveJson);
    const envelope = makeSaveEnvelope(saveObj, buildEnvelopeOptions(saveObj));
    const mirrored = persistSaveEnvelopeToStorage(envelope);
    const persisted = await persistSaveEnvelopeToIndexedDB(envelope, { slotId, kind });
    return mirrored || persisted;
  } catch (_error) {
    return false;
  }
}
