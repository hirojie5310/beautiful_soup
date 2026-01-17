# ============================================================
# char_build: キャラ構築

# build_party_members	セーブデータ → キャラ最終ステ（パーティ全員）
# partial_petrify_gauge_from_status_effects	セーブデータのステータスから部分石化ゲージを計算
# character_from_party_entry	partyの1人分の情報からキャラクター・装備・戦闘状態を生成
# statuses_from_status_effects	セーブデータのstatus_effectsをStatusの集合に変換する
# apply_job_equipment_restrictions	Job.raw["Weapons"]/["Armors"]に基づいて装備の適用可否を判断
# equipment_summary	EquipmentSetを人間が読みやすい1ブロックの文字列にする
# _canon_name	表記ブレの修正（’ と ' の違い、- と – の違い、全角/半角、& と and）
# build_name_index	武器・防具名称比較のための正規化辞書を作成
# weapon_stats	武器名→(威力,命中%,長距離フラグ,属性リスト)に変換
# armor_stats	防具名→(Defense,Evasion,MagicDefense,盾フラグ,属性耐性,属性無効)に変換
# compute_character_final_stats	基礎ステータス+装備名+JSONデータから、戦闘用の最終ステータスを自動算出
# interpolate_stats	StatsByLevelからStr/Agi/Vit/Int/Mndを線形補完してtarget_levelのステータスを作る
# interpolate_mp	StatsByLevelからMPを線形補完してtarget_levelのMPを作る
# ============================================================

from dataclasses import replace
from typing import Optional, Dict, Tuple, Any, List
import unicodedata, re
import math

from combat.enums import Status
from combat.models import (
    Job,
    BaseCharacter,
    EquipmentSet,
    BattleActorState,
    FinalCharacterStats,
    PartyMemberRuntime,
)
from combat.runtime_state import RuntimeState
from combat.elements import parse_elements


# １．セーブデータ → キャラ最終ステ（パーティ全員）
def build_party_members_from_save(
    *,
    save: dict,
    jobs_by_name: Dict[str, Job],
    weapons: dict,
    armors: dict,
) -> List[PartyMemberRuntime]:
    party_members: List[PartyMemberRuntime] = []

    for entry in save["party"]:
        base, eq, char_state, eq_logs, job_name, job = character_from_party_entry(
            entry, jobs_by_name
        )

        char_final = compute_character_final_stats(
            base, eq, weapons, armors, job_name=job_name
        )

        char_name = entry.get("name", "キャラ")

        party_members.append(
            PartyMemberRuntime(
                name=char_name,
                job=job,
                base=base,
                stats=char_final,
                state=char_state,
                equipment=eq,
                equipment_logs=eq_logs,
            )
        )

    return party_members


# ★ セーブデータ → 部分石化ゲージ
def partial_petrify_gauge_from_status_effects(status_effects: dict) -> float:
    gauge = 0.0

    if status_effects.get("Partial Petrification (1/3)", False):
        gauge += 1.0 / 3.0
    if status_effects.get("Partial Petrification (1/2)", False):
        gauge += 1.0 / 2.0
    if status_effects.get("Partial Petrification (Full)", False):
        gauge += 1.0

    # 旧形式 `"Partial Petrification": true` にも一応対応しておく
    if status_effects.get("Partial Petrification", False):
        gauge = max(gauge, 1.0)

    return min(gauge, 1.0)


