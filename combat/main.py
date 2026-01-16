from __future__ import annotations

import random

from combat.runtime_state import *
from combat.magic_menu import *
from combat.char_build import *
from combat.debug_utils import *
from combat.enemy_build import *
from combat.input_ui import *
from combat.battle_sim import *


def main():
    # =========================
    # JSON 読み込み
    # =========================
    state = init_runtime_state()  # runtime_state

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

    print_party_debug_summary(party_members, party_magic_lists)
    print_inventory(state.save, show_zero=True)  # debug_utils

    # ==================================================
    # ２．敵も複数対応の形に
    # ==================================================
    enemy_names = ["Flyer", "Unei'S Clone"]
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

    # simulate_one_round_multi_party を1ターンずつ呼び出す場合
    for turn in range(1, max_turns + 1):
        print_round_header_and_state(turn, party_members, enemies)  # debug_utils

        # ラウンド前の終了判定
        pre_end = check_battle_end_before_round(party_members, enemies)  # debug_utils
        if pre_end is not None:
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
            print_end_reason(round_result.end_reason)  # debug_utils
            break


if __name__ == "__main__":
    main()
