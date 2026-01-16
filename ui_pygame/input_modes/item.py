from __future__ import annotations

from typing import Optional
import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def handle_item_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    """
    item input_mode の処理
    - ↑↓: アイテム選択
    - ESC/BS: commandへ戻る
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

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = "command"
        ui.selected_target_all = False
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    _play_se(getattr(ui, "se_enter", None))

    item_name = str(ui.item_candidates[ui.selected_item_idx][0])
    ui.selected_item_name = item_name

    ui.selected_target_side_idx = 0
    ui.target_side = "enemy"
    ui.input_mode = "target_side"
    ui.logs.append(f"[入力] 対象(敵/味方/自分)選択: {item_name}")
    return False
