# combat/battle_runner.py
from combat.models import PartyMemberRuntime
from system.exp_system import LevelTable

from combat.progression import apply_battle_exp_and_refresh


def finish_battle(
    party_members: list[PartyMemberRuntime],
    total_exp_reward: int,
    level_table: LevelTable,
    weapons: dict,
    armors: dict,
) -> list[tuple[str, int, int]]:
    """戻り値: レベルアップしたメンバーの (name, old, new) 一覧"""
    levelups: list[tuple[str, int, int]] = []

    # 例：生存者のみ配るならフィルタ
    for m in party_members:
        if m.state.hp <= 0:
            continue

        old_lv, new_lv = apply_battle_exp_and_refresh(
            m, total_exp_reward, level_table, weapons, armors
        )
        if new_lv != old_lv:
            levelups.append((m.name, old_lv, new_lv))

    return levelups
