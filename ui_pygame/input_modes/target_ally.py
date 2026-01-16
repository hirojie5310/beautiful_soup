# ============================================================
# target_ally:

# handle_target_ally_keydown: target_ally input_modeの処理
# ============================================================

# ui_pygame/input_modes/target_ally.py
from __future__ import annotations

from typing import Any, Sequence

import pygame

from combat.models import PlannedAction
from combat.life_check import is_out_of_battle
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import InputMode
from ui_pygame.app_context import BattleAppContext

from .target_select import handle_target_list_keydown


def _alive_ally_indices(party_members: Sequence[Any]) -> list[int]:
    return [i for i, m in enumerate(party_members) if not is_out_of_battle(m.state)]


def handle_target_ally_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
    on_escape_mode: InputMode = "target_side",
) -> bool:
    """
    target_ally input_mode の処理（magic/item由来）
    - ESC/BSP で target_side に戻る（既存挙動）
    """
    party_members = ctx.party_members
    alive = _alive_ally_indices(party_members)
    if not alive:
        ui.logs.append("[入力] 味方がいません")
        ui.input_mode = "member"
        return False

    member = party_members[ui.selected_member_idx]

    # ★ESC/BSP は target_side を「呼ばずに」戻すだけ
    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = on_escape_mode
        ui.selected_target_all = False
        return False

    def make_action(target_ally_index: int) -> PlannedAction:
        if ui.selected_spell_name:
            return PlannedAction(
                kind="magic",
                command="Magic",
                spell_name=ui.selected_spell_name,
                item_name=None,
                target_side="ally",
                target_index=target_ally_index,
            )
        return PlannedAction(
            kind="item",
            command="Item",
            spell_name=None,
            item_name=ui.selected_item_name,
            target_side="ally",
            target_index=target_ally_index,
        )

    def log_on_confirm(target_ally_index: int) -> str:
        ally_name = getattr(
            party_members[target_ally_index], "name", f"ally[{target_ally_index}]"
        )
        if ui.selected_spell_name:
            return f"[確定] {member.name}: Magic {ui.selected_spell_name} → {ally_name}"
        return f"[確定] {member.name}: Item {ui.selected_item_name} → {ally_name}"

    # ★ここが修正点：target_side ではなく「target_list」共通ハンドラを呼ぶ
    return handle_target_list_keydown(
        event=event,
        ui=ui,
        alive_indices=alive,
        target_side="ally",
        on_escape_mode=on_escape_mode,
        make_action=make_action,
        log_on_confirm=log_on_confirm,
    )
