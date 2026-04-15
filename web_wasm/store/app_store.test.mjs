import test from "node:test";
import assert from "node:assert/strict";

import { createAppStore } from "./app_store.js";
import { makeSaveEnvelope } from "../shared_storage.js";

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

test("resetForTitle clears active envelope and location selection", () => {
  globalThis.localStorage = createFakeLocalStorage();
  delete globalThis.indexedDB;

  const envelope = makeSaveEnvelope(
    {
      schema_version: 1,
      gil: 321,
      CP: 9,
      inventory: {},
      party: [{ name: "Refia", level: 15 }],
    },
    {
      selectedLocationGroup: "Ancient's Maze",
      selectedLocation: "Crystal Room",
      menuState: {
        party: [{ name: "Refia" }],
        resources: { cp: 9, cp_max: 255, gil: 321 },
      },
    },
  );
  localStorage.setItem("ff3_wasm_savedata_v1", JSON.stringify(envelope));
  localStorage.setItem("ff3_wasm_location_selection_v1", JSON.stringify({
    selected_location_group: "Ancient's Maze",
    selected_location: "Crystal Room",
  }));
  localStorage.setItem("ff3_wasm_menu_state_v1", JSON.stringify({
    party: [{ name: "Refia" }],
    resources: { cp: 9, cp_max: 255, gil: 321 },
  }));

  const store = createAppStore();
  store.resetForTitle();

  assert.deepEqual(store.getState(), {
    route: "location",
    selectedLocationGroup: "",
    selectedLocation: "",
    menuMemberIndex: 0,
    menuState: { party: [], resources: { cp: 0, cp_max: 255, gil: 0 } },
    saveEnvelope: null,
  });
  assert.equal(localStorage.getItem("ff3_wasm_savedata_v1"), null);
  assert.equal(localStorage.getItem("ff3_wasm_location_selection_v1"), null);
  assert.equal(localStorage.getItem("ff3_wasm_menu_state_v1"), null);
});
