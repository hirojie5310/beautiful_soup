# ============================================================
# target_side: target_side input_modeの処理

# handle_target_side: target_side input_modeの処理
# ============================================================

# ui_pygame/handlers/target_side.py
# ui_pygame/input_modes/target_side.py
from __future__ import annotations

import pygame

from combat.models import TargetSide

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def handle_target_side_keydown(
    *, event: pygame.event.Event, ui: BattleUIState, ctx: BattleAppContext
) -> bool:
    """
    target_side input_mode の処理
    - enemy/ally へ遷移するだけなら False
    - self を確定したら True（input_handler 側で ctx.on_committed が走る）
    """
    options: tuple[TargetSide, ...] = ("enemy", "ally", "self")

    if event.key == pygame.K_UP:
        ui.selected_target_side_idx = (ui.selected_target_side_idx - 1) % len(options)
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_target_side_idx = (ui.selected_target_side_idx + 1) % len(options)
        return False

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = "magic" if ui.selected_spell_name else "item"
        ui.selected_target_all = False
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    if ui.se_enter:
        ui.se_enter.play()

    chosen = options[ui.selected_target_side_idx]
    ui.target_side = chosen
    ui.selected_target_idx = 0

    if chosen == "enemy":
        ui.input_mode = "target_enemy"
        return False

    if chosen == "ally":
        ui.input_mode = "target_ally"
        return False

    # --- self はここで確定（Trueを返す） ---
    member = ctx.party_members[ui.selected_member_idx]

    if ui.selected_spell_name:
        act = ctx.make_planned_action(
            kind="magic",
            command="Magic",
            member_idx=ui.selected_member_idx,
            target_side="self",
            target_index=ui.selected_member_idx,
            spell_name=ui.selected_spell_name,
        )
        ui.logs.append(f"[確定] {member.name}: Magic {ui.selected_spell_name} → self")
    else:
        act = ctx.make_planned_action(
            kind="item",
            command="Item",
            member_idx=ui.selected_member_idx,
            target_side="self",
            target_index=ui.selected_member_idx,
            item_name=ui.selected_item_name,
        )
        ui.logs.append(f"[確定] {member.name}: Item {ui.selected_item_name} → self")

    ui.planned_actions[ui.selected_member_idx] = act

    if ui.se_confirm:
        ui.se_confirm.play()

    ui.input_mode = "member"
    return True
