import test from "node:test";
import assert from "node:assert/strict";

import { normalizeMapDefinition } from "./map_data.js";

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
