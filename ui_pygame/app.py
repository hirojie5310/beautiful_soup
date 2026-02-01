# ui_pygame/app.py
from __future__ import annotations

import random
import copy
from pathlib import Path
from dataclasses import dataclass
from typing import cast, Sequence, Callable
from collections import Counter

import pygame

from assets.data.data_loader import load_explicit_groups
from ui_pygame.controller import BattleController
from ui_pygame.state import (
    BattleUIState,
)  # BattleUIState を state.py に移している想定（未なら現状のimportに合わせて）
from ui_pygame.input_handler import handle_keydown

# ここは「今 main がいる場所」から持ってきて import する
# 例：combat / util / render など、あなたの構成に合わせて import 先を調整
from combat.enums import World
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
    build_location_index,
    pick_enemy_names,
    build_groups,
    LocationGroup,
    LocationMonsters,
)
from combat.progression import apply_victory_rewards
from combat.save_prompt import (
    save_savedata_with_backup,
    prompt_save_progress_and_write_pygame,
    _toast_pygame,
)
from system.exp_system import LevelTable
from system.cp_system import load_job_attribution

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
from ui_pygame.audio_manager import AudioManager


from ui_pygame.app_context import BattleAppContext  # ctx を定義した場所
from ui_pygame.logic import (
    reset_target_flags,
    build_magic_candidates_for_member as build_magic_candidates_for_member_idx,
    build_item_candidates_for_battle as build_item_candidates_for_battle_fn,
    make_planned_action,
)
from ui_pygame.assets_py.portrait_cache import PortraitCache
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from ui_pygame.assets_py.map_image_cache import load_map_preview

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
    face_dir: str = "assets/images/faces/"
    status_icon_dir: str = "assets/images/status_icons/"

    # ★BGM 定義（論理名 → ファイル名）
    bgm_enemy_select: str = "Fortune_Teller2"
    bgm_battle1: str = "battle1"
    bgm_battle2: str = "battle2"
    bgm_victory: str = "victory"
    bgm_requiem: str = "requiem"

    # ★SE 定義
    se_enter_path: str = "assets/sounds/se/se_enter.ogg"
    se_confirm_path: str = "assets/sounds/se/se_confirm.ogg"
    se_rareitem_path: str = "assets/sounds/se/se_rareitem.ogg"
    se_invalid: str = "assets/sounds/se/se_invalid.ogg"
    se_enter_volume: float = 0.35
    se_confirm_volume: float = 0.6
    se_rareitem_volume: float = 0.6
    se_invalid_volume: float = 0.6


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
    ui_se = build_ui_se(cfg)
    battle_ui_se = {
        "rareitem": ui_se["rareitem"],
    }

    state = init_runtime_state()

    k = next(iter(state.spells))

    spells_expanded = expand_spells_for_summons(state.spells)

    level_table = LevelTable("assets/data/level_exp.csv")
    job_attr = load_job_attribution("assets/data/job_attribution.csv")
    explicit_groups = load_explicit_groups("assets/data/explicit_groups.json")

    portrait_cache = PortraitCache(base_dir=cfg.face_dir)
    status_icon_cache = StatusIconCache(cfg.status_icon_dir)
    # 使用予定のステータス異常を列挙
    status_icon_cache.preload(
        [
            "poison",
            "blind",
            "mini",
            "silence",
            "toad",
            "confusion",
            "sleep",
            "paralysis",
            "petrification",
            "partial petrification",
            "ko",
        ]
    )

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
            flat_locations = build_location_index(state.monsters)
            # 存在チェック
            all_locations = {loc.location for loc in flat_locations}
            for gname, entry in explicit_groups.items():
                for m in entry["locations"]:
                    if m not in all_locations:
                        print(f"[WARN] Unknown location in group '{gname}': {m}")

            groups = build_groups(
                flat_locations,
                explicit_groups=explicit_groups,
            )

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

            while True:
                group = choose_location_group_pygame(
                    screen,
                    font,
                    groups,
                    party_members=party_members,
                    level_table=level_table,
                    job_attr=job_attr,
                    weapons=state.weapons,
                    armors=state.armors,
                    save_dict=state.save,
                    save_path=SAVE_PATH,
                    jobs_by_name=state.jobs_by_name,
                    portrait_cache=portrait_cache,
                    status_icon_cache=status_icon_cache,
                    recalc_stats_fn=recalc_stats_fn,
                    build_magic_fn=build_magic_fn,
                    spells_by_name=state.spells,
                    items_by_name=state.items_by_name,
                    ui_se=ui_se,
                )

                selected = choose_location_floor_pygame(
                    screen,
                    font,
                    group.children,
                    ui_se=ui_se,
                )

                if selected is not None:
                    break  # 決定

            """
            selected = choose_location_pygame(
                screen,
                font,
                locations,
                party_avg_lv=party_avg_lv,
                party_members=party_members,
                level_table=level_table,  # ★追加
                job_attr=job_attr,  # ★追加
                weapons=state.weapons,  # ★追加
                armors=state.armors,  # ★追加
                save_dict=state.save,
                save_path=SAVE_PATH,  # ←あなたの実ファイルパスに合わせて
                jobs_by_name=state.jobs_by_name,
                portrait_cache=portrait_cache,  # ★追加
                status_icon_cache=status_icon_cache,  # ★追加
                recalc_stats_fn=recalc_stats_fn,  # ★追加
                build_magic_fn=build_magic_fn,
                spells_by_name=state.spells,  # ★追加（ここが元の state.spells）
                items_by_name=state.items_by_name,  # ★追加
                ui_se=ui_se,  # ★これだけ,  # ★追加
            )
            """
            enemy_names = pick_enemy_names(selected, state.monsters, k_min=2, k_max=6)

        enemies = build_enemies(
            enemy_defs_by_name=state.monsters,
            spells_by_name=state.spells,
            enemy_names=enemy_names,
        )

        ctx_base = {
            "enemies": enemies,
            "spells_expanded": spells_expanded,
            "se_enter": ui_se["enter"],
            "se_confirm": ui_se["confirm"],
            "se_rareitem": ui_se["rareitem"],
            "se_invalid": ui_se["invalid"],
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
            status_icon_cache=status_icon_cache,  # ★追加
            ctx_base=ctx_base,
        )

        if end_reason == "quit":
            app_running = False
            break

        # =========================
        # ★戦闘後処理（勝利時）
        # =========================
        if end_reason == "enemy_defeated":
            # 事実の確定（ロジック）
            victory = apply_victory_rewards(
                party_members=party_members,
                enemies=enemies,
                state=state,
                level_table=level_table,
            )
            # 演出・表示（UI）
            show_victory_result_pygame(
                screen,
                font,
                victory,
                battle_ui_se=battle_ui_se,
            )
            # 永続化の確認（UX）差分表示 → 保存確認 → 保存
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
    status_icon_cache: StatusIconCache,
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
            status_icon_cache=status_icon_cache,
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


