# ============================================================
# status_effects: 状態異常, バフ/デバフ

# <状態異常>
# apply_partial_petrification	部分石化の蓄積処理
# apply_partial_petrify_from_status_attack	敵のStatusAttackによる部分石化の蓄積処理（apply_partial_petrificationに一本化）
# partial_petrify_amount_from_name	名前からamountを返す小ヘルパー（部分石化）
# ff3_confused_self_dummy_enemy	混乱時の「自傷」用に、キャラ自身を防御側として扱うためのダミー敵ステータスを作る
# ff3_confused_self_dummy_char	混乱時の「敵の自傷」用に、敵自身を“キャラの防御側”として扱うダミーを作る
# apply_status_spell_to_enemy	魔法/召喚が持つ状態異常情報を解釈し、敵に状態異常を付与する共通ヘルパー
# _compute_status_success_prob_for_enemy_spell	敵キャスターとキャラのステータスから状態異常スペルの成功確率を近似計算する
# apply_status_spell_to_char	敵が唱えた状態異常系スペルをキャラに適用する共通ヘルパー,
# _apply_enemy_spell_ailments_to_char	敵スペルの状態異常定義を基に、各種状態異常（Erase/Toad/Mini等）をキャラに適用する薄いラッパー
# _get_status_name_from_monster_spell	monsters.jsonのSpellsエントリから状態異常名を取り出すヘルパー

# <バフ/デバフ>
# apply_reflect_to_actor	対象アクターのReflectチャージ数を設定し、開始/更新/消失をログに出力する
# calc_buff_hit_percent	Haste/Protect系バフのBaseAccuracyとMINDからバフ命中率(0〜100%)を算出する
# apply_haste_buff	Haste系バフの効果量を計算してキャラの攻撃力/攻撃回数を強化し、適用前の値を返す
# apply_protect_buff	Protect系バフの効果量を計算してキャラの防御/魔法防御を強化し、適用前の値を返す
# ============================================================

import random
from typing import Optional, Dict, Any, List

from combat.enums import Status
from combat.models import BattleActorState, FinalCharacterStats, FinalEnemyStats
from combat.models import EnemyCasterStats
from combat.spell_metadata import spell_effect_category, spell_status_text
from utils.text_normalize import normalize_text_basic


