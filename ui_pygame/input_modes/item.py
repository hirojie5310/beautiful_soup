from __future__ import annotations

from typing import Optional
import pygame

from combat.item_effects import infer_battle_item_target_side
from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def _infer_item_target_side(
    *,
    item_name: str,
    ctx: BattleAppContext,
) -> str | None:
    item_json = ctx.items_by_name.get(item_name, {})
    if not item_json:
        return None
    return infer_battle_item_target_side(item_json)


def handle_item_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    """
    item input_mode の処理
    - ↑↓: アイテム選択
    - BACK/BS: commandへ戻る
    - Enter: item確定 → target_sideへ
    返り値: 行動が確定したら True（ここでは確定しないので基本 False）
    """
    if not ui.item_candidates:
        ui.logs.append("[入力] 使用可能なアイテムがありません")
        ui.input_mode = "command"
        return False

    if event.key == pygame.K_UP:
        ui.selected_item_idx = (ui.selected_item_idx - 1) % len(ui.item_candidates)
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_item_idx = (ui.selected_item_idx + 1) % len(ui.item_candidates)
        return False

    if event.key == pygame.K_BACKSPACE:
        ui.input_mode = "command"
        ui.selected_target_all = False
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    _play_se(getattr(ui, "se_enter", None))

    item_name = str(ui.item_candidates[ui.selected_item_idx][0])
    ui.selected_item_name = item_name

    inferred_target_side = _infer_item_target_side(item_name=item_name, ctx=ctx)
    ui.selected_target_idx = 0
    ui.selected_target_all = False

    if inferred_target_side == "enemy":
        ui.selected_target_side_idx = 0
        ui.target_side = "enemy"
        ui.input_mode = "target_enemy"
        ui.logs.append(f"[入力] ターゲット(敵)選択: {item_name}")
        return False

    if inferred_target_side == "ally":
        ui.selected_target_side_idx = 1
        ui.target_side = "ally"
        ui.input_mode = "target_ally"
        ui.logs.append(f"[入力] ターゲット(味方)選択: {item_name}")
        return False

    ui.selected_target_side_idx = 0
    ui.target_side = "enemy"
    ui.input_mode = "target_side"
    ui.logs.append(f"[入力] 対象(敵/味方/自分)選択: {item_name}")
    return False
