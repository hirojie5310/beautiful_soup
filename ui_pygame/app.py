# ui_pygame/app.py
from __future__ import annotations

import random
import copy
from pathlib import Path
from dataclasses import dataclass
from typing import cast, Sequence, Callable

import pygame

from ui_pygame.controller import BattleController
from ui_pygame.state import (
    BattleUIState,
)  # BattleUIState を state.py に移している想定（未なら現状のimportに合わせて）
from ui_pygame.input_handler import handle_keydown

# ここは「今 main がいる場所」から持ってきて import する
# 例：combat / util / render など、あなたの構成に合わせて import 先を調整
from combat.models import PartyMemberRuntime, FinalCharacterStats, EquipmentSet
from combat.char_build import (
    build_party_members_from_save,
    compute_character_final_stats,
)
from combat.runtime_state import init_runtime_state
from combat.magic_menu import build_party_magic_lists, expand_spells_for_summons
from combat.enemy_build import build_enemies
from combat.life_check import is_out_of_battle
from combat.input_ui import normalize_battle_command
from combat.enemy_selection import (
    LocationMonsters,
    build_location_index,
    pick_enemy_names,
    calc_party_avg_level,
    danger_label,
)
from combat.progression import (
    compute_exp_reward,
    apply_victory_exp_rewards,
    persist_party_progress_to_save,
)
from combat.progression import apply_victory_exp_rewards, persist_party_progress_to_save
from combat.save_prompt import (
    save_savedata_with_backup,
    diff_party_progress,
    prompt_save_progress_and_write_pygame,
)
from system.exp_system import LevelTable

from ui_pygame.logic import get_job_commands
from ui_pygame.render.hub import draw_header
from ui_pygame.render.sprites import (
    load_enemy_sprite_images,
    draw_enemy_sprites_formation,
)
from ui_pygame.render.floating_texts import (
    draw_floating_texts,
    apply_battle_events_to_ui,
)
from ui_pygame.render.party_panel import draw_party_panel
from ui_pygame.render.enemy_panel import draw_enemy_panel
from ui_pygame.render.command_panel import draw_command_panel
from ui_pygame.render.enemy_panel import draw_enemy_panel
from ui_pygame.render.log_panel import draw_log_panel
from ui_pygame.render.log_scroll import calc_log_scroll_max, handle_mousewheel
from ui_pygame.audio_manager import AudioManager


from ui_pygame.app_context import BattleAppContext  # ctx を定義した場所
from ui_pygame.logic import (
    reset_target_flags,
    find_next_unfilled,
    build_magic_candidates_for_member as build_magic_candidates_for_member_idx,
    build_item_candidates_for_battle as build_item_candidates_for_battle_fn,
    make_planned_action,
)

from scenes.menu import open_menu_pygame


SAVE_PATH = Path("assets/data/ffiii_savedata.json")


@dataclass
class BattleAppConfig:
    width: int = 960
    height: int = 540
    fps: int = 60
    caption: str = "FF3風 Battle Simulator"
    font_name: str = "meiryo"
    font_size: int = 18
    enemy_sprite_dir: str = "assets/images/enemy_sprites"

    # ★追加
    audio_dir: str = "assets/sounds/"

    # ★BGM 定義（論理名 → ファイル名）
    bgm_enemy_select: str = "Fortune_Teller2"
    bgm_battle1: str = "battle1"
    bgm_battle2: str = "battle2"
    bgm_victory: str = "victory"
    bgm_requiem: str = "requiem"

    # ★SE 定義
    se_enter_path: str = "assets/sounds/se/se_enter.ogg"
    se_confirm_path: str = "assets/sounds/se/se_confirm.ogg"
    se_enter_volume: float = 0.35
    se_confirm_volume: float = 0.6


