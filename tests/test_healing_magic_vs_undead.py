# tests/test_healing_magic_vs_undead.py
from random import Random
from types import SimpleNamespace

from combat.models import (
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    SpellInfo,
)
from combat.turn_logic import run_character_turn


def _char_stats(*, max_hp: int = 9999) -> FinalCharacterStats:
    return FinalCharacterStats(
        level=20,
        job_level=20,
        job_skill_point=0,
        max_hp=max_hp,
        strength=10,
        agility=10,
        vitality=10,
        intelligence=10,
        mind=40,
        row="front",
        main_power=0,
        main_accuracy=0,
        main_atk_multiplier=1,
        main_two=False,
        main_long=False,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        off_two=False,
        off_long=False,
        defense=0,
        defense_multiplier=0,
        evasion_percent=0,
        magic_defense=0,
        magic_def_multiplier=0,
        magic_resistance=0,
        shield_count=0,
    )


def _enemy_stats(name: str = "Skeleton", hp: int = 500) -> FinalEnemyStats:
    return FinalEnemyStats(
        name=name,
        hp=hp,
        level=10,
        job_level=1,
        attack_power=1,
        attack_multiplier=1,
        accuracy_percent=1,
        defense=1,
        defense_multiplier=1,
        evasion_percent=0,
        magic_defense=1,
        magic_def_multiplier=1,
        magic_resistance_percent=0,
        agility=1,
    )


def _cure_spell() -> tuple[SpellInfo, dict[str, object]]:
    return (
        SpellInfo(power=32, accuracy_percent=100, magic_type="white", elements=[]),
        {
            "Name": "Cure",
            "Type": "White Magic",
            "Level": 1,
            "Target": "One/All Allies",
            "Effect": "Restore target's HP",
        },
    )


def test_healing_magic_damages_single_undead_enemy() -> None:
    caster_stats = _char_stats()
    enemy_stats = _enemy_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500)
    spell, spell_json = _cure_spell()
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Skeleton",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={"Monster Type": "Undead"},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        aoe_selected_override=False,
    )

    assert damage > 0
    assert enemy_state.hp == 500 - damage
    assert result is None
    assert any("アンデッドに効く" in line for line in logs)


def test_healing_magic_has_no_effect_on_non_undead_enemy() -> None:
    caster_stats = _char_stats()
    enemy_stats = _enemy_stats(name="Goblin")
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    enemy_state = BattleActorState(hp=500, max_hp=500)
    spell, spell_json = _cure_spell()
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Goblin",
        char_stats=caster_stats,
        enemy_stats=enemy_stats,
        enemy_json={"Monster Type": "Beast"},
        char_state=caster_state,
        enemy_state=enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        aoe_selected_override=False,
    )

    assert damage == 0
    assert result is None
    assert enemy_state.hp == 500
    assert any("効果がない" in line for line in logs)


def test_healing_magic_aoe_only_damages_undead_enemies() -> None:
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell_json = {**spell_json, "Target": "One/All Enemies"}

    undead_enemy = SimpleNamespace(
        name="Skeleton",
        label="Skeleton",
        stats=_enemy_stats(name="Skeleton"),
        state=BattleActorState(hp=500, max_hp=500),
        json={"Monster Type": "Undead"},
    )
    living_enemy = SimpleNamespace(
        name="Goblin",
        label="Goblin",
        stats=_enemy_stats(name="Goblin"),
        state=BattleActorState(hp=450, max_hp=450),
        json={"Monster Type": "Beast"},
    )
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Refia",
        enemy_name="Skeleton",
        char_stats=caster_stats,
        enemy_stats=undead_enemy.stats,
        enemy_json=undead_enemy.json,
        char_state=caster_state,
        enemy_state=undead_enemy.state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        enemies=[undead_enemy, living_enemy],
        aoe_selected_override=True,
    )

    assert damage > 0
    assert undead_enemy.state.hp < 500
    assert living_enemy.state.hp == 450
    assert result is None
    assert any("Goblin" in line and "効果がない" in line for line in logs)


def test_healing_magic_aoe_logs_cast_message_only_once() -> None:
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell_json = {**spell_json, "Target": "One/All Enemies"}

    enemies = [
        SimpleNamespace(
            name="Skeleton A",
            label="Skeleton A",
            stats=_enemy_stats(name="Skeleton A"),
            state=BattleActorState(hp=500, max_hp=500),
            json={"Monster Type": "Undead"},
        ),
        SimpleNamespace(
            name="Goblin",
            label="Goblin",
            stats=_enemy_stats(name="Goblin"),
            state=BattleActorState(hp=450, max_hp=450),
            json={"Monster Type": "Beast"},
        ),
    ]
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Skeleton A",
        char_stats=caster_stats,
        enemy_stats=enemies[0].stats,
        enemy_json=enemies[0].json,
        char_state=caster_state,
        enemy_state=enemies[0].state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        enemies=enemies,
        aoe_selected_override=True,
    )

    assert damage > 0
    assert result is None
    assert sum("アンデッドに効く《Cure》を唱えた" in line for line in logs) == 1
    assert any(line.startswith("  ") and "Skeleton Aに" in line for line in logs)
    assert any(
        line == "  しかしGoblinはアンデッドではないため効果がない。" for line in logs
    )


