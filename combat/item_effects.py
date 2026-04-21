# ============================================================
# item_effects: アイテム関連（効果系）

# apply_item_effect_to_actor	アイテムの効果（回復・蘇生・バフなど）を対象1体に適用する
# apply_status_item_to_enemy	「状態異常だけ」を与えるタイプのアイテムを判定し、敵ステートに状態異常を付与する共通ヘルパー
# spell_from_item	アイテムJSONからSpellInfo（威力・命中・属性など）を組み立てる変換ヘルパー
# item_damage_char_to_enemy	攻撃アイテムのSpellInfoと敵ステータスからダメージ量を計算する
# ============================================================

import random
from typing import Optional, Dict, Any, List, Tuple

from combat.battle_items import is_weapon_spell_item
from combat.enums import ElementRelation, Status
from combat.models import (
    FinalCharacterStats,
    BattleActorState,
    SpellInfo,
    FinalEnemyStats,
)
from combat.elements import parse_elements, apply_element_relation_to_damage
from combat.status_effects import *
from utils.text_normalize import normalize_text_basic


# ============================================================
# アイテム効果用ヘルパ（回復・蘇生・状態異常回復）
# ============================================================


def _item_effect_category(item_json: Dict[str, Any]) -> str:
    return normalize_text_basic(item_json.get("effect_category") or "")


def _item_status_text(item_json: Dict[str, Any]) -> str:
    spell_info = item_json.get("SpellInfo") or {}
    return str(
        item_json.get("status_ailment")
        or item_json.get("StatusAilment")
        or item_json.get("StatusAilments")
        or spell_info.get("status_ailment")
        or spell_info.get("StatusAilment")
        or spell_info.get("StatusAilments")
        or ""
    ).strip()


def _item_status_list(item_json: Dict[str, Any]) -> List[str]:
    text = _item_status_text(item_json)
    if not text:
        return []
    return [normalize_text_basic(part) for part in text.split(",") if part.strip()]


def infer_battle_item_target_side(item_json: Dict[str, Any]) -> str | None:
    """
    戦闘中のアイテムが主に向く対象を推定する。
    - "ally": 回復・蘇生・補助
    - "enemy": 攻撃・敵向け状態異常
    - None: UIに対象面選択を委ねる
    """
    side = normalize_text_basic(item_json.get("default_target_side") or "")
    if side == "ally":
        return "ally"
    if side == "enemy":
        return "enemy"
    if side == "any":
        return None

    effect_category = _item_effect_category(item_json)
    if effect_category in {
        "heal_hp",
        "heal_full",
        "revive",
        "buff_attack",
        "buff_defense",
        "reflect",
        "status_recovery",
        "teleport",
    }:
        return "ally"
    if effect_category in {"damage", "drain", "status"}:
        return "enemy"
    if effect_category in {"field_utility", "status_toggle"}:
        return None

    return None