def character_from_party_entry(
    entry: dict,
    jobs_by_name: Dict[str, Job],
) -> tuple[BaseCharacter, EquipmentSet, BattleActorState, list[str], str, Job]:

    base = BaseCharacter(
        level=entry["level"],
        total_exp=entry["exp"],
        job_level=entry["job_level"]["level"],
        job_skill_point=entry["job_level"]["skill_point"],
        max_hp=entry["max_hp"],
        strength=entry["strength"],
        agility=entry["agility"],
        vitality=entry["vitality"],
        intelligence=entry["intelligence"],
        mind=entry["mind"],
        row=entry.get("row", "front"),  # ← 修正！
    )

    eq_data = entry["equipment"]
    eq = EquipmentSet(
        main_hand=eq_data.get("main_hand"),
        off_hand=eq_data.get("off_hand"),
        head=eq_data.get("head"),
        body=eq_data.get("body"),
        arms=eq_data.get("arms"),
    )

    # ★ ジョブ名の取得を savedata 形式に合わせて修正（両対応）
    job_name = entry.get("job") or entry.get("job_level", {}).get("job")
    if not isinstance(job_name, str) or not job_name:
        raise KeyError(
            "party_entry に job が見つかりません。savedata形式を確認してください。"
        )

    try:
        job = jobs_by_name[job_name]
    except KeyError as e:
        raise KeyError(
            f"jobs_by_name に '{job_name}' が存在しません。ジョブ名の綴りを確認してください。"
        ) from e

    # --- StatsByLevel（キャラLvテーブル）を dict 化 ---
    # job.raw["StatsByLevel"] は JSON の生配列
    job_stats_levels = {row["Level"]: row for row in job.raw.get("StatsByLevel", [])}

    # ★ ステータス補完
    interp_stats = interpolate_stats(job_stats_levels, base.level)

    base.strength = interp_stats["Str"]
    base.agility = interp_stats["Agi"]
    base.vitality = interp_stats["Vit"]
    base.intelligence = interp_stats["Int"]
    base.mind = interp_stats["Mnd"]

    # ★最大MPを補完取得（L1MP〜L8MPのdict）
    max_mp = interpolate_mp(job_stats_levels, base.level)

    state = BattleActorState(
        hp=entry["hp"],
        max_hp=entry["max_hp"],
        statuses=statuses_from_status_effects(entry.get("status_effects", {})),
    )

    # ★最大MPプールをセット
    state.max_mp_pool = {i: int(max_mp.get(f"L{i}MP", 0) or 0) for i in range(1, 9)}

    # ★現在MP（savedata優先）
    mp_from_save = entry.get("mp")
    if isinstance(mp_from_save, dict):
        state.mp_pool = {
            i: min(int(mp_from_save.get(f"L{i}MP", 0) or 0), state.max_mp_pool[i])
            for i in range(1, 9)
        }
    else:
        # savedataに無ければ満タン扱い
        state.mp_pool = dict(state.max_mp_pool)

    # ★ 現在MPが最大MPを超えないように丸める
    for i in range(1, 9):
        state.mp_pool[i] = min(state.mp_pool.get(i, 0), state.max_mp_pool[i])

    se = entry.get("status_effects", {})
    state.partial_petrify_gauge = partial_petrify_gauge_from_status_effects(se)

    g = state.partial_petrify_gauge
    if g >= 1.0:
        state.statuses.discard(Status.PARTIAL_PETRIFY)
        state.statuses.add(Status.PETRIFY)
        state.statuses.add(Status.KO)
        state.hp = 0
    elif g > 0 and Status.PETRIFY not in state.statuses:
        state.statuses.add(Status.PARTIAL_PETRIFY)

    # ★ ジョブによる装備制限を適用（ログ付き）
    eq, eq_logs = apply_job_equipment_restrictions(eq, job)

    return base, eq, state, eq_logs, job_name, job


def statuses_from_status_effects(status_effects: dict) -> set[Status]:
    """セーブデータの status_effects を Status の集合に変換する"""
    mapping = {
        "Poison": Status.POISON,
        "Blind": Status.BLIND,
        "Mini": Status.MINI,
        "Silence": Status.SILENCE,
        "Toad": Status.TOAD,
        "Petrification": Status.PETRIFY,
        "KO": Status.KO,
        "Confusion": Status.CONFUSION,
        "Sleep": Status.SLEEP,
        "Paralysis": Status.PARALYZE,
        # ★ 旧形式（互換用）
        "Partial Petrification": Status.PARTIAL_PETRIFY,
        # ★ 新形式（ゲージ付き）
        "Partial Petrification (1/3)": Status.PARTIAL_PETRIFY,
        "Partial Petrification (1/2)": Status.PARTIAL_PETRIFY,
    }

    result: set[Status] = set()
    for name, flag in status_effects.items():
        if flag and name in mapping:
            result.add(mapping[name])
    return result


