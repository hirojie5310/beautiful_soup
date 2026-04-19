import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_BATTLE_RETURN_CONTEXT,
  resolveMountedBattleReturnContext,
} from "./battle_context.js";

test("resolveMountedBattleReturnContext prefers fresh session context over stale in-memory context", () => {
  const result = resolveMountedBattleReturnContext(
    { return_route: "map", resume_map: true, map_id: "Alter_Cave_B1" },
    { return_route: "location", resume_map: false },
  );

  assert.deepEqual(result, {
    return_route: "map",
    resume_map: true,
    map_id: "Alter_Cave_B1",
  });
});

test("resolveMountedBattleReturnContext falls back to default location return when no context exists", () => {
  const result = resolveMountedBattleReturnContext(null, null);

  assert.deepEqual(result, { ...DEFAULT_BATTLE_RETURN_CONTEXT });
});
