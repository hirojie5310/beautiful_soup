# ============================================================
# magic_damage: 魔法関連

# _is_offensive_white	SpellInfoにnameが無い環境でも落ちない攻撃白魔判定
# use_mp_for_spell	FC版準拠：spell_json["Level"]のMPを1消費する
# healing_spell_kind	回復/補助系なら種類を返す（hp/status/revive/protect/haste）
# magic_heal_amount_to_char	回復白魔法の回復量を計算する簡易関数
# _calc_magic_power	黒/白/召喚/その他に応じて魔法の威力を算出する
# _calc_magic_multiplier	魔法攻撃のヒット回数（倍率）を計算
# _calc_magic_accuracy	魔法攻撃の命中率[%]を計算
# _calc_expected_magic_hits	魔法の倍率・命中率と相手の魔法防御倍率/抵抗率から平均魔法ヒット数（期待値）を計算する
# _calc_base_magic_damage_per_hit	魔法1ヒットあたりの基礎ダメージ（乱数込み）を計算
# magic_damage_char_to_enemy	キャラ→敵の魔法ダメージ（期待値）を計算
# apply_tornado_to_state	任意のアクターのHPを割合で削るTornado効果を適用し、ダメージログを出力する汎用ヘルパー
# enemy_cast_tornado_to_char	敵がTornadoをキャラに使用する際の属性判定・命中判定・HP削り処理をまとめたヘルパー
# calc_drain_damage_generic	Drain用に既存の攻撃魔法式を流用し、吸収ダメージの生ダメージ期待値を計算する
# enemy_cast_drain_to_char	敵がDrainをキャラに使用したときの属性判定・ダメージ計算・HP吸収処理とログ出力を行うヘルパー
# enemy_caster_from_monster	monsters.jsonから敵の魔法攻撃用パラメータ（基礎威力/倍率/命中率）を組み立ててEnemyCasterStatsを生成する
# magic_damage_enemy_to_char	敵→キャラの魔法ダメージ（期待値）を計算
# ============================================================

import random
from typing import Optional, Any, Dict
import traceback

from combat.enums import ElementRelation, Status
from combat.constants import OFFENSIVE_WHITE_ELEMENTS, OFFENSIVE_WHITE
from combat.models import (
    SpellInfo,
    BattleActorState,
    FinalCharacterStats,
    FinalEnemyStats,
    EnemyCasterStats,
)
from combat.elements import (
    element_relation_and_hits_for_char,
    apply_element_relation_to_damage,
)
from combat.elements import parse_elements
from combat.logging import log_damage


def _is_offensive_white(spell: SpellInfo) -> bool:
    """
    SpellInfo に name が無い環境でも落ちない攻撃白魔判定。
    - name があればそれを優先
    - 無ければ elements（holy/air）で判定
    """
    if spell.magic_type != "white":
        return False

    # ① name があるなら名前で判定（将来 name を追加してもOK）
    nm = getattr(spell, "name", None)
    if isinstance(nm, str) and nm:
        return nm.strip().lower() in OFFENSIVE_WHITE

    # ② name が無い場合は属性で判定（★parse_elements で正規化）
    elems = parse_elements(getattr(spell, "elements", None))
    return any(e in OFFENSIVE_WHITE_ELEMENTS for e in elems)


# spell_json["Level"] を使って MP 消費する関数
def use_mp_for_spell(char_state: BattleActorState, spell_json: Dict[str, Any]) -> bool:
    """
    FC版準拠：spell_json["Level"] の MP を1消費する。
    MPが足りれば True、足りなければ False を返す。
    """
    lvl = int(spell_json.get("Level", 1))
    lvl = max(1, min(lvl, 8))

    if char_state.mp_pool.get(lvl, 0) >= 1:
        char_state.mp_pool[lvl] -= 1
        return True
    else:
        return False


