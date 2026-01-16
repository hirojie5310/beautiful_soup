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

from combat.models import EnemyRuntime


def load_enemy_sprite_images(folder: str) -> Dict[str, pygame.Surface]:
    """
    folder配下の *.png をロードして
    {"s32_32_001": Surface, ...} を返す
    """
    cache: Dict[str, pygame.Surface] = {}
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".png"):
            continue
        sprite_id = os.path.splitext(fn)[0]
        path = os.path.join(folder, fn)

        surf = pygame.image.load(path).convert_alpha()
        cache[sprite_id] = surf
    return cache


# pygameでスプライトシートを切り出す
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

    show_list = (
        enemies  # 死亡も表示したいなら enemies のままでOK（あなたの意図に合わせて）
    )

    # 表示用Surfaceと幅を準備（Noneでもplaceholder幅を確保）
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

        # 「敵画像のRect」を作る（これがfloatingの基準）
        r = pygame.Rect(x, y, w, h)

        if surf is not None:
            screen.blit(surf, r.topleft)

            # 死亡時の暗転（任意）
            if show_dead_overlay and not alive:
                overlay = pygame.Surface((w, h), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 140))
                screen.blit(overlay, r.topleft)

        else:
            # spriteが無い場合のダミー枠
            pygame.draw.rect(screen, (80, 80, 100), r, border_radius=4)
            pygame.draw.rect(screen, (160, 160, 180), r, 2, border_radius=4)

        # 名前（画像の下）
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
) -> list[pygame.Rect]:
    """
    area_rect 内に敵スプライトを隊列配置する。
    - side="left" で左寄せ（FF風）
    - 最大6体想定：auto は 1-3体=1列, 4-6体=3x2 を推奨
    戻り値: 敵ごとの描画Rect（floating等の基準）
    """
    rects: list[pygame.Rect] = []
    show_list = enemies

    # 1) 表示用Surface作成（スケール込み）
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

    # 2) フォーメーション決定
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

    # 3) 各セルの最大サイズ（グリッドの整列のため）
    cell_w = max(w for _, _, w, _ in rendered)
    cell_h = max(h for _, _, _, h in rendered)

    # 名前表示分だけ縦を少し余裕
    cell_h_with_name = cell_h + (font.get_linesize() + name_offset_y)

    grid_w = cols * cell_w + (cols - 1) * gap_x
    grid_h = rows * cell_h_with_name + (rows - 1) * gap_y

    # 4) area_rect 内での開始位置（左右寄せ＋縦中央）
    if side == "left":
        start_x = area_rect.left + 24
    else:
        start_x = area_rect.right - 24 - grid_w

    start_y = area_rect.top + max(0, (area_rect.height - grid_h) // 2)

    # 5) 実配置（奥→手前っぽく見せるなら row を上→下で少しずらすのもアリ）
    for idx, (e, surf, w, h) in enumerate(rendered):
        col = idx % cols
        row = idx // cols
        if row >= rows:
            break  # 余った分は描かない（通常6以内なら起きない）

        # セル左上
        cx = start_x + col * (cell_w + gap_x)
        cy = start_y + row * (cell_h_with_name + gap_y)

        # セル中央寄せで描く
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

        # 名前（画像の下）
        name_col = (240, 240, 240) if alive else (140, 140, 140)
        name_surf = font.render(e.name, True, name_col)
        name_x = r.centerx - name_surf.get_width() // 2
        name_y = r.bottom + name_offset_y
        screen.blit(name_surf, (name_x, name_y))

        rects.append(r)

    return rects
