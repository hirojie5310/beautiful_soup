import test from "node:test";
import assert from "node:assert/strict";

import {
  findCompatibleMapDefinition,
  getMapManifestUrl,
  isInEncounterArea,
  normalizeMapDefinition,
  shouldTriggerEncounter,
} from "./map_data.js";

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
    encounter_areas: [
      { x_min: 0, y_min: 0, x_max: 24, y_max: 14 },
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
  assert.deepEqual(result.encounterAreas, [{ xMin: 0, yMin: 0, xMax: 24, yMax: 14 }]);
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
        movement: "fixed",
        direction: "down",
      },
    ],
  });

  assert.match(result.objects[0].spriteImageUrl, /\/assets\/images\/NPCs\/fs_man1\.png$/);
  assert.equal(result.objects[0].dialogue_index, 493);
  assert.equal(result.objects[0].movement, "fixed");
  assert.equal(result.objects[0].direction, "down");
});

test("encounter areas restrict random encounters by tile position", () => {
  const result = normalizeMapDefinition({
    id: "test",
    width: 32,
    height: 32,
    encounter_rate: 1,
    encounter_areas: [
      { x_min: 0, y_min: 0, x_max: 24, y_max: 14 },
    ],
    rows: Array.from({ length: 32 }, () => "1"),
  });

  assert.equal(isInEncounterArea(result, { tile_x: 24, tile_y: 14 }), true);
  assert.equal(isInEncounterArea(result, { tile_x: 25, tile_y: 14 }), false);
  assert.equal(isInEncounterArea(result, { tile_x: 24, tile_y: 15 }), false);
  assert.equal(shouldTriggerEncounter(result, 0, 6, { tile_x: 24, tile_y: 14 }), true);
  assert.equal(shouldTriggerEncounter(result, 0, 6, { tile_x: 25, tile_y: 14 }), false);
});

