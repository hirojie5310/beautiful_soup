import test from "node:test";
import assert from "node:assert/strict";

import { getLastUsedSaveSlotId } from "./shared_storage.js";
import { SaveRepository } from "./save_repository.js";

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

test("SaveRepository saves one envelope through the active mirror and selected slot", async () => {
  globalThis.localStorage = createFakeLocalStorage();
  globalThis.indexedDB = createFakeIndexedDb();

  const repository = new SaveRepository();
  const envelope = repository.makeEnvelope(
    {
      schema_version: 2,
      gil: 456,
      inventory: {},
      party: [{ name: "Arc", level: 9 }],
    },
    {
      selectedLocationGroup: "Floating Continent",
      selectedLocation: "Ur",
      menuState: { party: [{ name: "Arc" }], resources: { gil: 456 } },
    },
  );

  assert.equal(await repository.save(envelope, { slotId: "slot-1" }), true);
  assert.equal(repository.loadLocalMirror()?.save?.gil, 456);
  assert.equal((await repository.loadSlot("slot-1"))?.save?.party?.[0]?.name, "Arc");
  assert.equal(getLastUsedSaveSlotId(), "slot-1");
});

test("SaveRepository keeps menu_state writes behind the repository boundary", () => {
  globalThis.localStorage = createFakeLocalStorage();
  delete globalThis.indexedDB;

  const repository = new SaveRepository();
  assert.equal(repository.saveMenuState({ party: [{ name: "Refia" }] }), true);
  assert.deepEqual(repository.loadMenuState(), { party: [{ name: "Refia" }] });
});
