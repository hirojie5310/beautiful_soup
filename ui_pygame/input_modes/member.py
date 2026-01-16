from __future__ import annotations

from typing import Optional
import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def handle_member_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    """
    member input_mode の処理
    - ↑↓ : キャラ選択
    - Enter: コマンド選択へ
    - Backspace: そのキャラの planned_action を未入力に戻す
    返り値: 行動が確定したら True（memberでは基本 False）
    """
    n = len(ctx.party_members)
    if n <= 0:
        return False

    if event.key == pygame.K_UP:
        ui.selected_member_idx = (ui.selected_member_idx - 1) % n
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_member_idx = (ui.selected_member_idx + 1) % n
        return False

    if event.key == pygame.K_BACKSPACE:
        member = ctx.party_members[ui.selected_member_idx]
        ui.planned_actions[ui.selected_member_idx] = None
        ui.logs.append(
            f"[取消] {getattr(member, 'name', 'member')} を未入力に戻しました"
        )
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    # Enter
    _play_se(getattr(ui, "se_enter", None))

    member = ctx.party_members[ui.selected_member_idx]

    # 戦闘不能はスキップ（既存挙動）
    if ctx.is_out_of_battle(getattr(member, "state", None)):
        ui.logs.append("[入力] 戦闘不能のため選択不可")
        return False

    # ★前の人の AoE 状態などを必ず消す（既存挙動）
    ui.selected_target_all = False
    ui.selected_spell_name = None
    ui.selected_item_name = None

    # command へ
    ui.input_mode = "command"
    ui.command_candidates = ctx.get_job_commands(member)
    ui.selected_command_idx = 0

    ui.logs.append(f"[入力] {getattr(member, 'name', 'member')} コマンド選択")
    return False
