from __future__ import annotations

from typing import Optional
import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def handle_aoe_choice_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    """
    aoe_choice input_mode の処理（魔法のみ）
    - ↑↓: 0=単体, 1=全体
    - ESC/BS: magicへ戻る
    - Enter:
        - 全体なら target_enemy へ（target_side スキップ）
        - 単体なら target_side へ
    返り値: 行動が確定したら True（ここでは確定しないので基本 False）
    """
    if event.key == pygame.K_UP:
        ui.selected_aoe_idx = (ui.selected_aoe_idx - 1) % 2
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_aoe_idx = (ui.selected_aoe_idx + 1) % 2
        return False

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = "magic"
        ui.selected_target_all = False
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    _play_se(getattr(ui, "se_enter", None))

    choose_all = ui.selected_aoe_idx == 1  # 0=単体, 1=全体
    ui.selected_target_all = choose_all

    spell_name = ui.selected_spell_name
    member = ctx.party_members[ui.selected_member_idx]

    if choose_all:
        # ★全体はここで確定（target_enemyへ行かない）
        act = ctx.make_planned_action(
            kind="magic",
            command="Magic",
            member_idx=ui.selected_member_idx,
            target_side="enemy",
            target_index=None,  # 全体なので None 推奨
            spell_name=spell_name,
            target_all=True,  # ★必ず True
        )
        ui.planned_actions[ui.selected_member_idx] = act

        _play_se(getattr(ui, "se_confirm", None))
        ui.logs.append(
            f"[確定] {getattr(member, 'name', 'member')}: Magic {spell_name} → 敵全体"
        )

        ui.input_mode = "member"
        return True  # ★ committed=True にして確定

    # 単体は今まで通り target_side へ（敵/味方/自分を選ぶ）
    ui.selected_target_side_idx = 0
    ui.input_mode = "target_side"
    ui.logs.append("[入力] 単体 → 対象(敵/味方/自分)選択へ")
    return False
