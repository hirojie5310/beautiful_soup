# ============================================================
# magic_aoe: 全体化

# enemy_cast_aoe_damage_spell_to_party	敵がパーティ全体に放つ攻撃魔法（通常ダメージ）の命中とダメージ処理を行う汎用ヘルパー
# enemy_cast_aoe_status_spell_to_party	AoE状態異常専用関数（Mind Blast 向け）「命中判定＋状態付与」だけ
# <AoE状態異常専用関数用 判定ヘルパ（表記ゆれ吸収込み）>
# spell_name
# spell_target
# is_spell_aoe
# <AoE関数呼び出し用関数>
# spell_is_aoe
# spell_base_power
# spell_has_ailment
# ============================================================

import random
from typing import Optional

from combat.enums import Status
from combat.constants import STATUS_NAME_MAP
from combat.models import EnemyCasterStats, BattleActorState
from combat.elements import (
    element_relation_and_hits_for_char,
    elements_from_monster_spell,
)
from combat.magic_damage import magic_damage_enemy_to_char
from combat.life_check import is_out_of_battle
from combat.logging import log_damage


# 敵→キャラ「純粋な全体攻撃」（Snowstorm等）用の汎用ヘルパ
# normal: ダメージ攻撃専用関数
def enemy_cast_aoe_damage_spell_to_party(
    *,
    spell_json: dict,
    enemy_name: str,
    party_members: list,
    rng: random.Random,
    logs: list[str],
    caster_state: "BattleActorState",  # ★ 反射ダメを食らう敵
    caster_max_hp: Optional[int] = None,  # ★ ログ用（なくてもOK）
) -> bool:
    """
    AoEダメージ（魔法ダメージ式）専用。
    この関数が「計算」と「適用（HP反映・ログ）」まで完結させる。

    Returns:
        bool: Reflect 反射などで「敵（術者）が倒れた」なら True
    """
    if rng is None:
        rng = random

    spell_name = spell_json.get("Name") or "Spell"
    attack_elements = elements_from_monster_spell(spell_json or {})

    base_acc = float(
        spell_json.get("Accuracy", spell_json.get("BaseAccuracy", 1.0)) or 1.0
    )
    if base_acc > 1.0:
        base_acc = base_acc / 100.0
    hit_percent = base_acc * 100.0

    logs.append(f"{enemy_name}の《{spell_name}》！")

    alive_members = [pm for pm in party_members if not is_out_of_battle(pm.state)]
    split_to_targets = 1  # ★ All Enemies は割らない（あなたの仕様）

    base_power = int(spell_json.get("Power", spell_json.get("BasePower", 0)) or 0)
    mult = int(spell_json.get("Multiplier", 1) or 1)
    acc_percent = int(round(base_acc * 100))

    enemy_caster = EnemyCasterStats(
        magic_power_base=base_power,
        magic_multiplier=mult,
        magic_accuracy_percent=acc_percent,
    )

    is_reflectable = str(spell_json.get("Reflectable", "No")).strip().lower() == "yes"

    # ★ まとめログ用カウンタ
    reflect_count = 0
    reflect_total_damage = 0

    for pm in alive_members:
        state = pm.state
        stats = pm.stats
        name = pm.name

        # ★ ここが肝：ジャンプ中なら AoE を無効化
        if getattr(state, "is_jumping", False):
            logs.append(f"{name}は空中にいる！{spell_name}は届かない！")
            continue

        # 1) 属性相性（nullは無効）
        relation = "normal"
        hit_elems = []
        if attack_elements:
            relation, hit_elems = element_relation_and_hits_for_char(
                stats, attack_elements
            )
            if relation == "null":
                logs.append(
                    f"{name}は{spell_name}を無効化した！（{','.join(e.capitalize() for e in hit_elems)}）"
                )
                continue

        # 2) 命中判定
        roll = rng.random() * 100.0
        if roll >= hit_percent:
            logs.append(
                f"{name}は{spell_name}を耐えきった！（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )
            continue

        # 3) ダメージ算出
        old_hp = state.hp
        target_is_mini_or_toad = state.has(Status.MINI) or state.has(Status.TOAD)

        damage = magic_damage_enemy_to_char(
            enemy_caster=enemy_caster,
            char=stats,
            element_relation=relation,
            rng=rng,
            use_expectation=False,
            split_to_targets=split_to_targets,
            attacker_is_blind=False,
            target_is_mini_or_toad=target_is_mini_or_toad,
            target_state=state,
        )
        damage = int(max(0, damage))

        # 4) ★ Reflect（対象ごと）
        if is_reflectable and getattr(state, "reflect_charges", 0) > 0:
            state.reflect_charges -= 1
            reflect_count += 1
            reflect_total_damage += damage

            old_enemy_hp = caster_state.hp
            caster_state.hp = max(0, old_enemy_hp - damage)

            # 個別ログ（必要なら残す：あなたの案のまま）
            max_hp_enemy = caster_max_hp or getattr(caster_state, "max_hp", None)
            log_damage(
                logs,
                f"{name}を覆う魔法障壁が《{spell_name}》を跳ね返した！ ",
                enemy_name,
                damage,
                old_enemy_hp,
                caster_state.hp,
                "target",
                "arrow_with_max" if max_hp_enemy is not None else "arrow",
                max_hp_enemy,
                "",
                True,
            )

            # ★ 反射で敵が倒れたら即終了（呼び出し側に通知）
            if caster_state.hp <= 0:
                # KOステータス管理しているならここで付けてもOK（任意）
                # caster_state.statuses.add(Status.KO)
                # ★ まとめログはここで出しておくと情報が欠けない
                if reflect_count >= 2:
                    logs.append(
                        f"{spell_name}は{reflect_count}回反射された！（合計 {reflect_total_damage} ダメージ）"
                    )
                return True

            continue  # 対象への適用はしない（状態異常も不発扱い）

        # 5) 通常適用
        state.hp = max(0, old_hp - damage)

        max_hp = (
            getattr(stats, "hp_max", None)
            or getattr(stats, "max_hp", None)
            or getattr(state, "max_hp", None)
        )
        log_damage(
            logs=logs,
            prefix="",
            target_name=name,
            damage=damage,
            old_hp=old_hp,
            new_hp=state.hp,
            perspective="target",
            hp_style="arrow_with_max" if max_hp is not None else "arrow",
            max_hp=max_hp,
            shout=True,
        )

        if state.hp <= 0:
            logs.append(f"{name}は力尽きた…")

    # ★ AoE Reflect まとめログ（2回以上のときだけ出すのがおすすめ）
    if reflect_count >= 2:
        logs.append(
            f"{spell_name}は{reflect_count}回反射された！（合計 {reflect_total_damage} ダメージ）"
        )

    return False


# AoE状態異常専用関数（Mind Blast 向け）「命中判定＋状態付与」だけ
def enemy_cast_aoe_status_spell_to_party(
    *,
    spell_json: dict,
    enemy_name: str,
    party_members: list,
    rng: random.Random,
    logs: list[str],
) -> None:
    if rng is None:
        rng = random

    # name/Name 揺れ対策
    spell_name = (spell_json.get("Name") or spell_json.get("name") or "Spell").strip()

    # StatusAilment が特徴（Mind Blast）
    ailment = (
        spell_json.get("StatusAilment") or spell_json.get("Status") or ""
    ).strip()
    if not ailment or ailment == "-":
        logs.append(f"{enemy_name}の《{spell_name}》！")
        return

    status_obj = STATUS_NAME_MAP.get(ailment.lower())
    if status_obj is None:
        logs.append(f"{enemy_name}の《{spell_name}》！")
        logs.append(f"（未対応の状態異常: {ailment}）")
        return

    # 命中率（0〜1 or 0〜100 対応）
    acc = float(spell_json.get("Accuracy", spell_json.get("BaseAccuracy", 1.0)) or 1.0)
    if acc > 1.0:
        acc = acc / 100.0
    hit_percent = acc * 100.0

    logs.append(f"{enemy_name}の《{spell_name}》！")

    alive_members = [pm for pm in party_members if not is_out_of_battle(pm.state)]

    for pm in alive_members:
        state = pm.state
        name = pm.name

        # 命中判定
        roll = rng.random() * 100.0
        if roll >= hit_percent:
            logs.append(
                f"{name}は{spell_name}を耐えきった！（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )
            continue

        # すでに付いているなら上書きしない（ログだけ変えるなどお好みで）
        if state.has(status_obj):
            logs.append(f"{name}にはすでに《{ailment}》が効いている…")
            continue

        state.add(status_obj)  # ← BattleActorStateに add() を追加した前提
        logs.append(f"{name}は《{ailment}》状態になった！")


# AoE状態異常専用関数用 判定ヘルパ（表記ゆれ吸収込み）
def spell_name(spell: dict) -> str:
    return (spell.get("Name") or spell.get("name") or "").strip()


def spell_target(spell: dict) -> str:
    return (spell.get("Target") or spell.get("target") or "").strip().lower()


def is_spell_aoe(spell: dict) -> bool:
    t = spell_target(spell)
    return t in {"all enemies"}  # 必要なら増やす


# AoE関数呼び出し用関数
def spell_is_aoe(spell_def: dict) -> bool:
    target = (spell_def.get("Target") or "").strip().lower()
    return target == "all enemies"


def spell_base_power(spell_def: dict) -> int:
    return int(spell_def.get("Power", spell_def.get("BasePower", 0)) or 0)


def spell_has_ailment(spell_def: dict) -> bool:
    a = (spell_def.get("StatusAilment") or spell_def.get("Status") or "").strip()
    return bool(a and a != "-")