def test_healing_magic_single_target_does_not_end_battle_if_other_enemies_alive() -> (
    None
):
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell = SpellInfo(power=9999, accuracy_percent=100, magic_type="white", elements=[])

    target_enemy = SimpleNamespace(
        name="Skeleton",
        label="Skeleton",
        stats=_enemy_stats(name="Skeleton", hp=54),
        state=BattleActorState(hp=54, max_hp=54),
        json={"Monster Type": "Undead"},
    )
    other_enemy = SimpleNamespace(
        name="Shadow",
        label="Shadow",
        stats=_enemy_stats(name="Shadow", hp=65),
        state=BattleActorState(hp=65, max_hp=65),
        json={"Monster Type": "Mage"},
    )
    logs: list[str] = []

    _, result = run_character_turn(
        char_name="Runeth",
        enemy_name=target_enemy.name,
        char_stats=caster_stats,
        enemy_stats=target_enemy.stats,
        enemy_json=target_enemy.json,
        char_state=caster_state,
        enemy_state=target_enemy.state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        enemies=[target_enemy, other_enemy],
        aoe_selected_override=False,
    )

    assert target_enemy.state.hp == 0
    assert other_enemy.state.hp == 65
    assert result is None


def test_healing_magic_single_target_never_returns_enemy_defeated_in_turn_logic() -> (
    None
):
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell = SpellInfo(power=9999, accuracy_percent=100, magic_type="white", elements=[])

    target_enemy = SimpleNamespace(
        name="Skeleton",
        label="Skeleton",
        stats=_enemy_stats(name="Skeleton", hp=54),
        state=BattleActorState(hp=54, max_hp=54),
        json={"Monster Type": "Undead"},
    )
    dead_enemy = SimpleNamespace(
        name="Skeleton B",
        label="Skeleton B",
        stats=_enemy_stats(name="Skeleton B", hp=10),
        state=BattleActorState(hp=0, max_hp=10),
        json={"Monster Type": "Undead"},
    )
    logs: list[str] = []

    _, result = run_character_turn(
        char_name="Runeth",
        enemy_name=target_enemy.name,
        char_stats=caster_stats,
        enemy_stats=target_enemy.stats,
        enemy_json=target_enemy.json,
        char_state=caster_state,
        enemy_state=target_enemy.state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        enemies=[target_enemy, dead_enemy],
        aoe_selected_override=False,
    )

    assert target_enemy.state.hp == 0
    assert result is None


def test_healing_magic_on_already_dead_undead_target_does_not_set_enemy_defeated() -> (
    None
):
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell = SpellInfo(power=9999, accuracy_percent=100, magic_type="white", elements=[])
    dead_enemy_state = BattleActorState(hp=0, max_hp=54)
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Skeleton A",
        char_stats=caster_stats,
        enemy_stats=_enemy_stats(name="Skeleton A", hp=54),
        enemy_json={"Monster Type": "Undead"},
        char_state=caster_state,
        enemy_state=dead_enemy_state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        aoe_selected_override=False,
    )

    assert damage >= 0
    assert dead_enemy_state.hp == 0
    assert result is None


def test_healing_magic_aoe_all_undead_keeps_compact_log() -> None:
    caster_stats = _char_stats()
    caster_state = BattleActorState(hp=999, max_hp=9999)
    caster_state.mp_pool[1] = 1
    caster_state.max_mp_pool[1] = 1
    spell, spell_json = _cure_spell()
    spell_json = {**spell_json, "Target": "One/All Enemies"}

    enemies = [
        SimpleNamespace(
            name="Skeleton A",
            label="Skeleton A",
            stats=_enemy_stats(name="Skeleton A"),
            state=BattleActorState(hp=500, max_hp=500),
            json={"Monster Type": "Undead"},
        ),
        SimpleNamespace(
            name="Skeleton B",
            label="Skeleton B",
            stats=_enemy_stats(name="Skeleton B"),
            state=BattleActorState(hp=500, max_hp=500),
            json={"Monster Type": "Undead"},
        ),
        SimpleNamespace(
            name="Mummy",
            label="Mummy",
            stats=_enemy_stats(name="Mummy"),
            state=BattleActorState(hp=500, max_hp=500),
            json={"Monster Type": "Undead"},
        ),
    ]
    logs: list[str] = []

    damage, result = run_character_turn(
        char_name="Runeth",
        enemy_name="Skeleton A",
        char_stats=caster_stats,
        enemy_stats=enemies[0].stats,
        enemy_json=enemies[0].json,
        char_state=caster_state,
        enemy_state=enemies[0].state,
        char_attack_kind="magic",
        char_battle_command="Magic",
        char_weapon_hand="main",
        char_spell=spell,
        char_spell_json=spell_json,
        char_spell_healing_type="hp",
        char_spell_name="Cure",
        char_item=None,
        logs=logs,
        rng=Random(0),
        target_side="enemy",
        target_index=0,
        enemies=enemies,
        aoe_selected_override=True,
    )

    assert damage > 0
    assert result is None
    assert sum("アンデッドに効く《Cure》を唱えた" in line for line in logs) == 1
    assert all("しかし" not in line for line in logs)
    assert (
        sum(
            "Skeleton Aに" in line or "Skeleton Bに" in line or "Mummyに" in line
            for line in logs
        )
        == 3
    )
