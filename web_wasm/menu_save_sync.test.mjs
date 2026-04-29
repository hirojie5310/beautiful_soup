import test from "node:test";
import assert from "node:assert/strict";

import { mergeMenuStateIntoSave } from "./menu_save_sync.js";

test("mergeMenuStateIntoSave preserves treasure progress while syncing menu changes", () => {
  const nextSave = mergeMenuStateIntoSave(
    {
      schema_version: 2,
      gil: 100,
      CP: 3,
      treasures: {
        Alter_Cave_B1: {
          altar_cave_b1_treasure_right_room_left: true,
        },
      },
      map: {
        map: "Alter_Cave_B1",
        surface: "Alter Cave B1",
        x: 1,
        y: 1,
      },
      party: [
        {
          name: "Refia",
          job: "White Mage",
          current_job: "White Mage",
          row: "front",
          hp: 20,
          max_hp: 30,
          level: 4,
          exp: 100,
          mp_levels: {
            "1": { current: 2, max: 2 },
          },
          status_effects: { Poison: false },
        },
      ],
    },
    {
      resources: { gil: 250, cp: 7 },
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 9,
        tile_y: 12,
      },
      party: [
        {
          name: "Refia",
          job: "White Mage",
          current_job: "White Mage",
          row: "back",
          hp: 18,
          max_hp: 30,
          level: 5,
          exp: 140,
          mp_levels: {
            "1": { current: 1, max: 2 },
          },
          status_icons: [],
        },
      ],
    },
  );

  assert.equal(nextSave.gil, 250);
  assert.equal(nextSave.CP, 7);
  assert.equal(nextSave.map.x, 9);
  assert.equal(nextSave.map.y, 12);
  assert.equal(nextSave.party[0].row, "back");
  assert.equal(
    nextSave.treasures.Alter_Cave_B1.altar_cave_b1_treasure_right_room_left,
    true,
  );
});
