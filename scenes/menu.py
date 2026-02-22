from __future__ import annotations
import pygame
from dataclasses import dataclass
from typing import List, Callable, Optional, Dict, Any, Sequence
from copy import deepcopy
from pathlib import Path
import time


from combat.enums import Status
from combat.constants import (
    STATUS_ABBR,
    FIELD_MAGIC_WHITELIST,
    FIELD_MAGIC_TARGET_REQUIRED,
    FIELD_ITEM_TARGET_REQUIRED,
)
from combat.models import (
    PartyMemberRuntime,
    EquipmentSet,
    FinalCharacterStats,
)
from combat.char_build import (
    compute_character_final_stats,
    build_name_index,
    strip_illegal_equipment_for_job,
    apply_job_equipment_restrictions,
)
from assets.data.data_loader import (
    save_savedata,
    apply_party_equipment_to_save,
    apply_party_job_to_save,
)

from ui_pygame.assets_py.portrait_cache import PortraitCache
from ui_pygame.assets_py.status_icon_cashe import StatusIconCache
from ui_pygame.logic import make_cast_field_magic_fn, make_use_field_item_fn
from ui_pygame.field_effects import (
    get_battle_state,
    sync_equipment_to_save,
    FIELD_ITEM_TYPES,
)
from ui_pygame.render.status_icons import draw_status_icons, draw_status_immune_icons

from system.cp_system import compute_job_change_cp_cost
from utils.text_normalize import normalize_text_basic


# 色
WHITE = (255, 255, 255)
GRAY = (140, 140, 140)
HP_GREEN = (60, 255, 80)
YELLOW = (255, 220, 60)


# --- Elixir ---
def can_affect_elixir(ch) -> bool:
    # HP or MP が1つでも欠けていれば有効
    if ch.hp < ch.max_hp:
        return True
    st = ch.state
    for lv in range(1, 9):
        if st.mp_pool.get(lv, 0) < st.max_mp_pool.get(lv, 0):
            return True
    return False


# --- 通常HP回復 ---
def can_affect_hp_heal(ch) -> bool:
    # 生存していて、HPが減っている
    return ch.hp > 0 and ch.hp < ch.max_hp


# --- 状態回復 ---
def can_affect_antidote(ch) -> bool:
    return Status.POISON in ch.state.statuses


def can_affect_eyedrops(ch) -> bool:
    return Status.BLIND in ch.state.statuses


def can_affect_echoherbs(ch) -> bool:
    return Status.SILENCE in ch.state.statuses


def can_affect_goldneedle(ch) -> bool:
    return (
        Status.PETRIFY in ch.state.statuses
        or Status.PARTIAL_PETRIFY in ch.state.statuses
    )


# --- 蘇生 ---
def can_affect_phoenix_down(ch) -> bool:
    return ch.hp <= 0


ITEM_AFFECT_CHECKERS = {
    # HP回復
    "potion": can_affect_hp_heal,
    "hi potion": can_affect_hp_heal,
    # HP+MP全回復
    "elixir": can_affect_elixir,
    # 状態回復
    "antidote": can_affect_antidote,
    "eye drops": can_affect_eyedrops,
    "echo herbs": can_affect_echoherbs,
    "gold needle": can_affect_goldneedle,
    # 蘇生
    "phoenix down": can_affect_phoenix_down,
}


def canon(s: str) -> str:
    return normalize_text_basic(s)


# 効果がある対象だけ白表示
def can_affect(item_name: str, ch) -> bool:
    fn = ITEM_AFFECT_CHECKERS.get(canon(item_name))
    if fn:
        return fn(ch)
    return True  # 未定義アイテムは「使える」扱い


@dataclass
class GameState:
    party: List[PartyMemberRuntime]
    # inventory や装備候補DBなどは必要になったら追加


def open_menu_pygame(
    screen,
    font,
    party: Sequence[PartyMemberRuntime],  # ★これを追加
    *,
    save_dict: Optional[Dict[str, Any]] = None,
    save_path: Optional[Path] = None,
    level_table=None,
    job_attr=None,
    weapons=None,
    armors=None,
    jobs_by_name=None,  # ★追加
    portrait_cache: PortraitCache,  # ★追加
    status_icon_cache: StatusIconCache,  # ★追加
    recalc_stats_fn=None,
    build_magic_fn: Optional[Callable[[int], list[tuple[str, int, int]]]] = None,
    spells_by_name: Optional[dict[str, dict]] = None,  # ★追加
    items_by_name: Optional[dict[str, dict]] = None,  # ★追加
    ui_se: dict[str, pygame.mixer.Sound],
):
    clock = pygame.time.Clock()
    items = [
        "アイテム",
        "まほう",
        "そうび",
        "ステータス",
        "ならびかえ",
        "ジョブ",
        "セーブ",
    ]  # 画像に寄せるなら
    mode = "menu"  # "menu" or "row"
    idx = 0  # 右メニュー選択
    member_idx = 0  # 左キャラ選択（ならべかえ用）

    # make_use_field_item_fn を冒頭で1回だけ作る
    use_field_item_fn = None
    if items_by_name is not None:
        use_field_item_fn = make_use_field_item_fn(
            party=party,
            items_by_name=items_by_name,
            save_dict=save_dict,
            toast=lambda msg: show_toast_message(screen, font, msg, duration=1.0),
        )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    if mode == "row":
                        mode = "menu"  # ならべかえ解除
                    else:
                        return  # メニュー終了
                    continue

                if mode == "menu":
                    if event.key == pygame.K_UP:
                        idx = (idx - 1) % len(items)
                    elif event.key == pygame.K_DOWN:
                        idx = (idx + 1) % len(items)

                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                        choice = items[idx]

                        if choice == "ならびかえ":
                            mode = "row"
                            idx = items.index("ならびかえ")
                            member_idx = 0
                            continue
                        # ここから下は今までの choice 分岐（そうび/ステータス/ジョブ/セーブ…）

                        elif choice == "アイテム":
                            if items_by_name is None:
                                show_toast_message(
                                    screen, font, "Item unavailable", duration=1.0
                                )
                                continue

                            open_item_pygame(
                                screen,
                                font,
                                party,
                                save_dict=save_dict,
                                items_by_name=items_by_name,
                                use_field_item_fn=use_field_item_fn,
                                portrait_cache=portrait_cache,
                                status_icon_cache=status_icon_cache,
                                ui_se=ui_se,  # ★追加
                            )

                        elif choice == "まほう":
                            # print(f"[DBG build_magic_fn]{build_magic_fn}")
                            # print(f"[DBG spells_by_name]{spells_by_name}")
                            if build_magic_fn is None or spells_by_name is None:
                                show_toast_message(
                                    screen, font, "Magic unavailable", duration=1.0
                                )
                                continue

                            cast_field_magic_fn = make_cast_field_magic_fn(
                                party=party,
                                spells_by_name=spells_by_name,
                                build_magic_fn=build_magic_fn,
                                save_dict=save_dict,
                                toast=lambda msg: show_toast_message(
                                    screen, font, msg, duration=1.0
                                ),
                            )

                            open_magic_pygame(
                                screen,
                                font,
                                party,
                                portrait_cache=portrait_cache,
                                status_icon_cache=status_icon_cache,
                                build_magic_fn=build_magic_fn,
                                spells_by_name=spells_by_name,
                                cast_field_magic_fn=cast_field_magic_fn,
                                ui_se=ui_se,  # ★追加
                            )
                        if choice == "そうび":
                            if (
                                weapons is None
                                or armors is None
                                or recalc_stats_fn is None
                            ):
                                show_toast_message(
                                    screen, font, "Equip unavailable", duration=1.0
                                )
                                continue
                            open_equip_pygame(
                                screen,
                                font,
                                party,
                                weapons_by_name=weapons,
                                armors_by_name=armors,
                                save_dict=save_dict,  # ★追加（= state.save）
                                portrait_cache=portrait_cache,
                                status_icon_cache=status_icon_cache,
                            )
                        elif choice == "ステータス":
                            open_status_pygame(
                                screen,
                                font,
                                party,
                                level_table=level_table,
                                weapons=weapons,
                                portrait_cache=portrait_cache,
                                status_icon_cache=status_icon_cache,
                            )
                        elif choice == "ジョブ":
                            if jobs_by_name is None or recalc_stats_fn is None:
                                show_toast_message(
                                    screen, font, "Job unavailable", duration=1.0
                                )
                                continue
                            if (
                                weapons is None
                                or armors is None
                                or recalc_stats_fn is None
                            ):
                                show_toast_message(
                                    screen, font, "Equip unavailable", duration=1.0
                                )
                                continue
                            open_job_pygame(
                                screen,
                                font,
                                party,
                                job_attr=job_attr,
                                jobs_by_name=jobs_by_name,
                                weapons_by_name=weapons,
                                armors_by_name=armors,
                                recalc_stats_fn=recalc_stats_fn,
                                save_dict=save_dict,  # ★追加（OptionalでもOK）
                                portrait_cache=portrait_cache,
                                status_icon_cache=status_icon_cache,
                            )
                        elif choice == "セーブ":
                            if save_dict is None or save_path is None:
                                # ここで画面に「Save is unavailable」など表示して return でもOK
                                return
                            apply_party_equipment_to_save(save_dict, party)
                            apply_party_job_to_save(save_dict, party)  # ★追加
                            save_savedata(save_path, save_dict)
                            show_toast_message(screen, font, "Saved!", duration=1.0)
                        elif choice == "もどる":
                            return

                elif mode == "row":
                    if event.key == pygame.K_UP:
                        member_idx = (member_idx - 1) % min(4, len(members))
                    elif event.key == pygame.K_DOWN:
                        member_idx = (member_idx + 1) % min(4, len(members))
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                        ch = members[member_idx]
                        # front/back をトグル
                        ch.base.row = "back" if ch.base.row == "front" else "front"
                        if hasattr(ch.stats, "row"):
                            ch.stats.row = ch.base.row

                        # save_dict にも反映（nameで照合）
                        if isinstance(save_dict, dict):
                            sp_list = save_dict.get("party", [])
                            for sp in sp_list:
                                if sp.get("name") == ch.name:
                                    sp["row"] = ch.base.row
                                    break

        # ---- draw ----
        screen.fill((0, 0, 0))
        w, h = screen.get_width(), screen.get_height()

        # ========== レイアウト（固定） ==========
        margin = 24
        left_w = int(w * 0.62)
        right_w = w - left_w - margin * 3

        party_rect = pygame.Rect(margin, margin, left_w, int(h * 0.72))
        cmd_rect = pygame.Rect(
            party_rect.right + margin, margin, right_w, int(h * 0.54)
        )
        bottom_rect = pygame.Rect(
            margin,
            party_rect.bottom + margin,
            left_w,
            h - (party_rect.bottom + margin * 2),
        )
        # 右下にもう1枚欲しければ bottom_rect を2分割する

        draw_window(screen, party_rect)
        draw_window(screen, cmd_rect)
        draw_window(screen, bottom_rect)

        # ========== 左：パーティ情報 ==========
        pad = 18
        x0 = party_rect.x + pad
        y0 = party_rect.y + pad

        # 1人分の行高
        row_h = 90
        face_size = 64
        gap = 74

        # party が list ならそのまま、オブジェクトなら party.members 等に合わせて調整
        members = party

        for i, ch in enumerate(members[:4]):
            ry = y0 + i * row_h

            # 顔枠
            shift = 0 if ch.base.row == "front" else 24
            face_rect = pygame.Rect(x0 + shift, ry, face_size, face_size)

            # 「ならびかえ」モードの矢印表示（face_rect 作成後）
            if mode == "row" and i == member_idx:
                arrow = font.render("▶", True, WHITE)
                screen.blit(arrow, (x0 - arrow.get_width() - 10, ry + 18))

            inner = face_rect.inflate(-4, -4)

            key = getattr(ch, "portrait_key", None)
            if key:
                face = portrait_cache.get(key)
                img = pygame.transform.scale(face, (inner.w, inner.h))
                screen.blit(img, inner.topleft)
            else:
                pygame.draw.rect(screen, (60, 60, 60), inner)

            # 文字開始位置は「前列の基準位置」で固定
            tx = (x0 + face_size) + gap

            # 名前（上段左）
            name_s = font.render(get_name(ch), True, WHITE)
            screen.blit(name_s, (tx, ry))

            # draw_status_badges(screen, font, actor, xL, y)
            draw_status_icons(
                screen,
                ch,
                status_icon_cache,
                x=tx + 100,
                y=ry + 6,
            )

            # 職業 + LV（上段右寄せ）
            job = get_job_name(ch)
            lv = get_level(ch)
            joblv_text = f"{job}  LV {lv}"
            joblv_s = font.render(joblv_text, True, WHITE)
            screen.blit(joblv_s, (party_rect.right - pad - joblv_s.get_width(), ry))

            # ラベル
            label_s = font.render("HP", True, HP_GREEN)
            screen.blit(label_s, (tx, ry + font.get_linesize()))
            label_s = font.render("MP", True, WHITE)
            screen.blit(label_s, (tx, ry + font.get_linesize() * 2))

            # HP
            hp, mhp = ch.hp, ch.max_hp
            hp_s = font.render(f"{hp}/{mhp}", True, HP_GREEN)
            screen.blit(hp_s, (tx + 160, ry + font.get_linesize()))

            # MP（L1〜L8 現在値だけ）
            mp_vals = [f"{ch.mp_pool.get(lv, 0):2d}" for lv in range(1, 9)]
            one_line = "/".join(mp_vals)

            # 右端（はみ出し防止のため）
            max_w = party_rect.right - pad - (tx + 60)

            if font.size(one_line)[0] <= max_w:
                mp_s = font.render(one_line, True, WHITE)
                screen.blit(mp_s, (tx + 60, ry + font.get_linesize() * 2))
            else:
                line1 = "/".join(mp_vals[:4])
                line2 = "/".join(mp_vals[4:])
                mp1 = font.render(line1, True, WHITE)
                mp2 = font.render(line2, True, WHITE)
                screen.blit(mp1, (tx + 60, ry + font.get_linesize() * 2))
                screen.blit(mp2, (tx + 60, ry + font.get_linesize() * 3))

        # ========== 右：コマンド ==========
        cx = cmd_rect.x + pad
        cy = cmd_rect.y + pad

        title = font.render("アイテム", True, WHITE)  # 右上に固定タイトルを置くなら
        # screen.blit(title, (cx, cy))

        # コマンド行
        line_h = font.get_linesize() + 10
        list_top = cy  # + title.get_height() + 10  # タイトルを出すなら少し下げる

        for i, t in enumerate(items):
            if mode == "row":
                # rowモード中は「ならびかえ」だけ白、それ以外は固定グレー
                color = WHITE if t == "ならびかえ" else GRAY
            else:
                # 通常時は選択中だけ白
                color = WHITE if i == idx else GRAY

            text = font.render(t, True, color)
            screen.blit(text, (cx + 28, list_top + i * line_h))

        # カーソル（▶）は通常時だけ表示
        if mode == "menu":
            cursor = font.render("▶", True, WHITE)
            screen.blit(cursor, (cx, list_top + idx * line_h))

        # ========== 下：ヘルプ/所持金など ==========
        if mode == "menu":
            help_text = "↑↓: Select   Enter: OK   ESC: Back"
        else:
            help_text = "↑↓: Select   Enter: Toggle Row   ESC: End"

        # --- Gil / CP 取得 ---
        gil = 0
        cp = 0
        if isinstance(save_dict, dict):
            try:
                gil = int(save_dict.get("gil", 0))
            except (TypeError, ValueError):
                gil = 0
            try:
                cp = int(save_dict.get("CP", 0))
            except (TypeError, ValueError):
                cp = 0

        # --- ヘルプ表示（左） ---
        help_surf = font.render(help_text, True, GRAY)
        screen.blit(help_surf, (bottom_rect.x + pad, bottom_rect.y + pad))

        # --- GIL 表示（右端） ---
        gil_text = f"GIL {gil:,}"
        gil_surf = font.render(gil_text, True, WHITE)

        gil_x = bottom_rect.right - pad - gil_surf.get_width()
        gil_y = bottom_rect.y + pad
        screen.blit(gil_surf, (gil_x, gil_y))

        # --- CP 表示（GIL の左） ---
        if cp >= 255:
            cp_text = "CP MAX"
        else:
            cp_text = f"CP {cp}/255"
        cp_color = YELLOW if cp >= 255 else WHITE
        cp_surf = font.render(cp_text, True, cp_color)

        # GIL の左に余白をあけて配置
        gap = 16  # CP と GIL の間隔（お好みで）
        cp_x = gil_x - gap - cp_surf.get_width()
        cp_y = gil_y
        screen.blit(cp_surf, (cp_x, cp_y))

        pygame.display.flip()
        clock.tick(60)