def _ff3_raze_level_threshold(attacker_level: int) -> int:
    """NES版FF3 FAQ準拠: floor(floor(attacker/2) * 3 / 2)。"""
    return ((max(int(attacker_level), 0) // 2) * 3) // 2


def _status_immunity_keys_for_char(char_stats: FinalCharacterStats) -> set[str]:
    """キャラの装備由来ステータス異常無効を正規化して返す。"""
    raw_immunities = getattr(char_stats, "status_immunities", ()) or ()
    immune_set = {normalize_text_basic(x) for x in raw_immunities if isinstance(x, str)}
    if "confusion" in immune_set:
        immune_set.add("confuse")
    return immune_set


# <状態異常> =============================================================================


def apply_partial_petrification(
    target_state: BattleActorState,
    amount: float,
    target_name: str,
    logs: list[str],
) -> None:
    """
    部分石化の蓄積処理。
    amount: 1/3, 1/2, 1.0 などを加算する。
    累積値が 1.0 以上になったら Petrification に移行。
    """
    if amount <= 0:
        return

    old = getattr(target_state, "partial_petrify_gauge", 0.0)
    new = old + amount
    if new > 1.0:
        new = 1.0
    target_state.partial_petrify_gauge = new

    if new >= 1.0:
        # 完全に石化
        target_state.statuses.discard(Status.PARTIAL_PETRIFY)
        target_state.statuses.add(Status.PETRIFY)
        target_state.statuses.add(Status.KO)  # ← 修正！
        target_state.hp = 0  # 戦闘離脱ルールに合わせて HP 0 にしておく
        logs.append(f"{target_name}は部分石化が進行し、完全に石化してしまった！")
    else:
        # まだ途中段階
        target_state.statuses.add(Status.PARTIAL_PETRIFY)
        logs.append(f"{target_name}は部分的に石化した！（蓄積 {new:.2f}）")


def apply_partial_petrify_from_status_attack(
    target_state: BattleActorState,
    status_attack_name: str | None,
    logs: list[str],
    target_name: str,
) -> None:
    """敵の Status Attack による部分石化の蓄積処理（apply_partial_petrification に一本化）"""
    if not status_attack_name:
        return

    # 部分石化以外はスルー
    if not status_attack_name.startswith("Partial Petrification"):
        return

    # --- どのランクの部分石化かで加算量を決定 ---
    amount = partial_petrify_amount_from_name(status_attack_name)

    # --- 蓄積処理は apply_partial_petrification に全委譲 ---
    apply_partial_petrification(
        target_state=target_state,
        amount=amount,
        target_name=target_name,
        logs=logs,
    )


# 名前から amount を返す小ヘルパー（部分石化）
def partial_petrify_amount_from_name(name: str) -> float:
    n = normalize_text_basic(name)
    if "1/3" in n:
        return 1.0 / 3.0
    if "1/2" in n:
        return 1.0 / 2.0
    if "full" in n:
        return 1.0
    return 1.0  # 保険


# キャラクター自傷用のダミーキャラを作るヘルパ
def ff3_confused_self_dummy_enemy(char: FinalCharacterStats) -> FinalEnemyStats:
    """
    混乱時の「自傷」用に、キャラ自身を防御側として扱うためのダミー敵ステータスを作る。
    """
    return FinalEnemyStats(
        name=f"{char.row}_self",  # 適当でOK
        hp=char.max_hp,  # 使われないが入れておく
        level=char.level,
        job_level=char.job_level,
        # 攻撃パラメータ（ここは実際は使われない）
        attack_power=0,
        attack_multiplier=0,
        accuracy_percent=0,
        # 防御パラメータ：ここが重要
        defense=char.defense,
        defense_multiplier=char.defense_multiplier,
        evasion_percent=char.evasion_percent,
        magic_defense=char.magic_defense,
        magic_def_multiplier=char.magic_def_multiplier,
        magic_resistance_percent=char.magic_resistance,  # ← ここに修正
        # 行動順には使わないが、一応整合性のため入れておく
        agility=char.agility,
    )


# 敵自傷用のダミーキャラを作るヘルパ
def ff3_confused_self_dummy_char(enemy: FinalEnemyStats) -> FinalCharacterStats:
    """
    混乱時の「敵の自傷」用に、敵自身を“キャラの防御側”として扱うダミーを作る。
    physical_damage_enemy_to_char(enemy, char) を使い回すための器。
    """
    return FinalCharacterStats(
        level=enemy.level,
        job_level=enemy.job_level,
        job_skill_point=0,
        max_hp=enemy.hp,
        strength=0,
        agility=enemy.agility,
        vitality=0,
        intelligence=0,
        mind=0,
        row="front",
        main_power=0,
        main_accuracy=0,
        main_atk_multiplier=1,
        off_power=0,
        off_accuracy=0,
        off_atk_multiplier=1,
        # ★追加：武器属性（例：二刀流/長射程フラグ等）
        main_two=False,
        main_long=False,
        off_two=False,
        off_long=False,
        defense=enemy.defense,
        defense_multiplier=enemy.defense_multiplier,
        evasion_percent=enemy.evasion_percent,
        magic_defense=enemy.magic_defense,
        magic_def_multiplier=enemy.magic_def_multiplier,
        magic_resistance=enemy.magic_resistance_percent,
        shield_count=0,
    )


# ============================================================
# Spellで敵に状態異常を与える共通ヘルパー
# ============================================================


def apply_status_spell_to_enemy(
    spell_json: Dict[str, Any],
    enemy_state: BattleActorState,
    enemy_json: Dict[str, Any],
    enemy_name: str,
    rng: random.Random,
    logs: List[str],
    *,
    caster_stats: Optional[FinalCharacterStats] = None,  # ★追加
    summon_child_name: Optional[str] = None,
) -> bool:
    """
    魔法/召喚が持つ状態異常を敵に付与する。
    付与処理対象の魔法なら True を返す（成功/失敗は問わない）。
    """

    # ---- 0) 召喚の子スペル(Status)を拾う ----
    # Summon Magic の場合、spell_json["Spells"] に子データがあり、そこに Status が入る
    if spell_json.get("Type") == "Summon Magic" and summon_child_name:
        children = spell_json.get("Spells", [])

        # ① 完全一致（最優先）
        child = next((c for c in children if c.get("Name") == summon_child_name), None)

        # ② フル名 "Ramuh: Mind Blast" と suffix "Mind Blast" ともに対応
        if child is None:
            # 渡された名前の suffix を抽出
            if ":" in summon_child_name:
                suffix = summon_child_name.split(":", 1)[1].strip()
            else:
                suffix = summon_child_name.strip()

            # ③ suffix 完全一致
            child = next((c for c in children if c.get("Name") == suffix), None)

            # ④ 子スペルが "Ramuh: XXX" 形式なら suffix で比較
            if child is None:
                child = next(
                    (
                        c
                        for c in children
                        if ":" in c.get("Name", "")
                        and c["Name"].split(":", 1)[1].strip() == suffix
                    ),
                    None,
                )

        # ⑤ 状態異常を spell_json に注入
        if child:
            child_status = spell_status_text(child)
            if child_status and child_status != "-":
                spell_json = dict(spell_json)  # shallow copy
                spell_json["StatusAilment"] = child_status

    # ★ スペル名は最初に拾っておく（Name / name 両対応）
    spell_name = normalize_text_basic(
        spell_json.get("Name") or spell_json.get("name") or ""
    )

    # ---- 1) 状態異常リスト抽出（StatusAilment / StatusAilments） ----
    ailments = spell_status_text(spell_json)

    ailments_list: List[str] = []
    if isinstance(ailments, str) and ailments.strip():
        ailments_list = [
            normalize_text_basic(a) for a in ailments.split(",") if a.strip()
        ]

    # ★ ここでスペル名を取得（name / Name どちらにも対応）
    spell_name = normalize_text_basic(
        spell_json.get("Name") or spell_json.get("name") or ""
    )

    # ---- 1.5) Summon 子スペルの Status を拾う ----
    # expand_summon_magic_as_children 済みだと Type="Summon" の子が spells_by_name に入る。
    # 子は StatusAilment ではなく Status を持つのでここで吸う。
    if not ailments_list:
        raw_type = normalize_text_basic(spell_json.get("Type", ""))
        if raw_type == "summon" or raw_type.startswith("summon"):
            child_status = spell_status_text(spell_json)
            if child_status and child_status != "-":
                ailments_list = [
                    normalize_text_basic(a)
                    for a in child_status.split(",")
                    if a.strip()
                ]

    if not ailments_list and spell_effect_category(spell_json) == "status":
        child_status = spell_status_text(spell_json)
        if child_status and child_status != "-":
            ailments_list = [
                normalize_text_basic(a)
                for a in child_status.split(",")
                if a.strip()
            ]

    # ---- 2) それでも無い場合は Effect から抽出（Mini/Toad等含む） ----
    if not ailments_list:
        effect_text = normalize_text_basic(spell_json.get("Effect") or "")

        # パターンA: "Inflict xxx"
        if "inflict" in effect_text:
            # "inflict ko" / "inflict petrification" 等を吸う
            after = effect_text.split("inflict", 1)[1].strip()
            after = after.split("for")[0].strip()
            ailments_list = [after]

        # パターンB: Mini
        elif "miniaturize" in effect_text:
            ailments_list = ["mini"]

        # パターンC: Toad
        elif "toad" in effect_text and "turn target into a toad" in effect_text:
            ailments_list = ["toad"]

    # ★ ここで Erase を特別扱いする（return False より前）
    if not ailments_list and spell_name == "erase":
        ailments_list = ["erase"]

    if not ailments_list:
        return False  # 状態異常魔法ではない

    # ---- 2.5) Erase（黒魔法Lv5 全体即死）専用：ここでダミー状態異常を立てる ----
    if not ailments_list and spell_name == "erase":
        ailments_list = ["erase"]

    if not ailments_list:
        return False  # 状態異常魔法ではない

    # ---- 3) 敵の Immune 参照 ----
    immune_list = (
        enemy_json.get("StatusAilmentVulnerability", {}).get("Immune", []) or []
    )
    immune_set = set(normalize_text_basic(x) for x in immune_list)

    # ---- 3.5) Toad / Mini 専用処理（即KO系） ----
    for ail in ailments_list:
        if ail not in ("toad", "mini"):
            continue

        # 免疫なら即終了
        if ail in immune_set:
            logs.append(f"{enemy_name}には{ail.title()}が効かなかった！（無効）")
            return True

        # 命中率（Magic Hit% = BaseAccuracy% + Mind/2）
        base_acc = float(spell_json.get("BaseAccuracy") or 0.0)
        if base_acc <= 1.0:
            base_acc *= 100.0  # 0.8 → 80%

        mind = caster_stats.mind if caster_stats is not None else 0
        hit_percent = base_acc + (mind / 2.0)
        hit_percent = max(0.0, min(hit_percent, 100.0))

        roll = rng.random() * 100.0
        spell_label = spell_json.get("Name") or ("Toad" if ail == "toad" else "Mini")

        if roll < hit_percent:
            enemy_state.statuses.add(Status.KO)
            enemy_state.hp = 0
            logs.append(
                f"{enemy_name}は《{spell_label}》で逃げ出し、戦闘不能になった！"
                f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )
        else:
            logs.append(
                f"{enemy_name}には《{spell_label}》が効かなかった…"
                f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )

        return True  # Toad/Mini 用処理はここで完了

    # ---- 3.6) Erase / Raze 専用処理（即死系）----
    instant_ko_spell = None
    if "erase" in ailments_list:
        instant_ko_spell = "erase"
    elif spell_name == "raze":
        instant_ko_spell = "raze"

    if instant_ko_spell is not None:
        target_lv = int(enemy_json.get("Level", 1) or 1)
        caster_lv = caster_stats.level if caster_stats is not None else 1

        base_acc = float(spell_json.get("BaseAccuracy") or 0.0)
        if base_acc <= 1.0:
            base_acc *= 100.0

        mind = caster_stats.mind if caster_stats is not None else 0
        hit_percent = base_acc + (mind / 2.0)

        if instant_ko_spell == "raze":
            level_threshold = _ff3_raze_level_threshold(caster_lv)
            if target_lv >= level_threshold:
                hit_percent = 0.0
        else:
            if target_lv >= caster_lv * 0.75:
                hit_percent = 0.0

        hit_percent = max(0.0, min(hit_percent, 100.0))
        roll = rng.random() * 100.0
        spell_label = spell_json.get("Name") or instant_ko_spell.title()

        if roll < hit_percent:
            enemy_state.statuses.add(Status.KO)
            enemy_state.hp = 0
            if instant_ko_spell == "raze":
                logs.append(
                    f"{enemy_name}は《{spell_label}》の効果で倒れた！"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
            else:
                logs.append(
                    f"{enemy_name}は《{spell_label}》の効果で消し去られた！"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
        else:
            if instant_ko_spell == "raze" and hit_percent <= 0.0:
                level_threshold = _ff3_raze_level_threshold(caster_lv)
                logs.append(
                    f"{enemy_name}には《{spell_label}》が効かなかった…"
                    f"（対象Lv{target_lv} >= 閾値{level_threshold} で命中率0.0% 判定{roll:.1f}）"
                )
            else:
                logs.append(
                    f"{enemy_name}には《{spell_label}》が効かなかった…"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )

        return True  # 即死系専用処理はここで完了

    # ---- 4) 名前→Status enum 対応 ----
    status_map = {
        "poison": Status.POISON,
        "blind": Status.BLIND,
        "mini": Status.MINI,
        "silence": Status.SILENCE,
        "toad": Status.TOAD,
        "confusion": Status.CONFUSION,
        "confuse": Status.CONFUSION,  # 表記ゆれ対策
        "sleep": Status.SLEEP,
        "paralysis": Status.PARALYZE,
        "petrification": Status.PETRIFY,
        "ko": Status.KO,
        "partial petrification": Status.PARTIAL_PETRIFY,
        "partial petrification (1/3)": Status.PARTIAL_PETRIFY,
        "partial petrification (1/2)": Status.PARTIAL_PETRIFY,
        "partial petrification (full)": Status.PETRIFY,
    }

    # ---- 5) 命中率 ----
    acc = spell_json.get("BaseAccuracy")
    if acc is None:
        # Summon子スペルは Accuracy が 0-100 の整数で入る場合がある
        acc = spell_json.get("Accuracy")

    if acc is None:
        acc = 1.0

    acc = float(acc)
    if acc > 1.0:  # 例: 80 → 0.8
        acc = acc / 100.0

    # acc: 0.0〜1.0 の命中率
    hit_percent = acc * 100.0

    # ---- 6) 付与実行 ----
    for a in ailments_list:
        key = normalize_text_basic(a)

        if key in immune_set or (
            key.startswith("partial petrification")
            and "partial petrification" in immune_set
        ):
            logs.append(f"{enemy_name}には効かなかった！（{a}無効）")
            continue

        st = status_map.get(key)
        if st is None:
            logs.append(f"※ 未対応の状態異常: {a}")
            continue

        # ★ ロールを保持してログに使う
        roll = rng.random()
        roll_percent = roll * 100.0

        if roll < acc:
            if st == Status.PARTIAL_PETRIFY:
                amount = partial_petrify_amount_from_name(a.title())
                apply_partial_petrification(
                    target_state=enemy_state,
                    amount=amount,
                    target_name=enemy_name,
                    logs=logs,
                )
                logs.append(
                    f"{enemy_name}は部分石化した！（魔法："
                    f"命中率{hit_percent:.1f}% 判定{roll_percent:.1f}）"
                )
            else:
                enemy_state.statuses.add(st)

                if st == Status.KO:
                    # 即死系：HP0 にして戦闘不能扱い
                    enemy_state.hp = 0
                    logs.append(
                        f"{enemy_name}はKO状態になった！（魔法："
                        f"命中率{hit_percent:.1f}% 判定{roll_percent:.1f}）"
                    )

                elif st == Status.PETRIFY:
                    # 完全石化：KO も付けて戦闘離脱扱い
                    enemy_state.statuses.add(Status.KO)
                    enemy_state.hp = 0
                    logs.append(
                        f"{enemy_name}は完全に石化してしまった！（魔法："
                        f"命中率{hit_percent:.1f}% 判定{roll_percent:.1f}）"
                    )

                else:
                    # それ以外の通常状態異常
                    logs.append(
                        f"{enemy_name}は{st.name}状態になった！（魔法："
                        f"命中率{hit_percent:.1f}% 判定{roll_percent:.1f}）"
                    )
        else:
            logs.append(
                f"{enemy_name}は{a}を回避した！（魔法："
                f"命中率{hit_percent:.1f}% 判定{roll_percent:.1f}）"
            )

    # ★保険：ここまで来たら適用なし
    return False


# ============================================================
# 状態異常の発生確率モデル（追加）
# ============================================================


def _compute_status_success_prob_for_enemy_spell(
    enemy_caster: EnemyCasterStats,
    char: FinalCharacterStats,
) -> float:
    """
    敵スペルによる状態異常の「成功確率」の近似。
    ・MagicMultiplier 回の試行
    ・1回ごとの成功率 ≒ 魔法命中% - キャラ魔法抵抗%
    """
    n_hits = max(enemy_caster.magic_multiplier - char.magic_def_multiplier, 0)
    if n_hits <= 0:
        return 0

    hit_rate = max(0, min(enemy_caster.magic_accuracy_percent, 100)) / 100.0
    resist_rate = max(0, min(char.magic_resistance, 100)) / 100.0
    net_hit = max(hit_rate - resist_rate, 0.0)
    if net_hit <= 0.0:
        return 0

    prob = 1.0 - (1.0 - net_hit) ** n_hits
    return max(0.0, min(prob, 1.0))


# ============================================================
# 共通ヘルパー（特殊な効果の魔法）
# ============================================================


# 状態異常系（Toad / Mini / Erase）を敵→キャラに対応させる
def apply_status_spell_to_char(
    spell_json: dict,
    char_state: BattleActorState,
    char_stats: FinalCharacterStats,
    char_name: str,
    rng: random.Random,
    logs: list[str],
) -> bool:
    """
    敵が唱えた状態異常魔法をキャラに適用する。
    True: 「状態異常魔法として処理した」（成否は問わない）
    False: この関数の対象ではない
    """

    # 1) まずは敵用と同じように ailments_list を抽出する（ほぼコピペでOK）
    ailments = spell_json.get("StatusAilment") or spell_json.get("StatusAilments") or ""
    ailments_list: list[str] = []
    if isinstance(ailments, str) and ailments.strip():
        ailments_list = [
            normalize_text_basic(a) for a in ailments.split(",") if a.strip()
        ]

    # 2) まだ取れなかったら Effect から推定（Mini/Toad など）
    if not ailments_list:
        effect_text = normalize_text_basic(spell_json.get("Effect") or "")
        if "miniaturize" in effect_text:
            ailments_list = ["mini"]
        elif "toad" in effect_text and "turn target into a toad" in effect_text:
            ailments_list = ["toad"]

    # 2.x) Effect から抽出（Inflict / Mini / Toad）
    if not ailments_list:
        effect_text = normalize_text_basic(spell_json.get("Effect") or "")

        if "inflict" in effect_text:
            after = effect_text.split("inflict", 1)[1].strip()
            after = after.split("for")[0].strip()
            ailments_list = [after]

        elif "miniaturize" in effect_text:
            ailments_list = ["mini"]

        elif "toad" in effect_text and "turn target into a toad" in effect_text:
            ailments_list = ["toad"]

    # 3) Erase / Toad / Mini 特別扱い
    spell_name = normalize_text_basic(
        spell_json.get("Name") or spell_json.get("name") or ""
    )

    if not ailments_list:
        if spell_name == "erase":
            ailments_list = ["erase"]
        elif spell_name == "toad":
            ailments_list = ["toad"]
        elif spell_name == "mini":
            ailments_list = ["mini"]

    if not ailments_list:
        return False  # 状態異常魔法ではない

    # 4) キャラ側の状態異常無効（装備由来）を参照する
    immune_set = _status_immunity_keys_for_char(char_stats)

    # 5) 命中率を決める（敵なので Mind ではなく、ひとまず BaseAccuracy のみで判定）
    acc = spell_json.get("BaseAccuracy")
    if acc is None:
        acc = spell_json.get("Accuracy")
    if acc is None:
        acc = 1.0
    acc = float(acc)
    if acc > 1.0:  # 80 → 0.8
        acc = acc / 100.0
    hit_percent = acc * 100.0

    # 6) 名前→Status enum の対応表（敵用と共通でOK）
    status_map = {
        "poison": Status.POISON,
        "blind": Status.BLIND,
        "mini": Status.MINI,
        "silence": Status.SILENCE,
        "toad": Status.TOAD,
        "confusion": Status.CONFUSION,
        "confuse": Status.CONFUSION,
        "sleep": Status.SLEEP,
        "paralysis": Status.PARALYZE,
        "petrification": Status.PETRIFY,
        "ko": Status.KO,
        "partial petrification": Status.PARTIAL_PETRIFY,
        "partial petrification (1/3)": Status.PARTIAL_PETRIFY,
        "partial petrification (1/2)": Status.PARTIAL_PETRIFY,
        "partial petrification (full)": Status.PETRIFY,
    }

    # 7) Erase / Toad / Mini のような「特別ルール」を先に処理
    # ---- Erase（即死） ----
    if "erase" in ailments_list:
        target_lv = char_stats.level
        caster_lv = int(spell_json.get("AttackerLevel", 1) or 1)  # ★敵側から埋める

        if "ko" in immune_set:
            logs.append(f"{char_name}には《Erase》が効かなかった！（無効）")
            return True

        if target_lv >= caster_lv * 0.75:
            hit_percent = 0.0
        else:
            base_acc = float(spell_json.get("BaseAccuracy") or 0.0)
            if base_acc <= 1.0:
                base_acc *= 100.0
            hit_percent = max(0.0, min(base_acc, 100.0))

        roll = rng.random() * 100.0
        if roll < hit_percent:
            char_state.statuses.add(Status.KO)
            char_state.hp = 0
            logs.append(
                f"{char_name}は《Erase》で消し去られた！"
                f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )
        else:
            logs.append(
                f"{char_name}には《Erase》が効かなかった…"
                f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )
        return True

    # ---- Toad / Mini：キャラ側は KO ではなく普通に状態異常化させる想定 ----
    for ail in ailments_list:
        key = normalize_text_basic(ail)
        if key in ("toad", "mini"):
            if key in immune_set:
                logs.append(f"{char_name}には{key.title()}が効かなかった！（無効）")
                return True

            roll = rng.random() * 100.0
            if roll < hit_percent:
                st = Status.TOAD if key == "toad" else Status.MINI
                char_state.statuses.add(st)
                logs.append(
                    f"{char_name}は《{key.title()}》の効果を受けた！"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
            else:
                logs.append(
                    f"{char_name}には《{key.title()}》が効かなかった…"
                    f"（命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
            return True  # Toad/Mini はここで終了

    # 8) 通常の状態異常（Poison / Blind…）も enemy版と同様に処理
    for ail in ailments_list:
        key = normalize_text_basic(ail)
        if key in immune_set or (
            key.startswith("partial petrification")
            and "partial petrification" in immune_set
        ):
            logs.append(f"{char_name}には{key}が効かなかった！（無効）")
            continue

        st = status_map.get(key)
        if st is None:
            logs.append(f"※ 未対応の状態異常: {ail}")
            continue

        roll = rng.random() * 100.0
        if roll < hit_percent:
            if st == Status.PARTIAL_PETRIFY:
                amount = partial_petrify_amount_from_name(ail)
                apply_partial_petrification(
                    target_state=char_state,
                    amount=amount,
                    target_name=char_name,
                    logs=logs,
                )
                logs.append(
                    f"{char_name}は部分石化した！（魔法："
                    f"命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
            else:
                char_state.statuses.add(st)
                logs.append(
                    f"{char_name}は{st.name}状態になった！（魔法："
                    f"命中率{hit_percent:.1f}% 判定{roll:.1f}）"
                )
        else:
            logs.append(
                f"{char_name}は{ail}を回避した！（魔法："
                f"命中率{hit_percent:.1f}% 判定{roll:.1f}）"
            )

    return True


# 上記関数の薄いラッパ関数
def _apply_enemy_spell_ailments_to_char(
    spell_json: Dict[str, Any],
    enemy_json: Dict[str, Any],
    enemy_name: str,
    char_stats: FinalCharacterStats,
    char_state: BattleActorState,
    char_name: str,
    enemy_caster: Optional[EnemyCasterStats],
    rng: random.Random,
    logs: List[str],
) -> bool:
    """
    敵の使用する状態異常系魔法（Erase / Toad / Mini / それ以外のStatusAilment持ち）を
    キャラに適用するための薄いラッパ。

    現時点では enemy_json / enemy_name / enemy_caster はロジックで使っていないが、
    インターフェース拡張（敵側の Mind などを命中率に反映する）余地として受け取っておく。
    戻り値:
        True  -> 「状態異常魔法として処理した」（成功/失敗は問わない）
        False -> 状態異常魔法ではなかった
    """
    # いまのところ処理本体は apply_status_spell_to_char に委譲すればよい
    return apply_status_spell_to_char(
        spell_json=spell_json,
        char_state=char_state,
        char_stats=char_stats,
        char_name=char_name,
        rng=rng,
        logs=logs,
    )


# ============================================================
# 敵 → キャラ攻撃（通常攻撃 + スペシャル攻撃を含む）
# ============================================================


def _get_status_name_from_monster_spell(spell_def: Dict[str, Any]) -> Optional[str]:
    """
    monsters.json の Spells エントリから状態異常名を取り出すヘルパー。
    ・"Status" フィールドを優先
    ・なければ "StatusAilment"（旧仕様）も見る
    ・"-" や空文字は「状態異常なし」として None を返す
    """
    raw = spell_def.get("Status") or spell_def.get("StatusAilment") or ""
    raw = str(raw).strip()
    if not raw or raw == "-":
        return None
    return raw


# <バフ/デバフ> =============================================================================


# Reflect -----------------------
# 共通化した Reflect 適用関数
def apply_reflect_to_actor(
    target_state: BattleActorState,
    target_name: str,
    logs: list[str],
    *,
    charges: int = 1,
) -> bool:
    old = target_state.reflect_charges
    if charges > 0 and old > 0:
        logs.append(f"{target_name}には既にReflectがかかっている。")
        return False

    target_state.reflect_charges = charges
    if old <= 0 and charges > 0:
        logs.append(f"{target_name}は魔法反射のバリアを張った！（Reflect）")
    else:
        logs.append(f"{target_name}のReflect効果が消えた。")
    return True


# ============================================================
# Haste / Protect 共通ヘルパ
# ============================================================


# Haste / Protect 共通ヘルパ: 命中率計算
def calc_buff_hit_percent(base_acc_raw: float | int | None, mind: int) -> int:
    """
    BaseAccuracy(0〜1 or 0〜100) と MIND からヒット率(0〜100)を返す。
    """
    if base_acc_raw is None:
        base_acc_raw = 1.0
    acc = float(base_acc_raw)
    if acc > 1.0:  # 例: 16 or 75 → 0.16 / 0.75
        acc = acc / 100.0

    base_percent = acc * 100.0
    hit_percent = base_percent + (mind / 2.0)

    if hit_percent > 99.0:
        hit_percent = 99.0
    if hit_percent < 0.0:
        hit_percent = 0.0

    return int(round(hit_percent))


def buff_target_magic_parameters(
    *,
    target_magic_defense: int,
    target_magic_def_multiplier: int,
    target_magic_resistance_percent: int,
    target_is_friendly: bool,
) -> tuple[int, int, int]:
    """
    FAQ の self-targetting に合わせた補助/回復用の魔法防御パラメータを返す。

    味方対象の魔法では Step 4 で Magic Defense / Magic Defense Multiplier を 0 と
    みなすため、Haste / Protect の転写量計算でも同じ補正を使う。
    Magic Evade% 相当の耐性値は FAQ 記述どおりそのまま残す。
    """
    if target_is_friendly:
        return 0, 0, target_magic_resistance_percent
    return (
        target_magic_defense,
        target_magic_def_multiplier,
        target_magic_resistance_percent,
    )


def calc_haste_buff_amounts(
    *,
    base_power: float,
    base_factor: int,
    target_magic_defense: int,
    target_magic_def_multiplier: int,
    target_magic_resistance_percent: int,
    rng: random.Random,
    use_expectation: bool = False,
) -> tuple[int, int]:
    """
    Haste の魔法式を物理へ転写するための加算量を返す。

    戻り値:
      - add_power: FAQ の「Final Damage」を物理 Base Damage 加算へ転写した値
      - add_mul: FAQ の「M」を物理 Attack Multiplier 加算へ転写した値
    """
    if base_factor <= 0:
        return 0, 0

    magic_acc_percent = 100
    hit_rate = magic_acc_percent / 100.0
    resist_rate = max(0, min(target_magic_resistance_percent, 100)) / 100.0

    if use_expectation:
        net_hits = max(
            base_factor * hit_rate - target_magic_def_multiplier * resist_rate,
            0.0,
        )
        factor = 1.25
    else:
        attack_hits = sum(1 for _ in range(base_factor) if rng.random() < hit_rate)
        evade_hits = sum(
            1
            for _ in range(max(target_magic_def_multiplier, 0))
            if rng.random() < resist_rate
        )
        net_hits = float(max(attack_hits - evade_hits, 0))
        factor = rng.uniform(1.0, 1.5)

    if net_hits <= 0:
        return 0, 0

    base_damage = int(base_power * factor) - target_magic_defense
    final_damage = max(int(base_damage * net_hits), 1)
    return final_damage, int(net_hits if use_expectation else net_hits)


# Haste / Protect 共通ヘルパ: Haste 系バフ適用
def apply_haste_buff(
    stats: FinalCharacterStats | FinalEnemyStats,
    *,
    base_power: float,
    base_factor: int,
    rng: random.Random,
    target_magic_defense: int,
    target_magic_def_multiplier: int,
    target_magic_resistance_percent: int,
) -> tuple[int, int, int, int, int, int]:
    """
    Haste 相当のバフを stats に適用し、
    適用前後の値と FAQ 転写量を返す。
    """
    add_power, add_mul = calc_haste_buff_amounts(
        base_power=base_power,
        base_factor=base_factor,
        target_magic_defense=target_magic_defense,
        target_magic_def_multiplier=target_magic_def_multiplier,
        target_magic_resistance_percent=target_magic_resistance_percent,
        rng=rng,
    )

    old_power_bonus = getattr(stats, "haste_power_bonus", 0)
    old_mul_bonus = getattr(stats, "haste_multiplier_bonus", 0)

    new_power_bonus = min(255, old_power_bonus + add_power)
    new_mul_bonus = min(16, old_mul_bonus + add_mul)

    stats.haste_power_bonus = new_power_bonus
    stats.haste_multiplier_bonus = new_mul_bonus

    return (
        old_power_bonus,
        new_power_bonus,
        old_mul_bonus,
        new_mul_bonus,
        add_power,
        add_mul,
    )


def calc_protect_buff_amount(
    *,
    base_power: float,
    base_factor: int,
    target_magic_defense: int,
    target_magic_def_multiplier: int,
    target_magic_resistance_percent: int,
    rng: random.Random,
    use_expectation: bool = False,
) -> int:
    """
    FAQ の Safe / Protect 用に、Step1-6 相当の Final Damage を返す。

    Haste と同様に魔法ダメージ式を経由し、その最終値を Defense / Magic Defense へ
    同量加算する。
    """
    add_value, _ = calc_haste_buff_amounts(
        base_power=base_power,
        base_factor=base_factor,
        target_magic_defense=target_magic_defense,
        target_magic_def_multiplier=target_magic_def_multiplier,
        target_magic_resistance_percent=target_magic_resistance_percent,
        rng=rng,
        use_expectation=use_expectation,
    )
    return add_value


# Haste / Protect 共通ヘルパ: Protect 系バフ適用
def apply_protect_buff(
    target_stats: FinalCharacterStats | FinalEnemyStats,
    *,
    base_power: float,
    base_factor: int,
    rng: random.Random,
    target_magic_defense: int,
    target_magic_def_multiplier: int,
    target_magic_resistance_percent: int,
    use_expectation: bool = False,
) -> tuple[int, int, int]:
    """
    Protect 系バフの効果量を計算して target_stats に反映するヘルパー。

    FAQ の Safe / Protect に合わせ、Step1-6 相当の Final Damage を Defense /
    Magic Defense の両方へ同量加算する。戻り値は
    (適用前の defense, magic_defense, 今回の加算値)。
    """
    add_value = calc_protect_buff_amount(
        base_power=base_power,
        base_factor=base_factor,
        target_magic_defense=target_magic_defense,
        target_magic_def_multiplier=target_magic_def_multiplier,
        target_magic_resistance_percent=target_magic_resistance_percent,
        rng=rng,
        use_expectation=use_expectation,
    )

    old_def = target_stats.defense
    old_mdef = target_stats.magic_defense

    target_stats.defense = min(255, target_stats.defense + add_value)
    target_stats.magic_defense = min(255, target_stats.magic_defense + add_value)

    return old_def, old_mdef, add_value
