# ui_pygame.save_prompt_adapter.py
# Pygame 専用の保存確認UI
from __future__ import annotations

from pathlib import Path
from typing import Sequence, Callable

import pygame

from combat.progression import apply_item_stock_to_inventory
from combat.save_prompt import diff_party_progress, diff_item_stock


def prompt_save_progress_and_write_pygame(
    *,
    screen: pygame.Surface,
    font: pygame.font.Font,
    before_save: dict,
    after_save: dict,
    save_path: Path,
    save_func: Callable[[Path, dict], None],
    caption: str = "Save updated progress?",
) -> bool:
    # ギル差分も取得
    before_gil = int(before_save.get("gil", 0))
    after_gil = int(after_save.get("gil", 0))
    gil_diff = after_gil - before_gil

    # CP差分も取得
    before_cp = int(before_save.get("CP", 0))
    after_cp = int(after_save.get("CP", 0))
    cp_diff = after_cp - before_cp

    # アイテム差分も取得
    item_diffs = diff_item_stock(after_save)

    diffs = diff_party_progress(before_save, after_save)

    # 「変更がない」ことの判定
    if not diffs and gil_diff == 0 and cp_diff == 0 and not item_diffs:
        _toast_pygame(screen, font, "[Save] No progress changes.", ms=900)
        return False

    lines = ["=== Save Preview (Lv/EXP/JobLv/SP changes) ==="]
    for name, job, blv, alv, bexp, aexp, bjl, ajl, bsp, asp in diffs:
        lv_str = f"Lv{blv} -> Lv{alv}" if blv != alv else f"Lv{blv}"
        if ajl == 99:
            jl_str = f"{job} JobLv99 (MAX)"
        elif ajl > bjl:
            jl_str = f"{job} JobLv{bjl} -> JobLv{ajl} ↑"
        else:
            jl_str = f"{job} JobLv{bjl}"
        lines.append(f"- {name}: {lv_str}, EXP {bexp} -> {aexp}")
        lines.append(f"    {jl_str}, SP {bsp} -> {asp}")

    if gil_diff != 0:
        lines.append("")
        sign = "+" if gil_diff > 0 else ""
        lines.append(f"Gil: {before_gil} -> {after_gil} ({sign}{gil_diff})")

    if cp_diff != 0:
        sign = "+" if cp_diff > 0 else ""
        lines.append(f"CP: {before_cp} -> {after_cp} ({sign}{cp_diff})")

    if item_diffs:
        lines.append("Items:")
        for item, diff in item_diffs:
            sign = "+" if diff > 0 else ""
            lines.append(f"- {item}: ({sign}{diff})")

    lines.append("Y / Enter: Save N / Esc: Cancel")

    ok = _prompt_lines_yes_no(screen, font, caption, lines)
    if not ok:
        _toast_pygame(screen, font, "[Save] Cancelled.", ms=700)
        return False

    apply_item_stock_to_inventory(after_save)
    save_func(save_path, after_save)
    _toast_pygame(screen, font, f"[Save] Saved: {save_path.name}", ms=900)
    return True


def _prompt_lines_yes_no(
    screen: pygame.Surface,
    font: pygame.font.Font,
    title: str,
    lines: Sequence[str],
) -> bool:
    clock = pygame.time.Clock()

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_y, pygame.K_RETURN, pygame.K_KP_ENTER):
                    return True
                if ev.key in (pygame.K_n, pygame.K_ESCAPE):
                    return False

        screen.fill((0, 0, 0))
        y = 40
        _draw_center_text(screen, font, title, y)
        y += 50

        margin_x = 40
        line_h = font.get_linesize() + 6
        h = screen.get_size()[1]
        for line in lines:
            surf = font.render(line, True, (255, 255, 255))
            screen.blit(surf, (margin_x, y))
            y += line_h
            if y > h - 30:
                break

        pygame.display.flip()
        clock.tick(60)


def _draw_center_text(
    screen: pygame.Surface, font: pygame.font.Font, text: str, y: int
) -> None:
    surf = font.render(text, True, (255, 255, 255))
    rect = surf.get_rect(center=(screen.get_width() // 2, y))
    screen.blit(surf, rect)


def _toast_pygame(
    screen: pygame.Surface, font: pygame.font.Font, message: str, ms: int = 800
) -> None:
    clock = pygame.time.Clock()
    start = pygame.time.get_ticks()

    while pygame.time.get_ticks() - start < ms:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return

        screen.fill((0, 0, 0))
        _draw_center_text(screen, font, message, screen.get_height() // 2)
        pygame.display.flip()
        clock.tick(60)
