import test from "node:test";
import assert from "node:assert/strict";

import {
  applySwitchStateToMap,
  applyDialogueCharacterName,
  createDirectionalHoldRepeater,
  canNpcOccupyTile,
  canAirshipOccupyTile,
  buildMergedFixedContentPages,
  deriveMapLaunchContext,
  canOccupyTile,
  deriveInitialMapState,
  findAdjacentTileWithGid,
  findAdjacentObject,
  findAdjacentNpc,
  findBlockingObjectAt,
  findCrystalSpriteOrigin,
  findStandingEventTrigger,
  configureLoopingMapBgm,
  findShopActivation,
  isPlayerInCanoe,
  isAdjacentToCrystalSprite,
  isMapObjectAvailable,
  isAdjacentToTileCoordinate,
  isCastleSasuneMainKeep1FRecoveryTile,
  isStandingOnTileCoordinate,
  isCastleSasuneTowerEast4FRecoveryTile,
  isFloatingContinentMap,
  isUrInnItemShopRecoveryTile,
  interpolateMapPosition,
  findStandingObject,
  isWaterAnimationGid,
  moveMapPosition,
  moveAirshipPosition,
  normalizeCharacterJobKey,
  normalizeMergedFixedContent,
  normalizeNpcMovement,
  normalizeNpcDirection,
  npcDialogueIndices,
  npcObjectKey,
  openAdjacentTreasure,
  applyPendingGuardedTreasureReward,
  chooseNextNpcDirection,
  resolveNpcFacingScale,
  resolveNpcNextDirectionDelay,
  resolveNpcSpriteFrame,
  resolveCidFollowerDialogueIndex,
  resolveSaraFollowerDialogueIndex,
  reviveZeroHpPartyMembersToOneHp,
  resolveCharacterSpriteFrame,
  resolveAirshipUpperSprite,
  resolveFloatingContinentLocationFromPosition,
  resolveFloatingContinentSpawn,
  resolveCanoeSpriteFrame,
  resolveLeaderCharacterSprite,
  resolveLeaderCharacterSpriteUrl,
  resolveMapBgmUrl,
  resolveMapVisualPosition,
  resolveNpcDialogueIndicesForInteraction,
  resolveNpcInitialDirection,
  resolveInitialMapSelection,
  resolveTransitionSpawn,
  shouldTriggerFloatingContinentBigRockCrash,
  shouldRenderGuestFollowerOnMap,
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

function makeFloatingContinentMap() {
  const width = 131;
  const height = 132;
  const rows = Array.from({ length: height }, () => Array.from({ length: width }, () => 1));
  rows[74][70] = 31;
  return {
    ...stubMap,
    id: "FloatingContinent",
    name: "Floating Continent",
    width,
    height,
    spawn: { x: 95, y: 39 },
    locationRequirement: {
      group: "Floating Continent",
      locations: [],
    },
    rows,
    collisionGids: new Set([31]),
  };
}

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

test("deriveInitialMapState restores opened treasures from save data on fresh entry", () => {
  const result = deriveInitialMapState({
    saveEnvelope: {
      save: {
        treasures: {
          Alter_Cave_B1: {
            treasure1: true,
          },
        },
      },
    },
  }, stubMap);

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    steps_since_reset: 0,
    switch_states: {},
    opened_treasures: {
      treasure1: true,
    },
  });
});

test("deriveInitialMapState merges save treasures with resumed menu state", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 2,
        tile_y: 2,
        opened_treasures: {
          treasure2: true,
        },
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "Alter_Cave_B1", x: 2, y: 2 },
        treasures: {
          Alter_Cave_B1: {
            treasure1: true,
          },
        },
      },
    },
  }, stubMap, { resumeFromSavedPosition: true });

  assert.deepEqual(result, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 2,
    tile_y: 2,
    facing_direction: "down",
    steps_since_reset: 0,
    switch_states: {},
    opened_treasures: {
      treasure1: true,
      treasure2: true,
    },
  });
});

test("deriveInitialMapState restores airship state on Floating Continent after obtainment", () => {
  const result = deriveInitialMapState({
    menuState: {
      map_state: {
        current_map_id: "FloatingContinent",
        tile_x: 91,
        tile_y: 60,
        airship_riding: true,
      },
      airship_state: {
        tile_x: 91,
        tile_y: 60,
        riding: true,
      },
    },
    saveEnvelope: {
      save: {
        map: { map: "FloatingContinent", x: 91, y: 60 },
        event_flag: {
          cid_airship_obtained: true,
        },
      },
    },
  }, {
    ...stubMap,
    id: "FloatingContinent",
    spawn: { x: 90, y: 59 },
  }, {
    resumeFromSavedPosition: true,
  });

  assert.equal(result.airship_riding, true);
  assert.equal(result.airship_tile_x, 91);
  assert.equal(result.airship_tile_y, 60);
});

test("resolveFloatingContinentSpawn returns per-location spawn coordinates", () => {
  assert.deepEqual(resolveFloatingContinentSpawn("Floating Continent Near Castle Argus"), {
    x: 53,
    y: 54,
  });
  assert.deepEqual(resolveFloatingContinentSpawn("Floating Continent Near Lake Dohr"), {
    x: 25,
    y: 51,
  });
  assert.deepEqual(resolveFloatingContinentSpawn("unknown", { x: 1, y: 2 }), {
    x: 1,
    y: 2,
  });
});

test("deriveInitialMapState uses selected Floating Continent location spawn", () => {
  const result = deriveInitialMapState({
    selectedLocationGroup: "Floating Continent",
    selectedLocation: "Floating Continent Near Lake Dohr",
    menuState: {},
    saveEnvelope: {
      save: {
        event_flag: {},
      },
    },
  }, makeFloatingContinentMap());

  assert.equal(result.tile_x, 25);
  assert.equal(result.tile_y, 51);
});

test("deriveInitialMapState places Floating Continent airship left of spawn after obtainment", () => {
  const result = deriveInitialMapState({
    selectedLocationGroup: "Floating Continent",
    selectedLocation: "Floating Continent Near Castle Argus",
    menuState: {},
    saveEnvelope: {
      save: {
        event_flag: {
          cid_airship_obtained: true,
        },
      },
    },
  }, makeFloatingContinentMap());

  assert.equal(result.tile_x, 53);
  assert.equal(result.tile_y, 54);
  assert.equal(result.airship_riding, false);
  assert.equal(result.airship_tile_x, 52);
  assert.equal(result.airship_tile_y, 54);
});

test("deriveInitialMapState starts on the airship for Floating Continent seas", () => {
  const result = deriveInitialMapState({
    selectedLocationGroup: "Floating Continent",
    selectedLocation: "Floating Continent Seas",
    menuState: {},
    saveEnvelope: {
      save: {
        event_flag: {
          cid_airship_obtained: true,
        },
      },
    },
  }, makeFloatingContinentMap());

  assert.equal(result.tile_x, 70);
  assert.equal(result.tile_y, 74);
  assert.equal(result.airship_riding, true);
  assert.equal(result.airship_tile_x, 70);
  assert.equal(result.airship_tile_y, 74);
});