# 追加: 回復白魔法かどうかの判定
def healing_spell_kind(spell_json: Dict[str, Any]) -> str | None:
    """
    回復/補助系なら種類を返す：
      "hp"      : HP回復
      "status"  : 状態回復
      "revive"  : 蘇生
      "protect" : 防御アップ
      "haste"   : 攻撃力・攻撃回数アップ
    回復/補助系でなければ None
    """
    effect = (spell_json.get("Effect") or "").strip().lower()
    name = (spell_json.get("Name") or "").strip().lower()

    # --- HP回復 ---
    if "restore target's hp" in effect:
        return "hp"

    # ★ 召喚「Ifrit: Healing Light」（Effect が無い回復系）
    if "healing light" in name:
        return "hp"

    # --- 状態回復 ---
    if effect.startswith("cure"):
        return "status"

    # --- 蘇生 ---
    if effect.startswith("revive"):
        return "revive"

    # 防御アップ（Protect）
    if "enhance defense and magic defense" in effect or name == "protect":
        return "protect"

    # ヘイスト（Haste）
    if "enhance accuracy and attack multiplier" in effect or name == "haste":
        return "haste"

    return None


# 追加: 白魔法回復量（簡易式）
def magic_heal_amount_to_char(
    caster: FinalCharacterStats,
    spell: SpellInfo,
    rng: Optional[random.Random] = None,
    use_expectation: bool = False,
    blind: bool = False,
) -> int:
    """
    回復白魔法の回復量を計算する簡易関数。
    攻撃魔法の式を流用し、相手側の魔防/抵抗は無視。
    """
    magic_power = _calc_magic_power(caster, spell)
    magic_mult = _calc_magic_multiplier(caster, spell)
    magic_acc = _calc_magic_accuracy(caster, spell, blind=blind)

    # 命中・抵抗を簡易化：抵抗なし前提での期待ヒット数
    hit_rate = max(0, min(magic_acc, 100)) / 100.0
    expected_hits = magic_mult * hit_rate
    if expected_hits <= 0:
        return 0

    base_per_hit = _calc_base_magic_damage_per_hit(
        magic_power=magic_power,
        magic_defense=0,  # 回復は防御で減らさない
        rng=rng,
        use_expectation=use_expectation,
    )
    heal = int(base_per_hit * expected_hits)
    return max(heal, 0)


# ============================================================
# 魔法ダメージ計算：キャラ → 敵
# ============================================================


def _calc_magic_power(caster: FinalCharacterStats, spell: SpellInfo) -> int:
    if spell.magic_type == "black":
        return spell.power + caster.intelligence // 2

    if spell.magic_type == "white":
        if _is_offensive_white(spell):
            return spell.power + caster.mind // 2
        else:
            # 非攻撃白魔法（Cure系/Protect/Haste等）
            return spell.power

    if spell.magic_type == "summon":
        # Call Magic Power = Spell Damage + Int
        return spell.power + caster.intelligence

    # それ以外は従来通り（保険）
    return spell.power + caster.intelligence // 2


