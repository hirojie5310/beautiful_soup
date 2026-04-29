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
