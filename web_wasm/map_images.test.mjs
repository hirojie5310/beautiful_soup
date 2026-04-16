import test from "node:test";
import assert from "node:assert/strict";

import { locationGroupToMapKey } from "./map_images.js";

test("locationGroupToMapKey strips apostrophes to match map asset names", () => {
  assert.equal(locationGroupToMapKey("Ancient's Maze"), "ancients_maze");
  assert.equal(locationGroupToMapKey("Tozus's Tunnel"), "tozuss_tunnel");
});
