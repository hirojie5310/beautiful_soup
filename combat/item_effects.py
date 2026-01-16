# ============================================================
# item_effects: アイテム関連（効果系）

# apply_item_effect_to_actor	アイテムの効果（回復・蘇生・バフなど）を対象1体に適用する
# apply_status_item_to_enemy	「状態異常だけ」を与えるタイプのアイテムを判定し、敵ステートに状態異常を付与する共通ヘルパー
# spell_from_item	アイテムJSONからSpellInfo（威力・命中・属性など）を組み立てる変換ヘルパー
# item_damage_char_to_enemy	攻撃アイテムのSpellInfoと敵ステータスからダメージ量を計算する
# ============================================================

import random
from typing import Optional, Dict, Any, List, Tuple

from combat.enums import ElementRelation, Status
from combat.models import (
    FinalCharacterStats,
    BattleActorState,
    SpellInfo,
    FinalEnemyStats,
)
from combat.elements import parse_elements, apply_element_relation_to_damage
from combat.status_effects import *


# ============================================================
# アイテム効果用ヘルパ（回復・蘇生・状態異常回復）
# ============================================================


def apply_item_effect_to_actor(
    item_json: Dict[str, Any],
    target_state: BattleActorState,
    *,
    target_name: str = "対象",
    max_hp: Optional[int] = None,
    logs: Optional[List[str]] = None,
    target_stats: Optional[FinalCharacterStats] = None,
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
    effect_text = (spell_info.get("Effect") or "").lower()
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
    name_lower = (item_json.get("Name") or "").strip().lower()
    spell_effect = (item_json.get("SpellEffect") or "").strip().lower()

    is_haste_item = (
        "enhance accuracy and attack multiplier" in effect_text
        or spell_effect == "haste"
        or name_lower == "bacchus's cider"
    )

    if is_haste_item:
        # ステータス情報が無いと攻撃力・攻撃回数をいじれないので念のため
        if target_stats is None:
            if logs is not None:
                logs.append(f"{prefix} " f"しかし攻撃力アップ効果を適用できなかった…")
            return

        if rng is None:
            rng = random.Random()

        mind = target_stats.mind

        # ✅ 命中率 = BaseAccuracy + mind/2 を共通ヘルパに委譲
        base_acc = spell_info.get("BaseAccuracy")
        if base_acc is None:
            base_acc = 1.0

        hit_percent = calc_buff_hit_percent(base_acc, mind)

        # 命中判定
        if rng.random() * 100.0 >= hit_percent:
            if logs is not None:
                logs.append(f"{prefix} " f"しかし何も起こらなかった…")
            return

        # --- ここから成功時のバフ計算（Haste と同様）---
        L = target_stats.level
        J = target_stats.job_level
        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1

        base_power = float(spell_info.get("BasePower", 5))

        # Bacchus's Cider の攻撃回数増加量（デフォルト3）
        mul_default = int(spell_info.get("Multiplier") or 3)

        # ✅ 実際の攻撃力・攻撃回数の更新は共通ヘルパへ
        old_main_pow, old_off_pow, old_main_mul, old_off_mul = apply_haste_buff(
            target_stats,
            base_power=base_power,
            base_factor=base_factor,
            mul_default=mul_default,
            rng=rng,
        )

        if logs is not None:
            logs.append(
                f"{prefix} "
                f"攻撃力 右手 {old_main_pow}→{target_stats.main_power}"
                + (
                    f" / 左手 {old_off_pow}→{target_stats.off_power}"
                    if old_off_pow > 0
                    else ""
                )
                + f"、攻撃回数 右手 {old_main_mul}→{target_stats.main_atk_multiplier}"
                + (
                    f" / 左手 {old_off_mul}→{target_stats.off_atk_multiplier}"
                    if old_off_mul > 0
                    else ""
                )
                + " に上がった。"
            )

        return

    # ------------------------------------------
    # 0-b) Protect系バフアイテム（Turtle Shell）
    #    Effect: "Enhance Defense and Magic Defense"
    #    SpellEffect: "Protect"
    #    Multiplier は 3 で固定（※現状は未使用）
    # ------------------------------------------
    is_protect_item = (
        "enhance defense and magic defense" in effect_text
        or spell_effect == "protect"
        or name_lower == "turtle shell"
    )

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

        # 命中率 = BaseAccuracy + mind/2 （0〜100 にクランプ）
        base_acc = spell_info.get("BaseAccuracy")
        if base_acc is None:
            base_acc = 1.0
        hit_percent = calc_buff_hit_percent(base_acc, mind)

        if rng.random() * 100.0 >= hit_percent:
            logs.append(f"{prefix} " f"しかし何も起こらなかった…")
            return

        # --- ここから成功時のバフ計算（白魔法 Protect と同じ式）---
        base_factor = (mind // 16) + (L // 16) + (J // 32) + 1
        base_power = float(spell_info.get("BasePower", 5))

        old_def, old_mdef = apply_protect_buff(
            target_stats,
            base_power=base_power,
            base_factor=base_factor,
            rng=rng,
        )

        logs.append(
            f"{prefix} "
            f"防御力 {old_def}→{target_stats.defense}、"
            f"魔法防御 {old_mdef}→{target_stats.magic_defense} に上がった。"
        )
        return

    # ------------------------------------------
    # 1) HP 回復系 ("Restore target's HP")
    # ------------------------------------------
    if "restore target's hp" in effect_text:
        if is_ko:
            logs.append(f"{prefix}{target_name}は戦闘不能のため効果がなかった…")
            return
        heal = value
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
    if "restore target to full hp and mp" in effect_text:
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
    if "revive from ko" in effect_text:
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
    recognized_any = False  # ★ 追加：「この関数で認識している Cure かどうか」

    if "cure poison" in effect_text:
        recognized_any = True
        if Status.POISON in target_state.statuses:
            target_state.statuses.discard(Status.POISON)
            cured_any = True

    if "cure blind" in effect_text:
        recognized_any = True
        if Status.BLIND in target_state.statuses:
            target_state.statuses.discard(Status.BLIND)
            cured_any = True

    if "cure or inflict mini" in effect_text:
        recognized_any = True
        if Status.MINI in target_state.statuses:
            target_state.statuses.discard(Status.MINI)
            cured_any = True

    if "cure silence" in effect_text:
        recognized_any = True
        if Status.SILENCE in target_state.statuses:
            target_state.statuses.discard(Status.SILENCE)
            cured_any = True

    if "cure toad" in effect_text:
        recognized_any = True
        if Status.TOAD in target_state.statuses:
            target_state.statuses.discard(Status.TOAD)
            cured_any = True

    if "petrification" in effect_text:
        # "Cure Petrification and Partial Petrification" をまとめて処理
        recognized_any = True
        if (
            Status.PETRIFY in target_state.statuses
            or Status.PARTIAL_PETRIFY in target_state.statuses
        ):
            target_state.statuses.discard(Status.PETRIFY)
            target_state.statuses.discard(Status.PARTIAL_PETRIFY)
            # ★ 部分石化ゲージも 0 にリセット
            if hasattr(target_state, "partial_petrify_gauge"):
                target_state.partial_petrify_gauge = 0.0
            cured_any = True

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
    effect_text = (spell_info.get("Effect") or "").lower()

    # 今の JSON だと "Inflict Paralysis" などが入っている。
    # 必要に応じて "inflict poison" なども増やせるようにマッピングで書いておく。
    status_map: Dict[str, Tuple[Status, str]] = {
        "inflict poison": (Status.POISON, "毒"),
        "inflict blind": (Status.BLIND, "盲目"),
        "inflict mini": (Status.MINI, "小人"),
        "inflict silence": (Status.SILENCE, "沈黙"),
        "inflict toad": (Status.TOAD, "カエル"),
        "inflict petrification": (Status.PETRIFY, "石化"),
        "inflict ko": (Status.KO, "気絶"),
        "inflict sleep": (Status.SLEEP, "睡眠"),
        "inflict paralysis": (Status.PARALYZE, "麻痺"),
        "inflict partial petrification": (Status.PARTIAL_PETRIFY, "一部石化"),
        "inflict confusion": (Status.CONFUSION, "混乱"),
        # "inflict poison": (Status.POISON, "毒"),
        # "inflict blind": (Status.BLIND, "暗闇"),
        # ... 将来増やすときはここに追加
    }

    key = None
    for k in status_map.keys():
        if k in effect_text:
            key = k
            break

    if key is None:
        # この関数の対象ではない
        return False

    status_enum, status_label = status_map[key]

    base_acc = spell_info.get("BaseAccuracy")
    if base_acc is None:
        # 精度が未定義ならとりあえず 100% とする
        base_acc = 1.0

    if rng is None:
        rng = random.Random()

    if "inflict partial petrification" in effect_text:
        # どの段階か判定（アイテムJSONのEffectやNameに含まれる前提）
        src = (effect_text + " " + str(item_json.get("Name", ""))).lower()
        amount = partial_petrify_amount_from_name(src)

        # 命中したらゲージ処理へ
        if rng.random() < float(base_acc):
            apply_partial_petrification(
                target_state=enemy_state,
                amount=amount,
                target_name=enemy_name,
                logs=logs,
            )
        else:
            logs.append(f"{enemy_name}には一部石化が入らなかった…")

        return True

    # ★ ここを追加：通常の状態異常付与
    if rng.random() < float(base_acc):
        enemy_state.statuses.add(status_enum)
        logs.append(f"{enemy_name}に{status_label}が効いた！")
    else:
        logs.append(f"{enemy_name}には{status_label}が効かなかった…")

    return True


# ============================================================
# アイテム → SpellInfo に変換するヘルパー
# ============================================================


def spell_from_item(item_json: Dict[str, Any]) -> SpellInfo:
    spell_info = item_json.get("SpellInfo") or {}

    # ----------------------------
    # 1) Element / Elements / Elemental を読む（共通パーサ）
    # ----------------------------
    elem_raw = (
        spell_info.get("Element")
        or spell_info.get("Elements")
        or spell_info.get("Elemental")  # 念のため
    )

    elements: list[str] = parse_elements(elem_raw)

    # ----------------------------
    # 2) 無い場合は Effect から推定
    # ----------------------------
    if not elements:
        effect_text = (spell_info.get("Effect") or "").lower()
        spell_effect_name = str(item_json.get("SpellEffect") or "").lower()
        src = effect_text + " " + spell_effect_name

        def has(*keys):
            return any(k in src for k in keys)

        inferred: List[str] = []
        if has("air", "wind", "aero"):
            inferred.append("air")  # ★ Air で統一
        if has("ice", "blizzard"):
            inferred.append("ice")
        if has("fire", "fira", "firaga"):
            inferred.append("fire")
        if has("thunder", "lightning", "bolt", "zeus"):
            inferred.append("lightning")
        if has("earth", "quake"):
            inferred.append("earth")
        if has("holy"):
            inferred.append("holy")
        if has("dark"):
            inferred.append("dark")
        if has("recovery", "drain", "absorb hp"):
            inferred.append("recovery")

        elements = inferred

    # Power/Accuracy
    power = int(spell_info.get("BasePower", 0))
    base_acc = float(spell_info.get("BaseAccuracy", 1.0) or 1.0)
    acc_percent = int(round(base_acc * 100))

    # Magic type（適当に black/white）
    effect_text = (spell_info.get("Effect") or "").lower()
    if "deal" in effect_text and "damage" in effect_text:
        magic_type = "black"
    else:
        magic_type = "white"

    return SpellInfo(
        power=power,
        accuracy_percent=acc_percent,
        magic_type=magic_type,
        elements=elements,  # ★正しく ["air","ice"] になる
    )


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
    return max(0, int(total))
