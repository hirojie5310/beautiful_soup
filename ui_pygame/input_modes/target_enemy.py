# ============================================================
# target_enemy:

# handle_target_enemy_keydown: target_enemy input_modeの処理
# ============================================================


# ui_pygame/input_modes/target_enemy.py
from __future__ import annotations

from typing import Any, Sequence

import pygame

from combat.enums import ENEMY_SINGLE_TARGET_KINDS
from combat.models import PlannedAction
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import InputMode
from ui_pygame.app_context import BattleAppContext

from .target_select import handle_target_list_keydown


def _alive_enemy_indices(enemies: Sequence[Any]) -> list[int]:
    return [i for i, e in enumerate(enemies) if getattr(e, "hp", 0) > 0]


def handle_target_enemy_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
    on_escape_mode_magic_item: InputMode = "target_side",
    on_escape_mode_phys: InputMode = "command",
) -> bool:
    """
    target_enemy input_mode の処理
    - magic/item 由来なら ESC/BSP で target_side に戻す
    - physical/special 由来なら ESC/BSP で command に戻す（その場合 AoE を消す）
    """

    enemies = ctx.enemies
    alive = _alive_enemy_indices(enemies)
    if not alive:
        ui.logs.append("[入力] 敵がいません")
        ui.input_mode = "member"
        return False

    member = ctx.party_members[ui.selected_member_idx]

    # 直前が magic/item か、physical/special かで戻り先を切替
    from_magic_or_item = bool(ui.selected_spell_name or ui.selected_item_name)
    escape_mode: InputMode = (
        on_escape_mode_magic_item if from_magic_or_item else on_escape_mode_phys
    )

    # ★ここが重要：ESC/BSP は target_side を「呼ばずに」モードを戻すだけ
    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = escape_mode
        if escape_mode == "command":
            ui.selected_target_all = False  # 物理/特殊へ戻る時だけAoEを消す
        return False

    def make_action(target_enemy_index: int) -> PlannedAction:
        # 直前が magic
        if ui.selected_spell_name:
            return PlannedAction(
                kind="magic",
                command="Magic",
                spell_name=ui.selected_spell_name,
                item_name=None,
                target_side="enemy",
                target_index=target_enemy_index,
                target_all=bool(ui.selected_target_all),  # ★ここで確定
            )

        # 直前が item
        if ui.selected_item_name:
            return PlannedAction(
                kind="item",
                command="Item",
                spell_name=None,
                item_name=ui.selected_item_name,
                target_side="enemy",
                target_index=target_enemy_index,
            )

        # physical/special（command候補を再参照）
        cand = ui.command_candidates[ui.selected_command_idx]
        cmd = cand.cmd
        kind = cand.kind
        if kind not in ENEMY_SINGLE_TARGET_KINDS:
            ui.logs.append(
                f"[WARN] target_enemy で不正な kind={kind}, cmd={cmd} -> physical にフォールバック"
            )
            kind = "physical"  # 安全側に倒す

        return PlannedAction(
            kind=kind,
            command=cmd,
            spell_name=None,
            item_name=None,
            target_side="enemy",
            target_index=target_enemy_index,
        )

    def log_on_confirm(target_enemy_index: int) -> str:
        enemy_name = getattr(
            enemies[target_enemy_index], "name", f"enemy[{target_enemy_index}]"
        )

        if ui.selected_spell_name:
            return (
                f"[確定] {member.name}: Magic {ui.selected_spell_name} → {enemy_name}"
            )
        if ui.selected_item_name:
            return f"[確定] {member.name}: Item {ui.selected_item_name} → {enemy_name}"

        cand = ui.command_candidates[ui.selected_command_idx]
        cmd = cand.cmd
        return f"[確定] {member.name}: {cmd} → {enemy_name}"

    # ★ここが修正点：target_side ではなく「target_list」共通ハンドラを呼ぶ
    return handle_target_list_keydown(
        event=event,
        ui=ui,
        alive_indices=alive,
        target_side="enemy",
        on_escape_mode=escape_mode,
        make_action=make_action,
        log_on_confirm=log_on_confirm,
    )
