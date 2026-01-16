# ============================================================
# start_of_turn: ターン開始

# start_of_turn_for_actor	1アクター分のターン開始時処理（毒など）
# apply_start_of_turn_effects	毒など、ターン開始時に自動発動する効果をまとめる場所
# ============================================================

import random
from typing import Union, Optional, Dict, Any, List

from combat.enums import Status
from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats
from combat.logging import log_damage


# 2) ターン開始処理（毒ダメージ＋開始時バフ/デバフ）==================================================
# 外から呼ぶのは start_of_turn_for_actor
# 中で今の apply_start_of_turn_effects を呼ぶ
def start_of_turn_for_actor(
    actor_name: str,
    stats: Union[FinalCharacterStats, FinalEnemyStats],
    state: BattleActorState,
    logs: List[str],
    rng: random.Random,
    *,
    # 敵だけ max_hp を enemy_json["HP"] から取りたいのでオプションで渡せるようにする
    enemy_json: Optional[Dict[str, Any]] = None,
    is_enemy: bool = False,
):
    """
    1アクター分のターン開始時処理（毒など）。
    将来リジェネ等を増やすときもここに足していく。
    """

    # ① 既存の「状態だけで完結する」効果をまず適用
    apply_start_of_turn_effects(actor_name, state, logs)

    # ② 毒ダメージ
    if (
        state.has(Status.POISON)
        and state.hp > 0
        and not (state.has(Status.KO) or state.has(Status.PETRIFY))
    ):
        # max_hp の取り方をキャラ／敵で分ける
        if is_enemy:
            # 敵：enemy_json["HP"] があれば優先
            max_hp = int(
                (enemy_json or {}).get("HP", getattr(stats, "max_hp", state.hp))
            )
        else:
            # キャラ：FinalCharacterStats に max_hp がある前提
            max_hp = getattr(stats, "max_hp", state.hp)

        poison_dmg = max(1, max_hp // 16)

        old_hp = state.hp
        # 毒では死なず HP1 で止まる
        state.hp = max(1, state.hp - poison_dmg)

        log_damage(
            logs,
            f"{actor_name}は毒のダメージを受けた！",
            actor_name,
            poison_dmg,
            old_hp,
            state.hp,
            "neutral",
            "arrow_with_max",
            max_hp,
        )

    # ③ 将来、リジェネや「ターンごとにゲージ減少」などもここに追加していける


def apply_start_of_turn_effects(
    actor_name: str,
    state: BattleActorState,
    logs: List[str],
):
    """毒など、ターン開始時に自動発動する効果をまとめる場所"""
    # （今は何もしていないが、リジェネや自動バフ系を入れていける）
