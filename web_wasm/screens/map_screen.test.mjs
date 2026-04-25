import test from "node:test";
import assert from "node:assert/strict";

import {
  applySwitchStateToMap,
  createDirectionalHoldRepeater,
  canNpcOccupyTile,
  deriveMapLaunchContext,
  canOccupyTile,
  deriveInitialMapState,
  findAdjacentTileWithGid,
  findAdjacentObject,
  findAdjacentNpc,
  findBlockingObjectAt,
  findCrystalSpriteOrigin,
  isAdjacentToCrystalSprite,
  interpolateMapPosition,
  findStandingObject,
  moveMapPosition,
  normalizeCharacterJobKey,
  normalizeMergedFixedContent,
  normalizeNpcMovement,
  normalizeNpcDirection,
  openAdjacentTreasure,
  chooseNextNpcDirection,
  resolveNpcFacingScale,
  resolveNpcNextDirectionDelay,
  resolveNpcSpriteFrame,
  resolveCharacterSpriteFrame,
  resolveLeaderCharacterSprite,
  resolveLeaderCharacterSpriteUrl,
  resolveNpcInitialDirection,
  resolveInitialMapSelection,
  shouldCloseEventOverlayOnConfirm,
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

test("resolveCharacterSpriteFrame maps first-row walking frames and mirrors right", () => {
  assert.deepEqual(resolveCharacterSpriteFrame("up", 0), {
    frameIndex: 0,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("up", 1), {
    frameIndex: 1,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("left", 0), {
    frameIndex: 2,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("left", 1), {
    frameIndex: 3,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("down", 0), {
    frameIndex: 4,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("down", 1), {
    frameIndex: 5,
    facingScale: 1,
  });
  assert.deepEqual(resolveCharacterSpriteFrame("right", 1), {
    frameIndex: 3,
    facingScale: -1,
  });
});

test("resolveNpcSpriteFrame maps six-column NPC sheets", () => {
  assert.equal(resolveNpcSpriteFrame("up", 0), 0);
  assert.equal(resolveNpcSpriteFrame("up", 1), 1);
  assert.equal(resolveNpcSpriteFrame("left", 0), 2);
  assert.equal(resolveNpcSpriteFrame("left", 1), 3);
  assert.equal(resolveNpcSpriteFrame("right", 0), 2);
  assert.equal(resolveNpcSpriteFrame("right", 1), 3);
  assert.equal(resolveNpcSpriteFrame("down", 0), 4);
  assert.equal(resolveNpcSpriteFrame("down", 1), 5);
  assert.equal(resolveNpcSpriteFrame("unknown", 0), 4);
});

test("resolveNpcFacingScale mirrors left-facing frames for right-facing NPCs", () => {
  assert.equal(resolveNpcFacingScale("right"), -1);
  assert.equal(resolveNpcFacingScale("left"), 1);
  assert.equal(resolveNpcFacingScale("up"), 1);
  assert.equal(resolveNpcFacingScale("down"), 1);
});

test("chooseNextNpcDirection switches to a different supported direction", () => {
  assert.equal(chooseNextNpcDirection("up", 0), "left");
  assert.equal(chooseNextNpcDirection("up", 0.99), "down");
  assert.equal(chooseNextNpcDirection("left", 0), "up");
  assert.equal(chooseNextNpcDirection("", 0.99), "down");
});

test("resolveNpcNextDirectionDelay returns a few-second random delay", () => {
  assert.equal(resolveNpcNextDirectionDelay(0), 3000);
  assert.equal(resolveNpcNextDirectionDelay(1), 6000);
  assert.equal(resolveNpcNextDirectionDelay(0.5), 4500);
});

test("NPC movement config supports fixed facing and random movement", () => {
  assert.equal(normalizeNpcMovement("random"), "random");
  assert.equal(normalizeNpcMovement("fixed"), "fixed");
  assert.equal(normalizeNpcMovement(""), "fixed");
  assert.equal(normalizeNpcDirection("right"), "right");
  assert.equal(normalizeNpcDirection("bad", "down"), "down");
  assert.equal(resolveNpcInitialDirection({ direction: "left" }, 0.99), "left");
  assert.equal(resolveNpcInitialDirection({ movement: "random" }, 0.99), "down");
});

test("normalizeCharacterJobKey builds sprite lookup keys from job names", () => {
  assert.equal(normalizeCharacterJobKey("Sage"), "sage");
  assert.equal(normalizeCharacterJobKey("Mystic Knight"), "mystic-knight");
  assert.equal(normalizeCharacterJobKey("Devil's Knight"), "devils-knight");
});

test("resolveLeaderCharacterSpriteUrl prefers leader job and falls back to onion knight", () => {
  assert.match(resolveLeaderCharacterSpriteUrl({
    menuState: {
      party: [{ name: "Runeth", job: "Sage" }],
    },
  }), /\/assets\/images\/characters\/fs_sage\.png$/);

  assert.match(resolveLeaderCharacterSpriteUrl({
    menuState: {
      party: [{ name: "Runeth", current_job: "Mystic Knight", job: "Sage" }],
    },
  }), /\/assets\/images\/characters\/fs_mystic_knight\.png$/);

  assert.match(resolveLeaderCharacterSpriteUrl({
    menuState: {
      party: [{ name: "Runeth", job: "Bard" }],
    },
  }), /\/assets\/images\/characters\/fs_bard\.png$/);

  assert.match(resolveLeaderCharacterSpriteUrl({
    menuState: { party: [] },
    saveEnvelope: {
      save: {
        party: [{ name: "Runeth", job: "Sage" }],
      },
    },
  }), /\/assets\/images\/characters\/fs_sage\.png$/);

  assert.match(resolveLeaderCharacterSpriteUrl({
    menuState: {
      party: [{ name: "Runeth", job: "Unknown Job" }],
    },
  }), /\/assets\/images\/characters\/fs_onion_knight\.png$/);
});

test("resolveLeaderCharacterSprite returns sheet row metadata per sprite", () => {
  assert.deepEqual({
    ...resolveLeaderCharacterSprite({
      menuState: {
        party: [{ name: "Runeth", job: "Sage" }],
      },
    }),
    url: "sage.png",
  }, {
    rows: 1,
    url: "sage.png",
  });

  assert.deepEqual({
    ...resolveLeaderCharacterSprite({
      menuState: {
        party: [{ name: "Runeth", job: "Onion Knight" }],
      },
    }),
    url: "onion_knight.png",
  }, {
    rows: 4,
    url: "onion_knight.png",
  });
});

test("deriveInitialMapState ignores stale saved map id on fresh location entry", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 9,
        tile_y: 9,
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B2", x: 4, y: 5 },
      },
    },
  }, {
    ...stubMap,
    id: "Alter_Cave_B3",
    spawn: { x: 9, y: 23 },
  });

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B3",
    tile_x: 9,
    tile_y: 23,
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

test("deriveInitialMapState resumes menu map position ahead of save map position", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B4",
        tile_x: 16,
        tile_y: 26,
        steps_since_reset: 7,
        switch_states: { switch1: true },
        opened_treasures: { chest1: true },
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B3", x: 9, y: 23 },
      },
    },
  }, {
    ...stubMap,
    id: "Alter_Cave_B4",
    spawn: { x: 24, y: 27 },
  }, {
    resumeFromSavedPosition: true,
  });

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B4",
    tile_x: 16,
    tile_y: 26,
    steps_since_reset: 7,
    switch_states: { switch1: true },
    opened_treasures: { chest1: true },
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