def play_se(ui_se: dict | None, key: str):
    if not ui_se:
        return
    snd = ui_se.get(key)
    if snd:
        snd.play()


LINE_HEIGHT = 28
LIST_TOP = 80
VISIBLE_LINES = 12


# スクロール計算ヘルパー
def calc_view_range(cursor: int, total: int, visible: int) -> tuple[int, int]:
    """
    表示開始 index と終了 index を返す
    """
    if total <= visible:
        return 0, total

    half = visible // 2
    start = max(0, cursor - half)
    end = start + visible

    if end > total:
        end = total
        start = end - visible

    return start, end


WORLD_COLORS = {
    World.FLOATING_CONTINENT: (120, 180, 255),
    World.WORLD: (120, 220, 120),
    World.DARKNESS: (200, 80, 120),
}


def choose_location_group_pygame(
    screen: pygame.Surface,
    font: pygame.font.Font,
    groups: list[LocationGroup],
    *,
    party_members: Sequence[PartyMemberRuntime],
    level_table=None,
    job_attr=None,
    weapons=None,
    armors=None,  # ★追加
    save_dict=None,
    save_path=None,
    jobs_by_name=None,
    portrait_cache: PortraitCache,  # ★追加
    status_icon_cache: StatusIconCache,  # ★追加
    recalc_stats_fn=None,  # ★追加
    build_magic_fn=None,  # ★追加
    spells_by_name=None,  # ★追加
    items_by_name=None,  # ★追加
    ui_se: dict[str, pygame.mixer.Sound],
) -> LocationGroup:
    cursor = 0
    clock = pygame.time.Clock()
    preview_cache: dict[str, pygame.Surface | None] = {}

    while True:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
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
                        job_attr=job_attr,
                        weapons=weapons,
                        armors=armors,
                        jobs_by_name=jobs_by_name,
                        portrait_cache=portrait_cache,  # ★追加
                        status_icon_cache=status_icon_cache,  # ★追加
                        recalc_stats_fn=recalc_stats_fn,
                        build_magic_fn=build_magic_fn,
                        spells_by_name=spells_by_name,  # ★ここが重要
                        items_by_name=items_by_name,
                        ui_se=ui_se,
                    )  # ← game_state等は後述
                    continue

                if event.key == pygame.K_UP:
                    cursor = (cursor - 1) % len(groups)
                    play_se(ui_se, "cursor")

                elif event.key == pygame.K_DOWN:
                    cursor = (cursor + 1) % len(groups)
                    play_se(ui_se, "cursor")

                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    play_se(ui_se, "decide")
                    return groups[cursor]

        # --- 描画 ---
        screen.fill((0, 0, 0))

        title = font.render("Select Location", True, (255, 255, 255))
        screen.blit(title, (40, 20))

        start, end = calc_view_range(cursor, len(groups), VISIBLE_LINES)

        y = LIST_TOP
        prev_world: World | None = None  # ★追加

        for i in range(start, end):
            g = groups[i]

            # --- ★ world 見出し ---
            if g.world != prev_world:
                if g.world is not None:
                    header_color = WORLD_COLORS.get(g.world, (200, 200, 200))
                    header_text = f"=== {g.world.value.upper()} ==="
                else:
                    header_color = (200, 200, 200)
                    header_text = "=== UNKNOWN ==="

                header = font.render(header_text, True, header_color)
                screen.blit(header, (40, y))
                y += LINE_HEIGHT
                prev_world = g.world

            # --- 通常のグループ描画 ---
            is_sel = i == cursor

            color = (255, 80, 80) if g.boss_count > 0 else (160, 200, 255)
            if not is_sel:
                color = tuple(c // 2 for c in color)

            text = f"{g.group_name}  (LV:{g.min_level}-{g.max_level})"
            surf = font.render(text, True, color)

            if is_sel:
                screen.blit(font.render("▶", True, color), (20, y))

            screen.blit(surf, (40, y))
            y += LINE_HEIGHT

        # --- スクロールサイン ---
        if start > 0:
            screen.blit(
                font.render("▲", True, (120, 120, 120)),
                (360, LIST_TOP - 20),
            )

        if end < len(groups):
            screen.blit(
                font.render("▼", True, (120, 120, 120)),
                (360, LIST_TOP + VISIBLE_LINES * LINE_HEIGHT),
            )

        # --- マッププレビュー ---
        selected_group = groups[cursor]
        preview = load_map_preview(selected_group.group_name, preview_cache)

        PREVIEW_X = 420
        PREVIEW_Y = 80
        PREVIEW_W = 360
        PREVIEW_H = 240

        pygame.draw.rect(
            screen,
            (120, 120, 120),
            (PREVIEW_X - 2, PREVIEW_Y - 2, PREVIEW_W + 4, PREVIEW_H + 4),
            1,
        )

        if preview is not None:
            img = preview
            iw, ih = img.get_size()

            scale = min(PREVIEW_W / iw, PREVIEW_H / ih)
            scaled = pygame.transform.smoothscale(
                img,
                (int(iw * scale), int(ih * scale)),
            )

            screen.blit(
                scaled,
                (
                    PREVIEW_X + (PREVIEW_W - scaled.get_width()) // 2,
                    PREVIEW_Y + (PREVIEW_H - scaled.get_height()) // 2,
                ),
            )

        # --- 下部ヒント ---
        w, h = screen.get_width(), screen.get_height()
        hint = font.render(
            "↑↓: Select  Enter: Decision  M: Menu  ESC: Quit", True, (180, 180, 180)
        )
        screen.blit(
            hint,
            (w // 2 - hint.get_width() // 2, h - 60),
        )

        pygame.display.flip()


def choose_location_floor_pygame(
    screen: pygame.Surface,
    font: pygame.font.Font,
    locations: list[LocationMonsters],
    *,
    ui_se=None,
) -> LocationMonsters | None:
    assert ui_se is None or isinstance(ui_se, dict)

    cursor = 0
    clock = pygame.time.Clock()

    while True:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    cursor = (cursor - 1) % len(locations)
                    play_se(ui_se, "cursor")

                elif event.key == pygame.K_DOWN:
                    cursor = (cursor + 1) % len(locations)
                    play_se(ui_se, "cursor")

                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    play_se(ui_se, "decide")
                    return locations[cursor]

                elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    play_se(ui_se, "cancel")
                    return None

        # --- 描画 ---
        screen.fill((0, 0, 0))

        title = font.render("Select Floor", True, (255, 255, 255))
        screen.blit(title, (40, 20))

        start, end = calc_view_range(cursor, len(locations), VISIBLE_LINES)

        y = LIST_TOP
        for i in range(start, end):
            loc = locations[i]
            is_sel = i == cursor

            color = (255, 80, 80) if loc.boss_count > 0 else (160, 200, 255)
            if not is_sel:
                color = tuple(c // 2 for c in color)

            # 表示は「階層名だけ」にしてもFFっぽい
            text = f"{loc.location}  (LV:{loc.min_level}-{loc.max_level})"
            surf = font.render(text, True, color)

            if is_sel:
                screen.blit(font.render("▶", True, color), (20, y))

            screen.blit(surf, (40, y))
            y += LINE_HEIGHT

        # --- スクロールサイン ---
        if start > 0:
            screen.blit(
                font.render("▲", True, (120, 120, 120)),
                (360, LIST_TOP - 20),
            )

        if end < len(locations):
            screen.blit(
                font.render("▼", True, (120, 120, 120)),
                (360, LIST_TOP + VISIBLE_LINES * LINE_HEIGHT),
            )

        pygame.display.flip()


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


RARE_ITEMS = {
    "Elixir",
    "Yoichi Arrow",
    "Onion Shield",
    "Onion Helm",
    "Onion Armor",
    "Onion Sword",
}


# ★戦闘勝利結果表示
def show_victory_result_pygame(
    screen,
    font,
    victory,
    battle_ui_se,
):
    ui = BattleUIState()
    ui.se_rareitem = pygame.mixer.Sound(battle_ui_se["rareitem"])

    # ① EXP
    _toast_pygame(
        screen,
        font,
        f"EXP +{victory['gained_exp']}",
        ms=1000,
    )

    # ② LvUP
    for name, old_lv, new_lv in victory["levelups"]:
        _toast_pygame(
            screen,
            font,
            f"{name} Lv{old_lv} → Lv{new_lv}!",
            ms=1000,
        )

    # ③ Gil
    if victory["gained_gil"] > 0:
        _toast_pygame(
            screen,
            font,
            f"{victory['gained_gil']} ギルを手に入れた！",
            ms=1000,
        )

    # ④ CP
    if victory["gained_cp"] > 0:
        _toast_pygame(
            screen,
            font,
            f"{victory['gained_cp']} CPを手に入れた！",
            ms=1000,
        )

    # ⑤ Drop Item
    dropped_items = victory.get("dropped_item", [])
    if dropped_items:
        loot_counter = Counter(dropped_items)

        for item, count in loot_counter.items():
            if item not in RARE_ITEMS:
                if count == 1:
                    msg = f"{item} を手に入れた！"
                else:
                    msg = f"{item} を{count}こ手に入れた！"

                _toast_pygame(
                    screen,
                    font,
                    msg,
                    ms=1000,
                )

        for item, count in loot_counter.items():
            if item in RARE_ITEMS:
                ui.se_rareitem.play()
                if count == 1:
                    msg = f"✨ {item} を手に入れた！ ✨"
                else:
                    msg = f"✨ {item} を{count}こ手に入れた！ ✨"

                _toast_pygame(
                    screen,
                    font,
                    msg,
                    ms=1500,
                )


# UI 用 SE をまとめたファクトリ関数
def build_ui_se(cfg: BattleAppConfig) -> dict[str, pygame.mixer.Sound]:
    ui_se = {
        "enter": pygame.mixer.Sound(cfg.se_enter_path),
        "confirm": pygame.mixer.Sound(cfg.se_confirm_path),
        "rareitem": pygame.mixer.Sound(cfg.se_rareitem_path),
        "invalid": pygame.mixer.Sound(cfg.se_invalid),
    }

    ui_se["enter"].set_volume(cfg.se_enter_volume)
    ui_se["confirm"].set_volume(cfg.se_confirm_volume)
    ui_se["rareitem"].set_volume(cfg.se_rareitem_volume)
    ui_se["invalid"].set_volume(cfg.se_rareitem_volume)  # or 専用 volume を後で追加

    return ui_se
