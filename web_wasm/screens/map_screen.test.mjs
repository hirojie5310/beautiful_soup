import test from "node:test";
import assert from "node:assert/strict";

import {
  canOccupyTile,
  deriveInitialMapState,
  moveMapPosition,
} from "./map_screen.js";
import {
  buildEncounterSelection,
  isMapSelectionCompatible,
  shouldTriggerEncounter,
} from "../map_data.js";

const stubMap = {
  id: "Alter_Cave_B1",
  name: "Alter Cave B1",
  width: 3,
  height: 3,
  spawn: { x: 1, y: 1 },
  locationRequirement: {
    group: "Altar Cave",
    locations: ["Altar Cave B1"],
  },
  encounterRate: 0.1,
  rows: [
    [19, 19, 19],
    [19, 5, 19],
    [19, 5, 5],
  ],
  collisionGids: new Set([19]),
};

test("deriveInitialMapState always starts from map spawn", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 2,
        tile_y: 2,
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "ignored", x: 0, y: 0 },
      },
    },
  }, stubMap);

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
  });
});

test("deriveInitialMapState can resume from saved position after battle", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 2,
        tile_y: 2,
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B1", x: 1, y: 2 },
      },
    },
  }, stubMap, {
    resumeFromSavedPosition: true,
  });

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 2,
    tile_y: 2,
  });
});

test("canOccupyTile rejects collision gids and bounds", () => {
  assert.equal(canOccupyTile(stubMap, 1, 1), true);
  assert.equal(canOccupyTile(stubMap, 0, 0), false);
  assert.equal(canOccupyTile(stubMap, -1, 1), false);
});

test("moveMapPosition advances only onto passable tiles", () => {
  const start = { current_map_id: "Alter_Cave_B1", tile_x: 1, tile_y: 1 };
  const moved = moveMapPosition(stubMap, start, "down");
  assert.equal(moved.moved, true);
  assert.deepEqual(moved.nextState, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 2,
  });

  const blocked = moveMapPosition(stubMap, moved.nextState, "left");
  assert.equal(blocked.moved, false);
  assert.equal(blocked.reason, "blocked");
});

test("isMapSelectionCompatible requires matching location", () => {
  assert.equal(isMapSelectionCompatible(stubMap, {
    selected_location_group: "Altar Cave",
    selected_location: "Altar Cave B1",
  }), true);
  assert.equal(isMapSelectionCompatible(stubMap, {
    selected_location_group: "Mythril Mines",
    selected_location: "Mythril Mines B1",
  }), false);
});

test("buildEncounterSelection prefers map-linked location", () => {
  assert.deepEqual(buildEncounterSelection(stubMap, {
    selected_location_group: "Other",
    selected_location: "Other B1",
  }), {
    selected_location_group: "Altar Cave",
    selected_location: "Altar Cave B1",
  });
});

test("shouldTriggerEncounter uses encounterRate threshold", () => {
  assert.equal(shouldTriggerEncounter(stubMap, 0.05), true);
  assert.equal(shouldTriggerEncounter(stubMap, 0.5), false);
});
