import test from "node:test";
import assert from "node:assert/strict";

import {
  AUTO_SAVE_SLOT_ID,
  clearMenuStateFromStorage,
  clearSaveEnvelopeFromStorage,
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

function createDelayedFakeIndexedDb({ onPut } = {}) {
  const data = new Map();
  const storeNames = new Set();
  const pendingPuts = [];

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
              pendingPuts.push(() => {
                onPut?.(value);
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
    flushNextPut() {
      const runner = pendingPuts.shift();
      runner?.();
    },
    pendingPutCount() {
      return pendingPuts.length;
    },
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

test("shared_storage coalesces overlapping IndexedDB writes per slot to the latest envelope", async () => {
  globalThis.localStorage = createFakeLocalStorage();
  let putCount = 0;
  const fakeIndexedDb = createDelayedFakeIndexedDb({
    onPut() {
      putCount += 1;
    },
  });
  globalThis.indexedDB = fakeIndexedDb;

  const firstEnvelope = makeSaveEnvelope(
    {
      schema_version: 1,
      gil: 10,
      inventory: {},
      party: [{ name: "Luneth", level: 1 }],
    },
    {},
  );
  const secondEnvelope = makeSaveEnvelope(
    {
      schema_version: 1,
      gil: 20,
      inventory: {},
      party: [{ name: "Arc", level: 2 }],
    },
    {},
  );
  const thirdEnvelope = makeSaveEnvelope(
    {
      schema_version: 1,
      gil: 30,
      inventory: {},
      party: [{ name: "Refia", level: 3 }],
    },
    {},
  );

  const firstWrite = persistSaveEnvelopeToIndexedDB(firstEnvelope, { slotId: "slot-hot", kind: "manual" });
  await Promise.resolve();
  const secondWrite = persistSaveEnvelopeToIndexedDB(secondEnvelope, { slotId: "slot-hot", kind: "manual" });
  const thirdWrite = persistSaveEnvelopeToIndexedDB(thirdEnvelope, { slotId: "slot-hot", kind: "manual" });

  while (fakeIndexedDb.pendingPutCount() === 0) {
    await Promise.resolve();
  }
  fakeIndexedDb.flushNextPut();
  while (fakeIndexedDb.pendingPutCount() === 0) {
    await Promise.resolve();
  }
  fakeIndexedDb.flushNextPut();

  const results = await Promise.all([firstWrite, secondWrite, thirdWrite]);
  const restored = await restoreSaveEnvelopeFromStorageAsync("slot-hot");

  assert.deepEqual(results, [true, true, true]);
  assert.equal(putCount, 2);
  assert.equal(restored?.save?.gil, 30);
  assert.equal(restored?.save?.party?.[0]?.name, "Refia");
});

test("shared_storage can clear local save and menu mirrors", () => {
  globalThis.localStorage = createFakeLocalStorage();

  const envelope = makeSaveEnvelope(
    {
      schema_version: 3,
      gil: 50,
      CP: 1,
      inventory: {},
      party: [],
    },
    {},
  );

  assert.equal(persistSaveEnvelopeToStorage(envelope), true);
  globalThis.localStorage.setItem("ff3_wasm_menu_state_v1", JSON.stringify({ party: [] }));

  assert.equal(clearSaveEnvelopeFromStorage(), true);
  assert.equal(clearMenuStateFromStorage(), true);
  assert.equal(restoreSaveEnvelopeFromStorage(), null);
  assert.equal(globalThis.localStorage.getItem("ff3_wasm_menu_state_v1"), null);
});
