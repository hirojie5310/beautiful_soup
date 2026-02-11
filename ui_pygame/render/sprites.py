# ============================================================
# render.sprites: UI共通描画関数群
# draw_enemy_sprites_row / draw_floating_texts など

# draw_enemy_sprites_row: 敵画像を横に並べて描画
# draw_floating_texts: 敵画像上にフローティングテキストを描画
# ============================================================

from __future__ import annotations
import pygame
from typing import Optional, Dict, Literal
import os

from combat.models import EnemyRuntime, PartyMemberRuntime
from utils.text_normalize import normalize_text_basic


def load_enemy_sprite_images(folder: str) -> Dict[str, pygame.Surface]:
    """
    folder配下の *.png をロードして
    {"s32_32_001": Surface, ...} を返す
    """
    cache: Dict[str, pygame.Surface] = {}
    for fn in os.listdir(folder):
        if not normalize_text_basic(fn).endswith(".png"):
            continue
        sprite_id = os.path.splitext(fn)[0]
        path = os.path.join(folder, fn)

        surf = pygame.image.load(path).convert_alpha()
        cache[sprite_id] = surf
    return cache


def load_party_idle_motion_images(
    folder: str,
    *,
    frame_w: int = 55,
    frame_h: int = 60,
) -> Dict[str, list[pygame.Surface]]:
    """
    Load motion sheets (*.png) and cache 3 horizontal frames.
    Expected sheet size is 165x60 (55x60 x 3), but this function crops safely.
    """
    cache: Dict[str, list[pygame.Surface]] = {}
    if not os.path.isdir(folder):
        return cache

    for fn in os.listdir(folder):
        if not normalize_text_basic(fn).endswith(".png"):
            continue
        key = os.path.splitext(fn)[0]
        path = os.path.join(folder, fn)
        sheet = pygame.image.load(path).convert_alpha()
        if sheet.get_width() <= 0 or sheet.get_height() <= 0:
            continue

        frames: list[pygame.Surface] = []
        for frame_idx in range(3):
            src_x = frame_idx * frame_w
            if src_x >= sheet.get_width():
                src_x = 0
            crop_w = min(frame_w, sheet.get_width() - src_x)
            crop_h = min(frame_h, sheet.get_height())
            if crop_w <= 0 or crop_h <= 0:
                continue
            frames.append(
                sheet.subsurface(pygame.Rect(src_x, 0, crop_w, crop_h)).copy()
            )

        if not frames:
            continue
        while len(frames) < 3:
            frames.append(frames[0].copy())
        cache[normalize_text_basic(key)] = frames
    return cache


def load_attack_effect_frames(
    folder: str,
    *,
    frame_w: int = 41,
    frame_h: int = 44,
    frame_count: int = 2,
) -> list[pygame.Surface]:
    """
    Load the first *.png under folder as a horizontal attack-effect sheet.
    Returns fixed-size frames (defaults: 41x44 x 2).
    """
    if not os.path.isdir(folder):
        return []

    png_files = sorted(
        fn for fn in os.listdir(folder) if normalize_text_basic(fn).endswith(".png")
    )
    if not png_files:
        return []

    path = os.path.join(folder, png_files[0])
    sheet = pygame.image.load(path).convert_alpha()
    if sheet.get_width() <= 0 or sheet.get_height() <= 0:
        return []

    frames: list[pygame.Surface] = []
    for frame_idx in range(max(1, frame_count)):
        src_x = frame_idx * frame_w
        if src_x >= sheet.get_width():
            src_x = 0
        crop_w = min(frame_w, sheet.get_width() - src_x)
        crop_h = min(frame_h, sheet.get_height())
        if crop_w <= 0 or crop_h <= 0:
            continue
        frame = sheet.subsurface(pygame.Rect(src_x, 0, crop_w, crop_h)).copy()
        if frame.get_width() != frame_w or frame.get_height() != frame_h:
            frame = pygame.transform.scale(frame, (frame_w, frame_h))
        frames.append(frame)

    if not frames:
        return []
    while len(frames) < frame_count:
        frames.append(frames[0].copy())
    return frames


# pygame helper: slice sprite sheet into fixed-size tiles
def slice_sprite_sheet(
    image_path: str,
    tile_w: int,
    tile_h: int,
    cols: int,
    rows: int,
) -> list[pygame.Surface]:
    sheet = pygame.image.load(image_path).convert_alpha()
    sprites = []

    for row in range(rows):
        for col in range(cols):
            rect = pygame.Rect(
                col * tile_w,
                row * tile_h,
                tile_w,
                tile_h,
            )
            sprite = sheet.subsurface(rect).copy()
            sprites.append(sprite)

    return sprites