test("getMapManifestUrl resolves registered maps without falling back", () => {
  assert.match(String(getMapManifestUrl("Castle_Sasune")), /\/assets\/maps\/Castle_Sasune\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_MainKeep_B1F")), /\/assets\/maps\/Castle_Sasune_MainKeep_B1F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_MainKeep_1F")), /\/assets\/maps\/Castle_Sasune_MainKeep_1F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_MainKeep_2F")), /\/assets\/maps\/Castle_Sasune_MainKeep_2F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_MainKeep_3F")), /\/assets\/maps\/Castle_Sasune_MainKeep_3F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_MainKeep_4F")), /\/assets\/maps\/Castle_Sasune_MainKeep_4F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_West_1F")), /\/assets\/maps\/Castle_Sasune_Tower_West_1F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_West_2F")), /\/assets\/maps\/Castle_Sasune_Tower_West_2F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_West_3F")), /\/assets\/maps\/Castle_Sasune_Tower_West_3F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_West_4F")), /\/assets\/maps\/Castle_Sasune_Tower_West_4F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_East_1F")), /\/assets\/maps\/Castle_Sasune_Tower_East_1F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_East_2F")), /\/assets\/maps\/Castle_Sasune_Tower_East_2F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_East_3F")), /\/assets\/maps\/Castle_Sasune_Tower_East_3F\.json$/);
  assert.match(String(getMapManifestUrl("Castle_Sasune_Tower_East_4F")), /\/assets\/maps\/Castle_Sasune_Tower_East_4F\.json$/);
  assert.match(String(getMapManifestUrl("Sealed_Cave_B1")), /\/assets\/maps\/Sealed_Cave_B1\.json$/);
  assert.match(String(getMapManifestUrl("Sealed_Cave_B2")), /\/assets\/maps\/Sealed_Cave_B2\.json$/);
  assert.match(String(getMapManifestUrl("Sealed_Cave_B2_1")), /\/assets\/maps\/Sealed_Cave_B2_1\.json$/);
  assert.match(String(getMapManifestUrl("Sealed_Cave_B2_2")), /\/assets\/maps\/Sealed_Cave_B2_2\.json$/);
  assert.match(String(getMapManifestUrl("Sealed_Cave_B3")), /\/assets\/maps\/Sealed_Cave_B3\.json$/);
  assert.match(String(getMapManifestUrl("Ur_Well")), /\/assets\/maps\/Ur-Well\.json$/);
  assert.match(String(getMapManifestUrl("FloatingContinent")), /\/assets\/maps\/FloatingContinent\.json$/);
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
      FloatingContinent: {
        id: "FloatingContinent",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Floating Continent", locations: ["Floating Continent Near Ur"] },
      },
      Sealed_Cave_B1: {
        id: "Sealed_Cave_B1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B1"] },
      },
      Sealed_Cave_B2: {
        id: "Sealed_Cave_B2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2"] },
      },
      Sealed_Cave_B2_1: {
        id: "Sealed_Cave_B2_1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_1"] },
      },
      Sealed_Cave_B2_2: {
        id: "Sealed_Cave_B2_2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_2"] },
      },
      Sealed_Cave_B3: {
        id: "Sealed_Cave_B3",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B3"] },
      },
      Airship_of_Cid: {
        id: "Airship_of_Cid",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "", locations: [] },
      },
      Castle_Sasune: {
        id: "Castle_Sasune",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_MainKeep_B1F: {
        id: "Castle_Sasune_MainKeep_B1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_MainKeep_1F: {
        id: "Castle_Sasune_MainKeep_1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_MainKeep_2F: {
        id: "Castle_Sasune_MainKeep_2F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_MainKeep_3F: {
        id: "Castle_Sasune_MainKeep_3F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_MainKeep_4F: {
        id: "Castle_Sasune_MainKeep_4F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_West_1F: {
        id: "Castle_Sasune_Tower_West_1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_West_2F: {
        id: "Castle_Sasune_Tower_West_2F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_West_3F: {
        id: "Castle_Sasune_Tower_West_3F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_West_4F: {
        id: "Castle_Sasune_Tower_West_4F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_East_1F: {
        id: "Castle_Sasune_Tower_East_1F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_East_2F: {
        id: "Castle_Sasune_Tower_East_2F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_East_3F: {
        id: "Castle_Sasune_Tower_East_3F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
      },
      Castle_Sasune_Tower_East_4F: {
        id: "Castle_Sasune_Tower_East_4F",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Castle Sasune", locations: ["Castle Sasune"] },
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
    if (!matchedId) {
      return {
        ok: true,
        async json() {
          return {
            id: "Unrelated",
            width: 1,
            height: 1,
            rows: ["1"],
            location_requirement: { group: "Other", locations: ["Other"] },
          };
        },
      };
    }
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
      FloatingContinent: {
        id: "FloatingContinent",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Floating Continent", locations: ["Floating Continent Near Ur"] },
      },
      Sealed_Cave_B1: {
        id: "Sealed_Cave_B1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B1"] },
      },
      Sealed_Cave_B2: {
        id: "Sealed_Cave_B2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2"] },
      },
      Sealed_Cave_B2_1: {
        id: "Sealed_Cave_B2_1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_1"] },
      },
      Sealed_Cave_B2_2: {
        id: "Sealed_Cave_B2_2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_2"] },
      },
      Sealed_Cave_B3: {
        id: "Sealed_Cave_B3",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B3"] },
      },
      Airship_of_Cid: {
        id: "Airship_of_Cid",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "", locations: [] },
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
    if (!matchedId) {
      return {
        ok: true,
        async json() {
          return {
            id: "Unrelated",
            width: 1,
            height: 1,
            rows: ["1"],
            location_requirement: { group: "Other", locations: ["Other"] },
          };
        },
      };
    }
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

test("findCompatibleMapDefinition prefers maps with explicit location requirements over generic maps", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const href = String(url);
    const payloadById = {
      Airship_of_Cid: {
        id: "Airship_of_Cid",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "", locations: [] },
      },
      FloatingContinent: {
        id: "FloatingContinent",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Floating Continent", locations: ["Floating Continent Near Ur"] },
      },
      Sealed_Cave_B1: {
        id: "Sealed_Cave_B1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B1"] },
      },
      Sealed_Cave_B2: {
        id: "Sealed_Cave_B2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2"] },
      },
      Sealed_Cave_B2_1: {
        id: "Sealed_Cave_B2_1",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_1"] },
      },
      Sealed_Cave_B2_2: {
        id: "Sealed_Cave_B2_2",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B2_2"] },
      },
      Sealed_Cave_B3: {
        id: "Sealed_Cave_B3",
        width: 1,
        height: 1,
        rows: ["1"],
        location_requirement: { group: "Sealed Cave", locations: ["Sealed Cave B3"] },
      },
    };
    const matchedId = Object.keys(payloadById).find((id) => href.includes(id));
    if (!matchedId) {
      return {
        ok: true,
        async json() {
          return {
            id: "Unrelated",
            width: 1,
            height: 1,
            rows: ["1"],
            location_requirement: { group: "Other", locations: ["Other"] },
          };
        },
      };
    }
    return {
      ok: true,
      async json() {
        return payloadById[matchedId];
      },
    };
  };

  try {
    const result = await findCompatibleMapDefinition({
      selected_location_group: "Floating Continent",
      selected_location: "Floating Continent Near Ur",
    });

    assert.equal(result?.id, "FloatingContinent");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
