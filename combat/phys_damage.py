# ============================================================
# phys_damage: 通常攻撃関連

# roll_critical: 敏捷と基礎確率からクリティカル発生を判定するヘルパー
# _calc_net_hits: 攻撃側/防御側の倍率と命中/回避率から物理攻撃の実効ヒット数（期待値）を求める
# _calc_base_phys_damage_per_hit: 攻撃力と防御力から1ヒットあたりの物理ダメージ（乱数込み）を算出する
# physical_damage_char_to_enemy: キャラ→敵の物理攻撃ダメージを計算し、必要に応じてクリティカル判定も行う
# _calc_base_phys_damage_per_hit_enemy_to_char: 敵攻撃力とキャラ防御値から、敵→キャラ用の1ヒットあたり物理ダメージを算出する
# physical_damage_enemy_to_char: 敵→キャラの物理ダメージ（Mini/Toad・ブラインド・クリティカル等を考慮）を計算する
# ============================================================

import random
from typing import Optional, overload, Literal

from combat.enums import ElementRelation
from combat.models import (
    FinalCharacterStats,
    FinalEnemyStats,
    BattleActorState,
    AttackResult,
)
from combat.elements import apply_element_relation_to_damage


# ============================================================
# クリティカル判定ヘルパ
# ============================================================


def roll_critical(
    agility: int,
    rng: Optional[random.Random] = None,
    base_chance: float = 1.0 / 16.0,  # 6.25%を基準に
    agi_bonus_div: int = 512,  # Agiが少しずつ効くように
) -> bool:
    """
    クリティカル判定。
    簡易式: base + Agi/agi_bonus_div
    """
    chance = base_chance + agility / agi_bonus_div
    chance = min(max(chance, 0.0), 0.5)  # 上限50%
    if rng is None:
        rng = random.Random()
    return rng.random() < chance


# ============================================================
# 物理ダメージ計算：キャラ → 敵
# ============================================================


def _calc_net_hits(
    atk_multiplier: int,
    hit_percent: int,
    def_multiplier: int,
    evade_percent: int,
) -> float:
    """平均ヒット数（期待値）を近似計算"""
    h = max(0, min(hit_percent, 100)) / 100.0
    e = max(0, min(evade_percent, 100)) / 100.0
    m = atk_multiplier * h - def_multiplier * e
    return max(m, 0.0)


def _calc_base_phys_damage_per_hit(
    attack_power: int,
    defense: int,
    *,
    rng: Optional[random.Random] = None,
    use_expectation: bool,
) -> int:
    """
    1ヒットあたりの物理ダメージ（乱数込み）
    AttackPower * [1.0, 1.5] - Defense （最低 1）
    """
    if use_expectation:
        factor = 1.25
    else:
        if rng is None:
            rng = random.Random()
        factor = rng.uniform(1.0, 1.5)
    raw = int(attack_power * factor)
    base = raw - defense
    return max(base, 1)


@overload
def physical_damage_char_to_enemy(
    char: FinalCharacterStats,
    enemy: FinalEnemyStats,
    hand: str = "main",
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    return_crit: Literal[False] = False,
    attacker_state=None,
    return_hits: Literal[False] = False,
) -> AttackResult: ...


@overload
def physical_damage_char_to_enemy(
    char: FinalCharacterStats,
    enemy: FinalEnemyStats,
    hand: str = "main",
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    return_crit: Literal[True] = True,
    attacker_state=None,
    return_hits: Literal[False] = False,
) -> AttackResult: ...


@overload
def physical_damage_char_to_enemy(
    char: FinalCharacterStats,
    enemy: FinalEnemyStats,
    hand: str = "main",
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    return_crit: Literal[True] = True,
    attacker_state=None,
    return_hits: Literal[True] = True,
) -> AttackResult: ...


