# ============================================================
# render.hub: UI共通描画関数群
# draw_header, draw_bar など共通小物描画関数群

# draw_header: ターン数・フェーズ表示
# draw_bar: 汎用バー描画（HP/MP/ゲージなど）
# ============================================================

from __future__ import annotations
import pygame


def draw_header(screen, font, turn: int, phase: str):
    text = font.render(f"Turn {turn}  Phase: {phase}", True, (240, 240, 240))
    screen.blit(text, (2, 0))


def draw_bar(
    screen, x, y, w, h, value, max_value, fg, bg=(40, 40, 40), border=(180, 180, 180)
):
    # 背景
    pygame.draw.rect(screen, bg, (x, y, w, h))
    # 中身
    if max_value <= 0:
        fill_w = 0
    else:
        ratio = max(0.0, min(1.0, value / max_value))
        fill_w = int(w * ratio)
    if fill_w > 0:
        pygame.draw.rect(screen, fg, (x, y, fill_w, h))
    # 枠
    pygame.draw.rect(screen, border, (x, y, w, h), 1)
