import test from "node:test";
import assert from "node:assert/strict";

import { findCompatibleMapDefinition, normalizeMapDefinition } from "./map_data.js";

test("normalizeMapDefinition adds render padding without changing logical spawn", () => {
  const result = normalizeMapDefinition({
    id: "test",
    width: 2,
    height: 2,
    tile_width: 11,
    tile_height: 11,
    padding: {
      top: 1,
      right: 2,
      bottom: 1,
      left: 2,
      fill_gid: 19,
    },
    spawn: {
      x: 1,
      y: 1,
    },
    rows: [
      "5,5",
      "5,19",
    ],
    tileset: {
      columns: 1,
      tile_count: 1,
      image: "../assets/images/maps/SNES - Alter Cave.png",
    },
  });

  assert.equal(result.width, 2);
  assert.equal(result.height, 2);
  assert.equal(result.renderWidth, 6);
  assert.equal(result.renderHeight, 4);
  assert.deepEqual(result.spawn, { x: 1, y: 1 });
  assert.equal(result.renderRows[0][0], 19);
  assert.equal(result.renderRows[1][2], 5);
  assert.equal(result.renderRows[2][3], 19);
});

test("normalizeMapDefinition resolves NPC sprite image URLs", () => {
  const result = normalizeMapDefinition({
    id: "test",
    width: 2,
    height: 2,
    rows: [
      "1,1",
      "1,1",
    ],
    objects: [
      {
        type: "npc",
        name: "Villager",
        x: 1,
        y: 1,
        sprite_image: "../assets/images/NPCs/fs_man1.png",
        dialogue_index: 493,
      },
    ],
  });

  assert.match(result.objects[0].spriteImageUrl, /\/assets\/images\/NPCs\/fs_man1\.png$/);
  assert.equal(result.objects[0].dialogue_index, 493);
});

test("findCompatibleMapDefinition returns the map that matches selected location", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const href = String(url);
    const payloadById = {
      Alter_Cave_B1: {
        id: "Alter_Cave_B1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B1"] },
      },
      Alter_Cave_B2: {
        id: "Alter_Cave_B2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B2"] },
      },
      Alter_Cave_B3: {
        id: "Alter_Cave_B3",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B3"] },
      },
      Alter_Cave_B4: {
        id: "Alter_Cave_B4",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B4"] },
      },
      Alter_Cave_Crystal_Room: {
        id: "Alter_Cave_Crystal_Room",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave Crystal Room"] },
      },
      Ur: {
        id: "Ur",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ElderHouse_1: {
        id: "Ur_ElderHouse_1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ElderHouse_2: {
        id: "Ur_ElderHouse_2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ArmorShop: {
        id: "Ur_ArmorShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_MagicShop: {
        id: "Ur_MagicShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_WeaponShop: {
        id: "Ur_WeaponShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Inn_ItemShop: {
        id: "Ur_Inn_ItemShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Pub: {
        id: "Ur_Pub",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Shed_1F: {
        id: "Ur_Shed_1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Shed_2F: {
        id: "Ur_Shed_2F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
    };
    const matchedId = Object.keys(payloadById).find((id) => href.includes(id));
    assert.ok(matchedId, `unexpected map url: ${href}`);
    return {
      ok: true,
      async json() {
        return payloadById[matchedId];
      },
    };
  };

  try {
    const result = await findCompatibleMapDefinition({
      selected_location_group: "Altar Cave",
      selected_location: "Altar Cave B3",
    });

    assert.equal(result?.id, "Alter_Cave_B3");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("findCompatibleMapDefinition returns null when no map matches selected location", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const href = String(url);
    const payloadById = {
      Alter_Cave_B1: {
        id: "Alter_Cave_B1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B1"] },
      },
      Alter_Cave_B2: {
        id: "Alter_Cave_B2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B2"] },
      },
      Alter_Cave_B3: {
        id: "Alter_Cave_B3",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B3"] },
      },
      Alter_Cave_B4: {
        id: "Alter_Cave_B4",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave B4"] },
      },
      Alter_Cave_Crystal_Room: {
        id: "Alter_Cave_Crystal_Room",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Altar Cave", locations: ["Altar Cave Crystal Room"] },
      },
      Ur: {
        id: "Ur",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ElderHouse_1: {
        id: "Ur_ElderHouse_1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ElderHouse_2: {
        id: "Ur_ElderHouse_2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_ArmorShop: {
        id: "Ur_ArmorShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_MagicShop: {
        id: "Ur_MagicShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_WeaponShop: {
        id: "Ur_WeaponShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Inn_ItemShop: {
        id: "Ur_Inn_ItemShop",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Pub: {
        id: "Ur_Pub",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Shed_1F: {
        id: "Ur_Shed_1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
      Ur_Shed_2F: {
        id: "Ur_Shed_2F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Ur", locations: ["Ur"] },
      },
    };
    const matchedId = Object.keys(payloadById).find((id) => href.includes(id));
    assert.ok(matchedId, `unexpected map url: ${href}`);
    return {
      ok: true,
      async json() {
        return payloadById[matchedId];
      },
    };
  };

  try {
    const result = await findCompatibleMapDefinition({
      selected_location_group: "Ancient's Maze",
      selected_location: "Crystal Room",
    });

    assert.equal(result, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
