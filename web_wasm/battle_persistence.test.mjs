import test from "node:test";
import assert from "node:assert/strict";

import { makeSaveEnvelope } from "./shared_storage.js";
import {
  applyBattleSavePatchToSave,
  persistFinishedBattleSave,
} from "./battle_persistence.js";

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
      store.delete(String(key));
    },
    clear() {
      store.clear();
    },
  };
}

test("applyBattleSavePatchToSave applies resource, party, and inventory deltas", () => {
  const nextSave = applyBattleSavePatchToSave(
    {
      schema_version: 2,
      gil: 100,
      CP: 2,
      inventory: { Anywhere: { Potion: 1 } },
      item_stock: { Potion: 1 },
      party: [
        {
          name: "Refia",
          hp: 8,
          max_hp: 10,
          level: 1,
          exp: 0,
          job_level: { level: 1, skill_point: 0 },
          mp: { L1MP: 1 },
          mp_levels: { "1": { current: 1, max: 2 } },
        },
      ],
    },
    {
      resource_changes: {
        gil: { before: 100, after: 125, delta: 25 },
        cp: { before: 2, after: 3, delta: 1 },
      },
      party_changes: [
        {
          name: "Refia",
          hp: { before: 8, after: 6, delta: -2 },
          max_hp: { before: 10, after: 12, delta: 2 },
          level: { before: 1, after: 2, delta: 1 },
          exp: { before: 0, after: 40, delta: 40 },
          job_level: {
            skill_point: { before: 0, after: 5, delta: 5 },
          },
          mp_levels: {
            "1": {
              current_before: 1,
              current_after: 0,
              current_delta: -1,
              max_before: 2,
              max_after: 3,
              max_delta: 1,
            },
          },
        },
      ],
      inventory_changes: [
        { path: ["Anywhere", "Potion"], before: 1, after: 2, delta: 1 },
      ],
      item_stock_changes: [
        { path: ["Potion"], before: 1, after: 0, delta: -1 },
      ],
      rewards: {},
    },
  );

  assert.equal(nextSave.gil, 125);
  assert.equal(nextSave.CP, 3);
  assert.equal(nextSave.party[0].hp, 6);
  assert.equal(nextSave.party[0].max_hp, 12);
  assert.equal(nextSave.party[0].level, 2);
  assert.equal(nextSave.party[0].exp, 40);
  assert.equal(nextSave.party[0].job_level.skill_point, 5);
  assert.equal(nextSave.party[0].mp.L1MP, 0);
  assert.deepEqual(nextSave.party[0].mp_levels["1"], { current: 0, max: 3 });
  assert.equal(nextSave.inventory.Anywhere.Potion, 2);
  assert.equal(nextSave.item_stock.Potion, 0);
});

test("persistFinishedBattleSave falls back to battle_save_patch when runtime export is unavailable", async () => {
  globalThis.localStorage = createFakeLocalStorage();
  delete globalThis.indexedDB;

  const envelope = makeSaveEnvelope(
    {
      schema_version: 2,
      gil: 100,
      CP: 2,
      inventory: { Anywhere: { Potion: 1 } },
      party: [{ name: "Refia", hp: 8, max_hp: 10 }],
    },
    {
      selectedLocationGroup: "Floating Continent",
      selectedLocation: "Bahamut's Lair",
      menuState: { party: [{ name: "Refia" }], resources: { gil: 100, cp: 2 } },
    },
  );
  localStorage.setItem("ff3_wasm_savedata_v1", JSON.stringify(envelope));

  const result = await persistFinishedBattleSave({
    pyodide: null,
    result: {
      selected_location_group: "Floating Continent",
      selected_location: "Bahamut's Lair",
      battle_save_patch: {
        resource_changes: {
          gil: { before: 100, after: 125, delta: 25 },
          cp: { before: 2, after: 3, delta: 1 },
        },
        party_changes: [
          {
            name: "Refia",
            hp: { before: 8, after: 6, delta: -2 },
            max_hp: { before: 10, after: 12, delta: 2 },
          },
        ],
        inventory_changes: [
          { path: ["Anywhere", "Potion"], before: 1, after: 2, delta: 1 },
        ],
        item_stock_changes: [],
        rewards: {},
      },
    },
    menuState: {
      party: [{ name: "Refia", hp: 6, max_hp: 12 }],
      resources: { gil: 125, cp: 3 },
    },
  });

  assert.equal(result.persisted, true);
  assert.equal(result.autosaved, true);
  assert.equal(result.envelope?.save?.gil, 125);
  assert.equal(result.envelope?.save?.CP, 3);
  assert.equal(result.envelope?.save?.party?.[0]?.hp, 6);
  assert.equal(result.envelope?.save?.inventory?.Anywhere?.Potion, 2);

  const mirrored = JSON.parse(localStorage.getItem("ff3_wasm_savedata_v1") || "{}");
  assert.equal(mirrored?.save?.gil, 125);
  assert.equal(mirrored?.save?.party?.[0]?.hp, 6);
});
