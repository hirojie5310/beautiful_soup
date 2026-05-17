import test from "node:test";
import assert from "node:assert/strict";

import {
  addPurchasedItemToInventory,
  buildSpellLevelByName,
  clearStoredLocationSelection,
  LOCAL_LOCATION_SELECTION_KEY,
  LOCAL_SAVE_STORAGE_KEY,
  getStoredLocationSelection,
  normalizeShopTypeToInventoryBucket,
  resolveInventoryBucketForItem,
  syncMenuStateAfterPurchase,
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

test("clearStoredLocationSelection removes persisted location choice", () => {
  globalThis.localStorage = createFakeLocalStorage();
  delete globalThis.indexedDB;

  assert.equal(syncStoredLocationSelection("Floating Continent", "Bahamut's Lair"), true);
  assert.deepEqual(getStoredLocationSelection(), {
    selected_location_group: "Floating Continent",
    selected_location: "Bahamut's Lair",
  });

  assert.equal(clearStoredLocationSelection(), true);
  assert.equal(localStorage.getItem(LOCAL_LOCATION_SELECTION_KEY), null);
  assert.deepEqual(getStoredLocationSelection(), {
    selected_location_group: "",
    selected_location: "",
  });
});

test("buildSpellLevelByName prefers lowercase spell master names", () => {
  const spellLevelByName = buildSpellLevelByName({
    spells: [
      { name: "Fire", Level: 1 },
      { Name: "Cura", level: 3 },
      { Name: "", Level: 4 },
    ],
  });

  assert.deepEqual(spellLevelByName, {
    Fire: 1,
    Cura: 3,
  });
});

test("Magic shop purchase stores lowercase-master spells in level buckets", () => {
  const spellLevelByName = buildSpellLevelByName({
    spells: [{ name: "Sleep", Level: 1 }],
  });
  const save = { inventory: {} };

  assert.equal(
    addPurchasedItemToInventory(save, spellLevelByName, "Magic", "Sleep", 1),
    true,
  );

  assert.equal(save.inventory.Magic.LV1.Sleep, 1);
});

test("syncMenuStateAfterPurchase stocks Magic from lowercase spell master names", () => {
  const spellLevelByName = buildSpellLevelByName({
    spells: [{ name: "Raise", Level: 5 }],
  });
  const envelope = {
    save: { gil: 123, inventory: {} },
    menu_state: { resources: { gil: 999 }, magic_setup: { stock_by_level: {} } },
  };

  syncMenuStateAfterPurchase(envelope, spellLevelByName, "Raise", "Magic");

  assert.equal(envelope.menu_state.resources.gil, 123);
  assert.deepEqual(envelope.menu_state.magic_setup.stock_by_level["5"], ["Raise"]);
});

test("resolveInventoryBucketForItem prefers catalog item types over mistaken preferred buckets", () => {
  const masterData = {
    itemTypeByName: {
      "Antarctic Wind": "Combat",
    },
    spellLevelByName: {},
    weaponNameSet: new Set(),
    armorNameSet: new Set(),
  };
  assert.equal(resolveInventoryBucketForItem(masterData, "Antarctic Wind", "Anywhere"), "Combat");
});

test("normalizeShopTypeToInventoryBucket still resolves magic and equipment buckets", () => {
  const masterData = {
    itemTypeByName: {
      Potion: "Anywhere",
    },
    spellLevelByName: {
      Cure: 1,
    },
    weaponNameSet: new Set(["Staff"]),
    armorNameSet: new Set(["Leather Armor"]),
  };
  assert.equal(normalizeShopTypeToInventoryBucket(masterData, { type: "Magic" }, "Cure"), "Magic");
  assert.equal(normalizeShopTypeToInventoryBucket(masterData, { type: "Weapons" }, "Staff"), "Weapon");
  assert.equal(normalizeShopTypeToInventoryBucket(masterData, { type: "Armor" }, "Leather Armor"), "Armor");
  assert.equal(normalizeShopTypeToInventoryBucket(masterData, { inventory_bucket: "Anywhere" }, "Potion"), "Anywhere");
});