def run_battle_app(
    enemy_names: list[str] | None = None, *, config: BattleAppConfig | None = None
) -> None:
    cfg = config or BattleAppConfig()

    pygame.init()
    screen = pygame.display.set_mode((cfg.width, cfg.height))
    pygame.display.set_caption(cfg.caption)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(cfg.font_name, cfg.font_size)

    enemy_sprite_cache = load_enemy_sprite_images(cfg.enemy_sprite_dir)

    pygame.mixer.init()
    audio = AudioManager(base_dir=cfg.audio_dir)

    state = init_runtime_state()
    spells_expanded = expand_spells_for_summons(state.spells)

    level_table = LevelTable("assets/data/level_exp.csv")

    se_enter = pygame.mixer.Sound(cfg.se_enter_path)
    se_confirm = pygame.mixer.Sound(cfg.se_confirm_path)
    se_enter.set_volume(cfg.se_enter_volume)
    se_confirm.set_volume(cfg.se_confirm_volume)

    app_running = True
    while app_running:
        audio.play_bgm(cfg.bgm_enemy_select, fade_ms=500)

        # ★戦闘前のsaveを保持（差分チェック用）
        save_before = copy.deepcopy(state.save)

        party_members = build_party_members_from_save(
            save=state.save,
            weapons=state.weapons,
            armors=state.armors,
            jobs_by_name=state.jobs_by_name,
            level_table=level_table,
        )
        party_magic_lists = cast(
            Sequence[Sequence[tuple[str, int, int]]], build_party_magic_lists(state)
        )

        build_magic_fn: Callable[[int], list[tuple[str, int, int]]] = (
            lambda member_idx: build_magic_candidates_for_member_idx(
                party_magic_lists, member_idx
            )
        )

        if enemy_names is None:
            locations = build_location_index(state.monsters)
            party_avg_lv = calc_party_avg_level(party_members)

            # 装備変更後は変更を反映させるため必ず呼ぶ
            def recalc_stats_fn(
                actor: PartyMemberRuntime, weapons: dict, armors: dict
            ) -> FinalCharacterStats:
                eq = actor.equipment or EquipmentSet()
                return compute_character_final_stats(
                    base=actor.base,
                    eq=eq,
                    weapons_by_name=weapons,
                    armors_by_name=armors,
                    job_name=actor.job.name,  # ★ここがポイント
                )

            selected = choose_location_pygame(
                screen,
                font,
                locations,
                party_avg_lv=party_avg_lv,
                party_members=party_members,
                level_table=level_table,  # ★追加
                weapons=state.weapons,  # ★追加
                armors=state.armors,  # ★追加
                save_dict=state.save,
                save_path=SAVE_PATH,  # ←あなたの実ファイルパスに合わせて
                jobs_by_name=state.jobs_by_name,
                recalc_stats_fn=recalc_stats_fn,  # ★追加
            )
            enemy_names = pick_enemy_names(selected, state.monsters, k_min=2, k_max=6)

        enemies = build_enemies(
            enemy_defs_by_name=state.monsters,
            spells_by_name=state.spells,
            enemy_names=enemy_names,
        )

        ctx_base = {
            "enemies": enemies,
            "spells_expanded": spells_expanded,
            "se_enter": se_enter,
            "se_confirm": se_confirm,
            "ctx_kwargs": dict(
                normalize_battle_command=normalize_battle_command,
                reset_target_flags=reset_target_flags,
                is_out_of_battle=is_out_of_battle,
                get_job_commands=get_job_commands,
                build_magic_candidates_for_member=build_magic_fn,
                build_item_candidates_for_battle=lambda: build_item_candidates_for_battle_fn(
                    state.items_by_name, state.save
                ),
                make_planned_action=make_planned_action,
            ),
        }

        end_reason = run_one_battle(
            screen,
            clock,
            font,
            cfg,
            audio,
            party_members,
            state,
            enemy_sprite_cache,
            ctx_base=ctx_base,
        )

        if end_reason == "quit":
            app_running = False
            break

        # =========================
        # ★戦闘後処理（勝利時）
        # =========================
        if end_reason == "enemy_defeated":
            # ① exp/level 反映（余りが出たら加算なしの仕様は apply_victory_exp_rewards 側で）
            apply_victory_exp_rewards(
                party_members,
                enemies,
                level_table=level_table,
                weapons=state.weapons,
                armors=state.armors,
            )

            # 勝利直後、persist の「前」
            print("[DBG] before persist save eq:", state.save["party"][0]["equipment"])

            # ② runtimeの成長を save に書き戻す（state.save を更新）
            persist_party_progress_to_save(state.save, party_members)

            # persist の「後」
            print("[DBG] after persist save eq:", state.save["party"][0]["equipment"])

            # ③ 差分表示 → 保存確認 → 保存
            prompt_save_progress_and_write_pygame(
                screen=screen,
                font=font,
                before_save=save_before,
                after_save=state.save,
                save_path=Path("assets/data/ffiii_savedata.json"),
                save_func=save_savedata_with_backup,  # ★ここで注入
                caption="Save updated Level/EXP to file?",
            )

        enemy_names = None

    pygame.quit()


