# ============================================================
# input_handler: 巨大な if/elif を、input_modeごとに関数分割
# pygame event -> controller呼び出し（巨大if/elifを分割）

# BattleUIState: UIのカーソル、入力モード、ログ、floating_texts 等
# FloatingText: 敵の上に表示するダメージ等のテキスト
# LogWindow: 画面下部のログウィンドウ
# ============================================================

# ui_pygame/input_handler.py
from __future__ import annotations
import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext

from ui_pygame.input_modes.member import handle_member_keydown
from ui_pygame.input_modes.command import handle_command_keydown
from ui_pygame.input_modes.magic import handle_magic_keydown
from ui_pygame.input_modes.aoe_choice import handle_aoe_choice_keydown
from ui_pygame.input_modes.item import handle_item_keydown
from ui_pygame.input_modes.target_side import handle_target_side_keydown
from ui_pygame.input_modes.target_enemy import handle_target_enemy_keydown
from ui_pygame.input_modes.target_ally import handle_target_ally_keydown


def handle_keydown(
    ui: BattleUIState, event: pygame.event.Event, ctx: BattleAppContext
) -> None:
    if ui.phase != "input":
        return

    mode = ui.input_mode
    committed = False

    if mode == "member":
        committed = handle_member_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "command":
        committed = handle_command_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "magic":
        committed = handle_magic_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "aoe_choice":
        committed = handle_aoe_choice_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "item":
        committed = handle_item_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "target_side":
        committed = handle_target_side_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "target_enemy":
        committed = handle_target_enemy_keydown(event=event, ui=ui, ctx=ctx)
    elif mode == "target_ally":
        committed = handle_target_ally_keydown(event=event, ui=ui, ctx=ctx)

    # committed 後の共通後処理（必要ならここに寄せる）
    if committed:
        # 確定SE（あるなら）
        if getattr(ui, "se_confirm", None):
            ui.se_confirm.play()

        ctx.on_committed(ui)

        # ★ 全員分の行動がそろったら resolve へ
        if ctx.all_actions_committed(ui):
            ui.phase = "resolve"
            ui.input_mode = "resolve"
            return  # ← ここで終わり

        # ★ まだなら「次に未確定のキャラ」へ進める
        n = len(ctx.party_members)
        start = ui.selected_member_idx

        next_idx = None
        for step in range(1, n + 1):
            i = (start + step) % n
            pm = ctx.party_members[i]

            # 戦闘不能は飛ばす
            if ctx.is_out_of_battle(pm.state):
                continue

            # まだ行動未確定の人を探す
            if ui.planned_actions[i] is None:
                next_idx = i
                break

        if next_idx is not None:
            ui.selected_member_idx = next_idx
            ui.command_candidates = ctx.get_job_commands(ctx.party_members[next_idx])

            # 次の人の入力に入る。ここは好みでどっちでもOK：
            # - すぐコマンド一覧を出したいなら "command"
            # - まずメンバー行にカーソルを当てたいなら "member"
            ui.input_mode = "command"
