import test from "node:test";
import assert from "node:assert/strict";

import { createNewGameSaveData } from "./title_screen_state.js";

test("createNewGameSaveData builds FF3 new game defaults", () => {
  const save = createNewGameSaveData();

  assert.equal(save.schema_version, 2);
  assert.equal(save.gil, 0);
  assert.equal(save.CP, 0);
  assert.deepEqual(save.inventory, {});
  assert.deepEqual(save.item_stock, {});
  assert.deepEqual(save.event_flag, {});
  assert.deepEqual(save.treasures, {});
  assert.equal(save.party.length, 4);

  save.party.forEach((member) => {
    assert.equal(member.level, 1);
    assert.equal(member.exp, 0);
    assert.equal(member.job, "Onion Knight");
    assert.equal(member.current_job, "Onion Knight");
    assert.deepEqual(member.job_level, { level: 1, skill_point: 0 });
    assert.deepEqual(member.job_levels, {
      "Onion Knight": { level: 1, skill_point: 0 },
    });
    assert.equal(Object.hasOwn(member, "hp"), false);
    assert.equal(Object.hasOwn(member, "max_hp"), false);
    assert.deepEqual(member.Magic, {
      LV1: [null, null, null],
      LV2: [null, null, null],
      LV3: [null, null, null],
      LV4: [null, null, null],
      LV5: [null, null, null],
      LV6: [null, null, null],
      LV7: [null, null, null],
      LV8: [null, null, null],
    });
    assert.equal(member.row, "front");
    assert.deepEqual(member.equipment, {
      main_hand: "Knife",
      off_hand: null,
      head: null,
      body: "Vest",
      arms: null,
    });
    assert.equal(member.status_effects.Poison, false);
    assert.equal(member.status_effects.KO, false);
    assert.equal(member.mp_levels["1"].current, 0);
    assert.equal(member.mp_levels["8"].max, 0);
  });
});