def apply_item_effect_to_actor(
    item_json: Dict[str, Any],
    target_state: BattleActorState,
    *,
    target_name: str = "対象",
    max_hp: Optional[int] = None,
    logs: Optional[List[str]] = None,
    target_stats: Optional[FinalCharacterStats] = None,
    actor_stats: Optional[FinalCharacterStats] = None,
    rng: Optional[random.Random] = None,
    actor_name: str | None = None,
) -> None:
    """
    ffiii_items.json の 1 アイテムを、味方 or 敵 1体に使用したときの効果を反映する簡易関数。
    ・主に「回復アイテム」「状態異常回復アイテム」「蘇生アイテム」を担当
    ・攻撃アイテム（Deal XXX damage）は別ヘルパーで魔法ダメージ計算に委譲する前提
    """
    item_name = (item_json.get("Name") or "").strip()

    # ここで「主語」を決める
    if actor_name and actor_name != target_name:
        prefix = f"{actor_name}は{target_name}に{item_name}を使った！ "
    else:
        prefix = f"{target_name}は{item_name}を使った！ "

    if logs is None:
        return

    spell_info = item_json.get("SpellInfo") or {}
    effect_category = _item_effect_category(item_json)
    item_statuses = _item_status_list(item_json)
    value = int(item_json.get("Value", 0) or 0)

    # 既に戦闘不能（HP<=0）の場合、HP回復系の扱いをどうするかは好みだが、
    # ここでは「蘇生系以外は効果なし」にしておく
    is_ko = target_state.hp <= 0

    # ------------------------------------------
    # 0) Haste系バフアイテム（Bacchus's Cider）
    #    Effect: "Enhance Accuracy and Attack Multiplier"
    #    SpellEffect: "Haste"
    #    Multiplier は 3 で固定
    # ------------------------------------------
    is_haste_item = effect_category == "buff_attack"

    if is_haste_item:
        # ステータス情報が無いと攻撃力・攻撃回数をいじれないので念のため
        if target_stats is None:
            if logs is not None:
                logs.append(f"{prefix} " f"しかし攻撃力アップ効果を適用できなかった…")
            return

        if rng is None:
            rng = random.Random()

        mind = target_stats.mind

        # NES 仕様に合わせて、アイテム使用時の命中率は使用者/対象ステータスに関係なく 100% とする。
        # --- ここから成功時のバフ計算（Haste と同様）---
        L = target_stats.level
        J = target_stats.job_level
        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1

        base_power = float(spell_info.get("BasePower", 5))
        magic_defense, magic_def_multiplier, magic_resistance_percent = (
            buff_target_magic_parameters(
                target_magic_defense=target_stats.magic_defense,
                target_magic_def_multiplier=target_stats.magic_def_multiplier,
                target_magic_resistance_percent=target_stats.magic_resistance,
                target_is_friendly=True,
            )
        )

        # ✅ FAQ 相当の Haste 転写量を共通ヘルパで算出・蓄積
        (
            old_power_bonus,
            new_power_bonus,
            old_mul_bonus,
            new_mul_bonus,
            add_power,
            add_mul,
        ) = apply_haste_buff(
            target_stats,
            base_power=base_power,
            base_factor=base_factor,
            rng=rng,
            target_magic_defense=magic_defense,
            target_magic_def_multiplier=magic_def_multiplier,
            target_magic_resistance_percent=magic_resistance_percent,
        )

        if logs is not None:
            logs.append(
                f"{prefix} "
                f"物理加算値 {old_power_bonus}→{new_power_bonus}"
                f"、攻撃回数加算 {old_mul_bonus}→{new_mul_bonus}"
                f"（今回 +{add_power}, +{add_mul}）に上がった。"
            )

        return

    # ------------------------------------------
    # 0-b) Protect系バフアイテム（Turtle Shell）
    #    Effect: "Enhance Defense and Magic Defense"
    #    SpellEffect: "Protect"
    #    Multiplier は 3 で固定（※現状は未使用）
    # ------------------------------------------
    is_protect_item = effect_category == "buff_defense"

    if is_protect_item:
        # ステータス情報が無いと防御をいじれないので念のため
        if target_stats is None:
            if logs is not None:
                logs.append(f"{prefix} " f"しかし防御アップ効果を適用できなかった…")
            return

        if rng is None:
            rng = random.Random()

        mind = target_stats.mind
        L = target_stats.level
        J = target_stats.job_level

        # NES 仕様に合わせて、アイテム使用時の命中率は使用者/対象ステータスに関係なく 100% とする。
        # --- ここから成功時のバフ計算（白魔法 Protect と同じ式）---
        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1
        base_power = float(spell_info.get("BasePower", 5))
        magic_defense, magic_def_multiplier, magic_resistance_percent = (
            buff_target_magic_parameters(
                target_magic_defense=target_stats.magic_defense,
                target_magic_def_multiplier=target_stats.magic_def_multiplier,
                target_magic_resistance_percent=target_stats.magic_resistance,
                target_is_friendly=True,
            )
        )

        old_def, old_mdef, add_value = apply_protect_buff(
            target_stats,
            base_power=base_power,
            base_factor=base_factor,
            rng=rng,
            target_magic_defense=magic_defense,
            target_magic_def_multiplier=magic_def_multiplier,
            target_magic_resistance_percent=magic_resistance_percent,
        )

        logs.append(
            f"{prefix} "
            f"防御力 {old_def}→{target_stats.defense}、"
            f"魔法防御 {old_mdef}→{target_stats.magic_defense}（今回 +{add_value}）に上がった。"
        )
        return

    # ------------------------------------------
    # 1) HP 回復系 ("Restore target's HP")
    # ------------------------------------------
    if effect_category == "heal_hp":
        if is_ko:
            logs.append(f"{prefix}{target_name}は戦闘不能のため効果がなかった…")
            return
        heal = value
        if is_weapon_spell_item(item_json) and actor_stats is not None:
            heal = weapon_spell_heal_amount_to_actor(
                caster_stats=actor_stats,
                item_json=item_json,
                rng=rng,
            )
        if max_hp is not None:
            old_hp = target_state.hp
            target_state.hp = min(target_state.hp + heal, max_hp)
            healed = target_state.hp - old_hp
        else:
            target_state.hp += heal
            healed = heal
        logs.append(f"{prefix}{target_name}のHPが {healed} 回復した！")
        return

    # ------------------------------------------
    # 2) エリクサー系 ("Restore target to full HP and MP")
    #    ※ MPの最大値管理をまだしていないので、ここでは HP のみ最大まで回復。
    # ------------------------------------------
    if effect_category == "heal_full":
        if is_ko and max_hp is None:
            # max_hp がないと蘇生＋全快を再現しにくいので、とりあえず 1 だけ復活させる例
            target_state.hp = 1
            logs.append(f"{prefix}{target_name}はHP1で復活した！")
        else:
            if max_hp is not None:
                target_state.hp = max_hp
            else:
                # max_hp 不明なら、とりあえず今の2倍にするなど適当な処理もあり
                target_state.hp = max(target_state.hp, 1) * 2
            logs.append(f"{prefix}{target_name}のHPが全回復した！")
        # MP の最大値を別で管理するようにしたら、ここで MP も全快にする
        return

    # ------------------------------------------
    # 3) 蘇生系 ("Revive from KO")
    # ------------------------------------------
    if effect_category == "revive":
        if not is_ko:
            logs.append(f"{prefix}{target_name}は倒れていないので効果がなかった。")
            return
        # 本家 FF3 だと成功率や回復量にランダム性があるが、
        # ここでは「確実に蘇生＋最大HPの 1/4 回復」など簡易ルールにしておく
        if max_hp is not None:
            target_state.hp = max(1, max_hp // 4)
        else:
            target_state.hp = 1
        logs.append(
            f"{prefix}{target_name}{target_name}は蘇生した！（HP {target_state.hp}）"
        )
        # 状態異常はそのままとし、必要ならここで解除しても良い
        return

    # ------------------------------------------
    # 4) 状態異常回復系
    #    "Cure Petrification and Partial Petrification"
    #    "Cure Toad"
    #    "Cure Silence"
    #    "Cure Blind"
    #    "Cure Poison"
    # ------------------------------------------
    cured_any = False
    recognized_any = effect_category in {"status_recovery", "status_toggle"}

    if recognized_any:
        status_map = {
            "poison": Status.POISON,
            "blind": Status.BLIND,
            "mini": Status.MINI,
            "silence": Status.SILENCE,
            "toad": Status.TOAD,
            "confusion": Status.CONFUSION,
            "sleep": Status.SLEEP,
            "paralysis": Status.PARALYZE,
            "petrification": Status.PETRIFY,
            "partial petrification": Status.PARTIAL_PETRIFY,
            "partial petrification (1/3)": Status.PARTIAL_PETRIFY,
            "partial petrification (1/2)": Status.PARTIAL_PETRIFY,
            "partial petrification (full)": Status.PETRIFY,
        }

        for ailment in item_statuses:
            status = status_map.get(ailment)
            if status is None:
                continue
            if status in target_state.statuses:
                target_state.statuses.discard(status)
                cured_any = True
            if status in {Status.PARTIAL_PETRIFY, Status.PETRIFY} and hasattr(
                target_state, "partial_petrify_gauge"
            ):
                target_state.partial_petrify_gauge = 0.0

    if cured_any:
        logs.append(
            f"{prefix}{target_name}の状態異常が回復した！（{item_json.get('Name')}）"
        )
        return

    # ★ ここを追加：「治せる状態異常は理解しているが、対象がその状態ではなかった」
    if recognized_any and not cured_any:
        logs.append(
            f"{prefix}{target_name}は回復対象の状態異常ではなかったため、"
            f"{item_json.get('Name')}は効果がなかった。"
        )
        return

    # ------------------------------------------
    # 5) ここまでにマッチしないものは「攻撃アイテム or キーアイテムなど」とみなす
    #    → 戦闘中の攻撃効果は別ヘルパーに任せ、ここでは何もしない。
    # ------------------------------------------
    logs.append(f"{item_json.get('Name')}はこの関数では効果が定義されていません。")


# ============================================================
# アイテムで敵に状態異常を与える共通ヘルパー
# ============================================================


def apply_status_item_to_enemy(
    item_json: Dict[str, Any],
    enemy_state: BattleActorState,
    enemy_name: str,
    rng: Optional[random.Random],
    logs: List[str],
) -> bool:
    """
    「状態異常を与えるだけ」のアイテムを処理するヘルパー。
    例: Tranquilizer ("Inflict Paralysis")

    戻り値:
        True  : 状態異常アイテムとして処理した（命中したかどうかは問わない）
        False : この関数では扱わないアイテムだった（＝他で処理してね）
    """
    spell_info = item_json.get("SpellInfo") or {}
    effect_category = _item_effect_category(item_json)
    ailments_list = _item_status_list(item_json)

    if effect_category not in {"status", "status_toggle"} or not ailments_list:
        # この関数の対象ではない
        return False

    status_map: Dict[str, Tuple[Status, str]] = {
        "poison": (Status.POISON, "毒"),
        "blind": (Status.BLIND, "盲目"),
        "mini": (Status.MINI, "小人"),
        "silence": (Status.SILENCE, "沈黙"),
        "toad": (Status.TOAD, "カエル"),
        "petrification": (Status.PETRIFY, "石化"),
        "ko": (Status.KO, "気絶"),
        "sleep": (Status.SLEEP, "睡眠"),
        "paralysis": (Status.PARALYZE, "麻痺"),
        "partial petrification": (Status.PARTIAL_PETRIFY, "一部石化"),
        "partial petrification (1/3)": (Status.PARTIAL_PETRIFY, "一部石化"),
        "partial petrification (1/2)": (Status.PARTIAL_PETRIFY, "一部石化"),
        "partial petrification (full)": (Status.PETRIFY, "石化"),
        "confusion": (Status.CONFUSION, "混乱"),
    }

    ailment = ailments_list[0]
    status_pair = status_map.get(ailment)
    if status_pair is None:
        return False

    status_enum, status_label = status_pair

    base_acc = spell_info.get("BaseAccuracy")
    if base_acc is None:
        # 精度が未定義ならとりあえず 100% とする
        base_acc = 1.0

    if rng is None:
        rng = random.Random()

    if ailment.startswith("partial petrification"):
        amount = partial_petrify_amount_from_name(ailment)

        apply_partial_petrification(
            target_state=enemy_state,
            amount=amount,
            target_name=enemy_name,
            logs=logs,
        )
        return True

    enemy_state.statuses.add(status_enum)
    if status_enum == Status.KO:
        enemy_state.hp = 0
    logs.append(f"{enemy_name}に{status_label}が効いた！")

    return True


# ============================================================
# アイテム → SpellInfo に変換するヘルパー
# ============================================================


def spell_from_item(item_json: Dict[str, Any]) -> SpellInfo:
    spell_info = item_json.get("SpellInfo") or {}
    weapon_spell = item_json.get("WeaponSpell") or {}

    # ----------------------------
    # 1) Element / Elements / Elemental を読む（共通パーサ）
    # ----------------------------
    elem_raw = (
        spell_info.get("Element")
        or spell_info.get("Elements")
        or spell_info.get("Elemental")  # 念のため
        or weapon_spell.get("Element")
        or weapon_spell.get("Elements")
    )

    elements: list[str] = parse_elements(elem_raw)

    # Power/Accuracy
    power = int(spell_info.get("BasePower", 0))
    base_acc = float(spell_info.get("BaseAccuracy", 1.0) or 1.0)
    acc_percent = int(round(base_acc * 100))

    # Magic type はデータ側の Type / MagicType / effect_category を優先する
    magic_type_raw = normalize_text_basic(
        spell_info.get("MagicType")
        or weapon_spell.get("Type")
        or item_json.get("MagicType")
        or ""
    )
    if "black" in magic_type_raw:
        magic_type = "black"
    elif "white" in magic_type_raw:
        magic_type = "white"
    elif "summon" in magic_type_raw:
        magic_type = "summon"
    else:
        effect_category = _item_effect_category(item_json)
        if effect_category in {"damage", "set_hp_critical", "drain"}:
            magic_type = "black"
        else:
            magic_type = "white"

    return SpellInfo(
        power,
        acc_percent,
        magic_type,
        elements,  # ★正しく ["air","ice"] になる
        False,
    )


def weapon_spell_magic_base_power(
    caster_stats: FinalCharacterStats,
    item_json: Dict[str, Any],
) -> int:
    spell_json = item_json.get("WeaponSpell") or {}
    spell_info = item_json.get("SpellInfo") or {}
    base_power = int(
        spell_json.get("BasePower", spell_info.get("BasePower", 0)) or 0
    )
    magic_type = normalize_text_basic(
        spell_json.get("Type") or spell_info.get("MagicType") or ""
    )

    if "white" in magic_type:
        return base_power + max(0, int(getattr(caster_stats, "mind", 0)) // 2)

    return base_power + max(0, int(getattr(caster_stats, "intelligence", 0)) // 2)


def weapon_spell_heal_amount_to_actor(
    *,
    caster_stats: FinalCharacterStats,
    item_json: Dict[str, Any],
    rng: Optional[random.Random] = None,
) -> int:
    if rng is None:
        rng = random.Random()

    base_power = weapon_spell_magic_base_power(caster_stats, item_json)
    factor = rng.uniform(1.0, 1.5)
    return max(int(base_power * factor), 0)


def weapon_spell_damage_char_to_enemy(
    *,
    caster_stats: FinalCharacterStats,
    item_json: Dict[str, Any],
    enemy: FinalEnemyStats,
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
) -> int:
    if rng is None:
        rng = random.Random()

    base_power = weapon_spell_magic_base_power(caster_stats, item_json)
    factor = rng.uniform(1.0, 1.5)
    raw = int(base_power * factor)
    dmg = max(raw - enemy.magic_defense, 0)
    dmg = apply_element_relation_to_damage(int(dmg), element_relation)
    return int(dmg)


# アイテム攻撃専用のダメージ関数
def item_damage_char_to_enemy(
    item_spell: SpellInfo,
    item_json: Dict[str, Any],
    enemy: FinalEnemyStats,
    element_relation: ElementRelation = "normal",
    rng: Optional[random.Random] = None,
) -> int:
    """
    FF3(DS)仕様の攻撃アイテムダメージ。
      - Power = item_spell.power (= BasePower)
      - Multiplier = item_json["Multiplier"] 固定（使用者ステ非依存）
      - Accuracy = 100%固定（blind無視）
    """
    if rng is None:
        rng = random.Random()

    base_power = int(item_spell.power)
    multiplier = int(item_json.get("Multiplier", 3) or 3)

    total = 0
    for _ in range(multiplier):
        # 魔法の1ヒットと同じ基礎ダメロール（factor 1.0〜1.5）
        factor = rng.uniform(1.0, 1.5)
        raw = int(base_power * factor)

        dmg = raw - enemy.magic_defense
        if dmg < 0:
            dmg = 0
        total += dmg

    total = apply_element_relation_to_damage(int(total), element_relation)
    return int(total)
