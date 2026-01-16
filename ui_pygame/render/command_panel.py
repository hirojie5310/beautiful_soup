# ============================================================
# render.command_panel: UIコマンドパネル描画関数群
# draw_command_panel + parse_elements 等

# draw_command_panel: コマンド選択/ターゲット選択パネル描画
# parse_elements: 属性情報の正規化関数
# ============================================================

# ui_pygame/render/command_panel.py
from __future__ import annotations

import pygame
from typing import List, Tuple
import re


def draw_command_panel(
    screen: pygame.Surface,
    font: pygame.font.Font,
    ui,
    party_members,
    enemies,
    *,
    rect: pygame.Rect | None = None,
):
    """
    入力中の「コマンド選択」「ターゲット選択」「AoE選択」を表示するパネル。

    ✅ rect 指定時：その領域内に収めて描画（下HUD右側用）
    ✅ rect 未指定時：従来通り「ログの上」に出す互換動作
    ✅ draw_menu：ヘッダをメニュー領域内に確保して重なりを防止
    ✅ menu領域クリップ：枠外描画事故を防止
    ✅ スクロール対応維持（ui.menu_scroll）
    ✅ magicモードだけ属性色つき
    """

    line_h = font.get_linesize()
    row_h = 22

    # -------------------------
    # rect 未指定なら従来配置（互換）
    # -------------------------
    if rect is None:
        x = 20
        w = 420

        screen_h = screen.get_height()
        log_h = 160
        menu_top_margin = 60
        panel_margin = 12

        visible_rows = ui.menu_visible_rows

        title_h = line_h + 8
        menu_h = visible_rows * row_h
        hint_h = line_h + 6
        h = title_h + menu_h + hint_h + 24

        y = screen_h - log_h - h - panel_margin
        rect = pygame.Rect(x, y, w, h)
    else:
        # rect 指定時：中に合わせて visible_rows を自動調整
        # だいたい「タイトル(約40) + ヒント(約26)」を除いた残りで行数を算出
        available = max(0, rect.h - (line_h + 18) - 18)  # タイトル + 少し余白だけ
        visible_rows = max(3, min(getattr(ui, "menu_visible_rows", 8), available // row_h))

    x, y, w, h = rect.x, rect.y, rect.w, rect.h

    # -------------------------
    # 背景
    # -------------------------
    pygame.draw.rect(screen, (25, 25, 35), rect, border_radius=6)
    pygame.draw.rect(screen, (120, 120, 150), rect, 2, border_radius=6)

    if ui.phase != "input":
        t = font.render("入力待ちではありません", True, (200, 200, 200))
        screen.blit(t, (x + 12, y + 12))
        return

    member = party_members[ui.selected_member_idx]

    def _ellipsize(text: str, max_px: int, suffix: str = "...") -> str:
        if font.size(text)[0] <= max_px:
            return text
        t = text
        while t and font.size(t + suffix)[0] > max_px:
            t = t[:-1]
        return (t + suffix) if t else suffix

    mode = ui.input_mode
    MODE_LABEL = {
        "command": "",
        "magic": "MAGIC",
        "item": "ITEM",
        "aoe_choice": "TARGET RANGE",
        "target_enemy": "TARGET (ENEMY)",
        "target_ally": "TARGET (ALLY)",
        "target_side": "TARGET SIDE",
    }

    suffix = MODE_LABEL.get(mode, "")
    if suffix:
        title_str = f"COMMAND  {member.name} > {suffix}"
    else:
        title_str = f"COMMAND  {member.name}"

    # タイトルは枠内に収める（右端に余白を残す）
    title_max_px = w - 24   # 左右padぶん
    title_str = _ellipsize(title_str, title_max_px)

    title = font.render(title_str, True, (255, 255, 255))
    screen.blit(title, (x + 12, y + 6))


    # -------------------------
    # 色付け（魔法用）
    # -------------------------
    def _spell_color(spell_name: str) -> Tuple[int, int, int]:
        spells_by_name = getattr(ui, "spells_by_name", None) or {}
        spell_json = spells_by_name.get(spell_name) or {}

        elem_raw = spell_json.get("Element") or spell_json.get("Elements") or ""
        elements = parse_elements(elem_raw)

        if "fire" in elements or "flame" in elements:
            return (255, 120, 120)
        if "ice" in elements or "blizzard" in elements or "frost" in elements:
            return (120, 180, 255)
        if "thunder" in elements or "lightning" in elements or "bolt" in elements:
            return (170, 170, 255)
        if "earth" in elements or "quake" in elements:
            return (190, 150, 110)
        if "wind" in elements or "aero" in elements:
            return (150, 220, 170)
        if "dark" in elements or "shadow" in elements:
            return (190, 150, 230)
        if "recovery" in elements or "heal" in elements or "holy" in elements:
            return (150, 255, 200)

        # フォールバック：名前推定（任意）
        n = (spell_name or "").strip().lower()
        if n.startswith(("fire", "fira", "firaga", "flare")):
            return (255, 120, 120)
        if n.startswith(("bliz", "ice")):
            return (120, 180, 255)
        if n.startswith(("thun", "bolt")):
            return (170, 170, 255)
        if n.startswith(("quake", "stone", "break")):
            return (190, 150, 110)
        if n.startswith(("aero", "wind")):
            return (150, 220, 170)
        if n.startswith(("dark", "death")):
            return (190, 150, 230)
        if n.startswith(("cura", "cur", "heal", "life")):
            return (150, 255, 200)

        return (230, 230, 230)

    # -------------------------
    # メニュー領域（rect基準）
    # -------------------------
    pad = 12
    title_h = line_h + 12
    # hint_h = line_h + 16
    hint_h = 0 # ヒント領域の幅

    # メニュー表示の開始位置
    menu_top = y + title_h
    menu_left = x + pad
    menu_w = w - pad * 2

    # メニュー領域クリップ（ここから下は枠外描画しない）
    # （上下の余白を少し残してヒント領域と干渉しにくくする）
    menu_clip = pygame.Rect(menu_left - 6, menu_top - 6, menu_w + 12, h - title_h - hint_h - 10)
    old_clip = screen.get_clip()
    screen.set_clip(menu_clip)
    try:

        def draw_menu(options, cursor, header="", *, color_fn=None, right_text_fn=None):
            total = len(options)
            visible = visible_rows

            # ---- ヘッダを「メニュー領域内の1行」として確保 ----
            y0 = menu_top
            if header:
                hh = font.render(header, True, (255, 200, 200))
                screen.blit(hh, (menu_left, y0))
                y0 += line_h + 6  # ★ここでリスト開始位置を下げる

            # 空メニュー保険
            if total <= 0:
                t = font.render("（表示項目がありません）", True, (230, 230, 230))
                screen.blit(t, (menu_left, y0))
                return

            cursor = max(0, min(cursor, total - 1))

            # スクロール追従
            if cursor < ui.menu_scroll:
                ui.menu_scroll = cursor
            elif cursor >= ui.menu_scroll + visible:
                ui.menu_scroll = cursor - visible + 1

            max_scroll = max(0, total - visible)
            ui.menu_scroll = max(0, min(ui.menu_scroll, max_scroll))

            start = ui.menu_scroll
            end = min(start + visible, total)
            shown = options[start:end]

            for i, opt in enumerate(shown):
                actual_idx = start + i
                row_y = y0 + i * row_h

                row_rect = pygame.Rect(menu_left - 4, row_y - 2, menu_w + 8, row_h)
                is_cur = (actual_idx == cursor)

                if is_cur:
                    pygame.draw.rect(screen, (60, 60, 90), row_rect, border_radius=4)

                prefix = "▶ " if is_cur else "  "

                # ---- 右側表示（例：Lv3 2/4） ----
                right = ""
                disabled = False

                if right_text_fn is not None:
                    r = None
                    try:
                        r = right_text_fn(opt, actual_idx)   # 2引数版があればこちら
                    except TypeError:
                        r = right_text_fn(opt)               # 1引数版はこちら

                    # ★返り値が (text, disabled) なら必ず分解
                    if isinstance(r, tuple) and len(r) >= 2:
                        right, disabled = r[0], bool(r[1])
                    else:
                        right = r

                # ★ここで “right は文字列だけ” に正規化
                if right is None:
                    right = ""
                else:
                    right = str(right)
                    
                # ★ 行ごとの色
                base_col = color_fn(opt) if color_fn is not None else (230, 230, 230)

                if disabled:
                    col = (130, 130, 130)
                elif is_cur:
                    col = (255, 255, 180)
                else:
                    col = base_col

                # ---- 右テキスト描画（★ここを1回だけ）----
                right_w = 0
                if right:
                    rt_col = (130, 130, 130) if disabled else (
                        (255, 255, 200) if is_cur else (200, 200, 220)
                    )
                    rt = font.render(right, True, rt_col)
                    right_w = rt.get_width()
                    rx = row_rect.right - 10 - right_w
                    screen.blit(rt, (rx, row_y))

                # 左テキスト（右テキスト分だけ省略）
                max_left_px = (row_rect.width - 20) - right_w
                left_text = prefix + str(opt)

                # 省略
                if font.size(left_text)[0] > max_left_px:
                    t = left_text
                    while t and font.size(t + "...")[0] > max_left_px:
                        t = t[:-1]
                    left_text = (t + "...") if t else "..."

                txt = font.render(left_text, True, col)
                screen.blit(txt, (menu_left, row_y))

            # スクロールインジケータ（ヘッダの有無で位置を合わせる）
            if start > 0:
                up = font.render("▲", True, (180, 180, 180))
                screen.blit(up, (x + w - 26, y0 - 16))
            if end < total:
                down = font.render("▼", True, (180, 180, 180))
                screen.blit(down, (x + w - 26, y0 + visible * row_h))

        # -------------------------
        # モード別描画
        # -------------------------
        mode = ui.input_mode

        if mode == "command":
            labels = [c.cmd for c in ui.command_candidates]
            draw_menu(labels, ui.selected_command_idx)

        elif mode == "magic":
            # ui.magic_candidates: [(spell_name, level, ...), ...] を想定
            spell_names = [m[0] for m in ui.magic_candidates]

            # ★ spell_name → level を確実に作る（actual_idx 依存をやめる）
            level_by_name = {}
            for cand in ui.magic_candidates:
                if isinstance(cand, (tuple, list)) and len(cand) >= 2:
                    level_by_name[str(cand[0])] = cand[1]

            # フォールバック：job raw の Spells からも引けるように（保険）
            job_level_by_name = {
                sp.get("Name"): sp.get("Level")
                for sp in member.job.raw.get("Spells", [])
                if isinstance(sp, dict)
            }

            def _right_magic(spell_name: str):
                lv = level_by_name.get(spell_name) or job_level_by_name.get(spell_name)
                if not lv:
                    return ("", False)

                state = getattr(member, "state", None)
                if not state:
                    return (f"Lv{lv}", False)

                remain = state.mp_pool.get(lv)
                maxv = state.max_mp_pool.get(lv)

                if remain is None:
                    return (f"Lv{lv}", False)

                disabled = (remain <= 0)

                if maxv is None:
                    return (f"Lv{lv} {remain:02d}", disabled)

                return (f"Lv{lv} {remain:02d}/{maxv:02d}", disabled)

            draw_menu(
                spell_names,
                ui.selected_magic_idx,
                color_fn=_spell_color,
                right_text_fn=_right_magic,   # ★ actual_idx を使わない版
            )

        elif mode == "item":
            options = [f"{n} x{q}" for (n, _, q) in ui.item_candidates]
            draw_menu(options, ui.selected_item_idx)   # ← header消す

        elif mode == "aoe_choice":
            draw_menu(ui.aoe_choice_candidates, ui.selected_aoe_idx)

        elif mode == "target_enemy":
            alive_indices = [i for i, e in enumerate(enemies) if getattr(e, "hp", 0) > 0]
            options = [f"{i+1}. {enemies[i].name}" for i in alive_indices]
            draw_menu(options, ui.selected_target_idx)

        elif mode == "target_ally":
            alive_indices = [i for i, m in enumerate(party_members) if getattr(m.state, "hp", 0) > 0]
            options = [f"{i+1}. {party_members[i].name}" for i in alive_indices]
            draw_menu(options, ui.selected_target_idx)

        elif mode == "target_side":
            options = ["敵", "味方", "自分"]
            draw_menu(options, ui.selected_target_side_idx)

        else:
            t = font.render(f"未対応の入力モード: {mode}", True, (230, 180, 180))
            screen.blit(t, (menu_left, menu_top))

    finally:
        # クリップを必ず戻す
        screen.set_clip(old_clip)


def parse_elements(elem_raw) -> List[str]:
    """
    elem_raw が str / list / None など混在しても、必ず list[str] に正規化する
    """
    if not elem_raw:
        return []

    if isinstance(elem_raw, list):
        parts = []
        for x in elem_raw:
            if x is None:
                continue
            parts.extend(re.split(r"[,\s/]+", str(x)))
    else:
        parts = re.split(r"[,\s/]+", str(elem_raw))

    out = []
    for p in parts:
        p = p.strip().lower()
        if p:
            out.append(p)
    return out