test("deriveInitialMapState does not restore the airship after it is destroyed", () => {
  const result = deriveInitialMapState({
    selectedLocationGroup: "Floating Continent",
    selectedLocation: "Floating Continent Near Castle Argus",
    menuState: {},
    saveEnvelope: {
      save: {
        event_flag: {
          cid_airship_obtained: true,
          cid_airship_destroyed: true,
        },
      },
    },
  }, makeFloatingContinentMap());

  assert.equal(result.airship_riding, undefined);
  assert.equal(result.airship_tile_x, undefined);
  assert.equal(result.airship_tile_y, undefined);
});

test("resolveFloatingContinentLocationFromPosition maps coordinates to area-specific encounters", () => {
  const floatingMap = makeFloatingContinentMap();

  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 95, tile_y: 39 }),
    "Floating Continent Near Ur",
  );
  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 53, tile_y: 54 }),
    "Floating Continent Near Castle Argus",
  );
  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 38, tile_y: 44 }),
    "Floating Continent North of Gulgan Gulch",
  );
  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 25, tile_y: 51 }),
    "Floating Continent Near Lake Dohr",
  );
  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 70, tile_y: 74 }),
    "Floating Continent Seas",
  );
  assert.equal(
    resolveFloatingContinentLocationFromPosition(floatingMap, { tile_x: 57, tile_y: 84 }),
    "Floating Continent Near desert",
  );
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

test("resolveCanoeSpriteFrame maps horizontal and vertical rowing frames", () => {
  assert.deepEqual(resolveCanoeSpriteFrame("left", 0), {
    frameIndex: 0,
    facingScale: 1,
  });
  assert.deepEqual(resolveCanoeSpriteFrame("right", 1), {
    frameIndex: 1,
    facingScale: 1,
  });
  assert.deepEqual(resolveCanoeSpriteFrame("up", 0), {
    frameIndex: 2,
    facingScale: 1,
  });
  assert.deepEqual(resolveCanoeSpriteFrame("down", 1), {
    frameIndex: 3,
    facingScale: 1,
  });
});