test("confirm button closes event overlay while event text is open", () => {
  assert.equal(shouldCloseEventOverlayOnConfirm(true), true);
  assert.equal(shouldCloseEventOverlayOnConfirm(false), false);
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

test("deriveMapLaunchContext prefers battle return map for map resume", () => {
  assert.deepEqual(deriveMapLaunchContext({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B2",
      },
      map_return_pending: true,
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B1" },
      },
    },
  }, {
    return_route: "map",
    resume_map: true,
    map_id: "Alter_Cave_B4",
  }, null), {
    freshLocationEntry: false,
    resumeFromSavedPosition: true,
    returningFromBattle: true,
    requestedMapId: "Alter_Cave_B4",
  });
});

test("deriveMapLaunchContext falls back to menu map when returning from menu", () => {
  assert.deepEqual(deriveMapLaunchContext({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B3",
      },
      map_return_pending: true,
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B1" },
      },
    },
  }, null, null), {
    freshLocationEntry: false,
    resumeFromSavedPosition: true,
    returningFromBattle: false,
    requestedMapId: "Alter_Cave_B3",
  });
});

test("resolveInitialMapSelection prefers the current map-linked location when resuming from menu", () => {
  assert.deepEqual(resolveInitialMapSelection({
    selectedLocationGroup: "Ancient's Maze",
    selectedLocation: "Crystal Room",
  }, stubMap, {
    resumeFromSavedPosition: true,
    returningFromBattle: false,
  }), {
    selected_location_group: "Altar Cave",
    selected_location: "Altar Cave B1",
  });
});

