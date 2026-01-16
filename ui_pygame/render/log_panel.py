import pygame
from typing import List

from ui_pygame.logic import clamp


def draw_log_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    logs: List[str],
    scroll: int,
    *,
    rect: pygame.Rect | None = None,
) -> pygame.Rect:
    """
    ログ表示パネル
    - rect を渡すとその領域内に描画
    - rect 未指定なら従来通り画面下固定
    scroll: 0が最下部（最新）
    """
    # 既存互換：rect未指定なら従来配置
    if rect is None:
        w, h = screen.get_size()
        panel_h = 160
        rect = pygame.Rect(0, h - panel_h, w, panel_h)

    # 背景
    pygame.draw.rect(screen, (5, 5, 10), rect, border_radius=6)
    pygame.draw.rect(screen, (80, 80, 120), rect, 2, border_radius=6)

    pad = 10

    # タイトル
    title = font.render("LOG", True, (220, 220, 220))
    screen.blit(title, (rect.x + pad, rect.y + 6))

    # 表示可能行数
    line_h = font.get_linesize()
    top_y = rect.y + 28
    bottom_y = rect.bottom - pad
    max_lines = max(1, (bottom_y - top_y) // line_h)

    # 表示開始位置（末尾基準）
    end_idx = clamp(len(logs) - scroll, 0, len(logs))
    start_idx = max(0, end_idx - max_lines)
    visible = logs[start_idx:end_idx]

    # 行描画
    y = top_y
    for line in visible:
        surf = font.render(str(line), True, (235, 235, 235))
        screen.blit(surf, (rect.x + pad, y))
        y += line_h

    # スクロールヒント（右上）
    hint = font.render("MouseWheel / ↑↓", True, (150, 150, 170))
    screen.blit(
        hint,
        (rect.right - hint.get_width() - pad, rect.y + 6),
    )

    return rect
