import pygame
from typing import List

from ui_pygame.state import BattleUIState


def calc_log_scroll_max(logs: List[str], font: pygame.font.Font, screen_h: int) -> int:
    """
    スクロール可能最大値（どれだけ昔まで遡れるか）
    """
    panel_h = 160
    line_h = font.get_linesize()
    top_y = (screen_h - panel_h) + 28
    bottom_y = screen_h - 10
    max_lines = max(1, (bottom_y - top_y) // line_h)

    # 末尾基準スクロールなので、最大は「先頭が見える」状態の差分
    return max(0, len(logs) - max_lines)


def handle_mousewheel(
    ui: BattleUIState, event: pygame.event.Event, *, max_scroll: int
) -> None:
    ui.scroll = max(0, min(max_scroll, ui.scroll + event.y))
