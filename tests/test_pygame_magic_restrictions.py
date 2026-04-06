from __future__ import annotations

from combat.runtime_state import init_runtime_state
from system.exp_system import LevelTable
from ui_pygame.game_flow_service import prepare_battle_resources


def test_pygame_magic_candidates_respect_mystic_knight_spell_restrictions():
    state = init_runtime_state()
    state.save["party"][0]["job"] = "Mystic Knight"
    state.save["party"][0]["current_job"] = "Mystic Knight"
    state.save["party"][0]["job_levels"]["Mystic Knight"] = {
        "level": state.save["party"][0].get("job_level", {}).get("level", 1),
        "skill_point": state.save["party"][0].get("job_level", {}).get("skill_point", 0),
    }
    state.save["party"][0]["Magic"] = {
        "LV1": ["Cure", None, None],
        "LV2": ["Shiva", None, None],
        "LV3": ["Cura", None, None],
        "LV4": [None, None, None],
        "LV5": [None, None, None],
        "LV6": [None, None, None],
        "LV7": [None, None, None],
        "LV8": ["Bahamut", None, None],
    }

    level_table = LevelTable("assets/data/level_exp.csv")
    _enemies, _party_members, build_magic_fn = prepare_battle_resources(
        state=state,
        level_table=level_table,
        enemy_names=sorted(state.monsters.keys())[:3],
        select_enemy_names=lambda party_members, build_magic_fn: sorted(state.monsters.keys())[:3],
    )

    assert [row[0] for row in build_magic_fn(0)] == ["Cure", "Cura"]