def run_one_battle(
    screen,
    clock,
    font,
    cfg,
    audio,
    party_members,
    state,
    enemy_sprite_cache,
    *,
    ctx_base,
) -> str:
    """
    return: end_reason (例: 'enemy_defeated', 'party_defeated', 'escape' など)
    """
    end_reason = "end"

    # enemies は ctx_base が持つ selected_enemy_names などから作る、でもOK
    enemies = ctx_base["enemies"]

    controller = BattleController(
        rng=random.Random()
    )  # ★毎回作り直すと _bgm_started もリセットされる

    ui = BattleUIState()
    ui.turn = 1
    ui.phase = "input"
    ui.input_mode = "member"
    ui.logs = ["戦闘開始！"]
    ui.scroll = 0
    ui.planned_actions = [None] * len(party_members)

    # ctx（依存注入）※先に作る
    ctx = BattleAppContext(
        config=cfg,
        party_members=party_members,
        enemies=enemies,
        **ctx_base["ctx_kwargs"],
    )

    # ★追加：元の run_battle_app にあった初期化を戻す
    ui.spells_by_name = ctx_base.get("spells_expanded") or {}  # None対策
    ui.se_enter = ctx_base.get("se_enter")
    ui.se_confirm = ctx_base.get("se_confirm")

    # ★次に入力すべきメンバー（戦闘可能な先頭）を選ぶ
    def first_alive_member_index() -> int:
        for i, pm in enumerate(party_members):
            if not ctx.is_out_of_battle(pm.state):
                return i
        return 0

    ui.selected_member_idx = first_alive_member_index()
    ui.command_candidates = ctx.get_job_commands(party_members[ui.selected_member_idx])

    # ctx（依存注入）
    ctx = BattleAppContext(
        config=cfg,
        party_members=party_members,
        enemies=enemies,
        **ctx_base["ctx_kwargs"],
    )

    running_battle = True
    while running_battle:
        ui.dt_ms = clock.tick(cfg.fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"

            # ★戦闘終了後の入力（例：Enterで敵選択へ戻る）
            if ui.phase == "end" and event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    end_reason = getattr(ui, "battle_end_reason", "end")
                    running_battle = False
                    break

            if ui.phase == "input" and event.type == pygame.KEYDOWN:
                handle_keydown(ui, event, ctx)

            if event.type == pygame.MOUSEWHEEL:
                ui.scroll += event.y

        controller.update(
            ui=ui,
            party_members=party_members,
            enemies=enemies,
            state=state,
            ctx=ctx,
            save=state.save,
            spells_by_name=ui.spells_by_name,
            items_by_name=state.items_by_name,
        )

        if ui.events:
            audio.handle_events(ui.events)
            apply_battle_events_to_ui(ui, ui.events)
            ui.events.clear()

        # -------- render --------
        # 0) レイアウト定義（960×540前提だが cfgに追従）
        W, H = cfg.width, cfg.height

        TOP_H = 140
        BOT_H = 150
        MID_H = H - TOP_H - BOT_H  # 250

        M = 16  # 外周マージン
        G = 12  # パネル間ギャップ

        top_rect = pygame.Rect(0, 0, W, TOP_H)
        field_rect = pygame.Rect(0, TOP_H, W, MID_H)
        bottom_rect = pygame.Rect(0, TOP_H + MID_H, W, BOT_H)

        # 上HUD：左=ENEMY / 右=PARTY（FF風：敵左・味方右）
        enemy_rect = pygame.Rect(M, M, 360, TOP_H - M * 2)  # 360×108
        party_rect = pygame.Rect(W - M - 560, M, 560, TOP_H - M * 2)  # 560×108

        # 下HUD：LOG（左）＋ COMMAND（右）を横並び
        LOG_H = 170
        hud_y = H - LOG_H - M

        cmd_w = 360
        cmd_h = LOG_H  # ★LOGと同じ高さにする（横並びが崩れない）

        # 右にCOMMAND、残りをLOG
        cmd_rect = pygame.Rect(W - M - cmd_w, hud_y, cmd_w, cmd_h)
        log_rect = pygame.Rect(M, hud_y, (W - M * 2) - cmd_w - G, LOG_H)

        # 1) ログスクロールのクランプ（log_panel側が行数計算するので、ここは安全側に）
        # scroll=0 が最新、増えるほど過去へ
        # ここでは「最大どこまで遡れるか」だけ制限
        approx_visible_lines = max(1, (log_rect.h - 40) // font.get_linesize())
        max_scroll = max(0, len(ui.logs) - approx_visible_lines)
        ui.scroll = max(0, min(ui.scroll, max_scroll))

        # 2) 背景
        screen.fill((10, 10, 20))

        # 任意：フィールド領域をうっすら区切る（デバッグにも便利）
        # pygame.draw.rect(screen, (20, 20, 30), field_rect, 0)
        # pygame.draw.rect(screen, (40, 40, 60), field_rect, 1)

        # 3) ヘッダ（左上）
        draw_header(screen, font, ui.turn, ui.phase)

        # 4) フィールド：敵スプライト（左側隊列）
        ui.enemy_sprite_rects = draw_enemy_sprites_formation(
            screen,
            font,
            enemies,
            enemy_sprite_cache,
            area_rect=field_rect,
            side="left",
            formation="auto",  # 1-3: 1列 / 4-6: 3x2
            scale=2,
        )

        # 5) フローティングテキスト（スプライトの上に出すならこの位置）
        draw_floating_texts(screen, font, ui)

        # 6) 上HUD：パーティ（右上）
        draw_party_panel(
            screen,
            font,
            party_members,
            ui.selected_member_idx,
            ui.planned_actions,
            ui,
            rect=party_rect,
        )

        # 7) 上HUD：敵パネル（左上）※選択/点滅状態を計算して渡す
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

        # 8) 下HUD：ログ（左下）
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

    # ★型チェッカー対策（通常ここには来ない想定）
    return end_reason


def choose_location_pygame(
    screen,
    font,
    entries,
    *,
    party_avg_lv: int,
    caption="Select Location",
    party_members=None,
    level_table=None,
    weapons=None,
    armors=None,  # ★追加
    save_dict=None,
    save_path=None,
    jobs_by_name=None,
    recalc_stats_fn=None,  # ★追加
):
    """
    操作:
      - ↑↓: 選択移動
      - PageUp/PageDown: 大きく移動
      - Enter: 決定
      - Esc: キャンセル（SystemExit）
      - 文字入力: インクリメンタル検索（Backspaceで削除）
    """
    clock = pygame.time.Clock()

    query = ""
    filtered = list(entries)
    selected_idx = 0
    top_idx = 0  # 表示の先頭（スクロール用）

    # 表示行数は画面サイズから計算
    line_h = font.get_linesize() + 4
    header_h = line_h * 3
    help_h = line_h + 16
    max_rows = max(3, (screen.get_height() - header_h - help_h) // line_h)

    def apply_filter() -> None:
        nonlocal filtered, selected_idx, top_idx
        q = query.strip().lower()
        if not q:
            filtered = list(entries)
        else:
            filtered = [e for e in entries if q in e.location.lower()]
        if not filtered:
            selected_idx = 0
            top_idx = 0
        else:
            selected_idx = min(selected_idx, len(filtered) - 1)
            top_idx = min(top_idx, max(0, len(filtered) - max_rows))

    def clamp_scroll() -> None:
        nonlocal top_idx
        if selected_idx < top_idx:
            top_idx = selected_idx
        elif selected_idx >= top_idx + max_rows:
            top_idx = selected_idx - max_rows + 1
        top_idx = max(0, min(top_idx, max(0, len(filtered) - max_rows)))

    def move(delta: int) -> None:
        nonlocal selected_idx
        if not filtered:
            return
        selected_idx = (selected_idx + delta) % len(filtered)
        clamp_scroll()

    # IME含む日本語入力を本気でやるなら別途対応が必要ですが、
    # まずは英数字の検索で十分ならこれでOKです。
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    raise SystemExit

                # ★追加：Mキーでメニューへ
                if event.key == pygame.K_m:
                    # ここでメニュー画面へ（戻ってきたらこの画面に復帰）
                    open_menu_pygame(
                        screen,
                        font,
                        party_members,
                        save_dict=save_dict,
                        save_path=save_path,
                        level_table=level_table,
                        weapons=weapons,
                        armors=armors,
                        jobs_by_name=jobs_by_name,
                        recalc_stats_fn=recalc_stats_fn,
                    )  # ← game_state等は後述
                    continue

                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if filtered:
                        return filtered[selected_idx]
                    # 候補0件なら何もしない
                    continue

                if event.key == pygame.K_UP:
                    move(-1)
                    continue
                if event.key == pygame.K_DOWN:
                    move(+1)
                    continue
                if event.key == pygame.K_PAGEUP:
                    move(-max_rows)
                    continue
                if event.key == pygame.K_PAGEDOWN:
                    move(+max_rows)
                    continue
                if event.key == pygame.K_HOME:
                    if filtered:
                        selected_idx = 0
                        clamp_scroll()
                    continue
                if event.key == pygame.K_END:
                    if filtered:
                        selected_idx = len(filtered) - 1
                        clamp_scroll()
                    continue

                if event.key == pygame.K_BACKSPACE:
                    if query:
                        query = query[:-1]
                        apply_filter()
                    continue

                # 文字入力（pygame2の event.unicode が使える）
                ch = event.unicode
                if ch and ch.isprintable():
                    # 制御文字などは除外
                    if ch not in ("\r", "\n", "\t"):
                        query += ch
                        apply_filter()
                    continue

            # --- マウスホイール（pygame2） ---
            if event.type == pygame.MOUSEWHEEL:
                # event.y: 上に回すと +1, 下に回すと -1
                # メニュー的には上回し = 選択を上へ なので符号を反転
                move(-event.y)
                continue

            # --- 互換用：pygame1系のホイール（button 4/5） ---
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:  # wheel up
                    move(-1)
                    continue
                if event.button == 5:  # wheel down
                    move(+1)
                    continue

        # ---------- 描画 ----------
        screen.fill((0, 0, 0))

        # タイトル
        title = font.render(caption, True, (255, 255, 255))
        screen.blit(title, (16, 12))

        # 検索文字列
        qtxt = font.render(f"Search: {query}", True, (200, 200, 200))
        screen.blit(qtxt, (16, 12 + line_h))

        # 件数
        cnt = font.render(
            f"{len(filtered)}/{len(entries)} locations", True, (160, 160, 160)
        )
        screen.blit(cnt, (16, 12 + line_h * 2))

        y0 = 12 + header_h

        if not filtered:
            msg = font.render(
                "No matches. Type to search, Backspace to delete.",
                True,
                (255, 180, 180),
            )
            screen.blit(msg, (16, y0))
        else:
            visible = filtered[top_idx : top_idx + max_rows]
            for i, e in enumerate(visible):
                row_idx = top_idx + i
                is_sel = row_idx == selected_idx

                prefix = "▶ " if is_sel else "  "
                lv_range = (
                    f"{e.min_level}"
                    if e.min_level == e.max_level
                    else f"{e.min_level}-{e.max_level}"
                )
                # 表示部
                dg = danger_label(e, party_avg_lv)

                text = (
                    f"{prefix}{e.location}  "
                    f"(LV: {e.avg_level} / {e.min_level}-{e.max_level}) "
                    f"(Danger: {dg})"
                )

                # 例：色分け
                if dg == "Boss":
                    color = (255, 80, 80)  # 赤
                elif dg == "HIGH":
                    color = (255, 180, 0)  # オレンジ
                elif dg == "LOW":
                    color = (120, 200, 255)  # 青
                else:
                    color = (220, 220, 220)

                row = font.render(text, True, color)
                screen.blit(row, (16, y0 + i * line_h))

        # ---------- ヘルプ（画面下） ----------
        help_text = "M: Menu   Enter: Select   Esc: Quit   ↑↓/Wheel: Move"
        help_surf = font.render(help_text, True, (160, 160, 160))
        screen.blit(help_surf, (16, screen.get_height() - help_surf.get_height() - 12))

        pygame.display.flip()
        clock.tick(60)


def prompt_save_yes_no_pygame(screen, font, caption: str) -> bool:
    import pygame

    # 1フレームで終わると押しっぱなしが拾われるので、KEYUPを見るのが安全
    while True:
        screen.fill((0, 0, 0))
        lines = [
            caption,
            "",
            "Y: Save   N: Don't save",
        ]
        y = 120
        for line in lines:
            surf = font.render(line, True, (255, 255, 255))
            rect = surf.get_rect(center=(screen.get_width() // 2, y))
            screen.blit(surf, rect)
            y += 40

        pygame.display.flip()

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYUP:
                if ev.key == pygame.K_y:
                    return True
                if ev.key == pygame.K_n or ev.key == pygame.K_ESCAPE:
                    return False