def _calc_magic_multiplier(caster: FinalCharacterStats, spell: SpellInfo) -> int:
    L = caster.level
    J = caster.job_level

    if spell.magic_type == "black":
        stat = caster.intelligence
        return max(1 + stat // 16 + L // 16 + J // 32, 0)

    if spell.magic_type == "white":
        stat = caster.mind  # ガイドの Spirit 相当
        return max(1 + stat // 16 + L // 16 + J // 32, 0)

    if spell.magic_type == "summon":
        stat = caster.intelligence
        # Call Magic Multiplier = Int/8 + (((JobLv/8)*3)/2) + 1
        return max(1 + stat // 8 + (((J // 8) * 3) // 2), 0)

    stat = caster.intelligence
    return max(1 + stat // 16 + L // 16 + J // 32, 0)


def _calc_magic_accuracy(
    caster: FinalCharacterStats, spell: SpellInfo, blind: bool = False
) -> int:
    if spell.magic_type == "black":
        acc = spell.accuracy_percent + caster.intelligence // 2

    elif spell.magic_type == "white":
        acc = spell.accuracy_percent + caster.mind // 2

    elif spell.magic_type == "summon":
        # Call Magic Accuracy% = Spell Accuracy% + Int
        acc = spell.accuracy_percent + caster.intelligence

    else:
        acc = spell.accuracy_percent + caster.intelligence // 2

    if blind:
        acc *= 0.5

    acc = int(acc)
    return max(0, min(acc, 100))


def _calc_expected_magic_hits(
    magic_mult: int,
    magic_acc_percent: int,
    mdef_mult: int,
    magic_resistance_percent: int,
) -> float:
    """魔法の平均ヒット数（期待値）"""
    hit_rate = max(0, min(magic_acc_percent, 100)) / 100.0
    resist_rate = max(0, min(magic_resistance_percent, 100)) / 100.0
    expected = magic_mult * hit_rate - mdef_mult * resist_rate
    return max(expected, 0.0)


def _calc_base_magic_damage_per_hit(
    magic_power: int,
    magic_defense: int,
    rng: Optional[random.Random],
    use_expectation: bool,
) -> int:
    """1ヒットあたり魔法ダメージ"""
    if use_expectation:
        factor = 1.25
    else:
        if rng is None:
            rng = random.Random()
        factor = rng.uniform(1.0, 1.5)
    raw = int(magic_power * factor)
    base = raw - magic_defense
    return max(base, 1)


def magic_damage_char_to_enemy(
    caster: FinalCharacterStats,
    spell: SpellInfo,
    enemy: FinalEnemyStats,
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    split_to_targets: int = 1,
    blind: bool = False,
) -> int:
    """
    キャラ → 敵の魔法ダメージ。
    use_expectation=False の場合は
      1) ヒット数を期待値でなく整数ロール
      2) 各ヒットごとに基礎ダメをロールして合計
    split_to_targets > 1 のときは単体魔法の全体化などでダメージを等分。
    """
    if rng is None:
        rng = random.Random()

    magic_power = _calc_magic_power(caster, spell)
    magic_mult = _calc_magic_multiplier(caster, spell)
    magic_acc = _calc_magic_accuracy(caster, spell, blind=blind)

    expected_hits = _calc_expected_magic_hits(
        magic_mult=magic_mult,
        magic_acc_percent=magic_acc,
        mdef_mult=enemy.magic_def_multiplier,
        magic_resistance_percent=enemy.magic_resistance_percent,
    )
    if expected_hits <= 0:
        return 0

    # --- ヒット数：期待値 or 整数ロール ---
    if use_expectation:
        real_hits = expected_hits
    else:
        base_hits = int(expected_hits)
        frac = expected_hits - base_hits
        real_hits = base_hits + (1 if rng.random() < frac else 0)

    # ---------------------------------------------
    # ★最小差分ポイント：ヒットごとロール
    # ---------------------------------------------
    if use_expectation:
        base_per_hit = _calc_base_magic_damage_per_hit(
            magic_power=magic_power,
            magic_defense=enemy.magic_defense,
            rng=rng,
            use_expectation=True,
        )
        dmg = base_per_hit * real_hits
    else:
        total = 0
        for _ in range(int(real_hits)):
            base_per_hit = _calc_base_magic_damage_per_hit(
                magic_power=magic_power,
                magic_defense=enemy.magic_defense,
                rng=rng,
                use_expectation=False,
            )
            total += base_per_hit
        dmg = total
    # ---------------------------------------------

    dmg = apply_element_relation_to_damage(int(dmg), element_relation)

    if split_to_targets > 1:
        dmg = int(dmg / split_to_targets)

    return max(int(dmg), 0)


# Tornado -----------------------
# Tornado 汎用ヘルパー: 任意のActorに対するTornado
def apply_tornado_to_state(
    target_state: BattleActorState,
    target_stats_level: int,
    target_name: str,
    rng: random.Random,
    logs: list[str],
    *,
    min_ratio: float = 0.05,
    max_ratio: float = 0.1,
    prefix: str = "",  # ★ 追加：前置きの文言（誰が何をしたか）
) -> None:
    """
    Tornadoの効果を「誰にでも」適用できる共通ヘルパー。
    - 現在HPの一定割合（5〜10%など）まで減らすが、0にはしない。
    - ボス免疫などは呼び出し元で判定する想定。
    """
    if target_state.hp <= 1:
        logs.append(f"{target_name}にはTornadoの効果がなかった。")
        return

    old_hp = target_state.hp
    ratio = rng.uniform(min_ratio, max_ratio)
    new_hp = max(1, int(target_state.hp * ratio))

    damage = old_hp - new_hp
    target_state.hp = new_hp

    # max_hp が state にあるならそれも表示
    max_hp = getattr(target_state, "max_hp", None)

    log_damage(
        logs=logs,
        prefix=prefix,  # 例: "Unei'S Cloneは《Tornado》を唱えた！ "
        target_name=target_name,  # 例: "Runeth"
        damage=damage,
        old_hp=old_hp,
        new_hp=new_hp,
        perspective="target",  # 「Runethは○ダメージを受けた」
        hp_style="arrow_with_max" if max_hp is not None else "arrow",
        max_hp=max_hp,
        shout=True,  # 「！」で〆る
    )


# 敵→キャラ Tornado 専用ヘルパー
def enemy_cast_tornado_to_char(
    spell_json: dict,
    char_state: BattleActorState,
    char_stats: FinalCharacterStats,
    char_name: str,
    enemy_name: str,
    rng: random.Random,
    logs: list[str],
) -> None:
    # 1) 属性相性チェック
    elems = ["air"]
    relation, hit_elems = element_relation_and_hits_for_char(char_stats, elems)

    if relation == "null":
        logs.append(f"{char_name}は風属性に完全耐性を持っている！Tornadoは無効だ。")
        return

    # 2) 命中チェック
    base_acc = float(spell_json.get("BaseAccuracy") or 1.0)
    if base_acc > 1.0:
        base_acc = base_acc / 100.0
    hit_percent = base_acc * 100.0

    roll = rng.random() * 100.0
    if roll >= hit_percent:
        logs.append(
            f"{char_name}はTornadoを避けた！（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
        )
        return

    # 3) 実際のHP削り＋ログ
    apply_tornado_to_state(
        target_state=char_state,
        target_stats_level=char_stats.level,
        target_name=char_name,
        rng=rng,
        logs=logs,
        prefix=f"{enemy_name}は《Tornado》を唱えた！ ",  # ★ ここが prefix
    )


# Drain -----------------------
# Drain: 共通ダメージヘルパー（既存の魔法ダメージ式を内部で利用）
def calc_drain_damage_generic(
    caster_magic_power: int,
    caster_magic_mult: int,
    caster_magic_acc: int,
    target_magic_def: int,
    target_magic_def_mult: int,
    *,
    rng: random.Random,
    use_expectation: bool = False,
) -> int:
    """
    Drain用の「生ダメージ」期待値だけを計算する。
    実際のHP増減（吸収）は呼び出し側がやる。
    ここでは通常の攻撃魔法の式を流用する想定。
    """
    # ここは既存の「attack magic」の内部計算をコピペしてOK
    hit_rate = max(0, min(caster_magic_acc, 100)) / 100.0
    expected_hits = caster_magic_mult * hit_rate
    if expected_hits <= 0:
        return 0

    base_per_hit = _calc_base_magic_damage_per_hit(
        magic_power=caster_magic_power,
        magic_defense=target_magic_def,
        rng=rng,
        use_expectation=use_expectation,
    )
    dmg = int(base_per_hit * expected_hits)
    return max(dmg, 0)


# 敵→キャラ Drain 専用ヘルパー
def enemy_cast_drain_to_char(
    spell: SpellInfo,
    enemy_stats: EnemyCasterStats,
    enemy_state: BattleActorState,
    char_stats: FinalCharacterStats,
    char_state: BattleActorState,
    char_name: str,
    rng: random.Random,
    logs: list[str],
) -> None:
    # 1) 反射チェックや属性相性などは他の攻撃魔法と同じルートで。
    elems = spell.elements or ["dark"]
    relation, hit_elems = element_relation_and_hits_for_char(char_stats, elems)

    # 無効なら何もしない
    if relation == "null":
        logs.append(f"{char_name}はDrainを完全に無効化した！")
        return

    # 2) 素ダメージ計算
    raw_damage = calc_drain_damage_generic(
        caster_magic_power=enemy_stats.magic_power_base,
        caster_magic_mult=enemy_stats.magic_multiplier,
        caster_magic_acc=enemy_stats.magic_accuracy_percent,
        target_magic_def=char_stats.magic_defense,
        target_magic_def_mult=char_stats.magic_def_multiplier,
        rng=rng,
    )

    # 3) 属性補正（半減／弱点など）
    dmg = apply_element_relation_to_damage(raw_damage, relation)

    if dmg <= 0:
        # 吸収されたパターンなど
        logs.append(f"{char_name}はDrainを受けたが、HPは減らなかった。")
        return

    # 4) 実HP増減（敵が吸収する）
    old_char_hp = char_state.hp
    old_enemy_hp = enemy_state.hp

    char_state.hp = max(0, char_state.hp - dmg)
    enemy_state.hp = min(
        enemy_state.max_hp or enemy_state.hp + dmg, enemy_state.max_hp or 9999
    )

    logs.append(
        f"{char_name}のHPが {old_char_hp} → {char_state.hp} に減少し、"
        f"敵のHPが {old_enemy_hp} → {enemy_state.hp} に吸収された！（Drain）"
    )

    # キャラが0なら KO フラグ
    if char_state.hp <= 0:
        char_state.statuses.add(Status.KO)


# ============================================================
# 魔法ダメージ計算：敵 → キャラ
# ============================================================


def enemy_caster_from_monster(
    monster: Dict[str, Any],
    magic_power_base: Optional[int] = None,
    magic_multiplier: Optional[int] = None,
    magic_accuracy_percent: Optional[int] = None,
) -> EnemyCasterStats:
    """
    monsters.json から敵の魔法攻撃用パラメータを作成するヘルパ。
    引数が指定されていればそちらを優先し、指定がなければ簡易に推定。
    """
    if magic_power_base is None and int(monster.get("AttackPower", 0)) == 0:
        print(
            "[Debug:magic_damage/enemy_caster_from_monster] enemy_caster_from_monster got AttackPower=0, monster keys:",
            list(monster.keys()),
        )
        traceback.print_stack(limit=6)  # 呼び出し元を出す

    if magic_power_base is None:
        magic_power_base = int(monster.get("AttackPower", 0))
    if magic_multiplier is None:
        mr = monster.get("MagicResistance", {}) or {}
        magic_multiplier = int(mr.get("Count") or 1)
    if magic_accuracy_percent is None:
        mr = monster.get("MagicResistance", {}) or {}
        magic_accuracy_percent = int(round((mr.get("Rate") or 1.0) * 100))

    return EnemyCasterStats(
        magic_power_base=magic_power_base,
        magic_multiplier=magic_multiplier,
        magic_accuracy_percent=magic_accuracy_percent,
    )


def magic_damage_enemy_to_char(
    enemy_caster: EnemyCasterStats,
    char: FinalCharacterStats,
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
    use_expectation: bool = True,
    split_to_targets: int = 1,
    attacker_is_blind: bool = False,
    target_is_mini_or_toad: bool = False,  # ★ 追加
    target_state: Optional[BattleActorState] = None,  # ★ Boost 判定用に追加
) -> int:
    """
    敵 → キャラの魔法ダメージ（期待値）。
    char 側は FinalCharacterStats の魔法防御ステを使用。
    """
    # print(f"[Debug:magic_damage/magic_damage_enemy_to_char] {enemy_caster}")

    if enemy_caster.magic_power_base == 0:
        print("[Debug] caller stack (power=0):", flush=True)
        stack = "".join(traceback.format_stack(limit=12))
        print(stack, flush=True)

    # キャラ側魔法防御パラメータ
    mdef = char.magic_defense
    mdef_mult = char.magic_def_multiplier

    # ★ Mini/Toad 中は魔法防御 0 扱い
    if target_is_mini_or_toad:
        mdef = 0
        mdef_mult = 0

    # ★ Black Belt: Boost 中は魔法防御も 0 扱い
    if target_state is not None:
        if getattr(target_state, "boost_count", 0) > 0:
            mdef = 0
            mdef_mult = 0

    mres_percent = max(0, min(char.magic_resistance, 100))

    acc = enemy_caster.magic_accuracy_percent
    if attacker_is_blind:
        acc //= 2

    expected_hits = _calc_expected_magic_hits(
        magic_mult=enemy_caster.magic_multiplier,
        magic_acc_percent=acc,
        mdef_mult=mdef_mult,
        magic_resistance_percent=mres_percent,
    )
    if expected_hits <= 0:
        return 0

    base_per_hit = _calc_base_magic_damage_per_hit(
        magic_power=enemy_caster.magic_power_base,
        magic_defense=mdef,
        rng=rng,
        use_expectation=use_expectation,
    )

    dmg = base_per_hit * expected_hits
    dmg = apply_element_relation_to_damage(int(dmg), element_relation)

    if split_to_targets > 1:
        dmg = int(dmg / split_to_targets)

    return max(int(dmg), 0)
