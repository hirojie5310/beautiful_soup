# tests/test_flask_menu_actions.py
from types import SimpleNamespace

from adapters.flask_menu_actions import make_cast_field_magic_fn, make_use_field_item_fn
from combat.enums import Status
from combat.models import BattleActorState


def test_flask_menu_action_builders_are_importable_without_pygame_dependency():
    assert callable(make_cast_field_magic_fn)
    assert callable(make_use_field_item_fn)


def _member(name: str, *, hp: int = 100, max_hp: int = 100) -> SimpleNamespace:
    state = BattleActorState(hp=hp, max_hp=max_hp)
    state.max_mp_pool[1] = 3
    state.mp_pool[1] = 3
    return SimpleNamespace(name=name, hp=hp, max_hp=max_hp, state=state)


def test_cast_field_magic_uses_spell_metadata_for_status_recovery() -> None:
    caster = _member("Refia")
    target = _member("Ingus")
    target.state.statuses.add(Status.SILENCE)
    save = {
        "party": [
            {"name": "Refia", "hp": caster.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ]
    }
    cast_magic = make_cast_field_magic_fn(
        party=[caster, target],
        spells_by_name={
            "Panacea": {
                "name": "Panacea",
                "effect_category": "status_recovery",
                "StatusAilments": "Silence",
                "default_target_side": "Ally",
                "target_scope": "one",
            }
        },
        build_magic_fn=lambda _idx: [("Panacea", 1, 1)],
        save_dict=save,
    )

    changed = cast_magic(0, "Panacea", 1)

    assert changed is True
    assert Status.SILENCE not in target.state.statuses
    assert caster.state.mp_pool[1] == 2


def test_cast_field_magic_uses_spell_metadata_for_revive() -> None:
    caster = _member("Refia")
    target = _member("Ingus", hp=0, max_hp=120)
    save = {
        "party": [
            {"name": "Refia", "hp": caster.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ]
    }
    cast_magic = make_cast_field_magic_fn(
        party=[caster, target],
        spells_by_name={
            "Rebirth": {
                "name": "Rebirth",
                "effect_category": "revive",
                "field_revive_hp": "half",
                "status_ailment": "KO",
                "default_target_side": "Ally",
                "target_scope": "one",
            }
        },
        build_magic_fn=lambda _idx: [("Rebirth", 1, 1)],
        save_dict=save,
    )

    changed = cast_magic(0, "Rebirth", 1)

    assert changed is True
    assert target.state.hp == 60
    assert caster.state.mp_pool[1] == 2


def test_cast_field_magic_uses_spell_metadata_for_full_revive() -> None:
    caster = _member("Refia")
    target = _member("Ingus", hp=0, max_hp=120)
    save = {
        "party": [
            {"name": "Refia", "hp": caster.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ]
    }
    cast_magic = make_cast_field_magic_fn(
        party=[caster, target],
        spells_by_name={
            "Miracle": {
                "name": "Miracle",
                "effect_category": "revive",
                "field_revive_hp": "full",
                "status_ailment": "KO",
                "default_target_side": "Ally",
                "target_scope": "one",
            }
        },
        build_magic_fn=lambda _idx: [("Miracle", 1, 1)],
        save_dict=save,
    )

    changed = cast_magic(0, "Miracle", 1)

    assert changed is True
    assert target.state.hp == 120
    assert caster.state.mp_pool[1] == 2


def test_use_field_item_uses_item_metadata_for_status_recovery() -> None:
    user = _member("Refia")
    target = _member("Ingus")
    target.state.statuses.add(Status.BLIND)
    save = {
        "party": [
            {"name": "Refia", "hp": user.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ],
        "inventory": {"Anywhere": {"Panacea Herb": 1}},
    }
    use_item = make_use_field_item_fn(
        party=[user, target],
        items_by_name={
            "Panacea Herb": {
                "Name": "Panacea Herb",
                "ItemType": "Anywhere",
                "effect_category": "status_recovery",
                "default_target_side": "Ally",
                "target_scope": "one",
                "status_ailment": "Blind",
            }
        },
        save_dict=save,
    )

    changed = use_item(0, "Panacea Herb", 1, "Anywhere")

    assert changed is True
    assert Status.BLIND not in target.state.statuses
    assert save["inventory"]["Anywhere"] == {}


def test_use_field_item_uses_item_metadata_for_hp_recovery() -> None:
    user = _member("Refia")
    target = _member("Ingus", hp=25, max_hp=120)
    save = {
        "party": [
            {"name": "Refia", "hp": user.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ],
        "inventory": {"Anywhere": {"Mega Potion": 1}},
    }
    use_item = make_use_field_item_fn(
        party=[user, target],
        items_by_name={
            "Mega Potion": {
                "Name": "Mega Potion",
                "ItemType": "Anywhere",
                "effect_category": "heal_hp",
                "default_target_side": "Ally",
                "target_scope": "one",
                "Value": 70,
            }
        },
        save_dict=save,
    )

    changed = use_item(0, "Mega Potion", 1, "Anywhere")

    assert changed is True
    assert target.state.hp == 95
    assert save["inventory"]["Anywhere"] == {}


def test_use_field_item_uses_item_metadata_for_full_recovery() -> None:
    user = _member("Refia")
    target = _member("Ingus", hp=25, max_hp=120)
    target.state.mp_pool[1] = 1
    save = {
        "party": [
            {"name": "Refia", "hp": user.state.hp},
            {"name": "Ingus", "hp": target.state.hp},
        ],
        "inventory": {"Anywhere": {"Megalixir": 1}},
    }
    use_item = make_use_field_item_fn(
        party=[user, target],
        items_by_name={
            "Megalixir": {
                "Name": "Megalixir",
                "ItemType": "Anywhere",
                "effect_category": "heal_full",
                "default_target_side": "Ally",
                "target_scope": "one",
            }
        },
        save_dict=save,
    )

    changed = use_item(0, "Megalixir", 1, "Anywhere")

    assert changed is True
    assert target.state.hp == 120
    assert target.state.mp_pool[1] == target.state.max_mp_pool[1]
    assert save["inventory"]["Anywhere"] == {}
