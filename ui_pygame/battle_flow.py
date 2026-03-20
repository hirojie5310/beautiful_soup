# ui_pygame/battle_flow.py
# battle_flow は BattleContext にだけ依存
# UI層は BattleAppContext に閉じる
import pygame
import random

from combat.battle_result import BattleResult

from ui_pygame.battle_context import BattleContext
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from ui_pygame.controller import BattleController
from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext  # UI専用 ctx
from ui_pygame.input_handler import handle_keydown
from ui_pygame.render.floating_texts import (
    draw_floating_texts,
    draw_attack_effects,
    apply_battle_events_to_ui,
)
from ui_pygame.render.hub import draw_header
from ui_pygame.render.enemy_panel import draw_enemy_panel
from ui_pygame.render.party_panel import draw_party_panel
from ui_pygame.render.sprites import (
    draw_enemy_sprites_formation,
    draw_party_idle_sprites_column,
)
from ui_pygame.render.log_panel import draw_log_panel
from ui_pygame.render.command_panel import draw_command_panel


def run_one_battle(
    screen,
    clock,
    font,
    cfg,
    audio,
    state,
    enemy_sprite_cache,
    party_motion_cache,
    attack_effect_frames,
    status_icon_cache: StatusIconCache,
    *,
    ctx: BattleContext,
) -> BattleResult:
    """
    return: BattleResult
    """

    # enemies are from BattleContext
    party_members = ctx.party_members
    enemies = ctx.enemies

    controller = BattleController(
        rng=random.Random()
    )  # ★毎回作り直すと _bgm_started もリセットされる

    ui = BattleUIState()
    ui.turn = 1
    ui.phase = "input"
    ui.input_mode = "member"
    ui.logs = ["Battle started."]
    ui.scroll = 0
    ui.planned_actions = [None] * len(party_members)

    # Carry spell dictionary from battle context
    ui.spells_by_name = ctx.spells_expanded or {}
    ui.se_enter = ctx.se.enter
    ui.se_confirm = ctx.se.confirm
    ui.se_invalid = ctx.se.invalid
    ui.party_motion_frame_indices = [0] * len(party_members)
    ui.party_attack_anim_queue = []
    ui.party_attack_anim_active = None
    ui.enemy_acting_highlight_idx = None
    ui.party_attack_anim_elapsed_ms = 0
    ui.party_attack_anim_step_ms = int(getattr(cfg, "motion_attack_step_ms", 90))
    ui.party_attack_anim_gap_ms = int(getattr(cfg, "motion_attack_gap_ms", 500))
    ui.party_attack_anim_gap_elapsed_ms = 0
    ui.attack_effects = []
    ui.attack_effect_frames = list(attack_effect_frames)

    # ★次に入力すべきメンバー（戦闘可能な先頭）を選ぶ
    def first_alive_member_index() -> int:
        for i, pm in enumerate(party_members):
            if not ctx.is_out_of_battle(pm.state):
                return i
        return 0

    def find_next_unfilled_member_index(ui: BattleUIState) -> int:
        for i, act in enumerate(ui.planned_actions):
            if ctx.is_out_of_battle(party_members[i].state):
                continue
            if act is None:
                return i
        return first_alive_member_index()

    ui.selected_member_idx = first_alive_member_index()
    ui.command_candidates = ctx.get_job_commands(party_members[ui.selected_member_idx])

    # BattleAppContext を「UI用」に限定して作る
    ui_ctx = BattleAppContext(
        config=cfg,
        party_members=party_members,
        enemies=enemies,
        items_by_name=state.items_by_name,
        normalize_battle_command=ctx.normalize_battle_command,
        reset_target_flags=ctx.reset_target_flags,
        is_out_of_battle=ctx.is_out_of_battle,
        get_job_commands=ctx.get_job_commands,
        build_magic_candidates_for_member=ctx.build_magic_candidates_for_member,
        build_item_candidates_for_battle=ctx.build_item_candidates_for_battle,
        make_planned_action=ctx.make_planned_action,
        find_next_unfilled_member_index=find_next_unfilled_member_index,
    )

    running_battle = True
    while running_battle:
        ui.dt_ms = clock.tick(cfg.fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return BattleResult.QUIT

            # End phase: confirm with Enter/Space
            if ui.phase == "end" and event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return ui.battle_result

            if ui.phase == "input" and event.type == pygame.KEYDOWN:
                handle_keydown(ui, event, ui_ctx)

            if event.type == pygame.MOUSEWHEEL:
                ui.scroll += event.y

        controller.update(
            ui=ui,
            party_members=party_members,
            enemies=enemies,
            state=state,
            battle_ctx=ctx,
            app_ctx=ui_ctx,
            save=state.save,
            spells_by_name=ui.spells_by_name,
            items_by_name=state.items_by_name,
        )

        if ui.events:
            audio.handle_events(ui.events)
            apply_battle_events_to_ui(ui, ui.events)
            ui.events.clear()
        else:
            apply_battle_events_to_ui(ui, [])

        # -------- render --------
        # 0) Layout constants
        W, H = cfg.width, cfg.height

        TOP_H = 140
        BOT_H = 150
        MID_H = H - TOP_H - BOT_H  # 250

        M = 16  # 外周マージン
        G = 12  # パネル間ギャップ

        top_rect = pygame.Rect(0, 0, W, TOP_H)
        field_rect = pygame.Rect(0, TOP_H, W, MID_H)
        bottom_rect = pygame.Rect(0, TOP_H + MID_H, W, BOT_H)

        # Top HUD: enemy panel (left) and party panel (right)
        enemy_rect = pygame.Rect(M, M, 360, TOP_H - M * 2)  # 360x108
        party_rect = pygame.Rect(W - M - 560, M, 560, TOP_H - M * 2)  # 560ﾃ・08

        # Middle field: enemy sprites on left, party motions on right
        party_motion_w = 110
        mid_split_gap = 12
        enemy_field_rect = pygame.Rect(
            field_rect.left,
            field_rect.top,
            max(0, field_rect.width - party_motion_w - mid_split_gap),
            field_rect.height,
        )
        party_motion_rect = pygame.Rect(
            enemy_field_rect.right + mid_split_gap,
            field_rect.top,
            party_motion_w,
            field_rect.height,
        )

        # 下HUD：LOG（左）＋ COMMAND（右）を横並び
        LOG_H = 170
        hud_y = H - LOG_H - M

        cmd_w = 360
        cmd_h = LOG_H  # ★LOGと同じ高さにする（横並びが崩れない）

        # 右にCOMMAND、残りをLOG
        cmd_rect = pygame.Rect(W - M - cmd_w, hud_y, cmd_w, cmd_h)
        log_rect = pygame.Rect(M, hud_y, (W - M * 2) - cmd_w - G, LOG_H)

        # Clamp scroll for log window
        approx_visible_lines = max(1, (log_rect.h - 40) // font.get_linesize())
        max_scroll = max(0, len(ui.logs) - approx_visible_lines)
        ui.scroll = max(0, min(ui.scroll, max_scroll))

        # 2) Back Ground
        screen.fill((10, 10, 20))

        # 任意：フィールド領域をうっすら区切る（デバッグにも便利）
        # pygame.draw.rect(screen, (40, 40, 60), field_rect, 1)

        # 3) Draw header
        draw_header(screen, font, ui.turn, ui.phase)

        # 4) Draw enemy and party sprites
        ui.enemy_sprite_rects = draw_enemy_sprites_formation(
            screen,
            font,
            enemies,
            enemy_sprite_cache,
            area_rect=enemy_field_rect,
            side="left",
            formation="auto",  # 1-3: 1 column/ 4-6: 3x2
            scale=2,
            highlighted_index=getattr(ui, "enemy_acting_highlight_idx", None),
            highlight_pulse_ms=max(
                1, int(getattr(ui, "party_attack_anim_elapsed_ms", 0))
            ),
        )
        ui.party_sprite_rects = draw_party_idle_sprites_column(
            screen,
            party_members,
            party_motion_cache,
            area_rect=party_motion_rect,
            frame_w=cfg.motion_frame_w,
            frame_h=cfg.motion_frame_h,
            gap=6,
            frame_indices=ui.party_motion_frame_indices,
        )

        # Draw attack effects / floating texts over sprites
        draw_attack_effects(screen, ui)
        draw_floating_texts(screen, font, ui)

        # Draw party status panel
        draw_party_panel(
            screen,
            font,
            party_members,
            ui.selected_member_idx,
            ui.planned_actions,
            ui,
            rect=party_rect,
            status_icon_cache=status_icon_cache,
        )

        # 7) Draw enemy panel and targeting highlight
        selected_enemy_index = None
        blink_all = False
        if ui.phase == "input" and ui.input_mode == "target_enemy":
            alive_indices = [
                i for i, e in enumerate(enemies) if getattr(e, "hp", 0) > 0
            ]
            if getattr(ui, "selected_target_all", False):
                blink_all = True
            else:
                if alive_indices:
                    idx = min(ui.selected_target_idx, len(alive_indices) - 1)
                    selected_enemy_index = alive_indices[idx]

        draw_enemy_panel(
            screen,
            font,
            enemies,
            rect=enemy_rect,
            selected_index=selected_enemy_index,
            blink_all=blink_all,
        )

        # 8) Draw log panel
        draw_log_panel(
            screen,
            font,
            ui.logs,
            ui.scroll,
            rect=log_rect,
        )

        # 9) 下HUD：コマンド（右下）※入力中のみ
        if ui.phase == "input" and ui.input_mode != "member":
            draw_command_panel(screen, font, ui, party_members, enemies, rect=cmd_rect)

        pygame.display.flip()

    # Safety fallback (normally not reached)
    return BattleResult.CONTINUE
