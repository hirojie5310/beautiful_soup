from __future__ import annotations

import random
import sys
from pathlib import Path


# `python combat/main.py` のように直接実行した場合でも
# プロジェクトルートを import 探索パスに追加して
# `from combat.xxx import ...` を解決できるようにする。
if __package__ is None or __package__ == "":
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from combat.debug_utils import (
    check_battle_end_before_round,
    print_end_reason,
    print_enemies_status_compact,
    print_inventory,
    print_logs,
    print_party_debug_summary,
    print_planned_actions,
    print_round_header_and_state,
)
from combat.input_ui import ask_actions_for_party
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session, execute_round


def main():
    state = init_runtime_state()
    session = build_battle_session(
        state=state,
        enemy_names=["Flyer", "Unei'S Clone"],
    )

    print_party_debug_summary(session.party_members, session.party_magic_lists)
    print_inventory(session.state.save, show_zero=True)
    print_enemies_status_compact(session.enemies)

    # ==================================================
    # ３．戦闘ターン
    # ==================================================
    rng = random.Random()
    max_turns = 50

    # simulate_one_round_multi_party を1ターンずつ呼び出す場合
    for turn in range(1, max_turns + 1):
        party_members = session.party_members
        enemies = session.enemies

        print_round_header_and_state(turn, party_members, enemies)

        # ラウンド前の終了判定
        pre_end = check_battle_end_before_round(party_members, enemies)  # debug_utils
        if pre_end is not None:
            print_end_reason(pre_end)  # debug_utils
            break

        # ① 行動入力
        planned_actions = ask_actions_for_party(
            party_members=party_members,
            enemies=enemies,
            spells_by_name=session.spells_expanded,
            items_by_name=session.state.items_by_name,
            party_magic_lists=session.party_magic_lists,
            save=session.state.save,
            input_func=input,
            output_func=print,
        )

        # デバッグ表示（必要な時だけ呼ぶ運用でもOK）
        print_planned_actions(party_members, planned_actions)  # debug_utils

        # ② イニシアティブ計算＆行動解決
        result = execute_round(
            session=session,
            planned_actions=planned_actions,
            rng=rng,
        )

        print_logs(result.logs)

        # ラウンド後の終了判定
        if result.round_result.end_reason != "continue":
            print_end_reason(result.round_result.end_reason)
            break


if __name__ == "__main__":
    main()
