# ============================================================
# render.enemy_panel: 敵パネル描画関数群
# draw_enemy_panel + targetハイライト など

# draw_enemy_panel: 敵パネル描画
# draw_target_guide: ターゲット選択ガイド表示
# ============================================================

from __future__ import annotations
import pygame
from ui_pygame.render.hub import draw_bar

from combat.life_check import is_out_of_battle


def _ellipsize(font: pygame.font.Font, text: str, max_px: int, suffix: str = "...") -> str:
    """フォント幅を見て末尾を省略する"""
    if font.size(text)[0] <= max_px:
        return text
    t = text
    while t and font.size(t + suffix)[0] > max_px:
        t = t[:-1]
    return (t + suffix) if t else suffix


def draw_enemy_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    enemies: list,
    *,
    rect: pygame.Rect | None = None,
    selected_index: int | None = None,   # enemies の実インデックス
    blink_all: bool = False,
):
    """
    ENEMYパネル（リスト専用）
    - 最大6体想定
    - 敵1〜3: 1列×3行
    - 敵4〜6: 2列×3行（左列1-3 / 右列4-6 の列優先）
    - 表示：番号 + 省略名 + ミニHPバー
    """
    if rect is None:
        rect = pygame.Rect(20, 20, 340, 108)

    x, y, w, h = rect.x, rect.y, rect.w, rect.h

    # 背景・枠
    pygame.draw.rect(screen, (30, 20, 20), rect, border_radius=8)
    pygame.draw.rect(screen, (220, 200, 200), rect, 2, border_radius=8)

    # タイトル
    title = font.render("ENEMIES", True, (255, 200, 200))
    screen.blit(title, (x + 10, y + 8))

    # レイアウト
    pad = 10
    title_h = font.get_linesize() + 10
    grid_top = y + title_h
    grid_h = h - title_h - 6

    # ★敵数で列数切替（最大6想定）
    n_total = min(len(enemies), 6)
    cols = 1 if n_total <= 3 else 2
    rows = 3

    col_gap = 10 if cols == 2 else 0
    row_gap = 4

    cell_w = (w - pad * 2 - col_gap * (cols - 1)) // cols
    cell_h = (grid_h - row_gap * (rows - 1)) // rows

    # ミニバー
    bar_h = 6
    bar_w = 46
    bar_bg = (60, 50, 50)
    bar_fg = (240, 120, 120)

    # 点滅（300ms）
    blink_on = (pygame.time.get_ticks() // 300) % 2 == 0

    # ★表示対象：実インデックス付きで保持（selected_index対策）
    show = list(enumerate(enemies))[:6]   # [(enemy_i, enemy_obj), ...]

    old_clip = screen.get_clip()
    screen.set_clip(rect)
    try:
        for slot in range(cols * rows):
            # ★並び：列優先（左列を上から埋めて、次に右列）
            if cols == 1:
                r, c = slot, 0
            else:
                r = slot % rows
                c = slot // rows

            cx = x + pad + c * (cell_w + col_gap)
            cy = grid_top + r * (cell_h + row_gap)
            cell_rect = pygame.Rect(cx, cy, cell_w, cell_h)

            if slot >= len(show):
                pygame.draw.rect(screen, (55, 40, 40), cell_rect, 1, border_radius=6)
                continue

            enemy_i, e = show[slot]
            alive = getattr(e, "hp", 0) > 0

            # ★ハイライト判定：実インデックスで比較
            is_selected = (selected_index == enemy_i)

            highlight = False
            if is_selected:
                highlight = True
            if blink_all and alive and blink_on:
                highlight = True

            if highlight:
                pygame.draw.rect(
                    screen,
                    (100, 60, 60) if blink_all else (80, 60, 60),
                    cell_rect,
                    border_radius=6,
                )
            else:
                pygame.draw.rect(screen, (40, 28, 28), cell_rect, border_radius=6)

            # テキスト：番号 + 名前（省略）
            prefix = "▶" if is_selected else " "
            num = f"{enemy_i + 1}"
            name = getattr(e, "name", "Enemy")

            left_head = f"{prefix}{num} "
            head_w = font.size(left_head)[0]
            name_max = cell_w - head_w - bar_w - 10
            name_max = max(40, name_max)

            name_disp = _ellipsize(font, name, name_max)
            col_text = (240, 240, 240) if alive else (140, 140, 140)

            t_head = font.render(left_head, True, col_text)
            t_name = font.render(name_disp, True, col_text)

            ty = cy + (cell_h - font.get_linesize()) // 2
            screen.blit(t_head, (cx + 6, ty))
            screen.blit(t_name, (cx + 6 + head_w, ty))

            # ミニHPバー
            hp = max(0, int(getattr(e, "hp", 0)))
            mx = max(1, int(getattr(e, "max_hp", 1)))

            bx = cx + cell_w - bar_w - 6
            by = cy + (cell_h - bar_h) // 2

            pygame.draw.rect(screen, bar_bg, (bx, by, bar_w, bar_h))
            ratio = max(0.0, min(1.0, hp / mx))
            fw = int(bar_w * ratio)
            if fw > 0:
                pygame.draw.rect(screen, bar_fg, (bx, by, fw, bar_h))
            pygame.draw.rect(screen, (120, 90, 90), (bx, by, bar_w, bar_h), 1)
    finally:
        screen.set_clip(old_clip)


def draw_target_guide(
    screen, font, ui, party_members, enemies, *, rect: pygame.Rect | None = None
):
    """
    ターゲット選択中の操作ガイドを表示する（rectベース）
    - rect を渡すと、その領域内に収まるよう描画
    - rect 未指定なら従来の固定座標（互換）
    """
    if ui.phase != "input":
        return

    mode = getattr(ui, "input_mode", "")
    if mode not in ("target_side", "target_enemy", "target_ally"):
        return

    member = party_members[ui.selected_member_idx]

    # -------------------------
    # メッセージ組み立て
    # -------------------------
    if mode == "target_side":
        msg1 = f"{member.name}：対象を選んでください"
        msg2 = "1=敵  2=味方  3=自分   Backspace/Esc=戻る"
        msg3 = ""
    elif mode == "target_enemy":
        alive_indices = [i for i, e in enumerate(enemies) if getattr(e, "hp", 0) > 0]
        if alive_indices:
            pos = max(0, min(ui.selected_target_idx, len(alive_indices) - 1))
            real_i = alive_indices[pos]
            tgt_name = enemies[real_i].name
            msg1 = f"{member.name}：敵を選択中 → {tgt_name}"
        else:
            msg1 = f"{member.name}：敵を選択中（生存敵なし）"

        msg2 = "↑↓=選択  Enter=決定   Backspace/Esc=戻る"
        msg3 = "（死んでいる敵は選べません）"
    else:  # target_ally
        alive_indices = [
            i for i, m in enumerate(party_members) if not is_out_of_battle(m.state)
        ]
        if alive_indices:
            pos = max(0, min(ui.selected_target_idx, len(alive_indices) - 1))
            real_i = alive_indices[pos]
            tgt_name = party_members[real_i].name
            msg1 = f"{member.name}：味方を選択中 → {tgt_name}"
        else:
            msg1 = f"{member.name}：味方を選択中（生存味方なし）"

        msg2 = "↑↓=選択  Enter=決定   Backspace/Esc=戻る"
        msg3 = ""

    # -------------------------
    # 描画先rect（未指定なら従来互換）
    # -------------------------
    if rect is None:
        # 従来位置
        x, y = 500, 300
        box_w = 430
        box_h = 74 if msg3 else 54
        rect = pygame.Rect(x, y, box_w, box_h)
    else:
        # rect 指定時は、その中に収まるサイズへ（padding含む）
        pad = 10
        # 文字数に応じた厳密な自動リサイズはやり過ぎなので、
        # ここでは rect いっぱいを使って描く（はみ出す場合は後述の省略）
        rect = rect.copy()
        pad = max(8, min(12, rect.w // 40))

    # -------------------------
    # 背景ボックス
    # -------------------------
    pygame.draw.rect(screen, (20, 20, 30), rect, border_radius=8)
    pygame.draw.rect(screen, (140, 140, 170), rect, 2, border_radius=8)

    # -------------------------
    # テキスト描画（rect内）
    # -------------------------
    pad = 12
    x0 = rect.x + pad
    y0 = rect.y + 8

    # はみ出しが気になる場合に備えて簡易省略
    def _ellipsize(text: str, max_px: int, suffix: str = "…") -> str:
        if font.size(text)[0] <= max_px:
            return text
        t = text
        while t and font.size(t + suffix)[0] > max_px:
            t = t[:-1]
        return (t + suffix) if t else suffix

    max_w = rect.w - pad * 2

    msg1 = _ellipsize(msg1, max_w)
    msg2 = _ellipsize(msg2, max_w)
    if msg3:
        msg3 = _ellipsize(msg3, max_w)

    t1 = font.render(msg1, True, (255, 255, 200))
    t2 = font.render(msg2, True, (220, 220, 220))

    screen.blit(t1, (x0, y0))
    screen.blit(t2, (x0, y0 + 22))

    if msg3:
        t3 = font.render(msg3, True, (180, 180, 200))
        screen.blit(t3, (x0, y0 + 44))