# Jobの武器・防具リストを使うヘルパー
# 装備制限：装備できない武器・防具は自動的に外す
def apply_job_equipment_restrictions(
    eq: EquipmentSet,
    job: Job,
) -> Tuple[EquipmentSet, List[str]]:
    """
    Job.raw["Weapons"] / ["Armors"] に基づいて、
    そのジョブが装備できない装備を eq から外す。
    ついでに、その過程の説明ログも返す。
    """
    logs: List[str] = []

    allowed_weapon_names = {
        w["Name"] for w in job.raw.get("Weapons", []) if w.get("Name")
    }
    allowed_armor_names = {
        a["Name"] for a in job.raw.get("Armors", []) if a.get("Name")
    }

    new_eq = replace(eq)

    # --- メインハンド（武器） ---
    if new_eq.main_hand and new_eq.main_hand not in allowed_weapon_names:
        logs.append(
            f"  [{job.name}] は main_hand の武器「{new_eq.main_hand}」を装備できないため、外しました。"
        )
        new_eq.main_hand = None

    # --- オフハンド（武器 or 防具） ---
    if new_eq.off_hand:
        if (
            new_eq.off_hand not in allowed_weapon_names
            and new_eq.off_hand not in allowed_armor_names
        ):
            logs.append(
                f"  [{job.name}] は off_hand の装備「{new_eq.off_hand}」を装備できないため、外しました。"
            )
            new_eq.off_hand = None

    # --- 防具スロット ---
    for slot in ("head", "body", "arms"):
        name = getattr(new_eq, slot)
        if name and name not in allowed_armor_names:
            logs.append(
                f"  [{job.name}] は {slot} の防具「{name}」を装備できないため、外しました。"
            )
            setattr(new_eq, slot, None)

    return new_eq, logs


# 最終的な装備一覧を出力
def equipment_summary(eq: EquipmentSet) -> str:
    """
    EquipmentSet を人間が読みやすい1ブロックの文字列にする。
    """

    def label(name: str | None) -> str:
        return name or "（なし）"

    lines = [
        f"    main_hand: {label(eq.main_hand)}",
        f"    off_hand : {label(eq.off_hand)}",
        f"    head     : {label(eq.head)}",
        f"    body     : {label(eq.body)}",
        f"    arms     : {label(eq.arms)}",
    ]
    return "\n".join(lines)


# ============================================================
# 装備 JSON → 簡易ステータス
# ============================================================