def open_equip_pygame(
    screen,
    font,
    party,
    *,
    weapons_by_name,
    armors_by_name,
    save_dict=None,
    portrait_cache: PortraitCache,
    status_icon_cache: StatusIconCache,
):
    clock = pygame.time.Clock()

    actor_idx = 0
    slots = ["main_hand", "off_hand", "unequip_all", "head", "body", "arms"]
    slot_idx = 0

    mode = "slot"  # "slot" | "candidate"
    cand_idx = 0
    cand_top = 0

    line_h = font.get_linesize() + 8

    while True:
        actor = party[actor_idx]
        eq = actor.equipment or EquipmentSet()

        # ★ 下部候補は「slot が選ばれているときだけ」作る
        candidates = build_equip_candidates(
            actor,
            slots[slot_idx],
            weapons_by_name=weapons_by_name,
            armors_by_name=armors_by_name,
        )
        if candidates:
            cand_idx = max(0, min(cand_idx, len(candidates) - 1))
        else:
            cand_idx = 0
            cand_top = 0

        # ---------------- input ----------------
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit

            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_BACKSPACE:
                    if mode == "candidate":
                        mode = "slot"
                    else:
                        return

                elif ev.key == pygame.K_LEFT:
                    actor_idx = (actor_idx - 1) % len(party)
                    slot_idx = 0
                    mode = "slot"
                    cand_idx = 0
                    cand_top = 0

                elif ev.key == pygame.K_RIGHT:
                    actor_idx = (actor_idx + 1) % len(party)
                    slot_idx = 0
                    mode = "slot"
                    cand_idx = 0
                    cand_top = 0

                elif ev.key == pygame.K_UP:
                    if mode == "slot":
                        slot_idx = (slot_idx - 1) % len(slots)
                        cand_idx = 0
                        cand_top = 0
                    else:
                        if candidates:
                            cand_idx = (cand_idx - 1) % len(candidates)
                            cand_top = clamp_scroll(
                                cand_idx, cand_top, max_rows, len(candidates)
                            )

                elif ev.key == pygame.K_DOWN:
                    if mode == "slot":
                        slot_idx = (slot_idx + 1) % len(slots)
                        cand_idx = 0
                        cand_top = 0
                    else:
                        if candidates:
                            cand_idx = (cand_idx + 1) % len(candidates)
                            cand_top = clamp_scroll(
                                cand_idx, cand_top, max_rows, len(candidates)
                            )

                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                    if mode == "slot":
                        # ★ ここで unequip_all を特別扱い
                        if slots[slot_idx] == "unequip_all":
                            # 全装備解除
                            if actor.equipment is None:
                                actor.equipment = EquipmentSet()

                            actor.equipment.main_hand = None
                            actor.equipment.off_hand = None
                            actor.equipment.head = None
                            actor.equipment.body = None
                            actor.equipment.arms = None

                            actor.equipment, _ = apply_job_equipment_restrictions(
                                actor.equipment, actor.job
                            )

                            actor.stats = compute_character_final_stats(
                                base=actor.base,
                                eq=actor.equipment,
                                weapons_by_name=weapons_by_name,
                                armors_by_name=armors_by_name,
                                job_name=actor.job.name,
                            )
                            sync_equipment_to_save(actor, save_dict)

                            # SEや演出を入れるならここ
                            # play_se("unequip")

                            # ★ candidate には入らない
                            mode = "slot"

                        else:
                            # 通常スロット → 候補選択へ
                            mode = "candidate"
                            cand_idx = 0
                            cand_top = 0

                    else:
                        # ★ 装備確定（既存処理）
                        if not candidates:
                            mode = "slot"
                            continue
                        kind, name, _ = candidates[cand_idx]

                        if actor.equipment is None:
                            actor.equipment = EquipmentSet()

                        if kind == "none":
                            setattr(actor.equipment, slots[slot_idx], None)
                        else:
                            setattr(actor.equipment, slots[slot_idx], name)

                        actor.equipment, logs = apply_job_equipment_restrictions(
                            actor.equipment, actor.job
                        )

                        actor.stats = compute_character_final_stats(
                            base=actor.base,
                            eq=actor.equipment,
                            weapons_by_name=weapons_by_name,
                            armors_by_name=armors_by_name,
                            job_name=actor.job.name,
                        )
                        sync_equipment_to_save(actor, save_dict)

                        mode = "slot"

        # ---------------- draw ----------------
        screen.fill((0, 0, 0))
        w, h = screen.get_width(), screen.get_height()
        margin = 24
        line_h = font.get_linesize()
        slots_y = 120

        # ========== 全体共通描画 ==========
        top_height = line_h * 4  # ← かなり圧縮できる
        top_y = 80
        candidate_y = top_y + top_height + 16
        max_rows = (h - candidate_y - 80) // line_h

        left_slots = ["main_hand", "off_hand", "unequip_all"]
        right_slots = ["head", "body", "arms"]

        # 上部：現在の装備表示
        top_end_y = draw_equip_current_2col(
            screen,
            font,
            actor,
            eq,
            left_slots=left_slots,
            right_slots=right_slots,
            slot_idx=slot_idx,
            x=80,
            y=slots_y,
            col_w=w * 0.6,
            line_h=line_h,
            portrait_cache=portrait_cache,
        )

        # draw 側がシンプルになるように calc_preview_stats をここで定義（kind, nameのみ）
        calc_preview = lambda kind, name: calc_preview_stats(
            actor,
            slot=slots[slot_idx],
            item_kind=kind,
            item_name=name,
            weapons_by_name=weapons_by_name,
            armors_by_name=armors_by_name,
        )
        # 下部：装備候補表示（★「上段の直下」から始める）
        candidate_y = top_end_y + margin
        max_rows = 8
        if slots[slot_idx] == "unequip_all":
            # 下段は描かない or 説明テキスト
            hint = font.render("すべての装備をはずします", True, (160, 160, 160))
            screen.blit(
                hint,
                (
                    w // 2 - hint.get_width() // 2,
                    h - 30,
                ),
            )
        else:
            draw_equip_candidates(
                screen,
                font,
                actor,
                slots[slot_idx],
                candidates,
                idx=cand_idx,
                top=cand_top,
                max_rows=max_rows,
                base_stats=actor.stats,
                calc_preview_stats_fn=calc_preview,
                x=80,
                y=candidate_y + 2,
                col_w=w * 0.6,
                line_h=line_h,
            )

        # 差分表示（mode が candidate のときだけ）
        # if mode == "candidate" and slots[slot_idx] != "unequip_all":
        if candidates:
            kind, name, _ = candidates[cand_idx]
            preview = calc_preview(kind, name)
        else:
            preview = actor.stats
        draw_equip_status_compare(
            screen,
            font,
            base_stats=actor.stats,
            preview_stats=preview,
            icon_cache=status_icon_cache,
            x=margin + w * 0.6 + 20,
            y=slots_y,
            w=w - ((margin + w * 0.6 + 8) + margin * 2),
            line_h=line_h,
        )

        # 下部ヒント
        hint = font.render("↑↓: Select  Enter: Equip BS: Back", True, (180, 180, 180))
        screen.blit(
            hint,
            (w // 2 - hint.get_width() // 2, h - 60),
        )

        pygame.display.flip()
        clock.tick(60)


# 上部：現在の装備表示
def draw_equip_current_2col(
    screen,
    font,
    actor,
    eq,
    left_slots,
    right_slots,
    slot_idx,
    *,
    x,
    y,
    col_w,
    line_h,
    portrait_cache: PortraitCache,
):
    def blit_line(text, x, y, color=(220, 220, 220)):
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))

    w = screen.get_width()
    rows = max(len(left_slots), len(right_slots)) + 1

    left_x = 80
    rect_width = col_w
    right_x = rect_width // 2 + 40

    # portrait
    face_size = 64
    face_rect = pygame.Rect(60, 20, face_size, face_size)
    inner = face_rect.inflate(-4, -4)

    key = getattr(actor, "portrait_key", None)
    if key:
        face = portrait_cache.get(key)
        img = pygame.transform.scale(face, (inner.w, inner.h))
        screen.blit(img, inner.topleft)

    # title
    title_y = 30
    title = font.render(f"{actor.name}   {actor.job.name}", True, (255, 255, 255))
    screen.blit(
        title,
        (w // 2 - title.get_width() // 2, title_y),
    )

    pl = font.render("EQUIPMENT", True, (160, 160, 160))
    screen.blit(
        pl,
        (w // 2 - pl.get_width() // 2, title_y + 30),
    )

    slots_y = y

    margin = 24
    slots_y = 120

    # 上部枠
    upper_h = int(line_h * rows) + 20
    upper_rect = pygame.Rect(margin, slots_y - 10, rect_width, upper_h)
    draw_window(screen, upper_rect)

    st = actor.stats
    blit_line(
        f"こうげき・・  {st.main_power} / {st.off_power}  ぼうぎょ・・ {st.defense}",
        80,
        slots_y,
    )

    # 左カラム
    for i, slot in enumerate(left_slots):
        is_sel = i == slot_idx
        prefix = "▶ " if is_sel else "  "
        color = (255, 255, 255) if is_sel else (140, 140, 140)

        if slot == "unequip_all":
            text = f"{prefix}そうびのかいじょ"
        else:
            val = getattr(eq, slot) or "なし"
            text = f"{prefix}{slot}: {val}"

        screen.blit(
            font.render(text, True, color), (left_x, slots_y + (i + 1) * line_h)
        )

    # 右カラム
    for i, slot in enumerate(right_slots):
        idx = len(left_slots) + i
        is_sel = idx == slot_idx
        prefix = "▶ " if is_sel else "  "
        color = (255, 255, 255) if is_sel else (140, 140, 140)

        val = getattr(eq, slot) or "なし"
        text = f"{prefix}{slot}: {val}"

        screen.blit(
            font.render(text, True, color), (right_x, slots_y + (i + 1) * line_h)
        )

    # ★ 上段で実際に使った最下端を返す
    bottom_y = slots_y + rows * line_h

    return bottom_y


# 下部：装備候補表示
def draw_equip_candidates(
    screen,
    font,
    actor,
    slot,
    candidates,
    *,
    idx,
    top,
    max_rows,
    base_stats,
    calc_preview_stats_fn,
    x,
    y,
    col_w,
    line_h,
):
    w = screen.get_width()
    margin = 24

    # 下部枠
    under_h = int(line_h * max_rows) + 20
    under_rect = pygame.Rect(margin, y - 10, col_w, under_h)
    draw_window(screen, under_rect)

    """
    下部：選択中 slot の装備候補一覧＋差分表示
    """
    visible = candidates[top : top + max_rows]

    can_scroll_up = top > 0
    can_scroll_down = top + max_rows < len(candidates)

    for i, (kind, name, data) in enumerate(visible):
        real_i = top + i
        is_sel = real_i == idx
        prefix = "▶ " if is_sel else "  "

        # 装備中判定
        cur = actor.equipment
        equipped = False
        if cur:
            if kind == "none":
                equipped = getattr(cur, slot) is None
            else:
                equipped = getattr(cur, slot) == name

        # 色
        if is_sel:
            color = (255, 255, 255)
        elif equipped:
            color = (120, 180, 255)  # 装備中（青）
        else:
            color = (140, 140, 140)

        # --- 表示テキスト ---
        if kind == "none":
            left_text = f"{prefix}{name}{' [E]' if equipped else ''}"
        elif kind == "weapon":
            atk = int(data.get("BasePower", 0) or 0)
            acc = int(round((data.get("BaseAccuracy", 0) or 0) * 100))
            left_text = (
                f"{prefix}{name}{' [E]' if equipped else ''}  " f"ATK:{atk}  ACC:{acc}%"
            )
        else:  # armor
            d = int(data.get("Defense", 0) or 0)
            eva = int(round((data.get("Evasion", 0) or 0) * 100))
            mdef = int(data.get("BaseMagicDefense", 0) or 0)
            left_text = (
                f"{prefix}{name}{' [E]' if equipped else ''}  "
                f"DEF:{d}  EVA:{eva}%  MDEF:{mdef}"
            )

        surf = font.render(left_text, True, color)
        screen.blit(surf, (x, y + i * line_h))

        # --- 差分表示（選択中のみ） ---
        if is_sel:
            preview = calc_preview_stats_fn(kind, name)
            diffs = []

            if slot in ("main_hand", "off_hand"):
                d, col = diff_text_and_color(base_stats.main_power, preview.main_power)
                if d:
                    diffs.append(("ATK" + d, col))

                if slot == "off_hand":
                    d2, col2 = diff_text_and_color(base_stats.defense, preview.defense)
                    if d2:
                        diffs.append(("DEF" + d2, col2))
            else:
                d, col = diff_text_and_color(base_stats.defense, preview.defense)
                if d:
                    diffs.append(("DEF" + d, col))

            dx = x + surf.get_width() + 12
            for txt, col in diffs:
                s = font.render(txt, True, col)
                screen.blit(s, (dx, y + i * line_h))
                dx += s.get_width() + 10

    # ★ ループが終わってから一度だけ描画
    arrow_color = (120, 120, 120)
    arrow_x = x - 24
    arrow_y_top = y - line_h
    arrow_y_bottom = y + max_rows * line_h

    if can_scroll_up:
        up = font.render("▲", True, arrow_color)
        screen.blit(up, (arrow_x, arrow_y_top))

    if can_scroll_down:
        down = font.render("▼", True, arrow_color)
        screen.blit(down, (arrow_x, arrow_y_bottom))


# 装備情報比較表示
def draw_equip_status_compare(
    screen,
    font,
    *,
    base_stats,
    preview_stats,
    icon_cache,  # ← 追加
    x,
    y,
    w,
    line_h,
):
    def blit(text, x, y, color=(220, 220, 220)):
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))

    def stat_line(label, now, new, x, y):
        diff = new - now
        if diff > 0:
            col = (80, 255, 80)
            d = f"(+{diff})"
        elif diff < 0:
            col = (255, 80, 80)
            d = f"({diff})"
        else:
            col = (160, 160, 160)
            d = ""

        blit(f"{label:5} {now} → {new} {d}", x, y, col)

    cur_y = y

    # ---- 枠 ----
    rect = pygame.Rect(x - 12, y - 10, w + 24, line_h * 13 + 20)
    draw_window(screen, rect)

    blit("STATUS", x, cur_y, (180, 180, 180))
    cur_y += line_h

    # ---- 数値系 ----
    stat_line("ATK", base_stats.main_power, preview_stats.main_power, x, cur_y)
    cur_y += line_h

    stat_line("DEF", base_stats.defense, preview_stats.defense, x, cur_y)
    cur_y += line_h

    stat_line(
        "EVA", base_stats.evasion_percent, preview_stats.evasion_percent, x, cur_y
    )
    cur_y += line_h

    stat_line("MDEF", base_stats.magic_defense, preview_stats.magic_defense, x, cur_y)
    cur_y += line_h

    # ---- 武器特性 ----
    flags = []
    if preview_stats.main_two:
        flags.append("Two-Handed")
    if preview_stats.main_long:
        flags.append("Long Range")

    if flags:
        cur_y += line_h // 2
        blit("[Weapon]", x, cur_y, (160, 160, 160))
        cur_y += line_h
        for f in flags:
            blit(f"- {f}", x + 16, cur_y)
            cur_y += line_h

    # ---- 属性・耐性 ----
    def list_block(title, items):
        nonlocal cur_y
        if not items:
            return
        cur_y += line_h // 2
        blit(title, x, cur_y, (160, 160, 160))
        cur_y += line_h
        blit(", ".join(items), x + 16, cur_y)
        cur_y += line_h

    list_block("[Elements]", preview_stats.main_weapon_elements)
    list_block("[Resist]", preview_stats.elemental_resists)
    list_block("[Null]", preview_stats.elemental_nulls)
    list_block("[Weak]", preview_stats.elemental_weaks)
    list_block("[Absorb]", preview_stats.elemental_absorbs)

    # ステータス異常耐性 アイコンで表示
    if preview_stats.status_immunities:
        cur_y += line_h // 2
        blit("[Status Immune]", x, cur_y, (160, 160, 160))
        cur_y += line_h

        draw_status_immune_icons(
            screen,
            preview_stats.status_immunities,
            icon_cache=icon_cache,  # ← open_equip_pygame から渡す
            x=x + 16,
            y=cur_y,
            spacing=4,
        )
        cur_y += line_h


