import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTO_SAVE_SLOT_ID,
  DEFAULT_SAVE_SLOT_ID,
  getLastUsedSaveSlotId,
  listSaveSlotsFromIndexedDB,
  makeSaveEnvelope,
  persistSaveEnvelopeToIndexedDB,
  persistSaveEnvelopeToStorage,
  restoreSaveEnvelopeFromStorage,
  restoreSaveEnvelopeFromStorageAsync,
} from "./shared_storage.js";

function createFakeLocalStorage() {
  const store = new Map();
  return {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(String(key), String(value));
    },
    removeItem(key) {
      store.delete(key);
    },
    clear() {
      store.clear();
    },
  };
}

function createFakeIndexedDb() {
  const data = new Map();
  const storeNames = new Set();

  function createRequest() {
    return {
      result: undefined,
      error: null,
      onsuccess: null,
      onerror: null,
      onupgradeneeded: null,
    };
  }

  const db = {
    objectStoreNames: {
      contains(name) {
        return storeNames.has(name);
      },
    },
    createObjectStore(name) {
      storeNames.add(name);
      return {
        createIndex() {
          return undefined;
        },
      };
    },
    transaction() {
      const tx = {
        error: null,
        oncomplete: null,
        onerror: null,
        onabort: null,
        objectStore() {
          return {
            put(value) {
              const request = createRequest();
              queueMicrotask(() => {
                data.set(String(value.slot_id), structuredClone(value));
                request.result = value.slot_id;
                tx.oncomplete?.();
              });
              return request;
            },
            get(key) {
              const request = createRequest();
              queueMicrotask(() => {
                request.result = data.get(String(key)) ?? undefined;
                tx.oncomplete?.();
              });
              return request;
            },
            getAll() {
              const request = createRequest();
              queueMicrotask(() => {
                request.result = Array.from(data.values()).map((row) => structuredClone(row));
                tx.oncomplete?.();
              });
              return request;
            },
            delete(key) {
              const request = createRequest();
              queueMicrotask(() => {
                data.delete(String(key));
                request.result = undefined;
                tx.oncomplete?.();
              });
              return request;
            },
          };
        },
      };
      return tx;
    },
    close() {
      return undefined;
    },
  };

  return {
    open() {
      const request = createRequest();
      queueMicrotask(() => {
        request.result = db;
        if (!storeNames.size) {
          request.onupgradeneeded?.();
        }
        request.onsuccess?.();
      });
      return request;
    },
  };
}

test("shared_storage keeps localStorage mirror and persists default slot to IndexedDB", async () => {
  globalThis.localStorage = createFakeLocalStorage();
  globalThis.indexedDB = createFakeIndexedDb();

  const envelope = makeSaveEnvelope(
    {
      schema_version: 1,
      gil: 123,
      CP: 4,
      inventory: {},
      party: [{ name: "Refia", level: 12 }],
    },
    {
      selectedLocationGroup: "Floating Continent",
      selectedLocation: "Bahamut's Lair",
    },
  );

  assert.equal(persistSaveEnvelopeToStorage(envelope), true);
  assert.equal(restoreSaveEnvelopeFromStorage()?.save?.gil, 123);

  await persistSaveEnvelopeToIndexedDB(envelope);
  const restored = await restoreSaveEnvelopeFromStorageAsync();
  const slots = await listSaveSlotsFromIndexedDB();

  assert.equal(restored?.save?.schema_version, 1);
  assert.equal(restored?.selected_location_group, "Floating Continent");
  assert.equal(slots.length, 1);
  assert.equal(slots[0].slot_id, DEFAULT_SAVE_SLOT_ID);
  assert.equal(slots[0].summary.lead_name, "Refia");
});

test("shared_storage tracks last used manual slot but ignores auto-save writes", async () => {
  globalThis.localStorage = createFakeLocalStorage();
  globalThis.indexedDB = createFakeIndexedDb();

  const envelope = makeSaveEnvelope(
    {
      schema_version: 2,
      gil: 999,
      CP: 8,
      inventory: {},
      party: [{ name: "Ingus", level: 22 }],
    },
    {},
  );

  await persistSaveEnvelopeToIndexedDB(envelope, { slotId: "slot-2", kind: "manual" });
  assert.equal(getLastUsedSaveSlotId(), "slot-2");

  await persistSaveEnvelopeToIndexedDB(envelope, {
    slotId: AUTO_SAVE_SLOT_ID,
    kind: "auto",
    rememberSelection: false,
  });
  assert.equal(getLastUsedSaveSlotId(), "slot-2");
});
