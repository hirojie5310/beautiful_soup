# tests/test_magic_spell_meta.py
from typing import cast

from adapters.flask_app import _build_magic_spell_meta
from combat.usecases import BattleSession


class _DummySession:
    def __init__(self) -> None:
        self.spells_expanded = {
            "Reflect": {
                "Name": "Reflect",
                "Type": "White Magic",
                "Level": 7,
                "Effect": "Grant Reflect",
                "Target": "One Enemy",
            },
            "Fire": {
                "Name": "Fire",
                "Type": "Black Magic",
                "Level": 1,
                "Effect": "Deal Fire damage",
                "Target": "One Enemy",
            },
            "Cure": {
                "Name": "Cure",
                "Type": "White Magic",
                "Level": 1,
                "Effect": "Restore target's HP",
                "Target": "One/All Allies",
            },
            "Leviathan: Demon Eye": {
                "Name": "Leviathan: Demon Eye",
                "Type": "Summon",
                "Level": 7,
                "Effect": "Deal wind damage and inflict Blind",
                "Target": "All Enemies",
            },
        }


def test_build_magic_spell_meta_marks_reflect_as_ally_only() -> None:
    meta = _build_magic_spell_meta(cast(BattleSession, _DummySession()))

    assert meta["Reflect"]["healing_type"] == "reflect"
    assert meta["Reflect"]["target_mode"] == "ally_only"


def test_build_magic_spell_meta_keeps_attack_magic_enemy_only() -> None:
    meta = _build_magic_spell_meta(cast(BattleSession, _DummySession()))

    assert meta["Fire"]["healing_type"] == ""
    assert meta["Fire"]["target_mode"] == "enemy_only"


def test_build_magic_spell_meta_marks_hp_heal_as_any_target() -> None:
    meta = _build_magic_spell_meta(cast(BattleSession, _DummySession()))

    assert meta["Cure"]["healing_type"] == "hp"
    assert meta["Cure"]["target_mode"] == "any"


def test_build_magic_spell_meta_marks_all_enemies_as_auto_all_target() -> None:
    meta = _build_magic_spell_meta(cast(BattleSession, _DummySession()))

    assert meta["Leviathan: Demon Eye"]["target_norm"] == "all enemies"
    assert meta["Leviathan: Demon Eye"]["auto_all_target"] is True
    assert meta["Leviathan: Demon Eye"]["can_select_all"] is False