test("resolveInitialMapSelection keeps explicit location on fresh entry", () => {
  assert.deepEqual(resolveInitialMapSelection({
    selectedLocationGroup: "Altar Cave",
    selectedLocation: "Altar Cave B3",
  }, stubMap, {
    resumeFromSavedPosition: false,
    returningFromBattle: false,
  }), {
    selected_location_group: "Altar Cave",
    selected_location: "Altar Cave B3",
  });
});

test("canOccupyTile rejects collision gids and bounds", () => {
  assert.equal(canOccupyTile(stubMap, 1, 1), true);
  assert.equal(canOccupyTile(stubMap, 0, 0), false);
  assert.equal(canOccupyTile(stubMap, -1, 1), false);
});

test("canOccupyTile rejects blocking NPC object tiles", () => {
  const mapWithNpc = {
    ...stubMap,
    objects: [
      { type: "npc", name: "Villager", x: 1, y: 1, dialogue_index: 493 },
      { type: "npc", name: "Ghost", x: 2, y: 2, dialogue_index: 494, blocking: false },
    ],
  };

  assert.deepEqual(findBlockingObjectAt(mapWithNpc, 1, 1), mapWithNpc.objects[0]);
  assert.equal(findBlockingObjectAt(mapWithNpc, 2, 2), null);
  assert.equal(canOccupyTile(mapWithNpc, 1, 1), false);
  assert.equal(canOccupyTile(mapWithNpc, 2, 2), true);
});

