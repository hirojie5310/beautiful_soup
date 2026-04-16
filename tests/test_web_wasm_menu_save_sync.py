from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_merge_menu_state_into_save_preserves_job_change_and_job_levels() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    CP: 50,
    gil: 100,
    party: [
      {
        name: "Refia",
        portrait_key: "refia",
        job: "Dragoon",
        current_job: "Dragoon",
        job_level: { level: 99, skill_point: 99 },
        job_levels: {
          Dragoon: { level: 99, skill_point: 99 },
        },
        equipment: { head: "Ribbon" },
        status_effects: { Poison: false },
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Refia",
        portrait_key: "refia",
        job: "Onion Knight",
        current_job: "Onion Knight",
        job_level: { level: 1, skill_point: 0 },
        job_levels: {
          Dragoon: { level: 99, skill_point: 99 },
          "Onion Knight": { level: 1, skill_point: 0 },
        },
        equipment: { head: "Ribbon" },
        hp: 321,
        max_hp: 654,
        row: "back",
        mp_levels: { "1": { current: 3 } },
        status_icons: [],
      },
    ],
    resources: { cp: 42, gil: 777 },
  },
);

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)
    entry = merged["party"][0]

    assert entry["job"] == "Onion Knight"
    assert entry["current_job"] == "Onion Knight"
    assert entry["job_level"]["level"] == 1
    assert entry["job_levels"]["Dragoon"]["level"] == 99
    assert entry["job_levels"]["Onion Knight"]["level"] == 1
    assert entry["equipment"]["head"] == "Ribbon"
    assert entry["hp"] == 321
    assert entry["max_hp"] == 654
    assert merged["CP"] == 42
    assert merged["gil"] == 777


def test_merge_menu_state_into_save_preserves_inventory_while_syncing_recovery() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    gil: 90,
    inventory: {
      Anywhere: { Potion: 2 },
      Weapon: { "Mythril Sword": 1 },
    },
    party: [
      {
        name: "Runeth",
        portrait_key: "runeth",
        hp: 12,
        max_hp: 500,
        mp_levels: { "1": { current: 0 } },
        status_effects: { Poison: true, Blind: true },
        status_icons: ["poison", "blind"],
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Runeth",
        portrait_key: "runeth",
        hp: 500,
        max_hp: 500,
        mp_levels: { "1": { current: 5 } },
        status_icons: [],
        row: "front",
      },
    ],
    resources: { gil: 80 },
  },
);

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)
    entry = merged["party"][0]

    assert merged["gil"] == 80
    assert merged["inventory"]["Anywhere"]["Potion"] == 2
    assert merged["inventory"]["Weapon"]["Mythril Sword"] == 1
    assert entry["hp"] == 500
    assert entry["mp"]["L1MP"] == 5
    assert entry["status_effects"]["Poison"] is False
    assert entry["status_effects"]["Blind"] is False


def test_merge_menu_state_into_save_preserves_inventory_delta_after_item_use() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    inventory: {
      Anywhere: { Potion: 1, "Hi Potion": 2 },
      Armor: { Ribbon: 1 },
    },
    party: [
      {
        name: "Ingus",
        portrait_key: "ingus",
        hp: 50,
        max_hp: 300,
        status_effects: { Poison: true },
        status_icons: ["poison"],
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Ingus",
        portrait_key: "ingus",
        hp: 140,
        max_hp: 300,
        row: "front",
        mp_levels: {},
        status_icons: [],
      },
    ],
    resources: { gil: 0 },
  },
);

merged.inventory.Anywhere.Potion = 0;
delete merged.inventory.Anywhere.Potion;

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)
    entry = merged["party"][0]

    assert "Potion" not in merged["inventory"]["Anywhere"]
    assert merged["inventory"]["Anywhere"]["Hi Potion"] == 2
    assert merged["inventory"]["Armor"]["Ribbon"] == 1
    assert entry["hp"] == 140
    assert entry["status_effects"]["Poison"] is False