def physical_damage_char_to_enemy(
    char: FinalCharacterStats,
    enemy: FinalEnemyStats,
    hand: str = "main",
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    return_crit: bool = False,  # 互換のため残す（使わない）
    attacker_state=None,
    return_hits: bool = False,  # 互換のため残す（使わない）
) -> AttackResult:
    """
    キャラクター → 敵 物理ダメージ（手を指定）。
    戻り値は常に AttackResult に統一する。
      - damage: 与えたダメージ（int）
      - hit_count: 表示用ヒット数（int、ミスは0）
      - is_critical: クリティカルか（期待値モードでは常にFalse）
    """

    # ★ Mini / Toad は物理攻撃力 0 扱い
    if attacker_is_mini_or_toad:
        return AttackResult(damage=0, hit_count=0, is_critical=False)

    if hand == "off":
        atk_power = char.off_power
        atk_mul = char.off_atk_multiplier
        hit_percent = char.off_accuracy
    else:
        atk_power = char.main_power
        atk_mul = char.main_atk_multiplier
        hit_percent = char.main_accuracy

    # ★ Cheer による攻撃力ボーナスを加算
    if attacker_state is not None:
        cheer_bonus = getattr(attacker_state, "cheer_bonus", 0)
        if cheer_bonus > 0:
            atk_power += cheer_bonus

    if atk_power <= 0 or atk_mul <= 0:
        return AttackResult(damage=0, hit_count=0, is_critical=False)

    if blind:
        hit_percent //= 2

    # ★後列ペナルティ：近距離武器のみ Hit% 半減（LongRangeは除外）
    if char.row == "back":
        is_long = char.off_long if hand == "off" else char.main_long
        if not is_long:
            hit_percent //= 2

    # ネットヒット数
    net_hits = _calc_net_hits(
        atk_multiplier=atk_mul,
        hit_percent=hit_percent,
        def_multiplier=enemy.defense_multiplier,
        evade_percent=enemy.evasion_percent,
    )

    # _calc_net_hits が float を返す可能性があるなら、表示用は丸めて int 化
    hit_count = int(round(net_hits)) if isinstance(net_hits, float) else int(net_hits)

    if hit_count <= 0:
        return AttackResult(damage=0, hit_count=0, is_critical=False)

    # 1ヒットあたり
    base_per_hit = _calc_base_phys_damage_per_hit(
        attack_power=atk_power,
        defense=enemy.defense,
        rng=rng,
        use_expectation=use_expectation,
    )

    dmg = int(base_per_hit * net_hits)
    dmg = apply_element_relation_to_damage(dmg, element_relation)
    dmg = max(dmg, 0)

    # ★クリティカル（乱数モードのみ）
    is_crit = False
    if not use_expectation:
        if rng is None:
            rng = random.Random()
        if roll_critical(char.agility, rng):
            is_crit = True
            dmg *= 2
            dmg = max(dmg, 0)

    return AttackResult(damage=dmg, hit_count=hit_count, is_critical=is_crit)


# ============================================================
# 物理ダメージ計算：敵 → キャラ
# ============================================================


def _calc_base_phys_damage_per_hit_enemy_to_char(
    enemy: FinalEnemyStats,
    defense_value: int,
    *,
    rng: Optional[random.Random] = None,
    use_expectation: bool,
) -> int:
    if use_expectation:
        factor = 1.25
    else:
        if rng is None:
            rng = random.Random()
        factor = rng.uniform(1.0, 1.5)
    raw = int(enemy.attack_power * factor)
    base = raw - defense_value
    return max(base, 1)


def physical_damage_enemy_to_char(
    enemy: FinalEnemyStats,
    char: FinalCharacterStats,
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    attacker_is_blind: bool = False,
    attacker_is_mini_or_toad: bool = False,
    target_is_mini_or_toad: bool = False,
    return_crit: bool = False,
    target_state: Optional[BattleActorState] = None,
) -> int | tuple[int, bool] | tuple[int, bool, float]:
    """
    敵 → キャラの物理ダメージ
    return_crit=True のとき (dmg, is_crit, net_hits) を返す
    """

    if attacker_is_mini_or_toad:
        return (0, False, 0) if return_crit else 0

    defense_value = char.defense
    def_mul = char.defense_multiplier
    evade_percent = char.evasion_percent

    if target_is_mini_or_toad:
        defense_value = 0

    if target_state is not None:
        if getattr(target_state, "boost_count", 0) > 0:
            defense_value = 0
            def_mul = 0

    hit_percent = enemy.accuracy_percent
    if attacker_is_blind:
        hit_percent //= 2

    # ★後列ペナルティ：後列を狙う物理攻撃は Hit% 半減
    if char.row == "back":
        hit_percent //= 2

    net_hits = _calc_net_hits(
        atk_multiplier=enemy.attack_multiplier,
        hit_percent=hit_percent,
        def_multiplier=def_mul,
        evade_percent=evade_percent,
    )
    if net_hits <= 0:
        return (0, False, 0) if return_crit else 0

    base_per_hit = _calc_base_phys_damage_per_hit_enemy_to_char(
        enemy=enemy,
        defense_value=defense_value,
        rng=rng,
        use_expectation=use_expectation,
    )

    dmg = base_per_hit * net_hits
    is_crit = False
    if not use_expectation:
        if rng is None:
            rng = random.Random()
        if roll_critical(enemy.level, rng, base_chance=1 / 20, agi_bonus_div=9999):
            is_crit = True
            dmg *= 2

    dmg = max(int(dmg), 0)

    return (dmg, is_crit, net_hits) if return_crit else dmg
