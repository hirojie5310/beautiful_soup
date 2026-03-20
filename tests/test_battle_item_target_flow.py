# tests/test_battle_item_target_flow.py
from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any, cast
import sys

from combat.models import PlannedAction

if "pygame" not in sys.modules:
    pygame_stub: Any = ModuleType("pygame")
    pygame_stub.K_UP = 273
    pygame_stub.K_DOWN = 274
    pygame_stub.K_BACKSPACE = 8
    pygame_stub.K_RETURN = 13
    pygame_stub.K_KP_ENTER = 271
    pygame_stub.event = SimpleNamespace(Event=object)
    pygame_stub.mixer = SimpleNamespace(Sound=object)
    sys.modules["pygame"] = pygame_stub

import pygame

from ui_pygame.app_context import BattleAppContext
from ui_pygame.input_modes.item import handle_item_keydown
from ui_pygame.state import BattleUIState


def _make_planned_action(**kwargs: Any) -> PlannedAction:
    return cast(PlannedAction, SimpleNamespace(**kwargs))


def _ctx(items_by_name: dict[str, dict]) -> BattleAppContext:
    return BattleAppContext(
        config=SimpleNamespace(),
        party_members=[],
        enemies=[],
        items_by_name=items_by_name,
        normalize_battle_command=lambda command: "item",
        reset_target_flags=lambda ui: None,
        is_out_of_battle=lambda actor: False,
        get_job_commands=lambda member: [],
        build_magic_candidates_for_member=lambda member_idx: [],
        build_item_candidates_for_battle=lambda: [],
        make_planned_action=_make_planned_action,
        find_next_unfilled_member_index=lambda ui: 0,
    )


def _event(key: int) -> Any:
    return cast(Any, SimpleNamespace(key=key))


def test_potion_selection_goes_directly_to_ally_target() -> None:
    ui = BattleUIState(
        item_candidates=[("Potion", "Combat", 1)],
        selected_item_idx=0,
        input_mode="item",
        logs=[],
    )
    ctx = _ctx(
        {
            "Potion": {
                "Name": "Potion",
                "SpellEffect": "Recovery",
                "SpellInfo": {"Effect": "Restore target's HP"},
            }
        }
    )

    committed = handle_item_keydown(event=_event(pygame.K_RETURN), ui=ui, ctx=ctx)

    assert committed is False
    assert ui.selected_item_name == "Potion"
    assert ui.target_side == "ally"
    assert ui.input_mode == "target_ally"
    assert ui.logs[-1] == "[入力] ターゲット(味方)選択: Potion"


def test_attack_item_selection_goes_directly_to_enemy_target() -> None:
    ui = BattleUIState(
        item_candidates=[("Bomb Fragment", "Combat", 1)],
        selected_item_idx=0,
        input_mode="item",
        logs=[],
    )
    ctx = _ctx(
        {
            "Bomb Fragment": {
                "Name": "Bomb Fragment",
                "SpellInfo": {"Effect": "Deal fire damage"},
            }
        }
    )

    committed = handle_item_keydown(event=_event(pygame.K_RETURN), ui=ui, ctx=ctx)

    assert committed is False
    assert ui.selected_item_name == "Bomb Fragment"
    assert ui.target_side == "enemy"
    assert ui.input_mode == "target_enemy"
    assert ui.logs[-1] == "[入力] ターゲット(敵)選択: Bomb Fragment"