# 表記ブレの修正（’ と ' の違い、- と – の違い、全角/半角、& と and）
def _canon_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.casefold()
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# 武器・防具名称比較のための正規化辞書を作成
def build_name_index(d: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for k, v in d.items():
        ck = _canon_name(k)
        # もし衝突したら検知したいならここで例外にする/ログ出す
        idx.setdefault(ck, v)
    return idx


def weapon_stats(
    weapons_by_name_norm: Dict[str, Dict[str, Any]],
    name: Optional[str],
) -> Tuple[int, int, bool, bool, List[str]]:
    """
    武器名 → (威力, 命中%, 両手武器フラグ, 長距離フラグ, 属性リスト)
    該当無しなら (0, 0, False, False, [])。
    """
    if not name:
        return 0, 0, False, False, []

    w = weapons_by_name_norm.get(_canon_name(name))
    if w is None:
        print(f"[warn] weapon not found: {name}")
        return 0, 0, False, False, []

    power = int(w.get("BasePower", 0))

    base_acc = float(w.get("BaseAccuracy", 0.0))  # 0.85 など
    acc_percent = int(round(base_acc * 100))

    # 両手武器フラグ（JSONのキーに合わせてどれかを見る）
    two_handed = (
        bool(w.get("TwoHanded"))
        or bool(w.get("Two-Handed"))
        or (str(w.get("Hands", "")).strip() == "2")
    )

    long_range = bool(w.get("LongRange")) and w.get("LongRange") not in ("", "-")

    elems_raw = w.get("Elements") or w.get("Element") or ""
    elements: List[str] = parse_elements(elems_raw)

    return power, acc_percent, two_handed, long_range, elements


def armor_stats(
    armors_by_name_norm: Dict[str, Dict[str, Any]],
    name: Optional[str],
) -> Tuple[int, float, int, bool, List[str], List[str], List[str]]:
    """
    防具名 → (Defense, Evasion(0.0〜1.0), MagicDefense, 盾フラグ,
              属性耐性リスト, 属性無効リスト)
    該当無しなら (0, 0.0, 0, False, [], [])。
    """
    if not name:
        return 0, 0.0, 0, False, [], [], []

    a = armors_by_name_norm.get(_canon_name(name))
    if a is None:
        print(f"[warn] armor not found: {name}")
        return 0, 0.0, 0, False, [], [], []

    defense = int(a.get("Defense", 0))
    evasion = float(a.get("Evasion", 0.0))
    mdef = int(a.get("BaseMagicDefense", 0))
    is_shield = a.get("ArmorType") == "Shield"

    # ✅ parse_elements で統一
    elem_resist = parse_elements(a.get("ElementalResist"))
    elem_null = parse_elements(a.get("ElementalNull"))

    # ✅ 状態異常無効（List[str]）
    status_imm = a.get("StatusImmunities", [])
    if not isinstance(status_imm, list):
        status_imm = []
    status_imm = [str(x) for x in status_imm if x]  # 念のため

    return defense, evasion, mdef, is_shield, elem_resist, elem_null, status_imm


# ============================================================
# キャラクター最終ステータス計算
# ============================================================


def compute_character_final_stats(
    base: BaseCharacter,
    eq: EquipmentSet,
    weapons_by_name: Dict[str, Dict[str, Any]],
    armors_by_name: Dict[str, Dict[str, Any]],
    job_name: Optional[str] = None,  # ← この引数がある
) -> FinalCharacterStats:
    """
    基礎ステータス + 装備名 + JSON データ から、戦闘用の最終ステータスを自動算出。
    """
    weapons_norm = build_name_index(weapons_by_name)
    armors_norm = build_name_index(armors_by_name)

    # --- 攻撃側（武器） ---
    main_pow, main_acc, main_two, main_long, main_weapon_elements = weapon_stats(
        weapons_norm, eq.main_hand
    )
    off_pow, off_acc, off_two, off_long, off_weapon_elements = weapon_stats(
        weapons_norm, eq.off_hand
    )

    # print(f"[Debug]eq:{eq.off_hand}")
    # print(f"[Debug]off_pow:{off_pow} off_acc:{off_acc} off_long:{off_long} off_weapon_elements:{off_weapon_elements}")

    # ----------------------------------------
    # Black Belt / Monk 素手補正
    # BasePower = 1
    # BaseAccuracy = 0.8（80%）
    # レベルボーナス = ceil(Level * 1.5)
    # ----------------------------------------
    if job_name in ("Black Belt", "Monk"):
        unarmed_level_bonus = math.ceil(base.level * 1.5)

        # メインハンドが素手の場合
        if main_pow == 0:
            main_pow = 1 + unarmed_level_bonus  # BasePower 1 + Lvボーナス
            main_acc = int(0.8 * 100)  # 80%

        # オフハンドが素手の場合
        if off_pow == 0:
            off_pow = 1 + unarmed_level_bonus
            off_acc = int(0.8 * 100)

    def atk_mul(level: int, agility: int) -> int:
        # AtkMul = 1 + Lv//16 + Agi//16
        return 1 + level // 16 + agility // 16

    main_mul = atk_mul(base.level, base.agility) if main_pow else 0
    off_mul = atk_mul(base.level, base.agility) if off_pow else 0

    # --- 防御側（防具 + 盾） ---
    total_def = 0
    total_eva = 0.0
    total_mdef = 0
    shield_count = 0
    elem_resist_total: set[str] = set()  # ★ 追加
    elem_null_total: set[str] = set()  # ★追加（現状は空のまま）
    status_imm_total: set[str] = set()

    # 盾は off_hand に入る可能性が高いので、防具としても見る
    for slot in (eq.off_hand, eq.head, eq.body, eq.arms):
        d, e, m, is_shield, elem_resist, elem_null, status_imm = armor_stats(
            armors_norm, slot
        )
        total_def += d
        total_eva += e
        total_mdef += m
        if is_shield:
            shield_count += 1
        elem_resist_total.update(elem_resist)  # ★ ここで耐性収集
        elem_null_total.update(elem_null)
        status_imm_total.update(status_imm)

    # 防御力 = 防具合計 + Vit//2
    defense = total_def + base.vitality // 2

    # 防御倍率：
    # 盾あり: shield_count + Lv//16 + Agi//16
    # 盾なし: Lv//32 + Agi//32
    if shield_count > 0:
        defense_multiplier = shield_count + base.level // 16 + base.agility // 16
    else:
        defense_multiplier = base.level // 32 + base.agility // 32

    # 回避率[%] = (防具 Evasion 合計 *100) + (Agi//4)
    evasion_percent = int(round(total_eva * 100 + (base.agility // 4)))

    magic_defense = total_mdef

    # 魔防倍率 = Agi//32 + Int//32 + Mind//32
    magic_def_multiplier = (
        base.agility // 32 + base.intelligence // 32 + base.mind // 32
    )

    # 魔法抵抗 = Int//2 + Mind//2
    magic_resistance = base.intelligence // 2 + base.mind // 2

    # Attack Power = 武器威力 + Str//4
    main_power = main_pow + base.strength // 4 if main_pow else 0
    off_power = off_pow + base.strength // 4 if off_pow else 0

    # 命中率 = 武器命中% + Agi//4 + JobLv//4
    main_accuracy = (
        main_acc + base.agility // 4 + base.job_level // 4 if main_pow else 0
    )
    off_accuracy = off_acc + base.agility // 4 + base.job_level // 4 if off_pow else 0

    final = FinalCharacterStats(
        level=base.level,
        job_level=base.job_level,
        max_hp=base.max_hp,
        strength=base.strength,
        agility=base.agility,
        vitality=base.vitality,
        intelligence=base.intelligence,
        mind=base.mind,
        row=base.row,
        main_power=main_power,
        main_accuracy=main_accuracy,
        main_atk_multiplier=main_mul,
        main_two=main_two,
        main_long=main_long,
        off_power=off_power,
        off_accuracy=off_accuracy,
        off_atk_multiplier=off_mul,
        off_two=off_two,
        off_long=off_long,
        defense=defense,
        defense_multiplier=defense_multiplier,
        evasion_percent=evasion_percent,
        magic_defense=magic_defense,
        magic_def_multiplier=magic_def_multiplier,
        magic_resistance=magic_resistance,
        shield_count=shield_count,
        elemental_resists=frozenset(elem_resist_total),
        elemental_nulls=frozenset(elem_null_total),
        elemental_weaks=frozenset(),
        elemental_absorbs=frozenset(),
        status_immunities=frozenset(status_imm_total),  # ★追加
    )

    # ★ 追加：武器属性を共通パーサで正規化
    final.main_weapon_elements = parse_elements(main_weapon_elements)
    final.off_weapon_elements = parse_elements(off_weapon_elements)

    return final


# 補完関数（ジョブデータにないステータス）
def interpolate_stats(job_stats_by_level: dict, target_level: int) -> dict:
    """
    StatsByLevel から Str/Agi/Vit/Int/Mnd を線形補完して target_level のステータスを作る。
    job_stats_by_level は {Level(int): {"Str":..,"Agi":..,"Vit":..,"Int":..,"Mnd":..}} という構造を想定。

    interpolate_mp() と同じ方針：
      - target が最小以下 → 最小レベルの値
      - target が最大以上 → 最大レベルの値
      - それ以外 → 左右2点で線形補完
      - None は 0 扱い
    """

    levels = sorted(job_stats_by_level.keys())
    if not levels:
        return {"Str": 0, "Agi": 0, "Vit": 0, "Int": 0, "Mnd": 0}

    # もし target_level が最小以下なら最初のレベル値を返す
    if target_level <= levels[0]:
        row = job_stats_by_level[levels[0]]
        return {
            "Str": int(row.get("Str", 0) or 0),
            "Agi": int(row.get("Agi", 0) or 0),
            "Vit": int(row.get("Vit", 0) or 0),
            "Int": int(row.get("Int", 0) or 0),
            "Mnd": int(row.get("Mnd", 0) or 0),
        }

    # target_level が最大以上なら最大レベルを返す
    if target_level >= levels[-1]:
        row = job_stats_by_level[levels[-1]]
        return {
            "Str": int(row.get("Str", 0) or 0),
            "Agi": int(row.get("Agi", 0) or 0),
            "Vit": int(row.get("Vit", 0) or 0),
            "Int": int(row.get("Int", 0) or 0),
            "Mnd": int(row.get("Mnd", 0) or 0),
        }

    # そうでなければ2点間で線形補完
    left = max(lv for lv in levels if lv <= target_level)
    right = min(lv for lv in levels if lv >= target_level and lv != left)

    left_stats = job_stats_by_level[left]
    right_stats = job_stats_by_level[right]

    result = {}
    for key in ("Str", "Agi", "Vit", "Int", "Mnd"):
        a = left
        b = right
        x = target_level

        ya = left_stats.get(key)
        yb = right_stats.get(key)

        ya = 0 if ya is None else ya
        yb = 0 if yb is None else yb

        # 線形補完
        y = ya + (yb - ya) * ((x - a) / (b - a))
        result[key] = int(y)

    return result


# 補完関数（ジョブデータにないMP）
def interpolate_mp(job_stats_by_level: dict, target_level: int) -> dict:
    """
    StatsByLevel から MP を線形補完して target_level の MP を作る。
    job_stats_by_level は {Level(int): {"L1MP":.., "L2MP":..}} という構造を想定。
    """

    levels = sorted(job_stats_by_level.keys())

    # もし target_level が最小以下なら最初のレベル値を返す
    if target_level <= levels[0]:
        return {
            key: int(job_stats_by_level[levels[0]].get(key, 0) or 0)
            for key in job_stats_by_level[levels[0]]
            if key.startswith("L") and key.endswith("MP")
        }

    # target_level が最大以上なら最大レベルを返す
    if target_level >= levels[-1]:
        return {
            key: int(job_stats_by_level[levels[-1]].get(key, 0) or 0)
            for key in job_stats_by_level[levels[-1]]
            if key.startswith("L") and key.endswith("MP")
        }

    # そうでなければ2点間で線形補完
    # 左の点（ target より小さい最大の Level ）
    left = max(lv for lv in levels if lv <= target_level)
    # 右の点（ target より大きい最小の Level ）
    right = min(lv for lv in levels if lv >= target_level and lv != left)

    left_stats = job_stats_by_level[left]
    right_stats = job_stats_by_level[right]

    result = {}

    for key in left_stats:
        if not (key.startswith("L") and key.endswith("MP")):
            continue

        a = left
        b = right
        x = target_level
        ya = left_stats.get(key)
        yb = right_stats.get(key)

        # None の場合 0 にする
        ya = 0 if ya is None else ya
        yb = 0 if yb is None else yb

        # 線形補完
        y = ya + (yb - ya) * ((x - a) / (b - a))
        result[key] = int(y)

    return result
