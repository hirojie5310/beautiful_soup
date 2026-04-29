import {
  AUTO_SAVE_SLOT_ID,
  DEFAULT_SAVE_SLOT_ID,
  LOCAL_MENU_STORAGE_KEY,
  clearMenuStateFromStorage,
  clearSaveEnvelopeFromStorage,
  deleteSaveSlotFromIndexedDB,
  listSaveSlotsFromIndexedDB,
  loadSaveEnvelopeFromIndexedDB,
  makeSaveEnvelope,
  parseMenuStateFromStorage,
  persistSaveEnvelopeToIndexedDB,
  persistSaveEnvelopeToStorage,
  restoreSaveEnvelopeFromStorage,
  restoreSaveEnvelopeFromStorageAsync,
} from "./shared_storage.js";

const SAVE_COMMIT_POLICIES = Object.freeze({
  runtime_checkpoint: Object.freeze({ mirror: true }),
  session_restored: Object.freeze({ mirror: true }),
  save_imported: Object.freeze({ mirror: true }),
  location_selected: Object.freeze({ mirror: true }),
  battle_finished: Object.freeze({ mirror: true, auto: true }),
  menu_confirmed: Object.freeze({ mirror: true, auto: true }),
  new_game_initialized: Object.freeze({ mirror: true, auto: true }),
  manual_save: Object.freeze({ mirror: true, slot: true, kind: "manual", rememberSelection: true }),
});

function resolveCommitPolicy(reason) {
  const key = String(reason || "").trim();
  const policy = SAVE_COMMIT_POLICIES[key];
  if (!policy) {
    throw new Error(`Unknown save commit reason: ${key || "(empty)"}`);
  }
  return policy;
}

function buildCommitResult({
  reason,
  mirrored = false,
  slotted = false,
  autosaved = false,
} = {}) {
  return {
    reason: String(reason || ""),
    mirrored: Boolean(mirrored),
    slotted: Boolean(slotted),
    autosaved: Boolean(autosaved),
    persisted: Boolean(mirrored || slotted || autosaved),
  };
}

export class SaveRepository {
  loadLocalMirror() {
    return restoreSaveEnvelopeFromStorage();
  }

  async load(slotId = DEFAULT_SAVE_SLOT_ID) {
    return restoreSaveEnvelopeFromStorageAsync(slotId);
  }

  async loadSlot(slotId = DEFAULT_SAVE_SLOT_ID) {
    return loadSaveEnvelopeFromIndexedDB(slotId);
  }

  saveLocalMirror(envelope) {
    return persistSaveEnvelopeToStorage(envelope);
  }

  commitSync({ reason, envelope, alreadyMirrored = false } = {}) {
    const policy = resolveCommitPolicy(reason);
    const mirrored = alreadyMirrored
      ? true
      : (policy.mirror ? this.saveLocalMirror(envelope) : false);
    return buildCommitResult({ reason, mirrored });
  }

  async commit({ reason, envelope, slotId = DEFAULT_SAVE_SLOT_ID, alreadyMirrored = false } = {}) {
    const policy = resolveCommitPolicy(reason);
    const mirrored = alreadyMirrored
      ? true
      : (policy.mirror ? this.saveLocalMirror(envelope) : false);
    const slotted = policy.slot
      ? await persistSaveEnvelopeToIndexedDB(envelope, {
        slotId,
        kind: policy.kind || "manual",
        rememberSelection: policy.rememberSelection ?? true,
      })
      : false;
    const autosaved = policy.auto
      ? await persistSaveEnvelopeToIndexedDB(envelope, {
        slotId: AUTO_SAVE_SLOT_ID,
        kind: "auto",
        rememberSelection: false,
      })
      : false;
    return buildCommitResult({
      reason,
      mirrored,
      slotted,
      autosaved,
    });
  }

  async save(
    envelope,
    { slotId = DEFAULT_SAVE_SLOT_ID, kind = "manual", rememberSelection = kind !== "auto" } = {},
  ) {
    const mirrored = this.saveLocalMirror(envelope);
    const slotted = await persistSaveEnvelopeToIndexedDB(envelope, {
      slotId,
      kind,
      rememberSelection,
    });
    return mirrored || slotted;
  }

  async saveSlot(envelope, slotId, options = {}) {
    return persistSaveEnvelopeToIndexedDB(envelope, {
      slotId,
      kind: options?.kind || "manual",
      rememberSelection: options?.rememberSelection ?? true,
    });
  }

  async saveAuto(envelope) {
    return persistSaveEnvelopeToIndexedDB(envelope, {
      slotId: AUTO_SAVE_SLOT_ID,
      kind: "auto",
      rememberSelection: false,
    });
  }

  async listSlots() {
    return listSaveSlotsFromIndexedDB();
  }

  async deleteSlot(slotId = DEFAULT_SAVE_SLOT_ID) {
    return deleteSaveSlotFromIndexedDB(slotId);
  }

  loadMenuState() {
    return parseMenuStateFromStorage();
  }

  saveMenuState(menuState) {
    try {
      localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(menuState || {}));
      return true;
    } catch (_error) {
      return false;
    }
  }

  clearLocalMirrors() {
    const saveCleared = clearSaveEnvelopeFromStorage();
    const menuCleared = clearMenuStateFromStorage();
    return saveCleared && menuCleared;
  }

  makeEnvelope(saveObj, options = {}) {
    return makeSaveEnvelope(saveObj, options);
  }
}

export const saveRepository = new SaveRepository();