def test_merge_menu_state_into_save_updates_row_change() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    party: [
      {
        name: "Runeth",
        portrait_key: "runeth",
        row: "front",
        hp: 300,
        max_hp: 300,
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Runeth",
        portrait_key: "runeth",
        row: "back",
        hp: 300,
        max_hp: 300,
        mp_levels: {},
        status_icons: [],
      },
    ],
    resources: { gil: 0 },
  },
);

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)

    assert merged["party"][0]["row"] == "back"


def test_merge_menu_state_into_save_updates_map_position() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    map: {
      map: "grassland",
      surface: "Grassland",
      x: 14,
      y: 32,
    },
    party: [],
  },
  {
    party: [],
    map_state: {
      current_map_id: "Alter_Cave_B1",
      tile_x: 8,
      tile_y: 31,
    },
    resources: { gil: 0 },
  },
);

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)

    assert merged["map"]["map"] == "Alter_Cave_B1"
    assert merged["map"]["surface"] == "Alter_Cave_B1"
    assert merged["map"]["x"] == 8
    assert merged["map"]["y"] == 31


def test_merge_menu_state_into_save_prefers_status_progress_over_stale_top_level_fields() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    party: [
      {
        name: "Refia",
        portrait_key: "refia",
        level: 1,
        exp: 0,
        job: "Onion Knight",
        current_job: "Onion Knight",
        job_level: { level: 1, skill_point: 0 },
        job_levels: {
          "Onion Knight": { level: 1, skill_point: 0 },
        },
        hp: 20,
        max_hp: 20,
        status_effects: { Poison: false },
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Refia",
        portrait_key: "refia",
        level: 1,
        exp: 0,
        job: "Onion Knight",
        current_job: "Onion Knight",
        hp: 22,
        max_hp: 22,
        mp_levels: {},
        status_icons: [],
        status: {
          level: 2,
          exp: 35,
          job_level: 3,
        },
      },
    ],
    resources: { gil: 0, cp: 0 },
  },
);

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)
    entry = merged["party"][0]

    assert entry["level"] == 2
    assert entry["exp"] == 35
    assert entry["job_level"]["level"] == 3
    assert entry["job_levels"]["Onion Knight"]["level"] == 3


def test_merge_menu_state_into_save_preserves_equipment_change_with_inventory_delta() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import { mergeMenuStateIntoSave } from "./web_wasm/menu_save_sync.js";

const merged = mergeMenuStateIntoSave(
  {
    inventory: {
      Weapon: { "Mythril Sword": 1 },
      Armor: { "Leather Shield": 2 },
    },
    party: [
      {
        name: "Arc",
        portrait_key: "arc",
        equipment: {
          main_hand: null,
          off_hand: "Leather Shield",
          head: null,
          body: null,
          arms: null,
        },
        hp: 200,
        max_hp: 200,
      },
    ],
  },
  {
    party: [
      {
        index: 0,
        name: "Arc",
        portrait_key: "arc",
        equipment: {
          main_hand: "Mythril Sword",
          off_hand: null,
          head: null,
          body: null,
          arms: null,
        },
        hp: 200,
        max_hp: 200,
        row: "front",
        mp_levels: {},
        status_icons: [],
      },
    ],
    resources: { gil: 0 },
  },
);

merged.inventory.Weapon["Mythril Sword"] = 0;
delete merged.inventory.Weapon["Mythril Sword"];
merged.inventory.Armor["Leather Shield"] = 3;

console.log(JSON.stringify(merged));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    merged = json.loads(completed.stdout)
    entry = merged["party"][0]

    assert entry["equipment"]["main_hand"] == "Mythril Sword"
    assert entry["equipment"]["off_hand"] is None
    assert "Mythril Sword" not in merged["inventory"]["Weapon"]
    assert merged["inventory"]["Armor"]["Leather Shield"] == 3
