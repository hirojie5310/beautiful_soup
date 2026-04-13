import test from "node:test";
import assert from "node:assert/strict";

import { findPartyMemberIndex } from "./shared_party.js";
import { syncSavePartyRecovery } from "./location_shared.js";
import { applyJobChangeToSaveEntry } from "./job_persistence.js";

test("findPartyMemberIndex matches members by identity instead of display order", () => {
  const saveParty = [
    { name: "Refia", portrait_key: "refia" },
    { name: "Runeth", portrait_key: "runeth" },
  ];
  const displayedMember = { name: "Runeth", portrait_key: "runeth", index: 0 };

  assert.equal(findPartyMemberIndex(saveParty, displayedMember, 0), 1);
});

test("syncSavePartyRecovery clears the matched member even when save order differs", () => {
  const save = {
    party: [
      {
        name: "Refia",
        portrait_key: "refia",
        hp: 10,
        max_hp: 100,
        status_effects: { Petrification: true, KO: true },
      },
      {
        name: "Runeth",
        portrait_key: "runeth",
        hp: 1,
        max_hp: 80,
        status_effects: { Petrification: true, KO: true },
      },
    ],
  };
  const recoveredParty = [
    {
      name: "Runeth",
      portrait_key: "runeth",
      index: 0,
      hp: 80,
      max_hp: 80,
      mp_levels: {},
    },
  ];

  syncSavePartyRecovery(save, recoveredParty);

  assert.deepEqual(save.party[0].status_effects, { Petrification: true, KO: true });
  assert.deepEqual(save.party[1].status_effects, { Petrification: false, KO: false });
  assert.equal(save.party[1].hp, 80);
});

test("job persistence updates the matched save entry when save order differs", () => {
  const saveParty = [
    {
      name: "Refia",
      portrait_key: "refia",
      job: "White Mage",
      current_job: "White Mage",
      job_level: { level: 4, skill_point: 0 },
      job_levels: {
        "White Mage": { level: 4, skill_point: 0 },
      },
    },
    {
      name: "Runeth",
      portrait_key: "runeth",
      job: "Monk",
      current_job: "Monk",
      job_level: { level: 7, skill_point: 0 },
      job_levels: {
        Monk: { level: 7, skill_point: 0 },
        Dragoon: { level: 3, skill_point: 0 },
      },
    },
  ];
  const displayedMember = {
    name: "Runeth",
    portrait_key: "runeth",
    index: 0,
  };
  const saveIndex = findPartyMemberIndex(saveParty, displayedMember, 0);

  saveParty[saveIndex] = applyJobChangeToSaveEntry(saveParty[saveIndex], {
    currentJob: "Monk",
    nextJob: "Dragoon",
    currentJobLevel: 7,
    currentJobSkillPoint: 0,
    nextJobLevel: 3,
    nextJobSkillPoint: 0,
  });

  assert.equal(saveParty[0].job, "White Mage");
  assert.equal(saveParty[1].job, "Dragoon");
  assert.equal(saveParty[1].current_job, "Dragoon");
});
