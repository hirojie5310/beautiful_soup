from typing import cast

from combat.wasm_api import _build_magic_spell_meta
from combat.usecases import BattleSession


class _DummySession:
    def __init__(self) -> None:
        self.spells_expanded = {
            "Cure": {
                "Name": "Cure",
                "Type": "White Magic",
                "Level": 1,
                "Target": "One/All Allies",
                "effect_category": "heal_hp",
                "default_target_side": "Any",
                "target_scope": "one_or_all",
                "field_heal_hp": 50,
            }
        }
        self.state = None


def test_wasm_magic_spell_meta_includes_field_heal_metadata() -> None:
    meta = _build_magic_spell_meta(cast(BattleSession, _DummySession()))

    assert meta["Cure"]["effect_category"] == "heal_hp"
    assert meta["Cure"]["field_heal_hp"] == 50
    assert meta["Cure"]["target_mode"] == "any"
