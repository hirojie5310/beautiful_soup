import test from "node:test";
import assert from "node:assert/strict";

import { applyMagicSetupToSaveParty } from "./magic_screen.js";

test("applyMagicSetupToSaveParty writes equipped magic rows into save entries", () => {
  const saveParty = [
    { name: "Refia", magic: { LV1: ["Old", null, null] } },
    { name: "Arc" },
  ];
  const equippedByMember = [
    {
      "1": ["Fire", "Cure", null],
      "2": [null, "Thunder", null],
    },
    {
      "1": [null, null, null],
      "8": ["Bahamut", null, null],
    },
  ];

  applyMagicSetupToSaveParty(saveParty, equippedByMember);

  assert.deepEqual(saveParty[0].Magic.LV1, ["Fire", "Cure", null]);
  assert.deepEqual(saveParty[0].Magic.LV2, [null, "Thunder", null]);
  assert.equal("magic" in saveParty[0], false);
  assert.deepEqual(saveParty[1].Magic.LV8, ["Bahamut", null, null]);
  assert.deepEqual(saveParty[1].Magic.LV3, [null, null, null]);
});
