import test from "node:test";
import assert from "node:assert/strict";

import {
  LOCAL_LOCATION_SELECTION_KEY,
  LOCAL_SAVE_STORAGE_KEY,
  getStoredLocationSelection,
  syncStoredLocationSelection,
} from "./location_shared.js";
import { makeSaveEnvelope, restoreSaveEnvelopeFromStorage } from "./shared_storage.js";

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

test("syncStoredLocationSelection does not create an empty save envelope", () => {
  globalThis.localStorage = createFakeLocalStorage();
  delete globalThis.indexedDB;

  assert.equal(syncStoredLocationSelection("Floating Continent", "Bahamut's Lair"), true);
  assert.equal(localStorage.getItem(LOCAL_SAVE_STORAGE_KEY), null);
  assert.deepEqual(getStoredLocationSelection(), {
    selected_location_group: "Floating Continent",
    selected_location: "Bahamut's Lair",
  });

  const rawSelection = JSON.parse(localStorage.getItem(LOCAL_LOCATION_SELECTION_KEY));
  assert.equal(rawSelection.selected_location_group, "Floating Continent");
  assert.equal(rawSelection.selected_location, "Bahamut's Lair");
});

test("syncStoredLocationSelection updates envelope metadata when a save already exists", () => {
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
    },
  );
  localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));

  assert.equal(syncStoredLocationSelection("Floating Continent", "Bahamut's Lair"), true);
  assert.equal(restoreSaveEnvelopeFromStorage()?.save?.gil, 321);
  assert.equal(
    restoreSaveEnvelopeFromStorage()?.selected_location_group,
    "Floating Continent",
  );
  assert.equal(
    restoreSaveEnvelopeFromStorage()?.selected_location,
    "Bahamut's Lair",
  );
});