def draw_enemy_sprites_row(
    screen: pygame.Surface,
    font: pygame.font.Font,
    enemies: list,
    sprite_cache: dict[str, pygame.Surface],
    *,
    y: int,
    scale: int = 2,
    gap: int = 20,
    placeholder_size: tuple[int, int] = (32, 32),
    show_dead_overlay: bool = True,
) -> list[pygame.Rect]:
    """
    画面中段に敵画像を横に並べて表示する。
    戻り値: 敵ごとの描画Rect（敵画像のRect。spriteなしの場合はダミーRect）
    """
    rects: list[pygame.Rect] = []

    show_list = enemies

    # Prepare render surfaces and fallback sizes.
    rendered: list[tuple[EnemyRuntime, Optional[pygame.Surface], int, int]] = []
    for e in show_list:
        sid = getattr(e, "sprite_id", None)
        surf = sprite_cache.get(sid) if sid else None

        if surf is not None and scale != 1:
            surf = pygame.transform.scale(
                surf, (surf.get_width() * scale, surf.get_height() * scale)
            )

        if surf is None:
            w, h = placeholder_size
        else:
            w, h = surf.get_width(), surf.get_height()

        rendered.append((e, surf, w, h))

    # 横幅合計を計算して中央寄せ
    total_w = sum(w for _, _, w, _ in rendered) + gap * max(0, len(rendered) - 1)
    x = (screen.get_width() - total_w) // 2

    for e, surf, w, h in rendered:
        alive = getattr(e, "hp", 0) > 0

        # Sprite rect used for floating-text anchors.
        r = pygame.Rect(x, y, w, h)

        if surf is not None:
            screen.blit(surf, r.topleft)

            # Dim dead enemies.
            if show_dead_overlay and not alive:
                overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 140))
                screen.blit(overlay, r.topleft)

        else:
            # dammy frame for the case of no sprite
            pygame.draw.rect(screen, (80, 80, 100), r, border_radius=4)
            pygame.draw.rect(screen, (160, 160, 180), r, 2, border_radius=4)

        # Name color
        name_col = (240, 240, 240) if alive else (140, 140, 140)
        name_surf = font.render(e.name, True, name_col)
        screen.blit(name_surf, (r.centerx - name_surf.get_width() // 2, r.bottom + 4))

        rects.append(r)
        x += w + gap

    return rects


# フィールド矩形の中に収める関数
def draw_enemy_sprites_formation(
    screen: pygame.Surface,
    font: pygame.font.Font,
    enemies: list,
    sprite_cache: dict[str, pygame.Surface],
    *,
    area_rect: pygame.Rect,
    side: Literal["left", "right"] = "left",
    formation: Literal["auto", "3x2", "2x3", "row"] = "auto",
    scale: int = 2,
    gap_x: int = 18,
    gap_y: int = 14,
    placeholder_size: tuple[int, int] = (32, 32),
    show_dead_overlay: bool = True,
    name_offset_y: int = 4,
    highlighted_index: int | None = None,
    highlight_pulse_ms: int = 0,
) -> list[pygame.Rect]:
    """
    area_rect 内に敵スプライトを隊列配置する。
    - side="left" で左寄せ（FF風）
    - 最大6体想定：auto は 1-3体=1列, 4-6体=3x2 を推奨
    戻り値: 敵ごとの描画Rect（floating等の基準）
    """
    rects: list[pygame.Rect] = []
    show_list = enemies

    # 1) Prepare render surfaces and fallback sizes.
    rendered: list[tuple[EnemyRuntime, Optional[pygame.Surface], int, int]] = []
    for e in show_list:
        sid = getattr(e, "sprite_id", None)
        surf = sprite_cache.get(sid) if sid else None

        if surf is not None and scale != 1:
            surf = pygame.transform.scale(
                surf, (surf.get_width() * scale, surf.get_height() * scale)
            )

        if surf is None:
            w, h = placeholder_size
        else:
            w, h = surf.get_width(), surf.get_height()
        rendered.append((e, surf, w, h))

    n = len(rendered)
    if n == 0:
        return rects

    # 2) Decide formation
    if formation == "auto":
        # 最大6なら：1-3は1列、4-6は3x2が扱いやすい
        if n <= 3:
            cols, rows = n, 1
        else:
            cols, rows = 3, 2
    elif formation == "3x2":
        cols, rows = 3, 2
    elif formation == "2x3":
        cols, rows = 2, 3
    else:  # "row"
        cols, rows = n, 1

    cols = max(1, cols)
    rows = max(1, rows)

    # 3) Compute max cell size across sprites.
    cell_w = max(w for _, _, w, _ in rendered)
    cell_h = max(h for _, _, _, h in rendered)

    # Include name text area in each row height.
    cell_h_with_name = cell_h + (font.get_linesize() + name_offset_y)

    grid_w = cols * cell_w + (cols - 1) * gap_x
    grid_h = rows * cell_h_with_name + (rows - 1) * gap_y

    # 4) Anchor within area_rect.
    if side == "left":
        start_x = area_rect.left + 24
    else:
        start_x = area_rect.right - 24 - grid_w

    start_y = area_rect.top + max(0, (area_rect.height - grid_h) // 2)

    # 5) Place sprites on the grid.
    for idx, (e, surf, w, h) in enumerate(rendered):
        col = idx % cols
        row = idx // cols
        if row >= rows:
            break
        # Cell origin.
        cx = start_x + col * (cell_w + gap_x)
        cy = start_y + row * (cell_h_with_name + gap_y)

        x = cx + (cell_w - w) // 2
        y = cy + (cell_h - h) // 2

        alive = getattr(e, "hp", 0) > 0
        r = pygame.Rect(x, y, w, h)

        if surf is not None:
            screen.blit(surf, r.topleft)
            if show_dead_overlay and not alive:
                overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 140))
                screen.blit(overlay, r.topleft)
        else:
            pygame.draw.rect(screen, (80, 80, 100), r, border_radius=4)
            pygame.draw.rect(screen, (160, 160, 180), r, 2, border_radius=4)

        if highlighted_index is not None and idx == int(highlighted_index) and alive:
            pulse = 160 + (highlight_pulse_ms % 120)
            glow = pygame.Surface((w + 10, h + 10), pygame.SRCALPHA)
            glow.fill((255, 255, 120, min(255, pulse)))
            screen.blit(
                glow, (r.left - 5, r.top - 5), special_flags=pygame.BLEND_RGBA_ADD
            )
            pygame.draw.rect(
                screen, (255, 240, 120), r.inflate(6, 6), 2, border_radius=6
            )

        # Name color
        name_col = (240, 240, 240) if alive else (140, 140, 140)
        name_surf = font.render(e.name, True, name_col)
        name_x = r.centerx - name_surf.get_width() // 2
        name_y = r.bottom + name_offset_y
        screen.blit(name_surf, (name_x, name_y))

        rects.append(r)

    return rects


def draw_party_idle_sprites_column(
    screen: pygame.Surface,
    party_members: list[PartyMemberRuntime],
    motion_cache: dict[str, list[pygame.Surface]],
    *,
    area_rect: pygame.Rect,
    frame_w: int = 55,
    frame_h: int = 60,
    gap: int = 6,
    perspective_shift_px: int = 40,
    front_row_shift_px: int | None = None,
    show_dead_overlay: bool = True,
    frame_indices: list[int] | None = None,
) -> list[pygame.Rect]:
    """
    Draw party idle sprites in a top-to-bottom column inside area_rect.
    The sprite key prefers PartyMemberRuntime.portrait_key.
    """
    rects: list[pygame.Rect] = []
    if not party_members:
        return rects

    n = len(party_members)
    total_h = n * frame_h + max(0, n - 1) * gap
    start_y = area_rect.top + max(0, (area_rect.height - total_h) // 2)
    base_x = area_rect.left + max(0, (area_rect.width - frame_w) // 2)

    # Add slight depth: upper members are shifted toward screen center,
    # while the bottom member stays at the original x position.
    screen_center_x = screen.get_rect().centerx
    shift_sign = -1 if area_rect.centerx >= screen_center_x else 1
    max_shift = max(0, int(perspective_shift_px))
    front_shift_default = max(0, int(frame_w))

    for idx, member in enumerate(party_members):
        key = normalize_text_basic(getattr(member, "portrait_key", "") or "")
        if not key:
            key = normalize_text_basic(getattr(member, "name", "") or "")
        frames = motion_cache.get(key) if key else None
        frame_idx = 0
        if frame_indices is not None and 0 <= idx < len(frame_indices):
            frame_idx = max(0, min(2, int(frame_indices[idx])))
        surf = None
        if frames:
            surf = frames[frame_idx] if frame_idx < len(frames) else frames[0]

        y = start_y + idx * (frame_h + gap)
        if n <= 1:
            shift = 0
        else:
            depth_ratio = (n - 1 - idx) / (n - 1)  # top=1.0 ... bottom=0.0
            shift = int(round(max_shift * depth_ratio))
        x = base_x + shift_sign * shift

        row = str(getattr(getattr(member, "base", None), "row", "") or "").lower()
        if row == "front":
            front_shift = front_shift_default
            if front_row_shift_px is not None:
                front_shift = max(0, int(front_row_shift_px))
            x += shift_sign * front_shift

        x = max(area_rect.left, min(area_rect.right - frame_w, x))

        r = pygame.Rect(x, y, frame_w, frame_h)
        alive = getattr(member, "hp", 0) > 0

        if surf is not None:
            if surf.get_width() != frame_w or surf.get_height() != frame_h:
                surf = pygame.transform.scale(surf, (frame_w, frame_h))
            screen.blit(surf, r.topleft)
            if show_dead_overlay and not alive:
                overlay = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 140))
                screen.blit(overlay, r.topleft)
        else:
            pygame.draw.rect(screen, (80, 80, 100), r, border_radius=4)
            pygame.draw.rect(screen, (160, 160, 180), r, 2, border_radius=4)
            if show_dead_overlay and not alive:
                overlay = pygame.Surface((frame_w, frame_h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 100))
                screen.blit(overlay, r.topleft)

        rects.append(r)

    return rects
