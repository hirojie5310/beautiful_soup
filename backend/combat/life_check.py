# ============================================================
# life_check: 生存確認＋ターゲット選択

# is_out_of_battle	HPが0以下又はStatus.KO/Status.PETRIFYのときに戦闘離脱扱い（True）とする判定ヘルパー
# all_enemies_defeated	全滅判定ヘルパ
# all_chars_defeated
# any_char_alive	パーティにis_out_of_battleではないメンバーが1人でもいればTrueを返す味方側の生存判定ユーティリティ
# any_enemy_alive	敵にis_out_of_battleではない敵が1体でもいればTrueを返す、敵側の生存判定ユーティリティ。
# first_alive_enemy_index	is_out_of_battleではない最初の敵のインデックス（0始まり）を返す
# first_alive_char_index	is_out_of_battleではない最初の味方のインデックス（0始まり）を返す
# choose_target_index_from_enemies	生存している敵だけを列挙し、ユーザーに番号入力させ、選択された敵のインデックス（0始まり）を返す
# choose_target_index_from_allies	生存している味方だけを列挙し、ユーザーに番号入力させて味方ターゲットのインデックス（0始まり）を返す
# random_alive_char_index	生存している味方キャラのインデックスをランダムに選ぶ
# is_out_of_battle	HPが0以下、またはKO/Petrify状態なら戦闘不能とみなす
# is_actor_alive	戦闘離脱状態かどうかを判定
# ============================================================

import random
from typing import Optional, List

from combat.enums import Status
from combat.models import BattleActorState, PartyMemberRuntime, EnemyRuntime
from combat.state_view import format_state_line


# 全滅判定ヘルパ
def all_enemies_defeated(enemies) -> bool:
    return all(em.state.hp <= 0 for em in enemies)


def all_chars_defeated(party_members) -> bool:
    return all(pm.state.hp <= 0 for pm in party_members)


# 生存判定ヘルパ
def any_char_alive(party_members: List[PartyMemberRuntime]) -> bool:
    return any(not is_out_of_battle(pm.state) for pm in party_members)


def any_enemy_alive(enemies: List[EnemyRuntime]) -> bool:
    return any(not is_out_of_battle(em.state) for em in enemies)


def first_alive_enemy_index(enemies: List[EnemyRuntime]) -> Optional[int]:
    for i, em in enumerate(enemies):
        if not is_out_of_battle(em.state):
            return i
    return None


def first_alive_char_index(party_members: List[PartyMemberRuntime]) -> Optional[int]:
    for i, pm in enumerate(party_members):
        if not is_out_of_battle(pm.state):
            return i
    return None


# ターゲット選択ヘルパー
def choose_target_index_from_enemies(
    enemies: List[EnemyRuntime],
) -> Optional[int]:
    alive_indices = [
        i for i, em in enumerate(enemies) if not is_out_of_battle(em.state)
    ]
    if not alive_indices:
        print("ターゲットにできる敵がいません。")
        return None

    print("攻撃対象の敵を選んでください。")
    for i in alive_indices:
        em = enemies[i]
        print(f"  {i+1}: {format_state_line(em.name, em.state)}")

    while True:
        s = input(f"番号を入力してください (1-{len(enemies)}): ").strip()
        if s.isdigit():
            n = int(s) - 1
            if n in alive_indices:
                return n
        print("入力が正しくありません。")


def choose_target_index_from_allies(
    party_members: List[PartyMemberRuntime],
    self_index: int,
) -> Optional[int]:
    alive_indices = [
        i for i, pm in enumerate(party_members) if not is_out_of_battle(pm.state)
    ]
    if not alive_indices:
        print("ターゲットにできる味方がいません。")
        return None

    print("対象の味方を選んでください。")
    for i in alive_indices:
        pm = party_members[i]
        mark = "(自分)" if i == self_index else ""
        print(f"  {i+1}: {format_state_line(pm.name, pm.state)} {mark}")

    while True:
        s = input(f"番号を入力してください (1-{len(party_members)}): ").strip()
        if s.isdigit():
            n = int(s) - 1
            if n in alive_indices:
                return n
        print("入力が正しくありません。")


# ランダムターゲット用ヘルパー
def random_alive_char_index(
    party_members: List[PartyMemberRuntime],
    rng: random.Random,
) -> Optional[int]:
    indices = [
        i for i, pm in enumerate(party_members) if not is_out_of_battle(pm.state)
    ]
    if not indices:
        return None
    return rng.choice(indices)


# 3) ターン開始時点で戦闘不能なら即終了 =============================================================
# ============================================================
# 戦闘不能判定ユーティリティ
# ============================================================


def is_out_of_battle(state: BattleActorState) -> bool:
    """
    HP が 0 以下、または KO / Petrify 状態なら戦闘不能とみなす。
    """
    return state.hp <= 0 or state.has(Status.KO) or state.has(Status.PETRIFY)


def is_actor_alive(state: BattleActorState) -> bool:
    return not is_out_of_battle(state)
