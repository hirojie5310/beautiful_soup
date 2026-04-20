import test from "node:test";
import assert from "node:assert/strict";

import { deriveMenuMapOpenRequest, hydrateMenuStateFromEnvelope } from "./menu_screen.js";

test("deriveMenuMapOpenRequest resumes directly to the current map when menu return is pending", () => {
  const result = deriveMenuMapOpenRequest({
    menuState: {
      map_return_pending: true,
      map_state: {
        current_map_id: "Alter_Cave_B3",
      },
    },
    saveEnvelope: {
      save: {
        map: {
          map: "Alter_Cave_B1",
        },
      },
    },
  });

  assert.deepEqual(result, {
    requestedMapId: "Alter_Cave_B3",
    resumeToCurrentMap: true,
  });
});

test("deriveMenuMapOpenRequest falls back to compatibility-checked map open when return is not pending", () => {
  const result = deriveMenuMapOpenRequest({
    menuState: {
      map_return_pending: false,
    },
    saveEnvelope: {
      save: {
        map: {
          map: "Alter_Cave_B2",
        },
      },
    },
  });

  assert.deepEqual(result, {
    requestedMapId: "Alter_Cave_B2",
    resumeToCurrentMap: false,
  });
});

test("deriveMenuMapOpenRequest falls back to default map when no map state exists", () => {
  const result = deriveMenuMapOpenRequest({
    menuState: {},
    saveEnvelope: {
      save: {},
    },
  });

  assert.deepEqual(result, {
    requestedMapId: "Alter_Cave_B1",
    resumeToCurrentMap: false,
  });
});

test("hydrateMenuStateFromEnvelope preserves map return context while filling party data", () => {
  const result = hydrateMenuStateFromEnvelope({
    map_return_pending: true,
    map_state: {
      current_map_id: "Alter_Cave_B4",
      tile_x: 12,
      tile_y: 8,
      steps_since_reset: 3,
    },
    party: [],
    resources: { cp: 0, cp_max: 255, gil: 0 },
  }, {
    save: {
      gil: 123,
      party: [{ name: "Refia", level: 10, hp: 80, max_hp: 100, row: "front" }],
      map: { map: "Alter_Cave_B1", x: 1, y: 1 },
    },
    menu_state: {
      party: [{ name: "Refia", level: 10, hp: 80, max_hp: 100, row: "front" }],
      resources: { cp: 7, cp_max: 255, gil: 123 },
      map_state: {
        current_map_id: "Alter_Cave_B1",
        tile_x: 1,
        tile_y: 1,
        steps_since_reset: 0,
      },
    },
  });

  assert.equal(result.map_return_pending, true);
  assert.deepEqual(result.map_state, {
    current_map_id: "Alter_Cave_B4",
    tile_x: 12,
    tile_y: 8,
    steps_since_reset: 3,
  });
  assert.ok(Array.isArray(result.party));
  assert.ok(result.party.length >= 1);
});

test("hydrateMenuStateFromEnvelope uses envelope map state when current menu state has no map context", () => {
  const result = hydrateMenuStateFromEnvelope({
    party: [],
    resources: { cp: 0, cp_max: 255, gil: 0 },
  }, {
    save: {
      gil: 321,
      party: [{ name: "Arc", level: 8, hp: 60, max_hp: 70, row: "back" }],
      map: { map: "Alter_Cave_B2", x: 5, y: 14 },
    },
    menu_state: {
      party: [{ name: "Arc", level: 8, hp: 60, max_hp: 70, row: "back" }],
      resources: { cp: 11, cp_max: 255, gil: 321 },
      map_state: {
        current_map_id: "Alter_Cave_B2",
        tile_x: 5,
        tile_y: 14,
        steps_since_reset: 2,
      },
      map_return_pending: true,
    },
  });

  assert.equal(result.map_return_pending, true);
  assert.deepEqual(result.map_state, {
    current_map_id: "Alter_Cave_B2",
    tile_x: 5,
    tile_y: 14,
    steps_since_reset: 2,
  });
});
