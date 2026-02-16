from __future__ import annotations

import copy
import random
from pathlib import Path

from combat.char_build import build_party_members_from_save
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
from combat.enemy_selection import (
    LocationMonsters,
    build_location_index,
    calc_party_avg_level,
    danger_label,
    pick_enemy_names,
)
from combat.input_ui import ask_actions_for_party
from combat.progression import apply_victory_rewards
from combat.runtime_state import init_runtime_state
from combat.save_prompt import prompt_save_progress_and_write, restore_backup_by_choice
from combat.usecases import build_battle_session, execute_round
from system.exp_system import LevelTable


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
    state = init_runtime_state()
    save_before = copy.deepcopy(state.save)

    # 場所選択のため、先にパーティ平均レベルを算出
    pre_level_table = LevelTable("assets/data/level_exp.csv")
    pre_party_members = build_party_members_from_save(
        save=state.save,
        weapons=state.weapons,
        armors=state.armors,
        jobs_by_name=state.jobs_by_name,
        level_table=pre_level_table,
    )

    party_avg_lv = calc_party_avg_level(pre_party_members)
    locations = build_location_index(state.monsters)
    selected = choose_location_console(locations, party_avg_lv=party_avg_lv)
    enemy_names = pick_enemy_names(selected, state.monsters, k_min=2, k_max=6)

    # UI非依存ユースケース境界を通して戦闘セッションを構築
    session = build_battle_session(
        state=state,
        enemy_names=enemy_names,
    )

    print_party_debug_summary(session.party_members, session.party_magic_lists)
    print_inventory(session.state.save, show_zero=True)
    print_enemies_status_compact(session.enemies)

    rng = random.Random()
    max_turns = 50
    end_reason = None

    for turn in range(1, max_turns + 1):
        party_members = session.party_members
        enemies = session.enemies

        print_round_header_and_state(turn, party_members, enemies)

        pre_end = check_battle_end_before_round(party_members, enemies)
        if pre_end is not None:
            end_reason = pre_end
            print_end_reason(pre_end)
            break

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

        print_planned_actions(party_members, planned_actions)

        result = execute_round(
            session=session,
            planned_actions=planned_actions,
            rng=rng,
        )
        print_logs(result.logs)

        if result.round_result.end_reason != "continue":
            end_reason = result.round_result.end_reason
            print_end_reason(result.round_result.end_reason)
            break

    if end_reason == "enemy_defeated":
        apply_victory_rewards(
            party_members=session.party_members,
            enemies=session.enemies,
            state=session.state,
            level_table=session.level_table,
        )

        save_path = Path("assets/data/ffiii_savedata.json")
        prompt_save_progress_and_write(
            before_save=save_before,
            after_save=session.state.save,
            save_path=Path(save_path),
        )
        restore_backup_by_choice(save_path)


if __name__ == "__main__":
    main()
