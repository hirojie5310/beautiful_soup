# tests/test_battle_magic_mouse_flow.py
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

    class _Rect:
        def __init__(self, x: int, y: int, w: int, h: int) -> None:
            self.x = x
            self.y = y
            self.w = w
            self.h = h

        def collidepoint(self, pos: tuple[int, int]) -> bool:
            px, py = pos
            return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    pygame_stub.Rect = _Rect
    pygame_stub.event = SimpleNamespace(Event=object)
    pygame_stub.mixer = SimpleNamespace(Sound=object)
    sys.modules["pygame"] = pygame_stub

import pygame

from ui_pygame.app_context import BattleAppContext
from ui_pygame.input_modes.magic import handle_magic_mousedown
from ui_pygame.state import BattleUIState


def _make_planned_action(**kwargs: Any) -> PlannedAction:
    return cast(PlannedAction, SimpleNamespace(**kwargs))


def _ctx() -> BattleAppContext:
    member = SimpleNamespace(
        name="Refia",
        state=SimpleNamespace(mp_pool={1: 3}, max_mp_pool={1: 3}),
        job=SimpleNamespace(raw={"Spells": [{"Name": "Cure", "Level": 1}]}),
    )
    return BattleAppContext(
        config=SimpleNamespace(),
        party_members=[member],
        enemies=[],
        items_by_name={},
        normalize_battle_command=lambda command: "magic",
        reset_target_flags=lambda ui: None,
        is_out_of_battle=lambda actor: False,
        get_job_commands=lambda member: [],
        build_magic_candidates_for_member=lambda member_idx: [],
        build_item_candidates_for_battle=lambda: [],
        make_planned_action=_make_planned_action,
        find_next_unfilled_member_index=lambda ui: 0,
    )


def _mouse_event(pos: tuple[int, int]) -> Any:
    return cast(Any, SimpleNamespace(button=1, pos=pos))


def test_magic_click_selects_row_and_moves_to_target_side() -> None:
    ui = BattleUIState()
    ui.input_mode = "magic"
    ui.magic_candidates = [("Fire", 1, 1), ("Cure", 1, 1)]
    ui.selected_magic_idx = 0
    ui.planned_actions = [None]
    ui.logs = []
    ui.spells_by_name = {"Cure": {"Target": "ally"}}
    ui.menu_option_rects = cast(
        Any,
        [
            (0, pygame.Rect(0, 0, 120, 20)),
            (1, pygame.Rect(0, 20, 120, 20)),
        ],
    )
    ctx = _ctx()

    committed = handle_magic_mousedown(
        event=_mouse_event((10, 25)),
        ui=ui,
        ctx=ctx,
    )

    assert committed is False
    assert ui.selected_magic_idx == 1
    assert ui.selected_spell_name == "Cure"
    assert ui.input_mode == "target_side"
    assert ui.logs[-1] == "[入力] 対象(敵/味方/自分)選択: Cure"
