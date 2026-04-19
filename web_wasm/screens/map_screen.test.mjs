import test from "node:test";
import assert from "node:assert/strict";

import {
  applySwitchStateToMap,
  deriveMapLaunchContext,
  canOccupyTile,
  deriveInitialMapState,
  findAdjacentObject,
  findStandingObject,
  moveMapPosition,
  openAdjacentTreasure,
  shouldResumeMapPosition,
  toggleAdjacentSwitch,
} from "./map_screen.js";
import {
  buildEncounterSelection,
  getEncounterRateForStep,
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
    steps_since_reset: 0,
    switch_states: {},
    opened_treasures: {},
  });
});

test("deriveInitialMapState can resume from saved position after battle", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 2,
        tile_y: 2,
        steps_since_reset: 4,
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
    steps_since_reset: 4,
    switch_states: {},
    opened_treasures: {},
  });
});

test("shouldResumeMapPosition resumes when returning from menu", () => {
  assert.equal(shouldResumeMapPosition({
    menuState: {
      map_return_pending: true,
    },
  }), true);
});

test("shouldResumeMapPosition resumes when returning from battle", () => {
  assert.equal(shouldResumeMapPosition({}, {
    return_route: "map",
    resume_map: true,
  }), true);
});

test("shouldResumeMapPosition does not resume for fresh map entry", () => {
  assert.equal(shouldResumeMapPosition({
    menuState: {
      map_return_pending: false,
    },
  }), false);
});

test("deriveMapLaunchContext forces default map for fresh location entry", () => {
  assert.deepEqual(deriveMapLaunchContext({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B3",
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B3" },
      },
    },
  }, null, {
    entry_route: "location",
    fresh_start: true,
    map_id: "Alter_Cave_B1",
  }), {
    freshLocationEntry: true,
    resumeFromSavedPosition: false,
    returningFromBattle: false,
    requestedMapId: "Alter_Cave_B1",
  });
});

test("canOccupyTile rejects collision gids and bounds", () => {
  assert.equal(canOccupyTile(stubMap, 1, 1), true);
  assert.equal(canOccupyTile(stubMap, 0, 0), false);
  assert.equal(canOccupyTile(stubMap, -1, 1), false);
});

test("moveMapPosition advances only onto passable tiles", () => {
  const start = { current_map_id: "Alter_Cave_B1", tile_x: 1, tile_y: 1, steps_since_reset: 0 };
  const moved = moveMapPosition(stubMap, start, "down");
  assert.equal(moved.moved, true);
  assert.deepEqual(moved.nextState, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 2,
    steps_since_reset: 1,
  });

  const blocked = moveMapPosition(stubMap, moved.nextState, "left");
  assert.equal(blocked.moved, false);
  assert.equal(blocked.reason, "blocked");
});

test("findStandingObject returns exit on matching tile", () => {
  const mapWithExit = {
    ...stubMap,
    objects: [
      {
        type: "exit",
        name: "Alter Cave B2",
        x: 1,
        y: 2,
        target_map: "Alter_Cave_B2",
        target_spawn: { x: 7, y: 4 },
      },
    ],
  };

  assert.deepEqual(findStandingObject(mapWithExit, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 2,
  }), mapWithExit.objects[0]);
});

test("findAdjacentObject returns switch next to player", () => {
  const mapWithSwitch = {
    ...stubMap,
    objects: [
      { type: "switch", name: "switch1", x: 2, y: 1, switch_id: "switch1" },
    ],
  };

  assert.deepEqual(findAdjacentObject(mapWithSwitch, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
  }, (row) => row.type === "switch"), mapWithSwitch.objects[0]);
});

test("applySwitchStateToMap flips linked barrier gid between 1 and 49", () => {
  const mapWithBarrier = {
    ...stubMap,
    width: 3,
    height: 3,
    baseRows: [
      [1, 1, 1],
      [1, 49, 1],
      [1, 1, 1],
    ],
    rows: [
      [1, 1, 1],
      [1, 49, 1],
      [1, 1, 1],
    ],
    renderPadding: { top: 0, right: 0, bottom: 0, left: 0, fillGid: 1 },
    objects: [
      { type: "barrier", name: "switch1 barrier", x: 1, y: 1, trigger_by: "switch1" },
    ],
  };

  const toggled = applySwitchStateToMap(mapWithBarrier, { switch1: true });
  assert.equal(toggled.rows[1][1], 1);
  const reverted = applySwitchStateToMap(mapWithBarrier, { switch1: false });
  assert.equal(reverted.rows[1][1], 49);
});

test("toggleAdjacentSwitch toggles switch state and linked barrier", () => {
  const mapWithSwitch = {
    ...stubMap,
    width: 3,
    height: 3,
    baseRows: [
      [1, 1, 1],
      [1, 49, 1],
      [1, 1, 1],
    ],
    rows: [
      [1, 49, 1],
      [1, 49, 1],
      [1, 1, 1],
    ],
    renderPadding: { top: 0, right: 0, bottom: 0, left: 0, fillGid: 1 },
    objects: [
      { type: "switch", name: "switch1", x: 2, y: 1, switch_id: "switch1" },
      { type: "barrier", name: "switch1 barrier", x: 1, y: 1, trigger_by: "switch1" },
    ],
  };

  const result = toggleAdjacentSwitch(mapWithSwitch, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    switch_states: {},
  });

  assert.equal(result.toggled, true);
  assert.equal(result.enabled, true);
  assert.equal(result.mapState.switch_states.switch1, true);
  assert.equal(result.mapDefinition.rows[1][1], 1);
});

test("openAdjacentTreasure adds Potion to inventory and opens chest", () => {
  const mapWithTreasure = {
    ...stubMap,
    width: 3,
    height: 3,
    baseRows: [
      [1, 1, 1],
      [1, 1, 125],
      [1, 1, 1],
    ],
    rows: [
      [1, 1, 1],
      [1, 1, 125],
      [1, 1, 1],
    ],
    renderPadding: { top: 0, right: 0, bottom: 0, left: 0, fillGid: 1 },
    objects: [
      {
        type: "treasure",
        name: "treasure1",
        treasure_id: "treasure1",
        x: 2,
        y: 1,
        item_name: "Potion",
        inventory_bucket: "Anywhere",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { inventory: {} },
    menu_state: {},
  });

  assert.equal(result.opened, true);
  assert.equal(result.itemName, "Potion");
  assert.equal(result.mapDefinition.rows[1][2], 126);
  assert.equal(result.mapState.opened_treasures.treasure1, true);
  assert.equal(result.saveEnvelope.save.inventory.Anywhere.Potion, 1);
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

test("getEncounterRateForStep reduces rate for first five steps", () => {
  assert.equal(getEncounterRateForStep(stubMap, 0), 0.1);
  assert.equal(getEncounterRateForStep(stubMap, 1), 0.02);
  assert.equal(getEncounterRateForStep(stubMap, 5), 0.02);
  assert.equal(getEncounterRateForStep(stubMap, 6), 0.1);
});

test("shouldTriggerEncounter uses adjusted encounter threshold", () => {
  assert.equal(shouldTriggerEncounter(stubMap, 0.05, 1), false);
  assert.equal(shouldTriggerEncounter(stubMap, 0.01, 1), true);
  assert.equal(shouldTriggerEncounter(stubMap, 0.05, 6), true);
  assert.equal(shouldTriggerEncounter(stubMap, 0.5, 6), false);
});
