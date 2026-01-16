# ============================================================
# render.party_panel: パーティパネル描画関数群
# draw_party_panel など

# draw_party_panel: パーティメンバーパネル描画
# ============================================================

from __future__ import annotations
import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.render.hub import draw_bar


STATUS_ABBR = {
    "Poison": ("POI", (180, 120, 200)),
    "Silence": ("SIL", (160, 160, 200)),
    "Blind": ("BLD", (180, 180, 180)),
    "Paralyze": ("PAR", (255, 200, 120)),
    "Stone": ("STN", (200, 200, 200)),
    "Haste": ("HST", (120, 255, 160)),
    "Slow": ("SLW", (200, 160, 120)),
}

def draw_party_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    party_members: list,
    selected_member_idx: int,
    planned_actions,
    ui: BattleUIState,
    *,
    rect: pygame.Rect | None = None,
):
    """
    PARTYパネル（HPのみ・タイトルなし）
    - TOP領域が狭い前提で、4人が必ず収まるよう row_h を自動調整
    - MP表示なし（FF3風：MPはコマンド/魔法画面側で回数を見せる想定）
    - 右端に OK / …（入力済/未入力）
    """
    if rect is None:
        # 互換：適当なデフォルト
        rect = pygame.Rect(380, 20, 560, 108)

    x, y, w, h = rect.x, rect.y, rect.w, rect.h

    # パネル枠
    pygame.draw.rect(screen, (20, 20, 30), rect, border_radius=8)
    pygame.draw.rect(screen, (200, 200, 220), rect, 2, border_radius=8)

    n = max(1, len(party_members))
    pad = 10

    # タイトル無しなので content はほぼ全体
    content = pygame.Rect(x + pad, y + pad, w - pad * 2, h - pad * 2)

    # 4人を確実に詰める：row_hは「最低24〜」くらいに落としてOK
    row_h = max(24, content.h // n)

    # --- 行内レイアウト ---
    marker_w = font.size("▶")[0] + 6
    state_w = font.size("OK")[0] + 6
    status_w = 60
    hp_text_w = font.size("HP 000/000")[0] + 8
    bar_w = 90
    gap = 6

    # 名前領域（残りを全部）
    name_w = content.w - (
        marker_w + hp_text_w + bar_w + state_w + status_w + gap * 5
    )
    name_w = max(60, name_w)

    # 文字の縦位置：行中央へ
    line_h = font.get_linesize()

    def _ellipsize(text: str, max_px: int, suffix: str = "...") -> str:
        if font.size(text)[0] <= max_px:
            return text
        t = text
        while t and font.size(t + suffix)[0] > max_px:
            t = t[:-1]
        return (t + suffix) if t else suffix

    for i, m in enumerate(party_members):
        cy = content.y + i * row_h
        row_rect = pygame.Rect(content.x, cy, content.w, row_h)

        # planned_actions が dict/list どちらでもOK
        action = None
        if isinstance(planned_actions, dict):
            action = planned_actions.get(i)
        else:
            if 0 <= i < len(planned_actions):
                action = planned_actions[i]

        is_selected = (i == selected_member_idx)
        is_filled = action is not None

        # 行背景
        bg = (30, 30, 50) if is_selected else (20, 20, 30)
        pygame.draw.rect(screen, bg, row_rect, border_radius=6)

        # 位置計算
        tx = row_rect.x + 6
        ty = row_rect.y + (row_h - line_h) // 2

        # ▶
        marker = "▶" if is_selected else " "
        marker_col = (255, 255, 160) if is_selected else (120, 120, 140)
        screen.blit(font.render(marker, True, marker_col), (tx, ty))
        tx += marker_w

        # 名前（省略）
        name = _ellipsize(getattr(m, "name", "???"), name_w)
        screen.blit(font.render(name, True, (255, 255, 255)), (tx, ty))
        tx += name_w + gap

        # HP テキスト
        hp = int(getattr(m, "hp", 0))
        mx = max(1, int(getattr(m, "max_hp", 1)))
        hp_txt = f"HP {hp}/{mx}"
        screen.blit(font.render(hp_txt, True, (230, 230, 230)), (tx, ty))
        tx += hp_text_w + gap

        # HPバー
        bar_y = row_rect.y + (row_h - 10) // 2  # バー高さ=10
        draw_bar(
            screen,
            tx,
            bar_y,
            bar_w,
            10,
            hp,
            mx,
            fg=(80, 220, 120),
        )
        tx += bar_w + gap

        # OK / …
        st = "OK" if is_filled else "…"
        st_col = (140, 255, 140) if is_filled else (200, 200, 220)
        screen.blit(font.render(st, True, st_col), (row_rect.right - state_w, ty))

        # ---- ステータス表示 ----
        statuses = []
        if hasattr(m, "battle") and hasattr(m.battle, "statuses"):
            statuses = m.battle.statuses
        elif hasattr(m, "state") and hasattr(m.state, "statuses"):
            statuses = m.state.statuses

        sx = row_rect.right - state_w - status_w - gap
        sy = ty

        shown = 0
        for st in statuses:
            name = getattr(st, "name", "")
            if name in STATUS_ABBR and shown < 3:
                abbr, col = STATUS_ABBR[name]
                surf = font.render(abbr, True, col)
                screen.blit(surf, (sx, sy))
                sx += surf.get_width() + 2
                shown += 1
