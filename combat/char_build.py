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
from typing import Optional, Dict, Tuple, Any, List, Callable
import math
import re

from combat.enums import Status
from combat.models import (
    Job,
    BaseCharacter,
    EquipmentSet,
    BattleActorState,
    FinalCharacterStats,
    PartyMemberRuntime,
    PartyEntryBuildResult,
)
from combat.elements import parse_elements
from system.exp_system import LevelTable
from utils.name_normalize import normalize_name
from utils.text_normalize import normalize_text_basic


# １．セーブデータ → キャラ最終ステ（パーティ全員）
from typing import Dict, List


def _cap_physical_accuracy_for_build(hit_percent: int) -> int:
    """通常攻撃の命中率はビルド時点で 99% を上限にする。"""
    return max(0, min(hit_percent, 99))


def build_party_members_from_save(
    *,
    save: dict,
    jobs_by_name: Dict[str, Job],
    weapons: dict,
    armors: dict,
    level_table: LevelTable,  # ← 追加
) -> List[PartyMemberRuntime]:
    party_members: List[PartyMemberRuntime] = []

    for entry in save["party"]:
        r = character_from_party_entry(entry, jobs_by_name, level_table)
        base = r.base
        eq = r.eq
        char_state = r.state
        eq_logs = r.eq_logs
        job_name = r.job_name
        job = r.job

        char_final = compute_character_final_stats(
            base, eq, weapons, armors, job_name=job_name
        )

        char_name = entry.get("name", "キャラ")
        portrait_key = entry.get("portrait_key")

        print("[DBG eq]", entry.get("name"), "eq:", eq, "poryrait_key:", portrait_key)

        party_members.append(
            PartyMemberRuntime(
                name=char_name,
                level=base.level,
                job=job,  # ← job_data 取り直し不要
                base=base,  # ★追加
                stats=char_final,
                state=char_state,
                equipment=eq,
                equipment_logs=eq_logs,
                portrait_key=portrait_key,
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
    level_table: LevelTable,
) -> PartyEntryBuildResult:

    entry = normalize_party_entry(entry, level_table)

    # total_exp から現在レベルを決める
    st = level_table.status_from_total_exp(entry["exp"])

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

    # ------------------------------------------------------------
    # ★追加：ジョブごとの job_level / skill_point を savedata に保持
    #  - 新形式: entry["job_levels"][job_name] = {"level":..., "skill_point":...}
    #  - 旧形式: entry["job_level"] = {"level":..., "skill_point":...}
    # 旧形式しか無ければ job_levels を生やして移行する
    # ------------------------------------------------------------
    job_levels = entry.get("job_levels")
    if not isinstance(job_levels, dict):
        job_levels = {}
        entry["job_levels"] = job_levels  # ★移行：辞書を生やす

    # 旧形式の現在ジョブ情報（フォールバック）
    jl_legacy = entry.get("job_level", {}) or {}
    legacy_level = int(jl_legacy.get("level", 1))
    legacy_sp = int(jl_legacy.get("skill_point", 0))

    # 新形式優先で現在ジョブの育成を取る
    jl_current = job_levels.get(job_name)
    if not isinstance(jl_current, dict):
        # ★初回（旧セーブ/初ジョブ）の場合は legacy から作る
        jl_current = {"level": legacy_level, "skill_point": legacy_sp}
        job_levels[job_name] = jl_current

    job_lv = int(jl_current.get("level", 1))
    job_sp = int(jl_current.get("skill_point", 0))

    # ★念のため丸め
    job_lv = max(1, job_lv)
    job_sp = max(0, min(99, job_sp))

    base = BaseCharacter(
        level=st.level,
        total_exp=st.total_exp,
        job_level=job_lv,
        job_skill_point=job_sp,
        max_hp=entry["max_hp"],
        strength=entry["strength"],
        agility=entry["agility"],
        vitality=entry["vitality"],
        intelligence=entry["intelligence"],
        mind=entry["mind"],
        row=entry.get("row", "front"),
    )

    eq_data = entry["equipment"]
    eq = EquipmentSet(
        main_hand=eq_data.get("main_hand"),
        off_hand=eq_data.get("off_hand"),
        head=eq_data.get("head"),
        body=eq_data.get("body"),
        arms=eq_data.get("arms"),
    )

    # --- StatsByLevel（キャラLvテーブル）を dict 化 ---
    job_stats_levels = {row["Level"]: row for row in job.raw.get("StatsByLevel", [])}

    # ★ ステータス補完
    interp_stats = interpolate_stats(job_stats_levels, base.level)

    base.strength = interp_stats["Str"]
    base.agility = interp_stats["Agi"]
    base.vitality = interp_stats["Vit"]
    base.intelligence = interp_stats["Int"]
    base.mind = interp_stats["Mnd"]

    # ★最大HPの期待値をジョブのVitテーブルから取得
    expected_hp = expected_max_hp_from_vit_table(
        job_stats_levels,
        base.level,
        initial_hp_lv1=32,
        rand_expect=1.25,
    )
    base.max_hp = expected_hp
    max_hP = expected_hp

    # ★最大MPを補完取得（L1MP〜L8MPのdict）
    max_mp = interpolate_mp(job_stats_levels, base.level)

    state = BattleActorState(
        hp=max_hP,
        max_hp=max_hP,
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

    return PartyEntryBuildResult(
        base=base, eq=eq, state=state, eq_logs=eq_logs, job_name=job_name, job=job
    )


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


# ---------------------------------------------------------
# build_name_index: これは提示のままでOK（normalize_nameに統一済み）
# ※衝突時に落とす仕様はそのまま
# ---------------------------------------------------------
def build_name_index(
    d: Dict[str, Dict[str, Any]],
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> Dict[str, Dict[str, Any]]:
    """
    正規化名 → 元データ のインデックスを作る
    """
    index: Dict[str, Dict[str, Any]] = {}

    for name, data in d.items():
        key = normalizer(name)

        # 重複チェック（仕様次第）
        if key in index:
            raise KeyError(f"正規化名が衝突しました: {name}")

        index[key] = data

    return index


# ---------------------------------------------------------
# weapon_stats: _canon_name をやめて normalize_name に統一
# ---------------------------------------------------------
def weapon_stats(
    weapons_by_name_norm: Dict[str, Dict[str, Any]],
    name: Optional[str],
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> Tuple[int, int, bool, bool, List[str]]:
    """
    武器名 → (威力, 命中%, 両手武器フラグ, 長距離フラグ, 属性リスト)
    該当無しなら (0, 0, False, False, [])。
    """
    if not name:
        return 0, 0, False, False, []

    key = normalizer(name)
    w = weapons_by_name_norm.get(key)
    if w is None:
        # print(f"[warn] weapon not found: {name} (norm={key})")
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


# ---------------------------------------------------------
# armor_stats: _canon_name をやめて normalize_name に統一
# ---------------------------------------------------------
def armor_stats(
    armors_by_name_norm: Dict[str, Dict[str, Any]],
    name: Optional[str],
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> Tuple[int, float, int, bool, List[str], List[str], list[str]]:
    """
    防具名 → (Defense, Evasion(0.0〜1.0), MagicDefense, 盾フラグ,
              属性耐性リスト, 属性無効リスト)
    該当無しなら (0, 0.0, 0, False, [], [])。
    """
    if not name:
        return 0, 0.0, 0, False, [], [], []

    key = normalizer(name)
    a = armors_by_name_norm.get(key)
    if a is None:
        # print(f"[warn] armor not found: {name} (norm={key})")
        return 0, 0.0, 0, False, [], [], []

    defense = int(a.get("Defense", 0))
    evasion = float(a.get("Evasion", 0.0))
    mdef = int(a.get("BaseMagicDefense", 0))
    is_shield = a.get("ArmorType") == "Shield"

    # parse_elements で統一（Noneや""でもOKな実装である前提）
    elem_resist = parse_elements(a.get("ElementalResist"))
    elem_null = parse_elements(a.get("ElementalNull"))

    status_imm = a.get("StatusImmunities", []) or []
    if not isinstance(status_imm, list):
        status_imm = []
    return defense, evasion, mdef, is_shield, elem_resist, elem_null, status_imm


def equipment_weight(
    weapons_by_name_norm: Dict[str, Dict[str, Any]],
    armors_by_name_norm: Dict[str, Dict[str, Any]],
    name: Optional[str],
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> int:
    """装備1つぶんの Weight を返す。データ未設定時は 0。"""
    if not name:
        return 0

    key = normalizer(name)
    row = weapons_by_name_norm.get(key) or armors_by_name_norm.get(key)
    if row is None:
        return 0

    return int(row.get("Weight", 0) or 0)


def item_stat_bonuses(item_data: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """装備1件の Bonus を能力値ボーナス辞書に正規化して返す。"""
    if not item_data:
        return {}

    bonus_raw = item_data.get("Bonus")
    if isinstance(bonus_raw, dict):
        result: Dict[str, int] = {}
        for key, value in bonus_raw.items():
            try:
                amount = int(value)
            except (TypeError, ValueError):
                continue
            mapped = _bonus_stat_key(str(key))
            if mapped is None or amount == 0:
                continue
            result[mapped] = result.get(mapped, 0) + amount
        return result

    if not isinstance(bonus_raw, str):
        return {}

    result: Dict[str, int] = {}
    for part in [p.strip() for p in bonus_raw.split(",")]:
        if not part:
            continue
        match = re.match(r"([A-Za-z ]+?)\s*([+-]?\d+)\s*$", part)
        if not match:
            continue
        mapped = _bonus_stat_key(match.group(1))
        if mapped is None:
            continue
        amount = int(match.group(2))
        if amount == 0:
            continue
        result[mapped] = result.get(mapped, 0) + amount
    return result


def _bonus_stat_key(raw_key: str) -> Optional[str]:
    key = raw_key.strip().lower().replace("_", "").replace(" ", "")
    mapping = {
        "strength": "strength",
        "agility": "agility",
        "vitality": "vitality",
        "intelligence": "intelligence",
        "intellect": "intelligence",
        "mind": "mind",
        "spirit": "mind",
    }
    return mapping.get(key)


_ELEMENTAL_MAGIC_ROD_BOOSTS: dict[str, tuple[str, ...]] = {
    "firerod": ("fire",),
    "icerod": ("ice",),
    "lightrod": ("thunder",),
    "omnirod": ("fire", "ice", "thunder", "earth", "air", "holy"),
}


def equipment_elemental_magic_boosts(
    eq: EquipmentSet,
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> Dict[str, int]:
    """装備ロッドによる属性魔法ブースト回数を返す。"""
    boosts: Dict[str, int] = {}

    for name in (eq.main_hand, eq.off_hand):
        if not name:
            continue
        key = normalizer(name)
        elements = _ELEMENTAL_MAGIC_ROD_BOOSTS.get(key)
        if elements is None:
            normalized = normalize_text_basic(name).replace(" ", "")
            elements = _ELEMENTAL_MAGIC_ROD_BOOSTS.get(normalized)
        if not elements:
            continue
        for element in elements:
            boosts[element] = boosts.get(element, 0) + 1

    return boosts


def equipment_stat_bonuses(
    weapons_by_name_norm: Dict[str, Dict[str, Any]],
    armors_by_name_norm: Dict[str, Dict[str, Any]],
    eq: EquipmentSet,
    *,
    normalizer: Callable[[str], str] = normalize_name,
) -> Dict[str, int]:
    """装備一式のステータス Bonus を合算する。"""
    total = {
        "strength": 0,
        "agility": 0,
        "vitality": 0,
        "intelligence": 0,
        "mind": 0,
    }

    for name in (eq.main_hand, eq.off_hand, eq.head, eq.body, eq.arms):
        if not name:
            continue
        key = normalizer(name)
        item_data = weapons_by_name_norm.get(key) or armors_by_name_norm.get(key)
        for stat, amount in item_stat_bonuses(item_data).items():
            total[stat] += amount

    return total


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
    stat_bonuses = equipment_stat_bonuses(weapons_norm, armors_norm, eq)

    strength = base.strength + stat_bonuses["strength"]
    agility = base.agility + stat_bonuses["agility"]
    vitality = base.vitality + stat_bonuses["vitality"]
    intelligence = base.intelligence + stat_bonuses["intelligence"]
    mind = base.mind + stat_bonuses["mind"]

    """
    print("[DBG total_exp]", base.total_exp)
    print(
        "[DBG weapon index size]", len(weapons_by_name), "norm size", len(weapons_norm)
    )
    print("[DBG eq main/off]", repr(eq.main_hand), "/", repr(eq.off_hand))

    print(
        "[DBG eq.main_hand]",
        repr(eq.main_hand),
        "raw_in_weapons?",
        eq.main_hand in weapons_by_name,
    )
    print(
        "[DBG eq.off_hand ]",
        repr(eq.off_hand),
        "raw_in_weapons?",
        eq.off_hand in weapons_by_name,
    )
    """

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

    main_mul = atk_mul(base.level, agility) if main_pow else 0
    off_mul = atk_mul(base.level, agility) if off_pow else 0

    # --- 防御側（防具 + 盾） ---
    total_def = 0
    total_eva = 0.0
    total_mdef = 0
    shield_count = 0
    total_weight = 0
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
        status_imm_total.update(status_imm)  # ★追加
        total_weight += equipment_weight(weapons_norm, armors_norm, slot)

    total_weight += equipment_weight(weapons_norm, armors_norm, eq.main_hand)

    # 防御力 = 防具合計 + Vit//2
    defense = total_def + vitality // 2

    # 防御倍率：
    # 盾あり: shield_count + Lv//16 + Agi//16
    # 盾なし: Lv//32 + Agi//32
    if shield_count > 0:
        defense_multiplier = shield_count + base.level // 16 + agility // 16
    else:
        defense_multiplier = base.level // 32 + agility // 32

    # 回避率[%] = (防具 Evasion 合計 *100) + (Agi//4)
    evasion_percent = int(round(total_eva * 100 + (agility // 4)))

    magic_defense = total_mdef

    # 魔防倍率 = Agi//32 + Int//32 + Mind//32
    magic_def_multiplier = agility // 32 + intelligence // 32 + mind // 32

    # 魔法抵抗 = Int//2 + Mind//2
    magic_resistance = intelligence // 2 + mind // 2

    # Attack Power = 武器威力 + Str//4
    main_power = main_pow + strength // 4 if main_pow else 0
    off_power = off_pow + strength // 4 if off_pow else 0

    # 命中率 = 武器命中% + Agi//4 + JobLv//4
    # FF3 FAQ に合わせて 99% 上限はここで適用し、その後に暗闇/後列ペナルティを掛ける。
    main_accuracy = (
        _cap_physical_accuracy_for_build(main_acc + agility // 4 + base.job_level // 4)
        if main_pow
        else 0
    )
    off_accuracy = (
        _cap_physical_accuracy_for_build(off_acc + agility // 4 + base.job_level // 4)
        if off_pow
        else 0
    )

    final = FinalCharacterStats(
        level=base.level,
        job_level=base.job_level,
        job_skill_point=base.job_skill_point,
        max_hp=base.max_hp,
        strength=strength,
        agility=agility,
        vitality=vitality,
        intelligence=intelligence,
        mind=mind,
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
        weight=total_weight,
        elemental_resists=frozenset(elem_resist_total),
        elemental_nulls=frozenset(elem_null_total),
        elemental_weaks=frozenset(),
        elemental_absorbs=frozenset(),
        status_immunities=frozenset(status_imm_total),  # ★追加
    )

    # ★ 追加：武器属性を共通パーサで正規化
    final.main_weapon_elements = parse_elements(main_weapon_elements)
    final.off_weapon_elements = parse_elements(off_weapon_elements)
    final.elemental_magic_boosts = equipment_elemental_magic_boosts(eq)

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


# HP期待値算出関数
def expected_max_hp_from_vit_table(
    job_stats_levels: Dict[int, Dict[str, Any]],
    target_level: int,
    *,
    initial_hp_lv1: int = 32,
    rand_expect: float = 1.25,
    vit_key: str = "Vit",
) -> int:
    """
    ジョブの StatsByLevel（Level->row dict）から、HP期待値を算出する。

    採用モデル:
      Lvアップ時HP上昇 = Level + Vit(level) * rand
      rand は 1.0～1.5 の期待値として rand_expect (=1.25) を使用

    - Lv1 の初期HPは initial_hp_lv1 とする
    - Lv2..target_level まで逐次加算
    - 各レベルの上昇分は floor（切り捨て）して整数化

    Args:
        job_stats_levels: {Level: {"Vit": ..., ...}, ...} の辞書（Level1～99が入っている想定）
        target_level: 期待値を求めたいレベル（1～99）
        initial_hp_lv1: Lv1の初期HP
        rand_expect: 乱数(1.0～1.5)の期待値（1.25）
        vit_key: row内のVitキー名（通常 "Vit"）

    Returns:
        期待最大HP（int）
    """
    if not (1 <= target_level <= 99):
        raise ValueError(f"target_level must be 1..99, got {target_level}")

    # Lv1は初期値
    if target_level == 1:
        return int(initial_hp_lv1)

    # Levelの欠損があると困るので早めに検出
    # （StatsByLevelを1～99格納した前提なら全部存在するはず）
    missing = [lv for lv in range(1, target_level + 1) if lv not in job_stats_levels]
    if missing:
        raise KeyError(
            f"job_stats_levels に Level が不足しています: {missing[:10]}"
            + (" ..." if len(missing) > 10 else "")
        )

    hp = float(initial_hp_lv1)

    # Lv2～targetまで加算
    for lv in range(2, target_level + 1):
        vit = job_stats_levels[lv].get(vit_key)
        if vit is None:
            raise KeyError(f"Level {lv} row に '{vit_key}' がありません")
        vit = int(vit)

        inc = lv + (vit * rand_expect)
        hp += math.floor(inc)

    return int(hp)


# セーブデータの正規化
def normalize_party_entry(entry: dict, level_table: LevelTable) -> dict:
    # entry を破壊的に変更したくなければ copy() する
    e = dict(entry)

    lv = int(e.get("level", 1))
    exp = int(e.get("exp", 0))

    e["level"] = lv
    e["exp"] = level_table.clamp_exp_to_level_lower(lv, exp)
    return e


# 汎用：装備可能判定
def can_equip_item(job, item_data: dict) -> bool:
    """
    item_data["EquippedBy"] の中に job.slug or job.name が含まれる想定。
    JSON仕様が違う場合はここだけ合わせればOK。
    """
    eq = item_data.get("EquippedBy")
    if not eq:
        return True
    # EquippedBy が list/str どちらでも耐える
    if isinstance(eq, str):
        return (job.slug in eq) or (job.name in eq)
    if isinstance(eq, list):
        return (job.slug in eq) or (job.name in eq)
    return True


# 装備不可を外す本体
def strip_illegal_equipment_for_job(
    eq: EquipmentSet,
    job,
    weapons_by_name: dict,
    armors_by_name: dict,
) -> tuple[EquipmentSet, list[str]]:
    """
    新ジョブで装備できないものを None にして返す。
    戻り値: (new_eq, removed_list)
    """
    removed: list[str] = []
    new_eq = EquipmentSet(
        main_hand=eq.main_hand,
        off_hand=eq.off_hand,
        head=eq.head,
        body=eq.body,
        arms=eq.arms,
    )

    # 武器は main/off
    for slot in ("main_hand", "off_hand"):
        name = getattr(new_eq, slot)
        if not name:
            continue
        data = weapons_by_name.get(name)
        # 武器データに無い（表記違い等）なら外さない/外すの選択があるが、まずは外す
        if data is None or not can_equip_item(job, data):
            removed.append(f"{slot}: {name}")
            setattr(new_eq, slot, None)

    # 防具は off_hand(盾) / head / body / arms
    for slot in ("off_hand", "head", "body", "arms"):
        name = getattr(new_eq, slot)
        if not name:
            continue
        data = armors_by_name.get(name)
        # off_hand は武器か盾か両方ありうるので、防具側にも無いならスキップ
        if data is None:
            continue
        if not can_equip_item(job, data):
            removed.append(f"{slot}: {name}")
            setattr(new_eq, slot, None)

    return new_eq, removed
