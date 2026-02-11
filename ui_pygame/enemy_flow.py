# ui_pygame/enemy_flow.py

from __future__ import annotations
import pygame
from typing import Sequence


from combat.enums import World
from combat.enemy_selection import (
    LocationGroup,
    LocationMonsters,
)
from combat.models import PartyMemberRuntime
from ui_pygame.assets_py.portrait_cache import PortraitCache
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from scenes.menu import open_menu_pygame
from ui_pygame.audio.ui_se import play_se
from ui_pygame.ui_utils import calc_view_range
from ui_pygame.assets_py.map_image_cache import load_map_preview

WORLD_COLORS = {
    World.FLOATING_CONTINENT: (120, 180, 255),
    World.WORLD: (120, 220, 120),
    World.DARKNESS: (200, 80, 120),
}

LINE_HEIGHT = 28
LIST_TOP = 80
VISIBLE_LINES = 12


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

                elif event.key == pygame.K_ESCAPE:
                    play_se(ui_se, "cancel")
                    raise SystemExit

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

                elif event.key == pygame.K_BACKSPACE:
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
