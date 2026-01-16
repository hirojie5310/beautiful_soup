from __future__ import annotations
import pygame
from dataclasses import dataclass
from typing import List, Callable, Optional, Dict, Any
from copy import deepcopy
from pathlib import Path
import time

from combat.models import PartyMemberRuntime, EquipmentSet, FinalCharacterStats
from combat.char_build import (
    compute_character_final_stats,
    build_name_index,
    weapon_stats,
    armor_stats,
    strip_illegal_equipment_for_job,
    apply_job_equipment_restrictions,
)
from combat.data_loader import (
    save_savedata,
    apply_party_equipment_to_save,
    apply_party_job_to_save,
)


@dataclass
class GameState:
    party: List[PartyMemberRuntime]
    # inventory や装備候補DBなどは必要になったら追加


def open_menu_pygame(
    screen,
    font,
    party,
    *,
    save_dict: Optional[Dict[str, Any]] = None,
    save_path: Optional[Path] = None,
    level_table=None,
    weapons=None,
    armors=None,
    jobs_by_name=None,  # ★追加
    recalc_stats_fn=None,
):
    clock = pygame.time.Clock()
    items = ["そうび", "ステータス", "ジョブ", "セーブ", "もどる"]
    idx = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return  # メニューを閉じてMap選択へ戻る

                if event.key == pygame.K_UP:
                    idx = (idx - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    idx = (idx + 1) % len(items)

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                    choice = items[idx]
                    if choice == "そうび":
                        if weapons is None or armors is None or recalc_stats_fn is None:
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
                        )
                    elif choice == "ステータス":
                        open_status_pygame(
                            screen,
                            font,
                            party,
                            level_table=level_table,
                            weapons=weapons,
                        )
                    elif choice == "ジョブ":
                        if jobs_by_name is None or recalc_stats_fn is None:
                            show_toast_message(
                                screen, font, "Job unavailable", duration=1.0
                            )
                            continue
                        if weapons is None or armors is None or recalc_stats_fn is None:
                            show_toast_message(
                                screen, font, "Equip unavailable", duration=1.0
                            )
                            continue
                        open_job_pygame(
                            screen,
                            font,
                            party,
                            jobs_by_name=jobs_by_name,
                            weapons_by_name=weapons,
                            armors_by_name=armors,
                            recalc_stats_fn=recalc_stats_fn,
                            save_dict=save_dict,  # ★追加（OptionalでもOK）
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

        # ---- draw ----
        screen.fill((0, 0, 0))
        title = font.render("Menu", True, (255, 255, 255))
        screen.blit(title, (screen.get_width() // 2 - title.get_width() // 2, 40))

        y = 120
        for i, t in enumerate(items):
            prefix = "▶ " if i == idx else "  "
            color = (255, 255, 255) if i == idx else (140, 140, 140)
            row = font.render(prefix + t, True, color)
            screen.blit(row, (screen.get_width() // 2 - 120, y))
            y += font.get_linesize() + 10

        # ---------- ヘルプ（画面下） ----------
        help_text = "↑↓: Select   Enter: OK   Esc: Back"
        help_surf = font.render(help_text, True, (160, 160, 160))
        screen.blit(
            help_surf,
            (16, screen.get_height() - help_surf.get_height() - 12),
        )

        pygame.display.flip()
        clock.tick(60)


def open_equip_pygame(
    screen,
    font,
    party,
    *,
    weapons_by_name,
    armors_by_name,
    save_dict: dict | None = None,  # ★追加
):
    clock = pygame.time.Clock()
    actor_idx = 0
    slots = ["main_hand", "off_hand", "head", "body", "arms"]
    slot_idx = 0
    line_h = font.get_linesize() + 8

    def recalc_stats(actor):
        eq = actor.equipment or EquipmentSet()
        return compute_character_final_stats(
            base=actor.base,
            eq=eq,
            weapons_by_name=weapons_by_name,
            armors_by_name=armors_by_name,
            job_name=actor.job.name,
        )

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

                if event.key == pygame.K_LEFT:
                    actor_idx = (actor_idx - 1) % len(party)
                elif event.key == pygame.K_RIGHT:
                    actor_idx = (actor_idx + 1) % len(party)
                elif event.key == pygame.K_UP:
                    slot_idx = (slot_idx - 1) % len(slots)
                elif event.key == pygame.K_DOWN:
                    slot_idx = (slot_idx + 1) % len(slots)

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                    actor = party[actor_idx]
                    slot = slots[slot_idx]
                    open_equip_candidate_pygame(
                        screen,
                        font,
                        actor,
                        slot,
                        weapons_by_name=weapons_by_name,
                        armors_by_name=armors_by_name,
                        recalc_stats_fn=lambda a=actor: recalc_stats(a),
                        save_dict=save_dict,  # ★追加：ここで渡す
                    )
                    continue

        actor = party[actor_idx]
        eq = actor.equipment or EquipmentSet()

        screen.fill((0, 0, 0))
        title = font.render(actor.name, True, (255, 255, 255))
        screen.blit(title, (screen.get_width() // 2 - title.get_width() // 2, 50))

        y = 160
        x = screen.get_width() // 2 - 220

        def get_slot_value(slot_name: str) -> str:
            return getattr(eq, slot_name) or "なし"

        for i, s in enumerate(slots):
            is_sel = i == slot_idx
            prefix = "▶ " if is_sel else "  "
            color = (255, 255, 255) if is_sel else (140, 140, 140)
            row = font.render(f"{prefix}{s}: {get_slot_value(s)}", True, color)
            screen.blit(row, (x, y + i * line_h))

        hint = font.render(
            "← →: Switch / ↑↓: Select / Enter: Choose / ESC: Back",
            True,
            (180, 180, 180),
        )
        screen.blit(
            hint,
            (screen.get_width() // 2 - hint.get_width() // 2, screen.get_height() - 60),
        )

        pygame.display.flip()
        clock.tick(60)


def open_status_pygame(screen, font, party, *, level_table, weapons):
    clock = pygame.time.Clock()
    idx = 0
    page = 0  # 0: status, 1: equipment

    line_h = font.get_linesize() + 6
    margin_top = 90

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

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                if event.key == pygame.K_LEFT:
                    idx = (idx - 1) % len(party)
                elif event.key == pygame.K_RIGHT:
                    idx = (idx + 1) % len(party)
                elif event.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
                    page = 1 - page

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

        title = font.render(f"{actor.name}   {actor.job.name}", True, (255, 255, 255))
        screen.blit(title, (screen.get_width() // 2 - title.get_width() // 2, 30))

        page_label = "STATUS" if page == 0 else "EQUIPMENT"
        pl = font.render(page_label, True, (160, 160, 160))
        screen.blit(pl, (screen.get_width() // 2 - pl.get_width() // 2, 60))

        xL = 80
        xR = screen.get_width() // 2 + 80

        if page == 0:
            # -------- Page 0: ステータス --------
            y = margin_top
            blit_line(f"LEVEL  {base.level}", xL, y)
            y += line_h
            blit_line(f"HP: {actor.hp}/{actor.max_hp}", xL, y)
            y += line_h
            blit_line(f"MP: {actor.mp}/{actor.max_mp}", xL, y)
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

        else:
            # -------- Page 1: 装備 --------
            y = margin_top
            blit_line("そうび", xL, y, (255, 255, 255))
            y += line_h
            blit_line(f"right_hand: {eq.main_hand or 'なし'}", xL, y)
            y += line_h
            blit_line(f"left_hand : {eq.off_hand  or 'なし'}", xL, y)
            y += line_h
            blit_line(f"head      : {eq.head     or 'なし'}", xL, y)
            y += line_h
            blit_line(f"body      : {eq.body     or 'なし'}", xL, y)
            y += line_h
            blit_line(f"arm       : {eq.arms     or 'なし'}", xL, y)
            y += line_h

        hint = font.render("← →: Switch / TAB: Page / ESC: Back", True, (180, 180, 180))
        screen.blit(
            hint,
            (screen.get_width() // 2 - hint.get_width() // 2, screen.get_height() - 60),
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
    "Dark Knight": "MK",  # JSON内で MK 表記になっています :contentReference[oaicite:2]{index=2}
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
    code = actor_job_code(actor).lower()
    return code in {str(x).lower() for x in allow}


# off_hand で「両手武器」を除外（重要）
def is_two_handed_weapon(w: dict) -> bool:
    return "Two-Handed" in w  # 値は説明文なのでキー存在でOK


def _actor_code_for_equip(actor) -> str:
    raw = _job_code_of_actor(actor)
    if raw in JOB_NAME_TO_CODE:
        return JOB_NAME_TO_CODE[raw]
    # slug が "wa" みたいなケースも吸収したいので、大小無視で合わせる
    inv = {k.lower(): v for k, v in JOB_NAME_TO_CODE.items()}
    if raw.lower() in inv:
        return inv[raw.lower()]
    return raw  # すでに "Wa" 等が入っているならそのまま


def _armor_allows(actor, armor_dict: dict) -> bool:
    codes = armor_dict.get("EquippedBy") or []
    if not codes:
        return True
    actor_code = _actor_code_for_equip(actor)
    return actor_code.lower() in {str(c).lower() for c in codes}


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


# 候補一覧UI
def open_equip_candidate_pygame(
    screen,
    font,
    actor,
    slot,
    *,
    weapons_by_name,
    armors_by_name,
    recalc_stats_fn,
    save_dict: dict | None = None,  # ★追加
):
    # 現在の装備ステータス（比較用）
    base_stats = actor.stats

    clock = pygame.time.Clock()
    candidates = build_equip_candidates(
        actor,
        slot,
        weapons_by_name=weapons_by_name,
        armors_by_name=armors_by_name,
    )

    idx = 0
    top = 0
    line_h = font.get_linesize() + 6
    header_h = line_h * 4
    max_rows = max(5, (screen.get_height() - header_h - 70) // line_h)

    # 候補一覧の先頭で一回だけ作る
    weapons_norm = build_name_index(weapons_by_name)
    armors_norm = build_name_index(armors_by_name)

    def calc_preview_stats(item_kind, item_name):
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

    def blit_row_with_diffs(
        x: int,
        y: int,
        left_text: str,
        left_color,
        diffs: list[tuple[str, tuple[int, int, int]]],
    ):
        left_surf = font.render(left_text, True, left_color)
        screen.blit(left_surf, (x, y))

        dx = x + left_surf.get_width() + 12
        for text, col in diffs:
            if not text:
                continue
            surf = font.render(text, True, col)
            screen.blit(surf, (dx, y))
            dx += surf.get_width() + 10

    # slot に応じて差分対象を切り替える
    def primary_diff(now: FinalCharacterStats, new: FinalCharacterStats, slot: str):
        """
        slot に応じて、表示すべき主要ステータスの差分を返す
        戻り値: (diff_text, diff_color)
        """
        # 武器系：攻撃力を主に見る（平均表示にしたいならここを差し替え）
        if slot in ("main_hand", "off_hand"):
            return diff_text_and_color(now.main_power, new.main_power)

        # 防具系：防御力を見る
        if slot in ("head", "body", "arms"):
            return diff_text_and_color(now.defense, new.defense)

        # 保険
        return "", (180, 180, 180)

    cur_eq = actor.equipment or EquipmentSet()

    def is_currently_equipped(kind, name):
        if kind == "none":
            return getattr(cur_eq, slot) is None
        return getattr(cur_eq, slot) == name

    def sync_equipment_to_save(a):
        if save_dict is None:
            return
        for sp in save_dict.get("party", []):
            if sp.get("name") != a.name:
                continue
            eq = a.equipment
            sp["equipment"] = {
                "main_hand": getattr(eq, "main_hand", None) if eq else None,
                "off_hand": getattr(eq, "off_hand", None) if eq else None,
                "head": getattr(eq, "head", None) if eq else None,
                "body": getattr(eq, "body", None) if eq else None,
                "arms": getattr(eq, "arms", None) if eq else None,
            }
            return

    def clamp():
        nonlocal top
        if idx < top:
            top = idx
        elif idx >= top + max_rows:
            top = idx - max_rows + 1
        top = max(0, min(top, max(0, len(candidates) - max_rows)))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return

                if event.key == pygame.K_UP:
                    idx = (idx - 1) % len(candidates)
                    clamp()
                elif event.key == pygame.K_DOWN:
                    idx = (idx + 1) % len(candidates)
                    clamp()

                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_z):
                    kind, name, _ = candidates[idx]

                    if actor.equipment is None:
                        actor.equipment = EquipmentSet()

                    if kind == "none":
                        setattr(actor.equipment, slot, None)
                    else:
                        setattr(actor.equipment, slot, name)

                    # ★ロード時と同じ制限を即適用
                    new_eq, eq_logs = apply_job_equipment_restrictions(
                        actor.equipment, actor.job
                    )
                    actor.equipment = new_eq
                    if eq_logs:
                        show_toast_message(screen, font, eq_logs[0], duration=1.0)

                    actor.stats = recalc_stats_fn(actor)  # ★再計算
                    sync_equipment_to_save(actor)  # ★追加：save に即反映
                    return

            if event.type == pygame.MOUSEWHEEL:
                idx = (idx - event.y) % len(candidates)
                clamp()

        # ---- draw ----
        screen.fill((0, 0, 0))

        title = font.render(f"{actor.name}  /  {slot}", True, (255, 255, 255))
        screen.blit(title, (16, 16))

        cur = actor.equipment or EquipmentSet()
        now_name = getattr(cur, slot) or "なし"
        curtxt = font.render(f"Current: {now_name}", True, (180, 180, 180))
        screen.blit(curtxt, (16, 16 + line_h))

        hint = font.render(
            "↑↓/Wheel: Select  Enter: Equip  ESC: Back", True, (160, 160, 160)
        )
        screen.blit(hint, (16, 16 + line_h * 2))

        y0 = 16 + header_h
        visible = candidates[top : top + max_rows]
        for i, (kind, name, data) in enumerate(visible):
            real_i = top + i
            is_sel = real_i == idx
            prefix = "▶ " if is_sel else "  "
            color = (255, 255, 255) if is_sel else (140, 140, 140)

            if kind == "none" or data is None:
                equipped = is_currently_equipped(kind, name)
                if is_sel:
                    left_color = (255, 255, 255)
                elif equipped:
                    left_color = (120, 180, 255)  # 装備中（青）
                else:
                    left_color = (140, 140, 140)
                mark = " [E]" if equipped else ""
                left_text = f"{prefix}{name}{mark}"

                diffs = []
                if is_sel:
                    preview = calc_preview_stats("none", None)
                    t, c = diff_text_and_color(base_stats.defense, preview.defense)
                    if t:
                        diffs.append((f"DEF{t}", c))

                blit_row_with_diffs(16, y0 + i * line_h, left_text, left_color, diffs)
                continue

            if kind == "weapon":
                atk = int(data.get("BasePower", 0) or 0)
                acc = int(round((data.get("BaseAccuracy", 0) or 0) * 100))

                equipped = is_currently_equipped(kind, name)
                if is_sel:
                    left_color = (255, 255, 255)
                elif equipped:
                    left_color = (120, 180, 255)  # 装備中（青）
                else:
                    left_color = (140, 140, 140)
                mark = " [E]" if equipped else ""
                left_text = f"{prefix}{name}{mark}  ATK:{atk}  ACC:{acc}%"

                diffs = []

                if is_sel:
                    preview = calc_preview_stats(kind, name)

                    # 攻撃差分（従来通り）
                    t1, c1 = diff_text_and_color(
                        base_stats.main_power, preview.main_power
                    )
                    if t1:
                        diffs.append((f"ATK{t1}", c1))

                    # ★off_hand のときは防御差分も出す（盾を持てなくなる等の影響が見える）
                    if slot == "off_hand":
                        t2, c2 = diff_text_and_color(
                            base_stats.defense, preview.defense
                        )
                        if t2:
                            diffs.append((f"DEF{t2}", c2))

                blit_row_with_diffs(
                    16,
                    y0 + i * line_h,
                    left_text,
                    left_color,
                    diffs,
                )
                continue

            if kind == "armor":
                d = int(data.get("Defense", 0) or 0)
                eva = int(round((data.get("Evasion", 0) or 0) * 100))
                mdef = int(data.get("BaseMagicDefense", 0) or 0)

                equipped = is_currently_equipped(kind, name)
                if is_sel:
                    left_color = (255, 255, 255)
                elif equipped:
                    left_color = (120, 180, 255)  # 装備中（青）
                else:
                    left_color = (140, 140, 140)
                mark = " [E]" if equipped else ""
                left_text = f"{prefix}{name}{mark}  DEF:{d}  EVA:{eva}%  MDEF:{mdef}"

                diffs = []
                if is_sel:
                    preview = calc_preview_stats(kind, name)
                    t1, c1 = diff_text_and_color(base_stats.defense, preview.defense)
                    if t1:
                        diffs.append((f"DEF{t1}", c1))

                    t2, c2 = diff_text_and_color(
                        base_stats.evasion_percent, preview.evasion_percent
                    )
                    if t2:
                        diffs.append((f"EVA{t2}", c2))

                    t3, c3 = diff_text_and_color(
                        base_stats.magic_defense, preview.magic_defense
                    )
                    if t3:
                        diffs.append((f"MDEF{t3}", c3))

                blit_row_with_diffs(16, y0 + i * line_h, left_text, left_color, diffs)
                continue

            else:
                text = f"{prefix}{name}"

            row = font.render(text, True, color)
            screen.blit(row, (16, y0 + i * line_h))

        pygame.display.flip()
        clock.tick(60)


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
    jobs_by_name: dict,
    weapons_by_name: dict,
    armors_by_name: dict,
    recalc_stats_fn,
    save_dict: dict | None = None,
):
    clock = pygame.time.Clock()
    actor_idx = 0

    job_names = sorted(list(jobs_by_name.keys()))
    if not job_names:
        return

    sel_idx = 0
    top = 0
    line_h = font.get_linesize() + 6
    header_h = line_h * 4
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
                if event.key == pygame.K_ESCAPE:
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
                        )

        # ---- draw ----
        screen.fill((0, 0, 0))
        a = actor()
        sp = find_save_entry_for_actor(a)

        title = font.render(f"Job  /  {a.name}", True, (255, 255, 255))
        screen.blit(title, (16, 16))

        cur = font.render(
            f"Current: {a.job.name}  (JobLv {a.base.job_level}  SP {a.base.job_skill_point})",
            True,
            (180, 180, 180),
        )
        screen.blit(cur, (16, 16 + line_h))

        hint = font.render(
            "←→: Character  ↑↓: Job  Enter: Set  ESC: Back", True, (160, 160, 160)
        )
        screen.blit(hint, (16, 16 + line_h * 2))

        # ---------- list ----------
        y0 = 16 + header_h
        visible = job_names[top : top + max_rows]
        for i, jn in enumerate(visible):
            real_i = top + i
            is_sel = real_i == sel_idx
            prefix = "▶ " if is_sel else "  "
            color = (255, 255, 255) if is_sel else (140, 140, 140)

            # ★表示：Bard (Lv12)
            saved_lv = get_saved_job_lv(sp, jn)
            if saved_lv is not None:
                label = f"{jn} (Lv{saved_lv})"
            else:
                label = jn

            # ★NEW マーク
            if is_new_job(sp, jn):
                label += " NEW"

            # ★現在ジョブマーク
            if jn == a.job.name:
                label += " [E]"

            row = font.render(prefix + label, True, color)
            screen.blit(row, (16, y0 + i * line_h))

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

            except Exception:
                # プレビュー計算で例外が出ても画面は落とさない
                pass

        pygame.display.flip()
        clock.tick(60)