# スクロール用ユーティリティ
def clamp_scroll(idx, top, max_rows, total):
    """
    idx: 現在選択インデックス
    top: 表示開始インデックス
    max_rows: 画面に表示できる最大行数
    total: 候補総数
    """
    if idx < top:
        top = idx
    elif idx >= top + max_rows:
        top = idx - max_rows + 1

    top = max(0, min(top, max(0, total - max_rows)))
    return top


def open_status_pygame(
    screen,
    font,
    party,
    *,
    level_table,
    weapons,
    portrait_cache: PortraitCache,
    status_icon_cache: StatusIconCache,
):
    clock = pygame.time.Clock()
    idx = 0

    line_h = font.get_linesize() + 6
    margin_top = 130

    def blit_line(text, x, y, color=(220, 220, 220)):
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))

    def hand_is_active(off_name, off_val):
        # off_hand がある or off側の値が有意なら「二刀」とみなす
        return (off_name is not None) or (off_val not in (0, None))

    def is_weapon(name: str | None) -> bool:
        return (name is not None) and (weapons is not None) and (name in weapons)

    def avg_from_equipped_weapons(eq: EquipmentSet, st) -> tuple[int, int, int]:
        """
        武器を装備している手だけで平均（盾は除外）。
        戻り値: (攻撃力, 命中率, 武器本数)
        """
        powers: list[int] = []
        accs: list[int] = []

        if is_weapon(eq.main_hand):
            powers.append(st.main_power)
            accs.append(st.main_accuracy)

        if is_weapon(eq.off_hand):
            powers.append(st.off_power)
            accs.append(st.off_accuracy)

        # 武器が0本（素手など）の場合は main を表示
        if not powers:
            powers = [st.main_power]
            accs = [st.main_accuracy]

        atk_value = int(round(sum(powers) / len(powers)))
        acc_value = int(round(sum(accs) / len(accs)))
        return atk_value, acc_value, len(powers)

    # 簡易折り返し（最大幅 max_w を超えたら次行へ）
    def blit_wrap(text, x, y, max_w, color=(220, 220, 220)):
        words = text.split("/")
        cur = ""
        yy = y
        for w in words:
            cand = (cur + "/" + w) if cur else w
            if font.size(cand)[0] <= max_w:
                cur = cand
            else:
                blit_line(cur, x, yy, color)
                yy += line_h
                cur = w
        if cur:
            blit_line(cur, x, yy, color)
            yy += line_h
        return yy

    def fmt_status_imm(imm) -> str:
        if not imm:
            return "-"
        # 表示順を安定させる
        labels = [STATUS_ABBR.get(s, str(s)[:3].upper()) for s in sorted(imm)]
        return "/".join(labels)

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    return
                if event.key == pygame.K_LEFT:
                    idx = (idx - 1) % len(party)
                elif event.key == pygame.K_RIGHT:
                    idx = (idx + 1) % len(party)

        # --- actor取得後の計算 ---
        actor = party[idx]
        base = actor.base
        st = actor.stats
        eq = actor.equipment or EquipmentSet()

        ls = level_table.status_from_level_and_exp(base.level, base.total_exp)
        exp_to_next = ls.exp_to_next

        atk_value, acc_value, weapon_count = avg_from_equipped_weapons(eq, st)

        # 攻撃回数：武器がある手だけ加算（盾は攻撃回数に含めない）
        atk_times = 0
        if is_weapon(eq.main_hand):
            atk_times += st.main_atk_multiplier
        if is_weapon(eq.off_hand):
            atk_times += st.off_atk_multiplier
        if atk_times == 0:
            atk_times = st.main_atk_multiplier  # 素手想定でmainを採用

        # 防御回数：defense_multiplier（既存設計に合わせる）
        def_times = st.defense_multiplier

        # ---- draw ----
        screen.fill((0, 0, 0))
        w, h = screen.get_width(), screen.get_height()
        margin = 24
        line_h = font.get_linesize()

        # ★portrait（左上に表示）
        face_size = 64
        face_rect = pygame.Rect(60, 20, face_size, face_size)
        inner = face_rect.inflate(-4, -4)

        key = getattr(actor, "portrait_key", None)
        if key:
            face = portrait_cache.get(key)
            img = pygame.transform.scale(face, (inner.w, inner.h))
            screen.blit(img, inner.topleft)
        else:
            pygame.draw.rect(screen, (60, 60, 60), inner)

        # title
        title = font.render(f"{actor.name}   {actor.job.name}", True, (255, 255, 255))
        screen.blit(title, (w // 2 - title.get_width() // 2, 30))

        page_label = "STATUS"
        pl = font.render(page_label, True, (160, 160, 160))
        screen.blit(pl, (w // 2 - pl.get_width() // 2, 60))

        # 全体枠
        rect = pygame.Rect(
            margin,
            face_size + margin * 2,
            w - margin * 2,
            h - (face_size + margin * 5),
        )
        draw_window(screen, rect)

        # -------- ステータス --------
        xL = 80
        xR = w // 2

        y = margin_top
        blit_line(f"LEVEL  {base.level}", xL, y)
        y += line_h
        blit_line(f"HP: {actor.hp}/{actor.max_hp}", xL, y)
        y += line_h

        mp_pool = getattr(actor, "mp_pool", None)
        if mp_pool is None:
            mp_pool = getattr(actor.state, "mp_pool", {})
        mp_vals = [f"{mp_pool.get(lv, 0):2d}" for lv in range(1, 9)]
        mp_text = "/".join(mp_vals)
        blit_line(f"MP: {mp_text}", xL, y)

        y += line_h
        y += line_h
        blit_line(f"ちから    {st.strength}", xL, y)
        y += line_h
        blit_line(f"すばやさ  {st.agility}", xL, y)
        y += line_h
        blit_line(f"たいりょく {st.vitality}", xL, y)
        y += line_h
        blit_line(f"ちせい    {st.intelligence}", xL, y)
        y += line_h
        blit_line(f"せいしん  {st.mind}", xL, y)
        y += line_h

        row_label = "FRONT" if base.row == "front" else "BACK"
        blit_line(f"ROW: {row_label}", xL, y)
        y += line_h
        # ステータス異常
        blit_line(f"STATUS:", xL, y)
        # draw_status_badges(screen, font, actor, xL, y)
        draw_status_icons(
            screen,
            actor,
            status_icon_cache,
            x=xL + 80,
            y=y + 6,
        )

        # 右側（要望反映）
        y2 = margin_top
        blit_line(f"じゅくれんど  {base.job_level}", xR, y2)
        y2 += line_h
        blit_line(f"EXP  {base.total_exp}", xR, y2)
        y2 += line_h
        blit_line(f"つぎのレベルまで  {exp_to_next}", xR, y2)
        y2 += line_h
        y2 += line_h

        blit_line(f"こうげき  {atk_times}かい…  {atk_value}", xR, y2)
        y2 += line_h
        blit_line(f"めいちゅうりつ …  {acc_value}%", xR, y2)
        y2 += line_h
        blit_line(f"ぼうぎょ  {def_times}かい…  {st.defense}", xR, y2)
        y2 += line_h
        blit_line(f"かいひりつ …  {st.evasion_percent}%", xR, y2)
        y2 += line_h

        # あると便利（既存の右側項目）
        blit_line(f"まほうぼうぎょ …  {st.magic_defense}", xR, y2)
        y2 += line_h
        blit_line(f"まほうかいひりつ …  {st.magic_resistance}%", xR, y2)
        y2 += line_h

        # 下部ヒント
        hint = font.render("← →: Switch / BS: Back", True, (180, 180, 180))
        screen.blit(
            hint,
            (w // 2 - hint.get_width() // 2, h - 60),
        )

        pygame.display.flip()
        clock.tick(60)


# 装備可能な候補を作る
SLOT_TO_ARMORTYPE = {
    "off_hand": {"Shield"},  # 盾
    "head": {"Helm"},  # 頭
    "body": {"Armor"},  # 体
    "arms": {"Gloves"},  # 手
}


def _job_code_of_actor(actor) -> str:
    # まずは slug を優先（例: "Wa" "OK" などに合わせたい）
    # ただしプロジェクトによって slug が "warrior" のような場合もあるので、
    # その場合は後述の JOB_NAME_TO_CODE で補正します。
    s = (getattr(actor.job, "slug", None) or "").strip()
    if s:
        return s

    # 最後の手段：name
    return (getattr(actor.job, "name", None) or "").strip()


# 必要ならここをあなたの Job 名に合わせて拡張してください
JOB_NAME_TO_CODE = {
    "Onion Knight": "OK",
    "Warrior": "Wa",
    "Monk": "Mo",
    "White Mage": "WM",
    "Black Mage": "BM",
    "Red Mage": "RM",
    "Ranger": "Ra",
    "Knight": "Kn",
    "Thief": "Th",
    "Scholar": "Sc",
    "Geomancer": "Ge",
    "Dragoon": "Dr",
    "Viking": "Vi",
    "Black Belt": "BB",
    "Evoker": "Ev",
    "Bard": "Ba",
    "Magus": "Ma",
    "Devout": "De",
    "Summoner": "Su",
    "Sage": "Sa",
    "Ninja": "Ni",
    "Mystic Knight": "MK",  # JSON内で MK 表記になっています :contentReference[oaicite:2]{index=2}
}


def actor_job_code(actor) -> str:
    # slug がすでに "Wa" 等ならそれを使う
    s = (getattr(actor.job, "slug", "") or "").strip()
    if s and len(s) <= 3:
        return s
    # name からコードへ
    n = (getattr(actor.job, "name", "") or "").strip()
    return JOB_NAME_TO_CODE.get(n, n)


# 「装備できるか」判定（武器/防具共通）
def allowed_by_job(actor, item_dict: dict) -> bool:
    allow = item_dict.get("EquippedBy") or []
    if not allow:
        return True
    code = canon(actor_job_code(actor))
    return code in {canon(x) for x in allow}


# off_hand で「両手武器」を除外（重要）
def is_two_handed_weapon(w: dict) -> bool:
    return "Two-Handed" in w  # 値は説明文なのでキー存在でOK


def _actor_code_for_equip(actor) -> str:
    raw = _job_code_of_actor(actor)
    if raw in JOB_NAME_TO_CODE:
        return JOB_NAME_TO_CODE[raw]
    # slug が "wa" みたいなケースも吸収したいので、大小無視で合わせる
    inv = {canon(k): v for k, v in JOB_NAME_TO_CODE.items()}
    raw_key = canon(raw)
    if raw_key in inv:
        return inv[raw_key]
    return raw  # すでに "Wa" 等が入っているならそのまま


def _armor_allows(actor, armor_dict: dict) -> bool:
    codes = armor_dict.get("EquippedBy") or []
    if not codes:
        return True
    actor_code = _actor_code_for_equip(actor)
    return canon(actor_code) in {canon(c) for c in codes}


def build_equip_candidates(actor, slot, *, weapons_by_name, armors_by_name):
    out = [("none", "はずす", None)]

    # ---- 武器候補 ----
    if slot in ("main_hand", "off_hand"):
        for name, w in weapons_by_name.items():
            if not allowed_by_job(actor, w):
                continue
            if slot == "off_hand" and is_two_handed_weapon(w):
                continue
            out.append(("weapon", name, w))

        # off_hand は盾も追加
        if slot == "off_hand":
            for name, a in armors_by_name.items():
                if a.get("ArmorType") == "Shield" and allowed_by_job(actor, a):
                    out.append(("armor", name, a))
        return out

    # ---- 防具候補（head/body/arms）----
    allow_types = SLOT_TO_ARMORTYPE.get(slot, set())
    for name, a in armors_by_name.items():
        if a.get("ArmorType") in allow_types and allowed_by_job(actor, a):
            out.append(("armor", name, a))

    return out


def calc_preview_stats(
    actor, *, slot, item_kind, item_name, weapons_by_name, armors_by_name
):
    # 装備をコピー（本体は絶対に触らない）
    eq_preview = deepcopy(actor.equipment or EquipmentSet())

    if item_kind == "none":
        setattr(eq_preview, slot, None)
    else:
        setattr(eq_preview, slot, item_name)

    return compute_character_final_stats(
        base=actor.base,
        eq=eq_preview,
        weapons_by_name=weapons_by_name,
        armors_by_name=armors_by_name,
        job_name=actor.job.name,
    )


def diff_text_and_color(now: int, new: int):
    d = new - now
    if d > 0:
        return f"(+{d})", (80, 255, 80)  # 緑
    if d < 0:
        return f"({d})", (255, 80, 80)  # 赤
    return "", (180, 180, 180)


def show_toast_message(
    screen,
    font,
    text: str,
    *,
    duration: float = 1.0,
    bg_color=(0, 0, 0),
    text_color=(255, 255, 255),
):
    """
    画面中央に text を duration 秒だけ表示する
    """
    clock = pygame.time.Clock()
    start = time.time()

    text_surf = font.render(text, True, text_color)
    pad = 16
    box_w = text_surf.get_width() + pad * 2
    box_h = text_surf.get_height() + pad * 2

    x = screen.get_width() // 2 - box_w // 2
    y = screen.get_height() // 2 - box_h // 2

    box = pygame.Surface((box_w, box_h))
    box.fill(bg_color)

    while time.time() - start < duration:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            # 入力は全部捨てる（操作不可）

        screen.blit(box, (x, y))
        screen.blit(
            text_surf,
            (x + pad, y + pad),
        )

        pygame.display.flip()
        clock.tick(60)


def open_job_pygame(
    screen,
    font,
    party,
    *,
    job_attr: Optional[Dict[str, Dict[str, int]]] = None,
    jobs_by_name: dict,
    weapons_by_name: dict,
    armors_by_name: dict,
    recalc_stats_fn,
    save_dict: dict | None = None,
    portrait_cache: PortraitCache,
    status_icon_cache: StatusIconCache,
):
    clock = pygame.time.Clock()
    actor_idx = 0

    job_names = sorted(list(jobs_by_name.keys()))
    if not job_names:
        return

    sel_idx = 0
    top = 0
    line_h = font.get_linesize() + 6
    header_h = line_h * 3.5
    max_rows = max(
        5, (screen.get_height() - header_h - 110) // line_h
    )  # ★プレビュー分少し確保

    # --------- helpers ---------
    def clamp():
        nonlocal top
        if sel_idx < top:
            top = sel_idx
        elif sel_idx >= top + max_rows:
            top = sel_idx - max_rows + 1
        top = max(0, min(top, max(0, len(job_names) - max_rows)))

    def actor():
        return party[actor_idx]

    def set_sel_to_current():
        nonlocal sel_idx
        try:
            sel_idx = job_names.index(actor().job.name)
        except ValueError:
            sel_idx = 0
        clamp()

    def find_save_entry_for_actor(a):
        if save_dict is None:
            return None
        for p in save_dict.get("party", []):
            if p.get("name") == a.name:
                return p
        return None

    def ensure_job_levels_dict(sp: dict) -> dict:
        jl = sp.get("job_levels")
        if not isinstance(jl, dict):
            jl = {}
            sp["job_levels"] = jl
        return jl

    def get_saved_job_lv(sp: dict | None, job_name: str) -> int | None:
        """保存済み JobLv を返す。無ければ None"""
        if sp is None:
            return None
        jl = sp.get("job_levels")
        if not isinstance(jl, dict):
            return None
        v = jl.get(job_name)
        if not isinstance(v, dict):
            return None
        try:
            return int(v.get("level", 1))
        except Exception:
            return None

    def is_new_job(sp: dict | None, job_name: str) -> bool:
        """未経験なら True（job_levels に存在しない）"""
        if sp is None:
            return False
        jl = sp.get("job_levels")
        if not isinstance(jl, dict):
            return True  # 古いセーブで job_levels 無い場合は全部NEW扱いでもOK
        return job_name not in jl

    def diff_text_and_color(now: int, new: int):
        d = new - now
        if d > 0:
            return f"+{d}", (80, 255, 80)
        if d < 0:
            return f"{d}", (255, 80, 80)
        return "0", (180, 180, 180)

    def preview_stats_for_job(a, new_job_name: str, sp: dict | None):
        """
        「選択中ジョブにした場合」の最終ステータスを作る（装備制限も反映）
        ※actor本体は変更しない
        """
        # new job runtime
        new_job = jobs_by_name[new_job_name]

        # job_level/skill_point の復元（無ければ初期）
        new_level = 1
        new_sp = 0
        if sp is not None:
            jl_dict = sp.get("job_levels")
            if isinstance(jl_dict, dict):
                v = jl_dict.get(new_job_name)
                if isinstance(v, dict):
                    new_level = int(v.get("level", 1))
                    new_sp = int(v.get("skill_point", 0))

        # base をコピーして job情報だけ差し替え
        base2 = deepcopy(a.base)
        base2.job_level = max(1, int(new_level))
        base2.job_skill_point = max(0, min(99, int(new_sp)))

        # 装備をコピーして制限反映
        eq2 = deepcopy(a.equipment or EquipmentSet())
        eq2, _removed = strip_illegal_equipment_for_job(
            eq2,
            new_job,
            weapons_by_name=weapons_by_name,
            armors_by_name=armors_by_name,
        )

        # stats算出
        return compute_character_final_stats(
            base=base2,
            eq=eq2,
            weapons_by_name=weapons_by_name,
            armors_by_name=armors_by_name,
            job_name=new_job.name,
        )

    set_sel_to_current()

    # -------- save sync helper（あなたの job_levels 対応版を使う想定）---------
    def update_save_for_actor(a):
        if save_dict is None:
            return
        for sp in save_dict.get("party", []):
            if sp.get("name") != a.name:
                continue

            sp["job"] = a.job.name

            job_levels = sp.get("job_levels")
            if not isinstance(job_levels, dict):
                job_levels = {}
                sp["job_levels"] = job_levels

            jl = max(1, int(getattr(a.base, "job_level", 1)))
            spv = max(0, min(99, int(getattr(a.base, "job_skill_point", 0))))

            job_levels[a.job.name] = {"level": jl, "skill_point": spv}
            sp["job_level"] = {"level": jl, "skill_point": spv}

            eq = a.equipment
            sp["equipment"] = {
                "main_hand": getattr(eq, "main_hand", None) if eq else None,
                "off_hand": getattr(eq, "off_hand", None) if eq else None,
                "head": getattr(eq, "head", None) if eq else None,
                "body": getattr(eq, "body", None) if eq else None,
                "arms": getattr(eq, "arms", None) if eq else None,
            }
            return

    # --------- main loop ---------
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    return

                if event.key == pygame.K_LEFT:
                    actor_idx = (actor_idx - 1) % len(party)
                    set_sel_to_current()

                elif event.key == pygame.K_RIGHT:
                    actor_idx = (actor_idx + 1) % len(party)
                    set_sel_to_current()

                elif event.key == pygame.K_UP:
                    sel_idx = (sel_idx - 1) % len(job_names)
                    clamp()

                elif event.key == pygame.K_DOWN:
                    sel_idx = (sel_idx + 1) % len(job_names)
                    clamp()

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                    a = actor()
                    old_job = a.job.name
                    new_job_name = job_names[sel_idx]
                    if old_job == new_job_name:
                        continue

                    sp = find_save_entry_for_actor(a)

                    # ===== CPチェック =====
                    to_lv = get_saved_job_lv(sp, new_job_name) or 1
                    if not isinstance(job_attr, dict):
                        need_cp = 0
                    else:
                        need_cp = compute_job_change_cp_cost(
                            from_job=old_job,
                            to_job=new_job_name,
                            to_job_level=to_lv,
                            job_attr=job_attr,
                        )

                    have_cp = 0
                    if isinstance(save_dict, dict):
                        try:
                            have_cp = int(save_dict.get("CP", 0))
                        except (TypeError, ValueError):
                            have_cp = 0

                    if have_cp < need_cp:
                        show_toast_message(
                            screen,
                            font,
                            f"Not enough CP ({need_cp} needed)",
                            duration=1.2,
                            text_color=(255, 80, 80),
                        )
                        continue

                    # CP消費
                    if isinstance(save_dict, dict):
                        save_dict["CP"] = max(0, have_cp - need_cp)

                    # 1) 変更前ジョブの進行を保存
                    if sp is not None:
                        job_levels = ensure_job_levels_dict(sp)
                        job_levels[old_job] = {
                            "level": int(a.base.job_level),
                            "skill_point": int(a.base.job_skill_point),
                        }

                    # 2) 新ジョブへ変更（runtime）
                    a.job = jobs_by_name[new_job_name]

                    # 3) 新ジョブの進行を復元（なければ初期値）
                    new_level = 1
                    new_spv = 0
                    if sp is not None:
                        job_levels = ensure_job_levels_dict(sp)
                        v = job_levels.get(new_job_name)
                        if not isinstance(v, dict):
                            v = {"level": 1, "skill_point": 0}
                            job_levels[new_job_name] = v
                        new_level = int(v.get("level", 1))
                        new_spv = int(v.get("skill_point", 0))

                    a.base.job_level = max(1, int(new_level))
                    a.base.job_skill_point = max(0, min(99, int(new_spv)))

                    # 4) 装備制限チェック → 外す
                    if a.equipment is None:
                        a.equipment = EquipmentSet()
                    new_eq, removed = strip_illegal_equipment_for_job(
                        a.equipment,
                        a.job,
                        weapons_by_name=weapons_by_name,
                        armors_by_name=armors_by_name,
                    )
                    a.equipment = new_eq

                    # 5) 再計算
                    a.stats = recalc_stats_fn(a, weapons_by_name, armors_by_name)

                    # 6) save_dict を現在状態で同期
                    update_save_for_actor(a)

                    # 7) 装備が外れたら装備画面へ誘導
                    if removed:
                        msg = "Removed: " + ", ".join(removed[:2])
                        if len(removed) > 2:
                            msg += "..."
                        show_toast_message(screen, font, msg, duration=1.2)

                        open_equip_pygame(
                            screen,
                            font,
                            party,
                            weapons_by_name=weapons_by_name,
                            armors_by_name=armors_by_name,
                            portrait_cache=portrait_cache,
                            status_icon_cache=status_icon_cache,
                        )

        # ---- draw ----
        screen.fill((0, 0, 0))
        w, h = screen.get_width(), screen.get_height()

        # ★portrait（左上に表示）
        face_size = 64
        face_rect = pygame.Rect(60, 20, face_size, face_size)
        inner = face_rect.inflate(-4, -4)

        # ========== レイアウト（固定） ==========
        margin = 24
        left_w = int(w * 0.65)
        right_w = w - left_w - margin * 3

        job_rect = pygame.Rect(
            margin,
            face_size + margin * 2,
            left_w,
            h - face_size - margin * 3,
        )
        exp_rect = pygame.Rect(
            job_rect.right + margin,
            face_size + margin * 2,
            right_w,
            h - face_size - margin * 3,
        )

        draw_window(screen, job_rect)
        draw_window(screen, exp_rect)
        # =======================================

        a = actor()
        sp = find_save_entry_for_actor(a)

        key = getattr(a, "portrait_key", None)
        if key:
            face = portrait_cache.get(key)
            img = pygame.transform.scale(face, (inner.w, inner.h))
            screen.blit(img, inner.topleft)
        else:
            pygame.draw.rect(screen, (60, 60, 60), inner)

        # キャラ名＋ジョブ名（中央上）
        title = font.render(f"{a.name}   {a.job.name}", True, WHITE)
        screen.blit(title, (screen.get_width() // 2 - title.get_width() // 2, 30))

        page_label = "JOB"
        pl = font.render(page_label, True, GRAY)
        screen.blit(pl, (screen.get_width() // 2 - pl.get_width() // 2, 60))

        # CP
        cp = int(save_dict.get("CP", 0)) if save_dict else 0
        cp_txt = font.render(f"CP {cp}/255", True, (255, 220, 60))
        screen.blit(cp_txt, (screen.get_width() - 160, 16))

        hint = font.render("←→: Character  ↑↓: Job  Enter: Set  BS: Back", True, GRAY)
        screen.blit(hint, (16, 16 + line_h * 2))

        # ---------- job list (2 columns) ----------
        y0 = 16 + header_h
        jobs = job_names
        num_rows = (len(jobs) + 1) // 2

        start_x = 40
        start_y = y0
        col_w = 300
        row_h = line_h

        for row in range(num_rows):
            for col in range(2):
                idx = row * 2 + col
                if idx >= len(jobs):
                    continue

                jn = jobs[idx]
                is_sel = idx == sel_idx

                x = start_x + col * col_w
                y = start_y + row * row_h

                prefix = "▶ " if is_sel else "  "
                color = (255, 255, 255) if is_sel else (140, 140, 140)

                # JobLv
                saved_lv = get_saved_job_lv(sp, jn) or 1

                # 必要CP
                need_cp = 0
                if isinstance(job_attr, dict):
                    need_cp = compute_job_change_cp_cost(
                        from_job=a.job.name,
                        to_job=jn,
                        to_job_level=saved_lv,
                        job_attr=job_attr,
                    )

                label = f"{jn}  Lv{saved_lv}  CP{need_cp}"

                # NEW
                # if is_new_job(sp, jn):
                # label += " NEW"

                # 現在ジョブ
                if jn == a.job.name:
                    label += " [E]"

                surf = font.render(prefix + label, True, color)
                screen.blit(surf, (x, y))

        # ---------- status diff preview ----------
        # 選択中ジョブが現在ジョブと違う時だけプレビュー表示
        sel_job = job_names[sel_idx]
        if sel_job != a.job.name:
            try:
                pv = preview_stats_for_job(a, sel_job, sp)
                now = a.stats

                # ここは好みで増やせます（まずは重要なものだけ）
                lines = []
                # ATK/ACCはあなたの仕様に合わせて表示（平均の方ならここを平均に）
                t, c = diff_text_and_color(now.main_power, pv.main_power)
                lines.append(("ATK", t, c))
                t, c = diff_text_and_color(now.defense, pv.defense)
                lines.append(("DEF", t, c))
                t, c = diff_text_and_color(now.evasion_percent, pv.evasion_percent)
                lines.append(("EVA", t, c))
                t, c = diff_text_and_color(now.magic_defense, pv.magic_defense)
                lines.append(("MDEF", t, c))

                # 右下に表示
                bx = screen.get_width() - 260
                by = screen.get_height() - 320

                cap = font.render("Preview diff", True, (180, 180, 180))
                screen.blit(cap, (bx, by))
                yy = by + line_h

                for key, txt, col in lines:
                    s = font.render(f"{key}: {txt}", True, col)
                    screen.blit(s, (bx, yy))
                    yy += line_h

                # ===== CPプレビュー =====
                to_lv = get_saved_job_lv(sp, sel_job) or 1
                if not isinstance(job_attr, dict):
                    need_cp = 0
                else:
                    need_cp = compute_job_change_cp_cost(
                        from_job=a.job.name,
                        to_job=sel_job,
                        to_job_level=to_lv,
                        job_attr=job_attr,
                    )

                have_cp = 0
                if isinstance(save_dict, dict):
                    have_cp = int(save_dict.get("CP", 0))

                cp_color = (255, 80, 80) if have_cp < need_cp else (255, 220, 60)
                cp_text = f"CP {need_cp}  (Have {have_cp})"
                cp_surf = font.render(cp_text, True, cp_color)
                screen.blit(cp_surf, (bx, yy + 4))

            except Exception:
                # プレビュー計算で例外が出ても画面は落とさない
                pass

        pygame.display.flip()
        clock.tick(60)


import pygame


def draw_window(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    fill=(0, 40, 140),
    border_outer=(230, 230, 230),
    border_inner=(80, 80, 80),
):
    """FFっぽい二重枠ウィンドウ（9-sliceなしの簡易版）"""
    pygame.draw.rect(surface, border_outer, rect, border_radius=8)
    inner = rect.inflate(-6, -6)
    pygame.draw.rect(surface, border_inner, inner, border_radius=6)
    body = rect.inflate(-10, -10)
    pygame.draw.rect(surface, fill, body, border_radius=4)


def get_name(ch) -> str:
    return ch.name


def get_job_name(ch) -> str:
    return ch.job.name


def get_level(ch) -> int:
    # 通常レベル
    return int(ch.base.level)


def get_job_level(ch) -> int:
    # FF3風の表示ならこっちが “LV”
    return int(ch.base.job_level)


def get_hp(ch):
    return int(ch.hp), int(ch.max_hp)


def get_mp(ch):
    return int(ch.mp), int(ch.max_mp)


def get_portrait_surface(ch):
    # portrait を実装したらここで返す
    return getattr(ch, "portrait_surface", None)


def draw_status_badges(screen, font, actor, x, y, color=(255, 255, 255)):
    statuses = getattr(actor.state, "statuses", set()) or set()
    label_by_status = {
        Status.POISON: "POI",
        Status.BLIND: "BLD",
        Status.SILENCE: "SIL",
        Status.PARALYZE: "PAR",
        Status.SLEEP: "SLP",
        Status.MINI: "MIN",
        Status.TOAD: "TOA",
        Status.PETRIFY: "STN",
        Status.KO: "KO",
    }
    xx = x
    for st in statuses:
        lab = label_by_status.get(st)
        if not lab:
            continue
        s = font.render(lab, True, color)
        screen.blit(s, (xx, y))
        xx += s.get_width() + 10


def fmt_elems(elems) -> str:
    if not elems:
        return "-"
    # 表示順を安定させたいなら sorted
    return "/".join(sorted(elems))


# 表示用：Lvごとの魔法リストを作る（データ整形）
def group_spells_by_level(spells: list[tuple[str, int, int]]) -> dict[int, list[str]]:
    """
    spells: (name, lv, cost) の列を Lv(1..8) -> [name,...] にまとめる
    表示はまず名前だけ（必要なら cost 表示も後で追加）
    """
    out: dict[int, list[str]] = {i: [] for i in range(1, 9)}

    for name, lv0, cost in spells:
        lv = int(lv0)

        # build_magic_fn が 0..7 を返しているので 1..8 に補正
        # if 0 <= lv <= 7:
        # lv += 1

        if 1 <= lv <= 8:
            out[lv].append(str(name))

    # 表示が安定するように並び順を揃える（任意）
    # for lv in range(1, 9):
    # out[lv].sort()

    return out


# まほう画面（Lv1〜8を上から表示、魔法名は右側に折り返し表示）
def open_magic_pygame(
    screen: pygame.Surface,
    font: pygame.font.Font,
    party,
    *,
    portrait_cache,
    status_icon_cache: StatusIconCache,
    build_magic_fn,  # member_idx -> [(name, lv, cost)]
    spells_by_name: dict[str, dict],  # ★追加
    cast_field_magic_fn: Callable[[int, str, int | None], bool] | None = None,
    ui_se: dict[str, pygame.mixer.Sound],
):
    clock = pygame.time.Clock()

    member_idx = 0
    lv_idx = 1  # 1..8
    mode = "level"  # "level" | "spell" | "target"
    spell_sel = 0  # spell list cursor
    target_sel = 0  # target cursor

    line_h = font.get_linesize() + 10

    # spells_by_name は "Flare" のように大文字始まりキーなので、
    # 小文字正規化で引ける index を一度作っておく（高速＆安全）
    spells_key_lut = {canon(k): k for k in spells_by_name.keys()}

    def blit_line(text, x, y, color=WHITE):
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))

    def _canon_spell_name(name: str) -> str:
        return canon(name)

    def _spell_lookup(name: str) -> dict:
        # 1) そのまま
        sp = spells_by_name.get(name)
        if sp:
            return sp
        # 2) 小文字正規化で引く
        k = spells_key_lut.get(_canon_spell_name(name))
        return spells_by_name.get(k, {}) if k else {}

    def magic_mark(spell: dict) -> str:
        t = str(spell.get("Type", ""))
        if "White" in t:
            return "〇"
        if "Black" in t:
            return "●"
        if "Summon" in t:
            return "◎"
        return "・"

    # 対象が必要かどうかの判定
    def needs_target_by_name(spell_name: str) -> bool:
        return _canon_spell_name(spell_name) in FIELD_MAGIC_TARGET_REQUIRED

    def target_candidates_for_field(spell_name: str, party) -> list[int]:
        """
        フィールドでの対象候補（indexのリスト）を返す。
        最低限の絞り込み：
          - Raise/Arise: KO（hp<=0）だけ
          - それ以外（回復/治療系）: 生存（hp>0）だけ
        さらに細かい「状態異常にかかってる人だけ」などは後で追加可能。
        """
        sn = canon(spell_name)

        is_revive = sn in ("raise", "arise")
        cand = []
        for i, ch in enumerate(party[:4]):
            hp = int(getattr(ch, "hp", 0))
            if is_revive:
                if hp <= 0:
                    cand.append(i)
            else:
                if hp > 0:
                    cand.append(i)

        # 候補が空だと操作不能になるので、空なら全員(先頭4人)にフォールバック
        if not cand:
            cand = list(range(min(4, len(party))))
        return cand

    def can_cast_now(actor, lv: int, cost: int) -> bool:
        """
        MPが足りるか（将来、Silence等の制限を追加してもOK）
        """
        mp_pool = actor.mp_pool  # PartyMemberRuntimeのpropertyで state.mp_pool に届く
        return int(mp_pool.get(lv, 0)) >= 1

    # 魔法名→コスト・Lv を引ける辞書を作る
    def build_magic_cost_map(
        spells_raw: list[tuple[str, int, int]],
    ) -> dict[str, tuple[int, int]]:
        # name -> (lv, cost)
        out: dict[str, tuple[int, int]] = {}
        for name, lv, cost in spells_raw:
            out[str(name)] = (int(lv), int(cost))
        return out

    def _ui_mp_pool(actor):
        st = get_battle_state(actor)
        return st.mp_pool if st is not None else {}

    def _ui_max_mp_pool(actor):
        st = get_battle_state(actor)
        return st.max_mp_pool if st is not None else {}

    while True:
        # -------- data build（先に作っておく：Enter処理で cur_list を使うため）--------
        actor = party[member_idx]
        spells_raw = build_magic_fn(member_idx)  # [(name, lv, cost)]

        spells_by_lv = {lv: [] for lv in range(1, 9)}
        for name, lv, cost in spells_raw:
            if _canon_spell_name(name) not in FIELD_MAGIC_WHITELIST:
                continue
            sp = _spell_lookup(name)
            if not sp:
                continue
            lv_real = int(sp.get("Level", lv) or lv)
            if not (1 <= lv_real <= 8):
                continue
            spells_by_lv[lv_real].append((name, lv_real, 1, sp))

        # ★C) 表示順を安定化：名前順（必要なら Type→名前 などに変更OK）
        for lv in range(1, 9):
            spells_by_lv[lv].sort(key=lambda t: t[0])

        cur_list = spells_by_lv.get(lv_idx, [])

        # 選択位置のクランプ
        if mode == "spell":
            spell_sel = min(spell_sel, max(0, len(cur_list) - 1)) if cur_list else 0

        selected_spell = None
        if cur_list and mode in ("spell", "target"):
            selected_spell = cur_list[spell_sel]  # (name, lv, cost, sp_dict)

        # -------- input --------
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit
            if ev.type != pygame.KEYDOWN:
                continue

            if ev.key == pygame.K_BACKSPACE:
                if mode == "target":
                    mode = "spell"
                elif mode == "spell":
                    mode = "level"
                else:
                    return
                continue

            if ev.key == pygame.K_LEFT:
                member_idx = (member_idx - 1) % len(party)
                spell_sel = 0
                target_sel = 0
                mode = "level"
                continue
            elif ev.key == pygame.K_RIGHT:
                member_idx = (member_idx + 1) % len(party)
                spell_sel = 0
                target_sel = 0
                mode = "level"
                continue

            if ev.key == pygame.K_UP:
                if mode == "level":
                    lv_idx = 8 if lv_idx == 1 else lv_idx - 1
                    spell_sel = 0
                elif mode == "spell":
                    spell_sel = max(0, spell_sel - 1)
                elif mode == "target":
                    name, lv, cost, sp = (
                        cur_list[spell_sel] if cur_list else ("", 1, 0, {})
                    )
                    cands = target_candidates_for_field(name, party)
                    n = max(1, len(cands))
                    target_sel = (target_sel - 1) % n
                continue

            if ev.key == pygame.K_DOWN:
                if mode == "level":
                    lv_idx = 1 if lv_idx == 8 else lv_idx + 1
                    spell_sel = 0
                elif mode == "spell":
                    spell_sel = spell_sel + 1  # 後でclamp
                elif mode == "target":
                    name, lv, cost, sp = (
                        cur_list[spell_sel] if cur_list else ("", 1, 0, {})
                    )
                    cands = target_candidates_for_field(name, party)
                    n = max(1, len(cands))
                    target_sel = (target_sel + 1) % n
                continue

            ##
            elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                if mode == "level":
                    mode = "spell"
                    spell_sel = 0
                    continue

                elif mode == "spell":
                    if not cur_list:
                        continue

                    name, lv, cost, sp = cur_list[spell_sel]

                    # MP不足ならここで弾く（任意）
                    if not can_cast_now(actor, lv, cost):
                        # show_toast_message(...) 等
                        continue

                    # ★ここが修正点：Target文字列は見ず、名前で対象要否を決める
                    if needs_target_by_name(name):
                        mode = "target"
                        target_sel = 0
                        continue
                    else:
                        # 対象なしで実行
                        # cast_field_magic_fn があるなら呼ぶ / 無いならDBGだけ
                        # print(
                        # f"[DBG] CAST field magic: caster={actor.name} spell={name} target=None"
                        # )
                        if cast_field_magic_fn:
                            cast_field_magic_fn(member_idx, name, None)
                        # else:
                        # print("[DBG] cast_field_magic_fn is None")
                        mode = "spell"
                        continue

                elif mode == "target":
                    if not selected_spell:
                        mode = "spell"
                        continue

                    name, lv, cost, sp = selected_spell
                    tgt_idx = target_sel
                    ch = party[tgt_idx]

                    # ★ 無効対象チェック
                    if not field_spell_will_affect(name, ch):
                        ui_se["invalid"].play()  # ★ブブー
                        continue

                    # 有効なら実行
                    if cast_field_magic_fn:
                        ui_se["confirm"].play()
                        cast_field_magic_fn(member_idx, name, tgt_idx)

                    mode = "spell"
                    continue
                ##

        # MP pool（描画用）
        mp_pool = _ui_mp_pool(actor)
        max_mp_pool = _ui_max_mp_pool(actor)

        # -------- draw --------
        screen.fill((0, 0, 0))
        w, h = screen.get_size()
        margin = 24

        # タイトル
        page_label = "MAGIC"
        pl = font.render(page_label, True, GRAY)
        screen.blit(pl, (w // 2 - pl.get_width() // 2, margin))

        # ====== 左右ペイン（ITEM画面と同型） ======
        left_w = int(w * 0.6)
        right_w = w - left_w - margin * 3

        left_rect = pygame.Rect(
            margin,
            pl.get_height() + margin * 2,
            left_w,
            h - pl.get_height() * 2 - margin * 3,
        )
        right_rect = pygame.Rect(
            left_rect.right + margin,
            pl.get_height() + margin * 2,
            right_w,
            h - pl.get_height() * 2 - margin * 3,
        )

        draw_window(screen, left_rect)
        draw_window(screen, right_rect)

        # ====== 左ペイン：Lv / MP / 魔法一覧 ======
        title_y = left_rect.y + 18
        blit_line(actor.name, left_rect.x + 24, title_y, WHITE)
        blit_line("まほう", left_rect.x + 200, title_y, WHITE)

        x_lv = left_rect.x + 28
        x_mp = x_lv + 70
        x_list = x_mp + 140
        y0 = left_rect.y + 70

        cursor = font.render("▶", True, WHITE)

        # --- Lv / MP ---
        for lv in range(1, 9):
            y = y0 + (lv - 1) * line_h
            if mode == "level" and lv == lv_idx:
                screen.blit(cursor, (x_lv - 24, y))
            blit_line(f"{lv}", x_lv, y)
            blit_line(f"{mp_pool.get(lv,0)}/{max_mp_pool.get(lv,0)}", x_mp, y)

        # --- 魔法リスト ---
        y = y0
        for i, (name, lv, cost, sp) in enumerate(cur_list[:8]):
            if mode == "spell" and i == spell_sel:
                screen.blit(cursor, (x_list - 24, y))

            enabled = can_cast_now(actor, lv, cost)
            color = WHITE if enabled else GRAY
            mark = magic_mark(sp)
            blit_line(f"{mark}{name}", x_list, y, color)
            y += line_h

        # ====== 右ペイン：ミニステータス ======
        if mode == "target" and selected_spell:
            name, lv, cost, sp = selected_spell
            cands = target_candidates_for_field(name, party)

            draw_party_ministatus(
                screen,
                right_rect,
                party,
                font,
                portrait_cache,
                status_icon_cache,
                selected_idx=cands[target_sel] if cands else None,
                cursor=cursor,
                spell_name=name,  # ★ここだけ
            )
        else:
            draw_party_ministatus(
                screen,
                right_rect,
                party,
                font,
                portrait_cache,
                status_icon_cache,
            )

        # ★魔法説明（spell / target 両方で表示）
        spell_for_desc = None
        if selected_spell:
            spell_for_desc = selected_spell[0]  # name

        draw_magic_description(
            screen,
            right_rect,
            font,
            spell_name=spell_for_desc,
            spells_by_name=spells_by_name,
        )

        # bottom strip（あなたの既存コードをそのまま挿入）
        # ...

        if mode == "level":
            hint_text = "← →: Switch  ↑ ↓: Level  Enter: Select  BS: Back"
        elif mode == "spell":
            hint_text = "↑ ↓: Spell  Enter: OK  BS: Back"
        else:
            hint_text = "↑ ↓: Target  Enter: OK  BS: Back"

        hint = font.render(hint_text, True, GRAY)
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 60))

        pygame.display.flip()
        clock.tick(60)


# 魔法名の正規化
def is_field_usable(spell: dict) -> bool:
    name = canon(spell.get("name", ""))
    if name in FIELD_MAGIC_WHITELIST:
        return True
    return False


# 状態異常回復用の判定
def field_spell_will_affect(spell_name: str, actor) -> bool:
    """
    フィールド魔法を actor に使ったとき、実際に効果があるか？
    （HPやStatusが変化するか）
    """
    sn = canon(spell_name)

    state = actor.state  # PartyMemberRuntime 前提

    # --- 状態異常回復 ---
    if sn == "poisona":
        return Status.POISON in state.statuses

    if sn == "blindna":
        return Status.BLIND in state.statuses

    if sn == "stona":
        return (
            Status.PETRIFY in state.statuses or Status.PARTIAL_PETRIFY in state.statuses
        )

    if sn == "esuna":
        ESUNA_SET = {
            Status.POISON,
            Status.BLIND,
            Status.MINI,
            Status.SILENCE,
            Status.TOAD,
            Status.CONFUSION,
            Status.SLEEP,
            Status.PARALYZE,
            Status.PETRIFY,
            Status.PARTIAL_PETRIFY,
        }
        return any(st in state.statuses for st in ESUNA_SET)

    # --- HP回復 ---
    if sn in ("cure", "cura", "curaga", "curaja"):
        return state.hp > 0 and state.hp < actor.max_hp

    # --- 蘇生 ---
    if sn in ("raise", "arise"):
        return state.hp <= 0 or Status.KO in state.statuses

    return True  # その他はとりあえず有効扱い


### --------------------------- ITEM


# フィールドで表示・使用できるアイテム一覧を作る
def iter_field_inventory(
    save_dict: Optional[dict],
) -> list[tuple[str, str, int]]:
    """
    フィールド用アイテム一覧:
      [(item_name, item_type, count), ...]
    item_type は "Anywhere" or "Field"
    """
    inv = (save_dict or {}).get("inventory", {})
    out: list[tuple[str, str, int]] = []
    for itype in FIELD_ITEM_TYPES:
        bucket = inv.get(itype, {})
        if isinstance(bucket, dict):
            for name, cnt in bucket.items():
                c = int(cnt or 0)
                if c > 0:
                    out.append((str(name), itype, c))
    # 表示順：名前順（好みで）
    out.sort(key=lambda t: t[0])
    return out


# 所持数を 1 減らす（0になったら消す or 0のまま）
def dec_inventory_item(save_dict: dict, item_name: str, item_type: str) -> bool:
    """
    inventory[item_type][item_name] を 1 減らす。
    成功したら True。
    """
    inv = (save_dict or {}).get("inventory", {})
    bucket = inv.get(item_type, {})
    if not isinstance(bucket, dict):
        return False
    cur = int(bucket.get(item_name, 0) or 0)
    if cur <= 0:
        return False
    nxt = cur - 1
    if nxt <= 0:
        bucket.pop(item_name, None)  # 0になったら消す方式
    else:
        bucket[item_name] = nxt
    return True


# 判定関数
def needs_target_item(item_name: str) -> bool:
    return canon(item_name) in FIELD_ITEM_TARGET_REQUIRED


# メニュー「アイテム」
def open_item_pygame(
    screen: pygame.Surface,
    font: pygame.font.Font,
    party,
    *,
    save_dict: Optional[dict],
    items_by_name: dict[str, dict],
    use_field_item_fn,  # make_use_field_item_fn(...) の戻り値
    portrait_cache: PortraitCache,
    status_icon_cache: StatusIconCache,
    ui_se: dict[str, pygame.mixer.Sound],
):
    clock = pygame.time.Clock()

    member_idx = 0
    mode = "item"  # "item" | "target"
    item_sel = 0
    target_sel = 0
    target_cands = []  # ★追加

    line_h = font.get_linesize() + 10

    def blit_line(text, x, y, color=WHITE):
        surf = font.render(text, True, color)
        screen.blit(surf, (x, y))

    # --- 対象が必要なアイテム ---
    def needs_target(item_name: str) -> bool:
        return canon(item_name) in FIELD_ITEM_TARGET_REQUIRED

    # --- 対象候補 ---
    def target_candidates(item_name: str):
        sn = canon(item_name)
        is_revive = sn == "phoenix down"
        cand = []
        for i, ch in enumerate(party[:4]):
            hp = int(ch.hp)
            if is_revive:
                if hp <= 0:
                    cand.append(i)
            else:
                if hp > 0:
                    cand.append(i)
        return cand if cand else list(range(min(4, len(party))))

    while True:
        # -------- data build --------
        actor = party[member_idx]

        # [(item_name, item_type, count), ...]
        items = iter_field_inventory(save_dict)

        item_sel = min(item_sel, max(0, len(items) - 1)) if items else 0

        selected_item = items[item_sel] if items else None
        # (name, item_type, count)

        # -------- input --------
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                raise SystemExit
            if ev.type != pygame.KEYDOWN:
                continue

            if ev.key == pygame.K_BACKSPACE:
                if mode == "target":
                    mode = "item"
                    target_cands = []  # ★追加
                else:
                    return
                continue

            if ev.key == pygame.K_UP:
                if mode == "item":
                    item_sel = max(0, item_sel - 1)
                    target_cands = []  # ★保険
                elif mode == "target":
                    if target_cands:
                        target_sel = (target_sel - 1) % len(target_cands)
                continue

            if ev.key == pygame.K_DOWN:
                if mode == "item":
                    item_sel += 1
                    target_cands = []  # ★保険
                elif mode == "target":
                    if target_cands:
                        target_sel = (target_sel + 1) % len(target_cands)
                continue

            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                if not selected_item:
                    continue

                name, item_type, count = selected_item

                if mode == "item":
                    if needs_target(name):
                        mode = "target"
                        target_cands = target_candidates(name)  # ★ここ
                        target_sel = 0
                        continue
                    else:
                        # 対象なしで使用
                        use_field_item_fn(
                            member_idx,
                            name,
                            None,
                            item_type,
                        )
                        continue

                elif mode == "target":
                    tgt_idx = target_cands[target_sel]
                    ch = party[tgt_idx]

                    if not can_affect(name, ch):
                        ui_se["invalid"].play()  # ★ブブー
                        # 効果なし → 何もしない（SE鳴らすならここ）
                        continue

                    use_field_item_fn(
                        member_idx,
                        name,
                        tgt_idx,
                        item_type,
                    )
                    mode = "item"
                    target_cands = []
                    continue

        # -------- draw --------
        screen.fill((0, 0, 0))
        w, h = screen.get_size()
        margin = 24

        # タイトル
        page_label = "ITEM"
        pl = font.render(page_label, True, GRAY)
        screen.blit(pl, (screen.get_width() // 2 - pl.get_width() // 2, margin))

        # ========== レイアウト（固定） ==========
        left_w = int(w * 0.6)
        right_w = w - left_w - margin * 3
        left_rect = pygame.Rect(
            margin,
            pl.get_height() + margin * 2,
            left_w,
            h - pl.get_height() * 2 - margin * 3,
        )
        right_rect = pygame.Rect(
            left_rect.right + margin,
            pl.get_height() + margin * 2,
            right_w,
            h - pl.get_height() * 2 - margin * 3,
        )
        draw_window(screen, left_rect)
        draw_window(screen, right_rect)

        x_list = left_rect.x + 48
        y0 = left_rect.y + 70
        cursor = font.render("▶", True, WHITE)

        # --- アイテム一覧 ---
        y = y0
        for i, (name, item_type, count) in enumerate(items[:10]):
            if mode == "item" and i == item_sel:
                screen.blit(cursor, (x_list - 24, y))

            color = WHITE
            if count <= 0:
                color = GRAY

            blit_line(f"{name}", x_list, y, color)
            blit_line(f"x{count}", x_list + 200, y, color)
            y += line_h

        # --- 右ウィンドウ ---
        if mode == "target" and selected_item is not None:
            draw_party_ministatus(
                screen,
                right_rect,
                party,
                font,
                portrait_cache,
                status_icon_cache,
                selected_idx=target_cands[target_sel] if target_cands else None,
                cursor=cursor,
                item_name=selected_item[0],  # ★ここ
            )
        else:
            draw_party_ministatus(
                screen,
                right_rect,
                party,
                font,
                portrait_cache,
                status_icon_cache,
            )

            # ★アイテム説明（itemモードのみ）
            if selected_item:
                draw_item_description(
                    screen,
                    right_rect,
                    font,
                    item_name=selected_item[0],
                    items_by_name=items_by_name,
                )

        hint = font.render(
            "↑↓: Select  Enter: OK  BS: Back",
            True,
            GRAY,
        )
        screen.blit(hint, (w // 2 - hint.get_width() // 2, h - 40))

        pygame.display.flip()
        clock.tick(60)


# ミニステータス表示
def draw_party_ministatus(
    screen,
    rect,
    party,
    font,
    portrait_cache,
    status_icon_cache,
    *,
    selected_idx=None,
    cursor=None,
    item_name=None,
    spell_name=None,
):
    """
    パーティのミニステータス表示（共通UI部品）

    - selected_idx : 対象選択中のキャラ index
    - item_name    : アイテム対象選択時（効果判定に使用）
    - spell_name   : 魔法対象選択時（効果判定に使用）

    UIは「効果があるかどうか」だけを見て描画する。
    ロジック判断は can_affect / field_spell_will_affect 側の責務。
    """
    padding = 16
    row_h = 80

    x0 = rect.x + padding
    y = rect.y + padding

    for i, ch in enumerate(party[:4]):
        # --- 効果判定（UIは結果のみ利用） ---
        effective = True
        if item_name is not None:
            effective = can_affect(item_name, ch)
        elif spell_name is not None:
            effective = field_spell_will_affect(spell_name, ch)

        text_color = WHITE if effective else GRAY

        # --- カーソル ---
        if selected_idx == i and cursor:
            screen.blit(cursor, (x0 - 24, y + 24))

        # --- ポートレート ---
        face_rect = pygame.Rect(x0, y, 48, 48)
        key = getattr(ch, "portrait_key", None)

        if key:
            face = portrait_cache.get(key)
            img = pygame.transform.scale(face, face_rect.size)

            if not effective:
                img = img.copy()
                img.fill((0, 0, 0, 120), special_flags=pygame.BLEND_RGBA_SUB)

            screen.blit(img, face_rect)
        else:
            pygame.draw.rect(screen, (60, 60, 60), face_rect)

        tx = x0 + 56
        ty = y

        # --- 上段：名前 ---
        screen.blit(
            font.render(ch.name, True, text_color),
            (tx, ty),
        )

        # --- ステータス異常アイコン ---
        draw_status_icons(
            screen,
            ch,
            status_icon_cache,
            x=tx + 100,
            y=ty + 6,
        )

        # --- 下段：HP ---
        hp_text = f"{int(ch.hp)}/{int(ch.max_hp)}"
        screen.blit(
            font.render(hp_text, True, text_color),
            (tx, ty + 28),
        )

        y += row_h


# アイテム説明文表示
def draw_item_description(
    screen,
    rect,
    font,
    *,
    item_name: str,
    items_by_name: dict,
):
    padding = 16
    line_h = font.get_linesize() + 6

    item = items_by_name.get(item_name)
    if not item:
        return

    spell_info = item.get("SpellInfo", {})
    effect = spell_info.get("Effect")
    if not effect:
        return

    # 回復量計算
    base = spell_info.get("BasePower")
    mult = spell_info.get("Multiplier")
    heal_amount = None
    if base is not None and mult is not None:
        heal_amount = base * mult

    # 右ウィンドウ下部
    y = rect.bottom - padding - line_h * 3
    x = rect.x + padding

    # 1行目：アイテム名
    screen.blit(font.render(item_name, True, WHITE), (x, y))
    y += line_h

    # 2行目：効果説明
    screen.blit(font.render(effect, True, WHITE), (x, y))
    y += line_h

    # 3行目：数値（ある場合のみ）
    if heal_amount is not None:
        screen.blit(
            font.render(f"+{heal_amount} HP", True, WHITE),
            (x, y),
        )


def draw_magic_description(
    screen,
    rect,
    font,
    *,
    spell_name: str | None,
    spells_by_name: dict[str, dict],
):
    """
    右ペイン下部に魔法の効果説明を表示する
    """
    if not spell_name:
        return

    # 小文字正規化で引く（open_magic_pygame と同じ思想）
    key = canon(spell_name)
    spell = None
    for k, v in spells_by_name.items():
        if canon(k) == key:
            spell = v
            break

    if not spell:
        return

    padding = 16
    x = rect.x + padding
    y = rect.bottom - 80  # 下寄せ（高さはお好みで）

    effect = str(spell.get("Effect", ""))
    base = spell.get("BasePower")

    lines = []

    if effect:
        lines.append(effect)

    # FF3風：数値は「威力」表記にする
    if base is not None:
        lines.append(f"Power {int(base)}")

    for i, line in enumerate(lines):
        surf = font.render(line, True, WHITE)
        screen.blit(surf, (x, y + i * (font.get_linesize() + 4)))