test("canNpcOccupyTile ignores itself but avoids player and blocking NPCs", () => {
  const walker = { type: "npc", name: "Walker", x: 1, y: 1, dialogue_index: 501 };
  const mapWithNpc = {
    ...stubMap,
    objects: [
      walker,
      { type: "npc", name: "Guard", x: 2, y: 2, dialogue_index: 502 },
      { type: "exit", name: "Door", x: 1, y: 2 },
    ],
  };

  assert.equal(canNpcOccupyTile(mapWithNpc, walker, { tile_x: 0, tile_y: 0 }, 1, 1), true);
  assert.equal(canNpcOccupyTile(mapWithNpc, walker, { tile_x: 1, tile_y: 2 }, 2, 1), false);
  assert.equal(canNpcOccupyTile(mapWithNpc, walker, { tile_x: 0, tile_y: 0 }, 2, 2), false);
  assert.equal(canNpcOccupyTile(mapWithNpc, walker, { tile_x: 0, tile_y: 0 }, 1, 2), false);
  assert.equal(canNpcOccupyTile(mapWithNpc, walker, { tile_x: 0, tile_y: 0 }, 0, 1), false);
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

test("interpolateMapPosition returns intermediate fractional tile positions", () => {
  assert.deepEqual(
    interpolateMapPosition({ x: 3, y: 4 }, { x: 4, y: 6 }, 0.25),
    { x: 3.25, y: 4.5 },
  );
});

test("interpolateMapPosition clamps progress to the animation range", () => {
  assert.deepEqual(
    interpolateMapPosition({ x: 3, y: 4 }, { x: 4, y: 6 }, -1),
    { x: 3, y: 4 },
  );
  assert.deepEqual(
    interpolateMapPosition({ x: 3, y: 4 }, { x: 4, y: 6 }, 2),
    { x: 4, y: 6 },
  );
});

test("createDirectionalHoldRepeater runs immediately, repeats while held, and stops cleanly", () => {
  const steps = [];
  const timeouts = [];
  const intervals = [];
  let nextId = 1;
  const scheduler = {
    setTimeout(callback, delay) {
      const id = nextId += 1;
      timeouts.push({ id, callback, delay });
      return id;
    },
    clearTimeout(id) {
      const hit = timeouts.find((entry) => entry.id === id);
      if (hit) hit.cleared = true;
    },
    setInterval(callback, delay) {
      const id = nextId += 1;
      intervals.push({ id, callback, delay });
      return id;
    },
    clearInterval(id) {
      const hit = intervals.find((entry) => entry.id === id);
      if (hit) hit.cleared = true;
    },
  };
  const repeater = createDirectionalHoldRepeater((direction) => {
    steps.push(direction);
  }, scheduler, {
    initialDelay: 200,
    repeatInterval: 90,
  });

  assert.equal(repeater.start("right"), true);
  assert.deepEqual(steps, ["right"]);
  assert.equal(timeouts.length, 1);
  assert.equal(timeouts[0].delay, 200);

  timeouts[0].callback();
  assert.equal(intervals.length, 1);
  assert.equal(intervals[0].delay, 90);

  intervals[0].callback();
  intervals[0].callback();
  assert.deepEqual(steps, ["right", "right", "right"]);
  assert.equal(repeater.isActive("right"), true);

  assert.equal(repeater.stop("right"), true);
  assert.equal(timeouts[0].cleared, true);
  assert.equal(intervals[0].cleared, true);
  assert.equal(repeater.isActive(), false);

  intervals[0].callback();
  assert.deepEqual(steps, ["right", "right", "right"]);
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

test("findAdjacentNpc returns neighboring NPC with dialogue index", () => {
  const mapWithNpc = {
    ...stubMap,
    objects: [
      { type: "npc", name: "Villager", x: 2, y: 1, dialogue_index: 493 },
      { type: "npc", name: "Silent", x: 1, y: 0 },
    ],
  };

  assert.deepEqual(findAdjacentNpc(mapWithNpc, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
  }), mapWithNpc.objects[0]);
});

test("normalizeMergedFixedContent strips merged_fixed control notation for map dialogue", () => {
  assert.equal(
    normalizeMergedFixedContent("'>-\n    \\n\\t[0x04]こんにちは\\nまたね'\n"),
    "こんにちは\nまたね",
  );
});

test("findAdjacentTileWithGid detects a matching neighboring tile", () => {
  const mapWithSpecialTile = {
    ...stubMap,
    rows: [
      [1, 1, 1],
      [1, 5, 36],
      [1, 1, 1],
    ],
  };

  assert.deepEqual(findAdjacentTileWithGid(mapWithSpecialTile, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
  }, 36), { x: 1, y: 0 });

  assert.equal(findAdjacentTileWithGid(mapWithSpecialTile, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 0,
    tile_y: 0,
  }, 36), null);
});

test("findCrystalSpriteOrigin locates the crystal sprite anchor in the crystal room", () => {
  const crystalRoomMap = {
    id: "Alter_Cave_Crystal_Room",
    width: 4,
    height: 4,
    rows: [
      [1, 1, 1, 1],
      [1, 125, 1, 1],
      [1, 7, 1, 1],
      [1, 1, 1, 1],
    ],
  };

  assert.deepEqual(findCrystalSpriteOrigin(crystalRoomMap), { x: 1, y: 1 });
  assert.equal(findCrystalSpriteOrigin({ ...crystalRoomMap, id: "Alter_Cave_B1" }), null);
});

test("isAdjacentToCrystalSprite accepts either half of the crystal column", () => {
  const crystalRoomMap = {
    id: "Alter_Cave_Crystal_Room",
    width: 4,
    height: 5,
    rows: [
      [1, 1, 1, 1],
      [1, 125, 1, 1],
      [1, 7, 1, 1],
      [1, 1, 1, 1],
      [1, 1, 1, 1],
    ],
  };

  assert.equal(isAdjacentToCrystalSprite(crystalRoomMap, { tile_x: 0, tile_y: 1 }), true);
  assert.equal(isAdjacentToCrystalSprite(crystalRoomMap, { tile_x: 2, tile_y: 2 }), true);
  assert.equal(isAdjacentToCrystalSprite(crystalRoomMap, { tile_x: 1, tile_y: 3 }), true);
  assert.equal(isAdjacentToCrystalSprite(crystalRoomMap, { tile_x: 0, tile_y: 3 }), false);
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

test("openAdjacentTreasure stores Magic treasure under inventory level buckets", () => {
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
      [1, 1, 125],
      [1, 1, 125],
      [1, 1, 1],
    ],
    renderPadding: { top: 0, right: 0, bottom: 0, left: 0, fillGid: 1 },
    objects: [
      {
        type: "treasure",
        name: "treasure_magic",
        treasure_id: "treasure_magic",
        x: 2,
        y: 1,
        item_name: "Sleep",
        inventory_bucket: "Magic",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Alter_Cave_B2",
    tile_x: 1,
    tile_y: 1,
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { inventory: {} },
    menu_state: {},
  }, {
    Sleep: 1,
  });

  assert.equal(result.opened, true);
  assert.equal(result.saveEnvelope.save.inventory.Magic.LV1.Sleep, 1);
  assert.equal(result.mapState.opened_treasures.treasure_magic, true);
});

test("openAdjacentTreasure leaves chest closed when Magic treasure level is unknown", () => {
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
        name: "treasure_magic_unknown",
        treasure_id: "treasure_magic_unknown",
        x: 2,
        y: 1,
        item_name: "Sleep",
        inventory_bucket: "Magic",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Alter_Cave_B2",
    tile_x: 1,
    tile_y: 1,
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { inventory: {} },
    menu_state: {},
  });

  assert.equal(result.opened, false);
  assert.equal(result.inventoryError, true);
  assert.equal(result.mapState.opened_treasures?.treasure_magic_unknown, undefined);
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
