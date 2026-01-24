from __future__ import annotations

import random
import copy
from pathlib import Path

from combat.runtime_state import *
from combat.magic_menu import *
from combat.char_build import *
from combat.debug_utils import *
from combat.enemy_build import *
from combat.input_ui import *
from combat.battle_sim import *
from combat.enemy_selection import (
    LocationMonsters,
    build_location_index,
    pick_enemy_names,
    danger_label,
    calc_party_avg_level,
)
from combat.progression import apply_victory_rewards
from combat.save_prompt import prompt_save_progress_and_write, restore_backup_by_choice


def choose_location_console(
    entries: list[LocationMonsters], *, party_avg_lv: int
) -> LocationMonsters:
    print("=== 場所を選択してください ===")
    for i, e in enumerate(entries, start=1):
        dg = danger_label(e, party_avg_lv)
        diff = e.avg_level - party_avg_lv

        print(
            f"{i:>3}. {e.location}  "
            f"(monsters: {len(e.monster_names)}) "
            f"(LV: {e.avg_level} / {e.min_level}-{e.max_level}) "
            f"(Δ: {diff:+}) "
            f"(Danger: {dg})"
        )

    while True:
        s = input("番号を入力 > ").strip()
        if s.isdigit():
            idx = int(s)
            if 1 <= idx <= len(entries):
                return entries[idx - 1]
        print(f"1〜{len(entries)} の範囲で数字を入力してください。")


def main():
    # =========================
    # JSON 読み込み
    # =========================
    state = init_runtime_state()  # runtime_state

    # ★戦闘前のsaveを保持（差分確認用）
    save_before = copy.deepcopy(state.save)

    # キャラごとのそのジョブで使える魔法一覧（リスト）
    party_magic_info = build_party_magic_info(state)  # magic_menu
    party_magic_lists = build_party_magic_lists(state)  # magic_menu
    # 召喚魔法の子Spellsを展開した辞書
    spells_expanded = expand_spells_for_summons(state.spells)  # magic_menu

    # ==================================================
    # １．セーブデータ → キャラ最終ステ（パーティ全員）
    # ==================================================
    level_table = LevelTable(
        "assets/data/level_exp.csv"
    )  # パスは実プロジェクトに合わせて
    party_members = build_party_members_from_save(
        save=state.save,
        weapons=state.weapons,
        armors=state.armors,
        jobs_by_name=state.jobs_by_name,
        level_table=level_table,
    )  # char_build

    print("weapons type:", type(state.weapons), "len:", len(state.weapons))
    if isinstance(state.weapons, dict):
        k = next(iter(state.weapons.keys()))
        print(
            "weapons sample key:",
            repr(k),
            "value keys:",
            list(state.weapons[k].keys())[:10],
        )
    else:
        print("weapons[0] keys:", list(state.weapons[0].keys())[:10])

    print_party_debug_summary(party_members, party_magic_lists)
    print_inventory(state.save, show_zero=True)  # debug_utils

    # ==================================================
    # ２．敵も複数対応の形に
    # ==================================================
    # enemy_names = ["Flyer", "Unei'S Clone"]
    party_avg_lv = calc_party_avg_level(party_members)
    locations = build_location_index(state.monsters)
    selected = choose_location_console(locations, party_avg_lv=party_avg_lv)
    enemy_names = pick_enemy_names(selected, state.monsters, k_min=2, k_max=6)
    enemies = build_enemies(
        enemy_defs_by_name=state.monsters,
        spells_by_name=state.spells,
        enemy_names=enemy_names,
    )

    print_enemies_status_compact(enemies)  # debug_utils

    # ==================================================
    # ３．戦闘ターン
    # ==================================================
    rng = random.Random()
    max_turns = 50
    end_reason = None

    # simulate_one_round_multi_party を1ターンずつ呼び出す場合
    for turn in range(1, max_turns + 1):
        print_round_header_and_state(turn, party_members, enemies)  # debug_utils

        # ラウンド前の終了判定
        pre_end = check_battle_end_before_round(party_members, enemies)  # debug_utils
        if pre_end is not None:
            end_reason = pre_end
            print_end_reason(pre_end)  # debug_utils
            break

        # ① 行動入力
        planned_actions = ask_actions_for_party(  # input_ui
            party_members=party_members,
            enemies=enemies,
            spells_by_name=spells_expanded,
            items_by_name=state.items_by_name,
            party_magic_lists=party_magic_lists,
            save=state.save,
        )

        # デバッグ表示（必要な時だけ呼ぶ運用でもOK）
        print_planned_actions(party_members, planned_actions)  # debug_utils

        # ② イニシアティブ計算＆行動解決
        logs, round_result, _event = simulate_one_round_multi_party(  # battle_sim
            party_members,
            enemies,
            planned_actions,
            rng=rng,
            save=state.save,
            spells_by_name=spells_expanded,
            items_by_name=state.items_by_name,
            state=state,
        )

        print_logs(logs)  # debug_utils

        # ラウンド後の終了判定
        if round_result.end_reason != "continue":
            end_reason = round_result.end_reason
            print_end_reason(round_result.end_reason)  # debug_utils
            break

    # --- 戦闘終了後の報酬適用（ここで一回だけ） ---
    if end_reason == "enemy_defeated":
        # 勝利処理
        victory = apply_victory_rewards(
            party_members=party_members,
            enemies=enemies,
            state=state,
            level_table=level_table,
        )

        # ★保存確認 → OKなら書き出し
        save_path = Path("assets/data/ffiii_savedata.json")
        prompt_save_progress_and_write(
            before_save=save_before,
            after_save=state.save,
            save_path=Path(save_path),
        )

        # 最新から即復元
        # restore_latest_backup(save_path)

        # 選択式復元
        restore_backup_by_choice(save_path)


if __name__ == "__main__":
    main()
