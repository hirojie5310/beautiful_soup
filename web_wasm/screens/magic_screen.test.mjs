import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFieldSpellEffect,
  applyMagicSetupToSaveParty,
  getSpellMeta,
  parseSpellStatusAilments,
  usableSpellNames,
} from "./magic_screen.js";

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

test("parseSpellStatusAilments splits comma-separated spell metadata", () => {
  assert.deepEqual(
    parseSpellStatusAilments("Blind, Confusion, Poison"),
    ["Blind", "Confusion", "Poison"],
  );
});

test("getSpellMeta resolves magic metadata by name", () => {
  const meta = getSpellMeta({
    Cure: { effect_category: "heal_hp", field_heal_hp: 50 },
  }, "Cure");

  assert.deepEqual(meta, { effect_category: "heal_hp", field_heal_hp: 50 });
});

test("usableSpellNames falls back to current job allowed names when candidate rows are stale", () => {
  const names = usableSpellNames({
    party: [{ job: "Red Mage", current_job: "Red Mage" }],
    magic_candidates_by_member: [[]],
    job_magic_allowed_names_by_job: {
      "Red Mage": ["Fire", "Cure"],
    },
  }, 0);

  assert.equal(names.has("Cure"), true);
  assert.equal(names.has("Fire"), true);
});

test("applyFieldSpellEffect heals from spell metadata", () => {
  const result = applyFieldSpellEffect(
    { mp_levels: { "1": { current: 3, max: 3 } } },
    { hp: 10, max_hp: 100, status_icons: [] },
    { effect_category: "heal_hp", field_heal_hp: 50 },
    1,
  );

  assert.equal(result.ok, true);
  assert.equal(result.target.hp, 60);
  assert.equal(result.caster.mp_levels["1"].current, 2);
});

test("applyFieldSpellEffect revives to full from metadata", () => {
  const result = applyFieldSpellEffect(
    { mp_levels: { "7": { current: 2, max: 2 } } },
    { hp: 0, max_hp: 120, status_icons: ["ko", "poison"] },
    { effect_category: "revive", field_revive_hp: "full", status_ailment: "KO" },
    7,
  );

  assert.equal(result.ok, true);
  assert.equal(result.target.hp, 120);
  assert.deepEqual(result.target.status_icons, ["poison"]);
  assert.equal(result.caster.mp_levels["7"].current, 1);
});

test("applyFieldSpellEffect clears statuses from metadata", () => {
  const result = applyFieldSpellEffect(
    { mp_levels: { "6": { current: 2, max: 2 } } },
    { hp: 50, max_hp: 100, status_icons: ["partial_petrify", "poison"] },
    { effect_category: "status_recovery", status_ailment: "Partial Petrification, Petrification" },
    6,
  );

  assert.equal(result.ok, true);
  assert.deepEqual(result.target.status_icons, ["poison"]);
  assert.equal(result.caster.mp_levels["6"].current, 1);
});

test("applyFieldSpellEffect allows teleport magic in the field", () => {
  const target = { hp: 50, max_hp: 100, status_icons: ["poison"] };
  const result = applyFieldSpellEffect(
    { mp_levels: { "4": { current: 2, max: 2 } } },
    target,
    { effect_category: "teleport" },
    4,
  );

  assert.equal(result.ok, true);
  assert.equal(result.usesTarget, false);
  assert.deepEqual(result.target, target);
  assert.equal(result.caster.mp_levels["4"].current, 1);
});

test("applyFieldSpellEffect allows field utility magic in the field", () => {
  const target = { hp: 80, max_hp: 100, status_icons: [] };
  const result = applyFieldSpellEffect(
    { mp_levels: { "3": { current: 1, max: 1 } } },
    target,
    { effect_category: "field_utility" },
    3,
  );

  assert.equal(result.ok, true);
  assert.equal(result.usesTarget, false);
  assert.deepEqual(result.target, target);
  assert.equal(result.caster.mp_levels["3"].current, 0);
});