test("resolveAirshipUpperSprite selects directional flight frames", () => {
  assert.deepEqual(resolveAirshipUpperSprite("up"), {
    startFrame: 2,
    endFrame: 3,
    facingScale: 1,
  });
  assert.deepEqual(resolveAirshipUpperSprite("left"), {
    startFrame: 4,
    endFrame: 5,
    facingScale: 1,
  });
  assert.deepEqual(resolveAirshipUpperSprite("right"), {
    startFrame: 4,
    endFrame: 5,
    facingScale: -1,
  });
  assert.deepEqual(resolveAirshipUpperSprite("down"), {
    startFrame: 6,
    endFrame: 7,
    facingScale: 1,
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

test("npcObjectKey keeps duplicate dialogue NPCs distinct and stable after movement", () => {
  const cursedNpc = {
    name: "Castle Sasune MainKeep 4F NPC 540",
    dialogue_index: 540,
    x: 6,
    y: 5,
    movement: "random",
    sprite_image: "../assets/images/NPCs/fs_cursed.png",
  };
  const guardNpc = {
    name: "Castle Sasune MainKeep 4F Soldier 540",
    dialogue_index: 540,
    x: 6,
    y: 5,
    movement: "fixed",
    sprite_image: "../assets/images/NPCs/fs_soldier1.png",
  };

  const cursedKey = npcObjectKey(cursedNpc);
  const guardKey = npcObjectKey(guardNpc);

  assert.notEqual(cursedKey, guardKey);

  cursedNpc.x = 7;
  cursedNpc.y = 5;
  assert.equal(npcObjectKey(cursedNpc), cursedKey);
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
    facing_direction: "down",
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
    facing_direction: "down",
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

test("canOccupyTile allows Floating Continent canoe water after the canoe is obtained", () => {
  const floatingWaterMap = {
    ...stubMap,
    id: "FloatingContinent",
    width: 2,
    height: 2,
    rows: [
      [1, 1],
      [1, 9],
    ],
    collisionGids: new Set([9]),
  };

  assert.equal(canOccupyTile(floatingWaterMap, 1, 1), false);
  assert.equal(canOccupyTile(floatingWaterMap, 1, 1, {
    save: {
      event_flag: {
        canoe_obtained: true,
      },
    },
  }), true);
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

test("canOccupyTile and canAirshipOccupyTile reject blocking decoration objects", () => {
  const mapWithBlockingDecoration = {
    ...stubMap,
    rows: [
      [1, 1, 1],
      [1, 1, 1],
      [1, 1, 1],
    ],
    collisionGids: new Set(),
    objects: [
      {
        type: "decoration",
        name: "Big Rock",
        x: 1,
        y: 1,
        blocking: true,
      },
    ],
  };
  assert.deepEqual(findBlockingObjectAt(mapWithBlockingDecoration, 1, 1), mapWithBlockingDecoration.objects[0]);
  assert.equal(canOccupyTile(mapWithBlockingDecoration, 1, 1), false);
  assert.equal(canAirshipOccupyTile(mapWithBlockingDecoration, 1, 1), false);
  assert.equal(canAirshipOccupyTile(mapWithBlockingDecoration, 2, 2), true);
});

test("resolveTransitionSpawn preserves explicit exit targets within map bounds", () => {
  const result = resolveTransitionSpawn(stubMap, { x: 0, y: 0 });

  assert.deepEqual(result, { x: 0, y: 0 });
});

test("resolveTransitionSpawn falls back to map spawn when explicit target is out of bounds", () => {
  const result = resolveTransitionSpawn(stubMap, { x: 99, y: 99 });

  assert.deepEqual(result, { x: 1, y: 1 });
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

test("canAirshipOccupyTile blocks only non-corner Floating Continent mountain tiles", () => {
  const map = {
    ...stubMap,
    width: 3,
    height: 2,
    rows: [
      [6, 7, 8],
      [38, 39, 40],
    ],
  };

  assert.equal(canAirshipOccupyTile(map, 0, 0), true);
  assert.equal(canAirshipOccupyTile(map, 2, 0), true);
  assert.equal(canAirshipOccupyTile(map, 0, 1), true);
  assert.equal(canAirshipOccupyTile(map, 2, 1), true);
  assert.equal(canAirshipOccupyTile(map, 1, 0), false);
  assert.equal(canAirshipOccupyTile(map, 1, 1), false);
});

test("moveMapPosition advances only onto passable tiles", () => {
  const start = { current_map_id: "Alter_Cave_B1", tile_x: 1, tile_y: 1, steps_since_reset: 0 };
  const moved = moveMapPosition(stubMap, start, "down");
  assert.equal(moved.moved, true);
  assert.deepEqual(moved.nextState, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 2,
    facing_direction: "down",
    steps_since_reset: 1,
  });

  const blocked = moveMapPosition(stubMap, moved.nextState, "left");
  assert.equal(blocked.moved, false);
  assert.equal(blocked.reason, "blocked");
  assert.equal(blocked.nextState.facing_direction, "left");
});

test("moveMapPosition enters Floating Continent canoe water after the canoe is obtained", () => {
  const floatingWaterMap = {
    ...stubMap,
    id: "FloatingContinent",
    width: 2,
    height: 2,
    rows: [
      [1, 1],
      [1, 9],
    ],
    collisionGids: new Set([9]),
  };
  const start = { current_map_id: "FloatingContinent", tile_x: 1, tile_y: 0, steps_since_reset: 0 };

  const blocked = moveMapPosition(floatingWaterMap, start, "down");
  assert.equal(blocked.moved, false);

  const moved = moveMapPosition(floatingWaterMap, start, "down", {
    save: {
      event_flag: {
        canoe_obtained: true,
      },
    },
  });
  assert.equal(moved.moved, true);
  assert.equal(moved.nextState.tile_x, 1);
  assert.equal(moved.nextState.tile_y, 1);
});

test("isPlayerInCanoe becomes true only on Floating Continent canoe water after obtainment", () => {
  const floatingWaterMap = {
    ...stubMap,
    id: "FloatingContinent",
    width: 2,
    height: 2,
    rows: [
      [1, 1],
      [1, 25],
    ],
    collisionGids: new Set([25]),
  };
  assert.equal(isPlayerInCanoe(floatingWaterMap, { tile_x: 1, tile_y: 1 }, null), false);
  assert.equal(isPlayerInCanoe(floatingWaterMap, { tile_x: 1, tile_y: 1 }, {
    save: {
      event_flag: {
        canoe_obtained: true,
      },
    },
  }), true);
});

test("shouldRenderGuestFollowerOnMap hides followers while riding a canoe", () => {
  const floatingWaterMap = {
    ...stubMap,
    id: "FloatingContinent",
    width: 2,
    height: 2,
    rows: [
      [1, 1],
      [1, 25],
    ],
    collisionGids: new Set([25]),
  };
  const cidFollowerSave = {
    save: {
      event_flag: {
        canoe_obtained: true,
        kazus_cid_follower_joined: true,
      },
    },
  };
  assert.equal(
    shouldRenderGuestFollowerOnMap(floatingWaterMap, { tile_x: 1, tile_y: 1 }, cidFollowerSave),
    false,
  );
  assert.equal(
    shouldRenderGuestFollowerOnMap(floatingWaterMap, { tile_x: 0, tile_y: 0 }, cidFollowerSave),
    true,
  );
});

test("moveAirshipPosition advances while updating airship coordinates", () => {
  const map = {
    ...stubMap,
    id: "FloatingContinent",
    width: 3,
    height: 3,
    rows: [
      [1, 1, 1],
      [1, 1, 1],
      [1, 1, 1],
    ],
  };
  const result = moveAirshipPosition(map, {
    current_map_id: "FloatingContinent",
    tile_x: 1,
    tile_y: 1,
    airship_tile_x: 1,
    airship_tile_y: 1,
    airship_riding: true,
    facing_direction: "down",
    steps_since_reset: 0,
  }, "right", {
    save: {
      event_flag: {
        cid_airship_obtained: true,
      },
    },
  });

  assert.equal(result.moved, true);
  assert.equal(result.nextState.tile_x, 2);
  assert.equal(result.nextState.tile_y, 1);
  assert.equal(result.nextState.airship_tile_x, 2);
  assert.equal(result.nextState.airship_tile_y, 1);
});

test("shouldTriggerFloatingContinentBigRockCrash requires the upgraded airship route conditions", () => {
  const floatingMap = { id: "FloatingContinent" };
  const ridingState = {
    current_map_id: "FloatingContinent",
    tile_x: 81,
    tile_y: 54,
    airship_riding: true,
  };
  const saveEnvelope = {
    save: {
      event_flag: {
        cid_airship_obtained: true,
        sara_left_party: true,
        kazus_cid_follower_joined: true,
        kazus_blacksmith_mythril_ram_complete: true,
      },
    },
  };
  assert.equal(
    shouldTriggerFloatingContinentBigRockCrash(floatingMap, ridingState, 82, 54, saveEnvelope),
    true,
  );
  assert.equal(
    shouldTriggerFloatingContinentBigRockCrash(floatingMap, ridingState, 82, 54, {
      save: { event_flag: { cid_airship_obtained: true, sara_left_party: true } },
    }),
    false,
  );
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

test("resolveMapVisualPosition prefers interpolated coordinates and falls back per axis", () => {
  assert.deepEqual(
    resolveMapVisualPosition({ x: 7.5 }, { x: 3, y: 4 }),
    { x: 7.5, y: 4 },
  );
  assert.deepEqual(
    resolveMapVisualPosition(null, { x: 3, y: 4 }),
    { x: 3, y: 4 },
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

test("resolveSaraFollowerDialogueIndex uses the scripted sequence before switching to random followups", () => {
  assert.equal(resolveSaraFollowerDialogueIndex(0, 0.9), 122);
  assert.equal(resolveSaraFollowerDialogueIndex(1, 0.9), 123);
  assert.equal(resolveSaraFollowerDialogueIndex(2, 0.9), 124);
  assert.equal(resolveSaraFollowerDialogueIndex(3, 0.9), 125);
  assert.equal(resolveSaraFollowerDialogueIndex(4, 0.0), 123);
  assert.equal(resolveSaraFollowerDialogueIndex(5, 0.5), 124);
  assert.equal(resolveSaraFollowerDialogueIndex(6, 0.99), 125);
});

test("resolveCidFollowerDialogueIndex uses the first line once, then random followups", () => {
  assert.equal(resolveCidFollowerDialogueIndex(0, 0.9), 108);
  assert.equal(resolveCidFollowerDialogueIndex(1, 0.0), 109);
  assert.equal(resolveCidFollowerDialogueIndex(2, 0.5), 110);
  assert.equal(resolveCidFollowerDialogueIndex(3, 0.99), 112);
  assert.equal(resolveCidFollowerDialogueIndex(1, 0.0, true), 112);
  assert.equal(resolveCidFollowerDialogueIndex(5, 0.5, true), 112);
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

test("findStandingEventTrigger resolves hidden standing events until completion flag is set", () => {
  const mapWithEvent = {
    ...stubMap,
    objects: [
      {
        type: "event",
        name: "Alter Cave Intro",
        x: 1,
        y: 2,
        dialogue_indices: [8],
        required_event_flag_absent: "altar_cave_b3_intro_complete",
        hidden: true,
      },
    ],
  };

  assert.deepEqual(
    findStandingEventTrigger(mapWithEvent, {
      current_map_id: "Alter_Cave_B3",
      tile_x: 1,
      tile_y: 2,
    }, {
      save: {
        event_flag: {},
      },
    }),
    mapWithEvent.objects[0],
  );

  assert.equal(
    findStandingEventTrigger(mapWithEvent, {
      current_map_id: "Alter_Cave_B3",
      tile_x: 1,
      tile_y: 2,
    }, {
      save: {
        event_flag: {
          altar_cave_b3_intro_complete: true,
        },
      },
    }),
    null,
  );
});

test("isMapObjectAvailable respects required event flags", () => {
  assert.equal(isMapObjectAvailable({
    type: "exit",
    required_event_flag: "airship_revealed",
  }, {
    save: {
      event_flag: {},
    },
  }), false);

  assert.equal(isMapObjectAvailable({
    type: "exit",
    required_event_flag: "airship_revealed",
    required_event_flag_absent: "airship_taken",
  }, {
    save: {
      event_flag: {
        airship_revealed: true,
      },
    },
  }), true);

  assert.equal(isMapObjectAvailable({
    type: "exit",
    required_event_flag: "airship_revealed",
    required_event_flag_absent: "airship_taken",
  }, {
    save: {
      event_flag: {
        airship_revealed: true,
        airship_taken: true,
      },
    },
  }), false);
});

test("findStandingObject ignores gated exits until flags are enabled", () => {
  const mapWithConditionalExit = {
    ...stubMap,
    objects: [
      {
        type: "exit",
        name: "Airship of Cid",
        x: 1,
        y: 2,
        required_event_flag: "airship_revealed",
      },
    ],
  };

  assert.equal(findStandingObject(mapWithConditionalExit, {
    current_map_id: "FloatingContinent",
    tile_x: 1,
    tile_y: 2,
  }, {
    save: {
      event_flag: {},
    },
  }), null);

  assert.deepEqual(findStandingObject(mapWithConditionalExit, {
    current_map_id: "FloatingContinent",
    tile_x: 1,
    tile_y: 2,
  }, {
    save: {
      event_flag: {
        airship_revealed: true,
      },
    },
  }), mapWithConditionalExit.objects[0]);
});

test("findAdjacentObject returns object in front of player", () => {
  const mapWithSwitch = {
    ...stubMap,
    objects: [
      { type: "switch", name: "switch1", x: 2, y: 1, switch_id: "switch1" },
      { type: "switch", name: "switch2", x: 1, y: 2, switch_id: "switch2" },
    ],
  };

  assert.deepEqual(findAdjacentObject(mapWithSwitch, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
  }, (row) => row.type === "switch"), mapWithSwitch.objects[0]);
  assert.equal(findAdjacentObject(mapWithSwitch, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "up",
  }, (row) => row.type === "switch"), null);
});

test("findAdjacentNpc returns NPC in facing direction with dialogue index", () => {
  const mapWithNpc = {
    ...stubMap,
    objects: [
      { type: "npc", name: "Villager", x: 2, y: 1, dialogue_index: 493 },
      { type: "npc", name: "Silent", x: 1, y: 0, dialogue_index: 494 },
    ],
  };

  assert.deepEqual(findAdjacentNpc(mapWithNpc, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
  }), mapWithNpc.objects[0]);
  assert.deepEqual(findAdjacentNpc(mapWithNpc, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "up",
  }), mapWithNpc.objects[1]);
});

test("findAdjacentNpc respects facing direction with dialogue indices", () => {
  const mapWithNpc = {
    ...stubMap,
    objects: [
      { type: "npc", name: "Elder", x: 2, y: 1, dialogue_indices: [505, 506, 507] },
      { type: "npc", name: "Silent", x: 1, y: 0 },
    ],
  };

  assert.deepEqual(findAdjacentNpc(mapWithNpc, {
    current_map_id: "Alter_Cave_B1",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
  }), mapWithNpc.objects[0]);
  assert.deepEqual(npcDialogueIndices(mapWithNpc.objects[0]), [505, 506, 507]);
});

test("isAdjacentToTileCoordinate checks only neighboring map tiles", () => {
  assert.equal(isAdjacentToTileCoordinate({ tile_x: 2, tile_y: 9 }, { x: 3, y: 9 }), true);
  assert.equal(isAdjacentToTileCoordinate({ tile_x: 3, tile_y: 8 }, { x: 3, y: 9 }), true);
  assert.equal(isAdjacentToTileCoordinate({ tile_x: 3, tile_y: 9 }, { x: 3, y: 9 }), false);
  assert.equal(isAdjacentToTileCoordinate({ tile_x: 1, tile_y: 9 }, { x: 3, y: 9 }), false);
});

test("isStandingOnTileCoordinate checks the exact map tile", () => {
  assert.equal(isStandingOnTileCoordinate({ tile_x: 7, tile_y: 8 }, { x: 7, y: 8 }), true);
  assert.equal(isStandingOnTileCoordinate({ tile_x: 7, tile_y: 9 }, { x: 7, y: 8 }), false);
});

test("isUrInnItemShopRecoveryTile resolves inn recovery floor tiles", () => {
  assert.equal(isUrInnItemShopRecoveryTile({ id: "Ur_Inn_ItemShop" }, { tile_x: 7, tile_y: 8 }), true);
  assert.equal(isUrInnItemShopRecoveryTile({ id: "Ur_Inn_ItemShop" }, { tile_x: 9, tile_y: 8 }), true);
  assert.equal(isUrInnItemShopRecoveryTile({ id: "Ur_Inn_ItemShop" }, { tile_x: 8, tile_y: 8 }), false);
  assert.equal(isUrInnItemShopRecoveryTile({ id: "Ur" }, { tile_x: 7, tile_y: 8 }), false);
});

test("isCastleSasuneMainKeep1FRecoveryTile resolves bed recovery tiles", () => {
  assert.equal(isCastleSasuneMainKeep1FRecoveryTile({ id: "Castle_Sasune_MainKeep_1F" }, { tile_x: 1, tile_y: 4 }), true);
  assert.equal(isCastleSasuneMainKeep1FRecoveryTile({ id: "Castle_Sasune_MainKeep_1F" }, { tile_x: 3, tile_y: 4 }), true);
  assert.equal(isCastleSasuneMainKeep1FRecoveryTile({ id: "Castle_Sasune_MainKeep_1F" }, { tile_x: 2, tile_y: 4 }), false);
  assert.equal(isCastleSasuneMainKeep1FRecoveryTile({ id: "Castle_Sasune" }, { tile_x: 1, tile_y: 4 }), false);
});

test("isCastleSasuneTowerEast4FRecoveryTile resolves the bed recovery tile", () => {
  assert.equal(isCastleSasuneTowerEast4FRecoveryTile({ id: "Castle_Sasune_Tower_East_4F" }, { tile_x: 4, tile_y: 3 }), true);
  assert.equal(isCastleSasuneTowerEast4FRecoveryTile({ id: "Castle_Sasune_Tower_East_4F" }, { tile_x: 4, tile_y: 4 }), false);
  assert.equal(isCastleSasuneTowerEast4FRecoveryTile({ id: "Castle_Sasune_Tower_East_3F" }, { tile_x: 4, tile_y: 3 }), false);
});

test("findShopActivation resolves tiles adjacent to Ur shop counters", () => {
  assert.deepEqual(findShopActivation({ id: "Ur_ArmorShop" }, { tile_x: 3, tile_y: 6 }), {
    mapId: "Ur_ArmorShop",
    x: 3,
    y: 5,
    shopMap: "Ur",
    shopType: "Armor",
  });
  assert.deepEqual(findShopActivation({ id: "Ur_MagicShop" }, { tile_x: 4, tile_y: 5 }), {
    mapId: "Ur_MagicShop",
    x: 4,
    y: 4,
    shopMap: "Ur",
    shopType: "Magic",
  });
  assert.deepEqual(findShopActivation({ id: "Ur_WeaponShop" }, { tile_x: 3, tile_y: 5 }), {
    mapId: "Ur_WeaponShop",
    x: 3,
    y: 4,
    shopMap: "Ur",
    shopType: "Weapons",
  });
  assert.deepEqual(findShopActivation({ id: "Ur_Inn_ItemShop" }, { tile_x: 8, tile_y: 14 }), {
    mapId: "Ur_Inn_ItemShop",
    x: 8,
    y: 15,
    shopMap: "Ur",
    shopType: "Items",
  });
  assert.equal(findShopActivation({ id: "Ur_ArmorShop" }, { tile_x: 3, tile_y: 5 }), null);
  assert.equal(findShopActivation({ id: "Ur_ArmorShop" }, { tile_x: 2, tile_y: 4 }), null);
});

test("findShopActivation resolves tiles adjacent to Kazus shopkeepers", () => {
  assert.deepEqual(findShopActivation({ id: "Kazus_ArmorShop" }, { tile_x: 3, tile_y: 6 }), {
    mapId: "Kazus_ArmorShop",
    x: 3,
    y: 5,
    shopMap: "Kazus",
    shopType: "Armor",
  });
  assert.deepEqual(findShopActivation({ id: "Kazus_MagicShop" }, { tile_x: 4, tile_y: 5 }), {
    mapId: "Kazus_MagicShop",
    x: 4,
    y: 4,
    shopMap: "Kazus",
    shopType: "Magic",
  });
  assert.deepEqual(findShopActivation({ id: "Kazus_WeaponShop" }, { tile_x: 3, tile_y: 5 }), {
    mapId: "Kazus_WeaponShop",
    x: 3,
    y: 4,
    shopMap: "Kazus",
    shopType: "Weapons",
  });
  assert.deepEqual(findShopActivation({ id: "Kazus_Inn_ItemShop_1F" }, { tile_x: 13, tile_y: 7 }), {
    mapId: "Kazus_Inn_ItemShop_1F",
    x: 13,
    y: 6,
    shopMap: "Kazus",
    shopType: "Items",
  });
  assert.equal(findShopActivation({ id: "Kazus_ArmorShop" }, { tile_x: 3, tile_y: 5 }), null);
  assert.equal(findShopActivation({ id: "Kazus_MagicShop" }, { tile_x: 6, tile_y: 4 }), null);
});

test("reviveZeroHpPartyMembersToOneHp revives only KO members and clears KO status", () => {
  const save = {
    party: [
      { name: "Luneth", hp: 0, max_hp: 20, status_icons: ["ko", "poison"], status_effects: { KO: true, Poison: true } },
      { name: "Arc", hp: 5, max_hp: 18, status_icons: ["poison"], status_effects: { Poison: true } },
    ],
  };
  const menuState = {
    party: [
      { name: "Luneth", hp: 0, max_hp: 20, status_icons: ["ko"], status: { hp: 0, status_icons: ["ko"], status_line: "KO" } },
      { name: "Arc", hp: 5, max_hp: 18, status_icons: ["poison"], status: { hp: 5, status_icons: ["poison"], status_line: "poison" } },
    ],
  };

  assert.equal(reviveZeroHpPartyMembersToOneHp(save, menuState), 1);
  assert.equal(save.party[0].hp, 1);
  assert.deepEqual(save.party[0].status_icons, ["poison"]);
  assert.deepEqual(save.party[0].status_effects, { KO: false, Poison: true });
  assert.equal(save.party[1].hp, 5);
  assert.equal(menuState.party[0].hp, 1);
  assert.deepEqual(menuState.party[0].status_icons, []);
  assert.deepEqual(menuState.party[0].status.status_icons, []);
  assert.equal(menuState.party[0].status.status_line, "-");
  assert.equal(menuState.party[1].hp, 5);
});

test("normalizeMergedFixedContent strips merged_fixed control notation for map dialogue", () => {
  assert.equal(
    normalizeMergedFixedContent("'>-\n    \\n\\t[0x04]こんにちは\\nまたね'\n"),
    "こんにちは\nまたね",
  );
});

test("applyDialogueCharacterName replaces xchar with the first party member name", () => {
  assert.equal(
    applyDialogueCharacterName("サラ「\\xcharたちが　ついてるもの。", [{ name: "Runeth" }]),
    "サラ「Runethたちが　ついてるもの。",
  );
});

test("applyDialogueCharacterName replaces char1[0x02] through char4[0x02] with party member names", () => {
  assert.equal(
    applyDialogueCharacterName(
      "\\char1[0x02]　\\char2[0x02]　\\char3[0x02]　\\char4[0x02]",
      [{ name: "Runeth" }, { name: "Arc" }, { name: "Refia" }, { name: "Ingus" }],
    ),
    "Runeth　Arc　Refia　Ingus",
  );
});

test("applyDialogueCharacterName replaces char1[0x01] through char4[0x01] with job names", () => {
  assert.equal(
    applyDialogueCharacterName(
      "\\char1[0x01]　\\char2[0x01]　\\char3[0x01]　\\char4[0x01]",
      [
        { name: "Runeth", current_job: "Warrior" },
        { name: "Arc", current_job: "Red Mage" },
        { name: "Refia", current_job: "White Mage" },
        { name: "Ingus", current_job: "Monk" },
      ],
    ),
    "Warrior　Red Mage　White Mage　Monk",
  );
});

test("buildMergedFixedContentPages splits Castle Sasune king dialogue into four pages", () => {
  const pages = buildMergedFixedContentPages(544, `>-
    「わたしはサスーンのおう。　ジンの　のろいに\\n　よって　みな　ゆうれいのようなすがたに\\n　かえられてしまった。　ジンを　たおさぬかぎり\\n　もとの　すがたには　もどれぬ。\\n『ジンはどこに？\\n「しろのきたにある　ふういんのどうくつにいる。\\n　だが　ミスリルのゆびわが　なければ\\n　ジンを　ふたたび　ふういんすることはできぬ。\\n『サラひめが　もっていると……\\n「おお　そうだ！　むかし　カズスより　サラひめに\\n　ミスリルのゆびわが　おくられた。　だが\\n　かんじんの　サラが　どこにもみあたらん。\\n　もしや　ジンにさらわれたのでは？！\\n　おお　サラひめ……\\n『ふういんのどうくつに　いってみましょう。\\n「おお　せんしたちよ　よくぞいってくれた。\\n　たしか　ふういんのどうくつには　１かしょ\\n　かくしとびらが　ある。　がいこつが　かぎに\\n　なっていたはずだ……\\n\\n　たのむ！\\n　ジンをたおし　ひとびとをすくってくれ！！\\n
`);
  assert.equal(pages.length, 4);
  assert.match(pages[0], /^「わたしはサスーンのおう/);
  assert.match(pages[1], /^『ジンはどこに？/);
  assert.match(pages[2], /^『ふういんのどうくつに　いってみましょう。/);
  assert.match(pages[3], /^たのむ！/);
});

test("buildMergedFixedContentPages splits post-Djinn king dialogue into two pages", () => {
  const pages = buildMergedFixedContentPages(545, `>-
    ありがとう　せんしたちよ。\\nふたたび　ジンをふういんし\\nサラひめを　たすけだしてくれたこと\\nれいをいう。\\nこれを　もっていくといい。\\nなにかのやくにたつかもしれん。\\n\\nおうさまから　カヌーをもらった！\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^ありがとう　せんしたちよ。/);
  assert.match(pages[1], /^これを　もっていくといい。/);
});

test("buildMergedFixedContentPages splits Sara room dialogue into two pages", () => {
  const pages = buildMergedFixedContentPages(546, `>-
    サラ「わたしは　おとうさまの　そばについて\\n\\t[0x03]いなくてはなりません。\\n\\t[0x03]ほんとうは　あなたについていきたい……\\n\\t[0x03]でもきっと　あしでまといになってしまいますね……\\n『サラひめ……\\n「たびが　おわったら　かならず　かえってきて\\n　くださいね。\\n　わたし　まっています。\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^サラ「わたしは　おとうさまの　そばについて/);
  assert.match(pages[1], /^『サラひめ……/);
});

test("buildMergedFixedContentPages keeps ordinary dialogue as a single page", () => {
  assert.deepEqual(
    buildMergedFixedContentPages(541, "ふういんのどうくつにいる　モンスターは\\nアンデッドばかりです。"),
    ["ふういんのどうくつにいる　モンスターは\nアンデッドばかりです。"],
  );
});

test("buildMergedFixedContentPages splits Castle Sasune gate guard dialogue into two pages", () => {
  const pages = buildMergedFixedContentPages(538, `>-
    しろのひとは　みんなジンの　のろいによって\\nゆうれいのようなすがたに　されてしまいました。\\nわたしは　つかいで　でていたので\\nたすかったのです……\\nミスリルのゆびわがあれば　ジンをふたたび　\\nふういんできるのですが　ゆいいつ　ゆびわを\\nつくれる　カズスのむらも　おなじような\\nありさまで……\\nいったい　わたしはどうしたらいいのか……\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^しろのひとは　みんなジンの　のろいによって/);
  assert.match(pages[1], /^ミスリルのゆびわがあれば　ジンをふたたび/);
});

test("buildMergedFixedContentPages splits Ur elder guidance dialogue into four pages", () => {
  const pages = buildMergedFixedContentPages(506, `>-
    「わかっておる。　まさか　おまえたちが\\n　えらばれるとは　かんがえもしなかった。\\n　\\char1[0x02]　\\char2[0x02]\\n　\\char3[0x02]　\\char4[0x02]……\\n　これは　ぐうぜんの　せんたくではないことを\\n　まず　しらなければならない。\\n　クリスタルは　そのいしで　おまえたちを\\n　えらんだのだ。\\n　さあ　そのちからを……　おまえたちの\\n　ひかりのこころを　むだにしてはならない。\\n　たびだつのじゃ！\\n　そして　やみのちからを　ふうじるのだ。\\n
`, [{ name: "Runeth" }, { name: "Arc" }, { name: "Refia" }, { name: "Ingus" }]);
  assert.equal(pages.length, 4);
  assert.match(pages[0], /^「わかっておる。　まさか　おまえたちが/);
  assert.match(pages[1], /^Runeth　Arc/);
  assert.match(pages[1], /Refia　Ingus……$/);
  assert.match(pages[2], /^これは　ぐうぜんの　せんたくではないことを/);
  assert.match(pages[3], /^さあ　そのちからを……　おまえたちの/);
});

test("buildMergedFixedContentPages splits Cid dialogue in Kazus inn into three pages", () => {
  const pages = buildMergedFixedContentPages(532, `>-
    わしはシド。　カナーンからきたんじゃ。\\nネルブのたにが　おおいわでふさがれてしまい\\nカナーンに　かえるにかえれなくなってしまった。\\nそこでこのまちに　ひとばんの　やどを\\nもとめたのじゃが　このざまじゃ。　フォフォフォ！\\nどうだわかいの　わしの　ひくうていを　かして\\nやるから　なんとかしてくれんかのう？\\nにしのさばくにかくしてあるんじゃ。\\nシドから　ひくうていを　かくしたばしょを\\nきいた！\\nにしの　さばくだ！！\\n
`);
  assert.equal(pages.length, 3);
  assert.match(pages[0], /^わしはシド。　カナーンからきたんじゃ。/);
  assert.match(pages[1], /^もとめたのじゃが　このざまじゃ。/);
  assert.match(pages[2], /^シドから　ひくうていを　かくしたばしょを/);
});

test("buildMergedFixedContentPages replaces char1[0x01] through char4[0x01] with job names", () => {
  const pages = buildMergedFixedContentPages(510, `>-
    わしが　おまえたちの　ちからを　あててみせよう！\\nんー\\n……\\n……\\n\\char1[0x01]\\n\\char2[0x01]\\n\\char3[0x01]\\n\\char4[0x01]じゃな。　あたっているじゃろう！\\n
`, [
    { name: "Runeth", current_job: "Warrior" },
    { name: "Arc", current_job: "Red Mage" },
    { name: "Refia", current_job: "White Mage" },
    { name: "Ingus", current_job: "Monk" },
  ]);
  assert.deepEqual(pages, [
    "わしが　おまえたちの　ちからを　あててみせよう！\nんー\n……\n……\nWarrior\nRed Mage\nWhite Mage\nMonkじゃな。　あたっているじゃろう！",
  ]);
});

test("buildMergedFixedContentPages splits Sara dialogue in Sealed Cave into three pages", () => {
  const pages = buildMergedFixedContentPages(550, `>-
    「わたしはサラ……　サスーンおうのむすめです。\\n『サラひめ。　どうしてこんなところに？\\n「わたしは　ミスリルのゆびわを　つけていたので\\n　ジンの　のろいに　かからなかったのです。\\n　しろの　みんなを　たすけたくて　ここまで\\n　きたのだけれど　まものがいて　さきには\\n　すすめません……\\n\\n『ここは　きけんだ。\\n　サラひめは　しろでまっていてください。\\n「いいえ！いきます。\\n　ひとりでもいくわ！！\\n
`);
  assert.equal(pages.length, 3);
  assert.match(pages[0], /^「わたしはサラ……/);
  assert.match(pages[1], /^しろの　みんなを　たすけたくて/);
  assert.match(pages[2], /^『ここは　きけんだ。/);
});

test("buildMergedFixedContentPages splits Sara followup dialogue into two pages", () => {
  const pages = buildMergedFixedContentPages(551, `>-
    『こまった　おひめさまだ……\\n「おねがい　いっしょにつれていって！\\n　この　ミスリルのゆびわがなければ　ジンを\\n　ふういんすることはできません！\\n『しかたがないな……\\nサラひめが　パーティーにくわわった！\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^『こまった　おひめさまだ……/);
  assert.match(pages[1], /^『しかたがないな……/);
});

test("buildMergedFixedContentPages splits Djinn pre-battle dialogue into two pages", () => {
  const pages = buildMergedFixedContentPages(12, `>-
    なにも　おこらない。\\nジン「ファファファ……　いまの　おれさまには\\n\\t[0x03]そんなもの　つうようしないわ。\\n\\t[0x03]ぞうだいした　やみのちからが　おれに\\n\\t[0x03]みかたしているのだ！\\nジンがおそってきた！\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^なにも　おこらない。/);
  assert.match(pages[1], /^みかたしているのだ！/);
});

test("buildMergedFixedContentPages splits Djinn post-battle dialogue into three pages", () => {
  const pages = buildMergedFixedContentPages(14, `>-
    ジンは　きりのように　とけてきえた。\\nゆびわの　ちからによって　ふたたび　どうくつの\\nおくへと　ふういんされたのだ。\\n\\n「ありがとうございます。\\n　あなたがたのおかげで　ジンを　ふたたび\\n　ふういんすることができました。\\n\\n　あとは　このゆびわを　サスーンじょうの\\n　せいなるいずみにつければ　ジンの　のろいを\\n　とくことができます。　ゆびわのちからで\\n　サスーンじょうまで　ワープしましょう！\\n
`);
  assert.equal(pages.length, 3);
  assert.match(pages[0], /^ジンは　きりのように　とけてきえた。/);
  assert.match(pages[1], /^「ありがとうございます。/);
  assert.match(pages[2], /^あとは　このゆびわを　サスーンじょうの/);
});

test("buildMergedFixedContentPages splits Sara farewell dialogue into three pages", () => {
  const pages = buildMergedFixedContentPages(15, `>-
    サラひめは　ゆびわを　いずみになげた。\\n「さあ　これでジンの　のろいは　とけたはずです。\\n　ありがとう。　あなたがたの　おかげだわ。\\n　おわかれですね……わたしは　おとうさまの\\n　そばにいなくてはなりません。\\n　ほんとうは　ついていきたい……\\n　でもきっと　あしでまといに　なってしまいますね\\n『サラ……\\n「たびが　おわったら　かならず　かえってきて\\n　くださいね。　わたし　まっています。\\n　いつまでも……\\nサラと　わかれた……\\n
`);
  assert.equal(pages.length, 3);
  assert.match(pages[0], /^サラひめは　ゆびわを　いずみになげた。/);
  assert.match(pages[1], /^そばにいなくてはなりません。/);
  assert.match(pages[2], /^「たびが　おわったら　かならず　かえってきて/);
});

test("buildMergedFixedContentPages splits Cid join dialogue in Kazus into two pages", () => {
  const pages = buildMergedFixedContentPages(16, `>-
    よくやった！\\nさすが　わしが　みこんだだけのことはあるわい。\\nひくうていは　おまえさんたちが　やくにたてるのが\\n１ばんいいじゃろう。\\nそれより　わしを　ばあさんのまつ　カナーンの\\nむらまで　つれていってくれ。\\nなっ　たのむ！\\nシドじいさんが　パーティーにくわわった。\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^よくやった！/);
  assert.match(pages[1], /^それより　わしを　ばあさんのまつ　カナーンの/);
});

test("buildMergedFixedContentPages splits Kazus blacksmith intro into two pages", () => {
  const pages = buildMergedFixedContentPages(535, `>-
    シド「カナーンへいくために　ネルブのおおいわを\\n　　　くだこうとおもうのだが……\\n　　　ひくうていにミスリルせいの　せんしゅを\\n　　　つければなんとかなるかもしれん。\\nタカ「よーしまっておれ！　いま　つくってやる！！\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^シド「カナーンへいくために/);
  assert.match(pages[1], /^タカ「よーしまっておれ！　いま　つくってやる！！/);
});

test("buildMergedFixedContentPages splits Kazus blacksmith completion into two pages", () => {
  const pages = buildMergedFixedContentPages(536, `>-
    そーれ　おわったぞい！\\nなーに　れいはいらんよ。　むらを　すくって\\nくれたんじゃからの。　あたりまえじゃ。\\nそれでは　きをつけていきなされ！\\nタカじいさんが　ひくうていに\\nミスリルのせんしゅを　つけてくれた！\\nシド「よーし　ひくうていで　おおいわに\\n　　　たいあたりじゃ！！\\n
`);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^そーれ　おわったぞい！/);
  assert.match(pages[1], /^タカじいさんが　ひくうていに/);
});

test("buildMergedFixedContentPages splits Sara reunion dialogue in Castle Sasune into two pages", () => {
  const pages = buildMergedFixedContentPages(518, `>-
    おう「おお　サラひめ！　ぶじだったか！\\nサラ「まっていてね。　わたしのこのゆびわで\\n　　　ジンを　ふういんします！\\nおう「しんぱいじゃ……\\nサラ「だいじょうぶよ！\\n　　　\\xcharたちが　ついてるもの。　ねっ！\\n
`, [{ name: "Runeth" }, { name: "Arc" }, { name: "Refia" }, { name: "Ingus" }]);
  assert.equal(pages.length, 2);
  assert.match(pages[0], /^おう「おお　サラひめ！/);
  assert.match(pages[0], /おう「しんぱいじゃ……$/);
  assert.match(pages[1], /^サラ「だいじょうぶよ！/);
  assert.match(pages[1], /Runethたちが　ついてるもの。　ねっ！$/);
});

test("resolveNpcDialogueIndicesForInteraction swaps the Sasune king dialogue when Sara is following", () => {
  const npcRow = { x: 7, y: 4, dialogue_index: 544 };
  const mapDefinition = { id: "Castle_Sasune_MainKeep_4F" };

  assert.deepEqual(
    resolveNpcDialogueIndicesForInteraction(mapDefinition, npcRow, {
      save: {
        event_flag: {
          sealed_cave_b2_2_sara_escort_started: true,
        },
      },
    }),
    [518],
  );
  assert.deepEqual(
    resolveNpcDialogueIndicesForInteraction(mapDefinition, npcRow, {
      save: {
        event_flag: {
          sealed_cave_b2_2_sara_escort_started: true,
          sara_left_party: true,
        },
      },
    }),
    [544],
  );
});

test("water highlight animation covers town and Floating Continent water tiles", () => {
  [5, 6, 9, 10, 11, 14, 15, 16, 30, 31, 32, 43, 46, 47, 48].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid), true);
  });
  assert.equal(isWaterAnimationGid(94), false);
  [5, 31, 32].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "Ur", tileset: { name: "TILESET - Ur" } }), false);
  });
  [6, 9, 10, 11, 14, 15, 16, 30, 43, 46, 47, 48].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "Ur", tileset: { name: "TILESET - Ur" } }), true);
  });
  [15, 30, 31, 32].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "Kazus", tileset: { name: "TILESET - Kazus" } }), false);
  });
  [5, 6, 9, 10, 11, 14, 16, 43, 46, 47, 48].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "Kazus", tileset: { name: "TILESET - Kazus" } }), true);
  });
  [6, 43].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "FloatingContinent", tileset: { name: "TILESET - FloatingContinent" } }), false);
  });
  [25, 26, 59, 67].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "FloatingContinent", tileset: { name: "TILESET - FloatingContinent" } }), true);
  });
  [5, 9, 10, 11, 14, 15, 16, 30, 31, 32, 46, 47, 48].forEach((gid) => {
    assert.equal(isWaterAnimationGid(gid, { id: "FloatingContinent", tileset: { name: "TILESET - FloatingContinent" } }), true);
  });
});

test("Floating Continent BGM only targets the world map", () => {
  assert.equal(isFloatingContinentMap({ id: "FloatingContinent" }), true);
  assert.equal(isFloatingContinentMap({ id: "Ur", name: "Floating Continent" }), false);
});

test("resolveMapBgmUrl selects map themes by map id or location group", () => {
  assert.match(resolveMapBgmUrl({ id: "FloatingContinent", locationRequirement: {} }), /eternal-wind\.ogg$/);
  assert.match(decodeURI(resolveMapBgmUrl({ id: "Ur_Pub", locationRequirement: { group: "Ur" } })), /Hometown of Ur\.ogg$/);
  assert.match(resolveMapBgmUrl({ id: "Kazus", locationRequirement: { group: "Kazus" } }), /jinn-the-fire\.ogg$/);
  assert.match(resolveMapBgmUrl({ id: "Alter_Cave_B1", locationRequirement: { group: "Alter Cave" } }), /crystal-cave\.ogg$/);
  assert.match(resolveMapBgmUrl({ id: "Alter_Cave_B2", locationRequirement: { group: "Altar Cave" } }), /crystal-cave\.ogg$/);
  assert.equal(resolveMapBgmUrl({ id: "Unknown", locationRequirement: { group: "Castle Sasune" } }), "");
});

test("configureLoopingMapBgm prepares an audio element for repeated playback", () => {
  const listeners = new Map();
  const audioElement = {
    src: "",
    loop: false,
    preload: "",
    addEventListener(type, handler) {
      listeners.set(type, handler);
    },
  };

  assert.equal(configureLoopingMapBgm(audioElement, "/assets/sounds/bgm/eternal-wind.ogg"), audioElement);
  assert.equal(audioElement.src, "/assets/sounds/bgm/eternal-wind.ogg");
  assert.equal(audioElement.loop, false);
  assert.equal(audioElement.preload, "metadata");
  assert.equal(typeof listeners.get("ended"), "function");
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

test("applySwitchStateToMap supports custom barrier gids", () => {
  const mapWithBarrier = {
    ...stubMap,
    width: 3,
    height: 3,
    baseRows: [
      [1, 1, 1],
      [1, 112, 1],
      [1, 1, 1],
    ],
    rows: [
      [1, 1, 1],
      [1, 112, 1],
      [1, 1, 1],
    ],
    renderPadding: { top: 0, right: 0, bottom: 0, left: 0, fillGid: 1 },
    objects: [
      {
        type: "barrier",
        name: "custom barrier",
        x: 1,
        y: 1,
        trigger_by: "switch1",
        closed_gid: 112,
        open_gid: 68,
      },
    ],
  };

  const toggled = applySwitchStateToMap(mapWithBarrier, { switch1: true });
  assert.equal(toggled.rows[1][1], 68);
  const reverted = applySwitchStateToMap(mapWithBarrier, { switch1: false });
  assert.equal(reverted.rows[1][1], 112);
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
    facing_direction: "right",
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
    facing_direction: "right",
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
  assert.equal(result.saveEnvelope.save.treasures.Alter_Cave_B1.treasure1, true);
});

test("openAdjacentTreasure adds GIL treasure to save and menu resources regardless of bucket", () => {
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
        name: "gil_treasure",
        treasure_id: "gil_treasure",
        x: 2,
        y: 1,
        item_name: "GIL",
        inventory_bucket: "Anywhere",
        quantity: 1000,
        closed_gid: 125,
        open_gid: 126,
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Castle_Sasune_MainKeep_1F",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { gil: 500, inventory: {} },
    menu_state: { resources: { cp: 0, cp_max: 255, gil: 500 } },
  });

  assert.equal(result.opened, true);
  assert.equal(result.itemName, "GIL");
  assert.equal(result.quantity, 1000);
  assert.equal(result.mapDefinition.rows[1][2], 126);
  assert.equal(result.saveEnvelope.save.gil, 1500);
  assert.equal(result.saveEnvelope.menu_state.resources.gil, 1500);
  assert.deepEqual(result.saveEnvelope.save.inventory, {});
  assert.equal(result.saveEnvelope.save.treasures.Castle_Sasune_MainKeep_1F.gil_treasure, true);
});

test("openAdjacentTreasure corrects mistaken treasure inventory buckets from item metadata", () => {
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
        name: "combat_treasure",
        treasure_id: "combat_treasure",
        x: 2,
        y: 1,
        item_name: "Antarctic Wind",
        inventory_bucket: "Anywhere",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Sealed_Cave_B3",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { gil: 0, inventory: {} },
    menu_state: { resources: { cp: 0, cp_max: 255, gil: 0 } },
  }, {
    spellLevelByName: {},
    itemTypeByName: { "Antarctic Wind": "Combat" },
    weaponNameSet: new Set(),
    armorNameSet: new Set(),
  });

  assert.equal(result.opened, true);
  assert.equal(result.saveEnvelope.save.inventory.Combat["Antarctic Wind"], 1);
  assert.equal(result.saveEnvelope.save.inventory.Anywhere, undefined);
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
    facing_direction: "right",
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
    facing_direction: "right",
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

test("openAdjacentTreasure starts guarded battle for guarded treasure chests", () => {
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
        name: "guarded_treasure",
        treasure_id: "guarded_treasure",
        x: 2,
        y: 1,
        item_name: "Wightslayer",
        inventory_bucket: "Weapon",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
        guarded_by: ["Griffon"],
      },
    ],
  };

  const result = openAdjacentTreasure(mapWithTreasure, {
    current_map_id: "Castle_Sasune_Tower_West_4F",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { inventory: {} },
    menu_state: {},
  });

  assert.equal(result.opened, false);
  assert.equal(result.guardedBattle, true);
  assert.deepEqual(result.enemyNames, ["Griffon"]);
  assert.deepEqual(result.pendingTreasureContext, {
    map_id: "Castle_Sasune_Tower_West_4F",
    treasure_key: "guarded_treasure",
  });
});

test("applyPendingGuardedTreasureReward opens guarded treasure after victory", () => {
  const mapWithTreasure = {
    ...stubMap,
    id: "Castle_Sasune_Tower_West_4F",
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
        name: "guarded_treasure",
        treasure_id: "guarded_treasure",
        x: 2,
        y: 1,
        item_name: "Wightslayer",
        inventory_bucket: "Weapon",
        quantity: 1,
        closed_gid: 125,
        open_gid: 126,
        guarded_by: ["Griffon"],
      },
    ],
  };

  const result = applyPendingGuardedTreasureReward(mapWithTreasure, {
    current_map_id: "Castle_Sasune_Tower_West_4F",
    tile_x: 1,
    tile_y: 1,
    facing_direction: "right",
    switch_states: {},
    opened_treasures: {},
  }, {
    save: { inventory: {} },
    menu_state: {},
  }, {
    map_id: "Castle_Sasune_Tower_West_4F",
    treasure_key: "guarded_treasure",
  });

  assert.equal(result.opened, true);
  assert.equal(result.itemName, "Wightslayer");
  assert.equal(result.mapDefinition.rows[1][2], 126);
  assert.equal(result.mapState.opened_treasures.guarded_treasure, true);
  assert.equal(result.saveEnvelope.save.inventory.Weapon.Wightslayer, 1);
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
