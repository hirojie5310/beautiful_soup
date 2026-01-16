# ============================================================
# target_select:

# handle_target_list_keydown: target_enemy / target_ally 共通ハンドラ
# ============================================================

# ui_pygame/input_modes/target_select.py
from __future__ import annotations
from typing import Optional, Sequence, Callable

import pygame

from combat.models import PlannedAction, TargetSide

from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import InputMode


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def _cycle_index(cur: int, n: int, delta: int) -> int:
    if n <= 0:
        return 0
    return (cur + delta) % n


def handle_target_list_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    alive_indices: Sequence[int],
    target_side: TargetSide,  # "enemy" or "ally"
    on_escape_mode: InputMode,  # 戻り先モード
    make_action: Callable[[int], PlannedAction],  # target_index -> PlannedAction
    log_on_confirm: Callable[[int], str],  # target_index -> log string
) -> bool:
    """
    target_enemy / target_ally 共通ハンドラ
    戻り先や PlannedAction の作り方は外から注入する。
    返り値: 行動が確定したら True（＝se_confirm鳴らす/次へ進む判断に使える）
    """

    # 対象ゼロなら呼び出し側でモード戻し済みにする設計でもOKだが、
    # 念のためここでも安全に。
    if not alive_indices:
        ui.logs.append("[入力] 対象がいません")
        ui.input_mode = on_escape_mode
        return False

    if event.key == pygame.K_UP:
        ui.selected_target_idx = _cycle_index(
            ui.selected_target_idx, len(alive_indices), -1
        )
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_target_idx = _cycle_index(
            ui.selected_target_idx, len(alive_indices), +1
        )
        return False

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = on_escape_mode
        # 物理/特殊へ戻る場合だけ AoE を消したい等があるなら、呼び出し側でやるか、
        # ここで条件分岐してもOK
        return False

    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
        if getattr(ui, "se_enter", None):
            _play_se(ui.se_enter)

        # alive_indices は「実インデックス」の列
        idx = alive_indices[min(ui.selected_target_idx, len(alive_indices) - 1)]

        # UI反映
        ui.target_side = target_side
        ui.selected_target_idx = 0

        # 行動確定
        act = make_action(idx)
        ui.planned_actions[ui.selected_member_idx] = act

        if getattr(ui, "se_confirm", None):
            _play_se(ui.se_confirm)

        ui.logs.append(log_on_confirm(idx))

        # 次へ
        ui.input_mode = "member"
        # reset_target_flags は呼び出し側に寄せてもいいが、
        # 「確定したら必ずクリア」ならここで呼んでもOK

        return True

    return False
