import test from "node:test";
import assert from "node:assert/strict";

import { rebuildMagicCandidatesForMember } from "./job_screen.js";

test("rebuildMagicCandidatesForMember allows Red Mage to use equipped Cure", () => {
  const rows = rebuildMagicCandidatesForMember({
    member: {
      mp_levels: {
        "1": { current: 3, max: 3 },
      },
    },
    equippedByLevel: {
      "1": ["Fire", "Cure", null],
    },
    selectedJobName: "Red Mage",
    magicSpellMetaByName: {
      Fire: { type: "Black Magic", level: 1 },
      Cure: { type: "White Magic", level: 1 },
    },
    jobMagicAllowedNamesByJob: {
      "Red Mage": ["Fire", "Cure"],
    },
  });

  assert.deepEqual(rows.map((row) => row.name), ["Fire", "Cure"]);
  assert.equal(rows[1].remaining_uses, 3);
  assert.equal(rows[1].group_label, "LV1 (3/3)");
});

test("rebuildMagicCandidatesForMember filters out spells disallowed by the new job", () => {
  const rows = rebuildMagicCandidatesForMember({
    member: {
      mp_levels: {
        "1": { current: 2, max: 3 },
      },
    },
    equippedByLevel: {
      "1": ["Fire", "Cure", null],
    },
    selectedJobName: "Black Mage",
    magicSpellMetaByName: {
      Fire: { type: "Black Magic", level: 1 },
      Cure: { type: "White Magic", level: 1 },
    },
    jobMagicAllowedNamesByJob: {
      "Black Mage": ["Fire"],
    },
  });

  assert.deepEqual(rows.map((row) => row.name), ["Fire"]);
});
