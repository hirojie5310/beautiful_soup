import test from "node:test";
import assert from "node:assert/strict";

import {
  applyFieldItemEffect,
  getItemMeta,
  itemRequiresTarget,
  parseItemStatusAilments,
} from "./item_screen.js";

test("parseItemStatusAilments splits comma-separated status metadata", () => {
  assert.deepEqual(
    parseItemStatusAilments("Partial Petrification, Petrification"),
    ["Partial Petrification", "Petrification"],
  );
});

test("getItemMeta resolves item metadata from inventory catalog", () => {
  const meta = getItemMeta({
    item_meta: {
      Potion: {
        effect_category: "heal_hp",
        value: 75,
      },
    },
  }, "Potion");

  assert.deepEqual(meta, {
    effect_category: "heal_hp",
    value: 75,
  });
});

test("itemRequiresTarget follows target_scope metadata instead of item names", () => {
  assert.equal(itemRequiresTarget({
    effect_category: "heal_hp",
    default_target_side: "Ally",
    target_scope: "one",
  }), true);
  assert.equal(itemRequiresTarget({
    effect_category: "buff_attack",
    default_target_side: "Ally",
    target_scope: "all",
  }), false);
});

test("applyFieldItemEffect heals hp using metadata value", () => {
  const result = applyFieldItemEffect(
    { hp: 10, max_hp: 100, status_icons: [] },
    { effect_category: "heal_hp", value: 75 },
  );

  assert.equal(result.changed, true);
  assert.equal(result.member.hp, 85);
});

test("applyFieldItemEffect fully restores hp and mp for heal_full items", () => {
  const result = applyFieldItemEffect(
    {
      hp: 10,
      max_hp: 120,
      mp_levels: {
        "1": { current: 1, max: 3 },
        "2": { current: 0, max: 4 },
      },
    },
    { effect_category: "heal_full" },
  );

  assert.equal(result.changed, true);
  assert.equal(result.member.hp, 120);
  assert.equal(result.member.mp_levels["1"].current, 3);
  assert.equal(result.member.mp_levels["2"].current, 4);
});

test("applyFieldItemEffect revives KO target and clears ko status", () => {
  const result = applyFieldItemEffect(
    { hp: 0, max_hp: 99, status_icons: ["ko", "poison"] },
    { effect_category: "revive", status_ailment: "KO" },
  );

  assert.equal(result.changed, true);
  assert.equal(result.member.hp, 49);
  assert.deepEqual(result.member.status_icons, ["poison"]);
});

test("applyFieldItemEffect clears statuses from metadata for recovery items", () => {
  const result = applyFieldItemEffect(
    { hp: 80, max_hp: 100, status_icons: ["blind", "poison"] },
    { effect_category: "status_recovery", status_ailment: "Blind" },
  );

  assert.equal(result.changed, true);
  assert.deepEqual(result.member.status_icons, ["poison"]);
});

test("applyFieldItemEffect clears toggled statuses from metadata for toggle items", () => {
  const result = applyFieldItemEffect(
    { hp: 80, max_hp: 100, status_icons: ["mini", "poison"] },
    { effect_category: "status_toggle", status_ailment: "Mini" },
  );

  assert.equal(result.changed, true);
  assert.deepEqual(result.member.status_icons, ["poison"]);
});
