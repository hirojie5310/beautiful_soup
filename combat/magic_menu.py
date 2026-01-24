# ============================================================
# magic_menu: メニュー生成まわり

# build_party_magic_lists	キャラごとのジョブで使える魔法一覧生成
# build_party_magic_info	パーティのジョブ名、使用できる魔法リスト等を生成
# build_magic_list	ジョブが使える魔法名(魔法名,種別,レベル)のリストにして整列して返す
# allowed_spell_names_for_job	ffiii_jobs_compact.jsonのjob.raw["Spells"]を正とし、
# print_magic_menu_by_level	魔法をLv単位で1行形式で表示する
# expand_spells_for_summons	spells.json内のSummonMagic（親：Bahamut等）を、子召喚魔法へ展開する
# ============================================================

from typing import Optional, Dict, Any, Tuple, List, Iterable
from collections import defaultdict

from combat.constants import JOB_CAST_CODE
from combat.models import (
    Job,
    BattleActorState,
    PartyMagicInfo,
    MagicCandidate,
    MagicType,
)


# party_entry からジョブ名を取得（揺れ対策）
def get_job_name_from_party_entry(party_entry: Dict[str, Any]) -> str:
    job_name = party_entry.get("job") or party_entry.get("job_level", {}).get("job")
    if not isinstance(job_name, str) or not job_name:
        raise KeyError("party_entry に job が見つかりません")
    return job_name


# キャラごとのジョブで使える魔法一覧生成（薄いラッパ）
def build_party_magic_lists(state) -> List[List[MagicCandidate]]:
    return build_party_magic_lists_from_party(
        party_entries=state.save["party"],
        jobs_by_name=state.jobs_by_name,
        spells_by_name=state.spells,
        job_cast_code=JOB_CAST_CODE,
    )


# キャラごとのジョブで使える魔法一覧生成
def build_party_magic_lists_from_party(
    *,
    party_entries: List[Dict[str, Any]],
    jobs_by_name: Dict[str, Any],  # Job型でもOK
    spells_by_name: Dict[str, Dict[str, Any]],  # expand後でもexpand前でもOK
    job_cast_code: Dict[str, str],  # = JOB_CAST_CODE
) -> List[List[MagicCandidate]]:
    spells_expanded = expand_spells_for_summons(spells_by_name)

    out: List[List[MagicCandidate]] = []

    for entry in party_entries:
        job_name = get_job_name_from_party_entry(entry)

        try:
            job_data = jobs_by_name[job_name]
        except KeyError as e:
            raise KeyError(f"jobs_by_name に '{job_name}' が存在しません") from e

        cast_code = job_cast_code.get(job_name)
        allowed_names = allowed_spell_names_for_job(job_data)

        magic_list = build_magic_list(
            spells_expanded,
            allowed_names=allowed_names,
            cast_code=cast_code,
        )
        out.append(magic_list)

    # print(f"[DBG build_party_magic_lists_from_party]{out}")
    return out


# パーティのジョブ名、使用できる魔法リスト等を生成（薄いラッパ）
def build_party_magic_info(state) -> List[PartyMagicInfo]:
    return build_party_magic_info_from_party(
        party_entries=state.save["party"],
        jobs_by_name=state.jobs_by_name,
        spells_by_name=state.spells,
        job_cast_code=JOB_CAST_CODE,
    )


# パーティのジョブ名、使用できる魔法リスト等を生成
def build_party_magic_info_from_party(
    *,
    party_entries: List[Dict[str, Any]],
    jobs_by_name: Dict[str, Any],
    spells_by_name: Dict[str, Dict[str, Any]],
    job_cast_code: Dict[str, str],
) -> List[PartyMagicInfo]:
    spells_expanded = expand_spells_for_summons(spells_by_name)

    out: List[PartyMagicInfo] = []

    for entry in party_entries:
        job_name = get_job_name_from_party_entry(entry)

        try:
            job_data = jobs_by_name[job_name]
        except KeyError as e:
            raise KeyError(f"jobs_by_name に '{job_name}' が存在しません") from e

        cast_code = job_cast_code.get(job_name)
        allowed_names = allowed_spell_names_for_job(job_data)

        magic_list = build_magic_list(
            spells_expanded,
            allowed_names=allowed_names,
            cast_code=cast_code,
        )

        out.append(
            PartyMagicInfo(
                job_name=job_name,
                cast_code=cast_code,
                allowed_names=allowed_names,
                magic_list=magic_list,
            )
        )

    return out


# --- ここから追加: 魔法一覧と選択メニュー ---
def build_magic_list(
    spells_by_name: Dict[str, Dict[str, Any]],
    *,
    allowed_names: Optional[Iterable[str]] = None,
    cast_code: Optional[str] = None,
) -> List[MagicCandidate]:

    allowed_set = set(allowed_names) if allowed_names is not None else None

    lst: List[MagicCandidate] = []
    for name, s in spells_by_name.items():

        if allowed_set is not None and name not in allowed_set:
            continue

        if cast_code is not None:
            cast_by = s.get("CastBy")
            if cast_by:
                if isinstance(cast_by, str):
                    ok = cast_code in [c.strip() for c in cast_by.split(",")]
                elif isinstance(cast_by, list):
                    ok = cast_code in cast_by
                else:
                    ok = False
                if not ok:
                    continue

        t_raw = s.get("Type", "")
        if t_raw not in ("Black Magic", "White Magic", "Summon Magic", "Summon"):
            continue

        level = int(s.get("Level", 0) or 0)

        # 子召喚(Type="Summon")は Summon Magic に寄せる
        t_raw = "Summon Magic" if t_raw == "Summon" else t_raw

        # ★ ここで Enum 化（境界変換）
        try:
            t_norm = MagicType(t_raw)
        except ValueError:
            continue

        lst.append((name, t_norm, level))

    type_order = {"Black Magic": 0, "White Magic": 1, "Summon Magic": 2}
    lst.sort(key=lambda x: (type_order.get(x[1], 99), x[2], x[0]))
    return lst


# ============================================================
# ジョブ別の魔法使用制限ヘルパー
# ============================================================


def allowed_spell_names_for_job(job: Job) -> set[str]:
    """
    ffiii_jobs_compact.json の job.raw["Spells"] を正とし、
    そのジョブが使用可能な魔法名の集合を返す。
    """
    spells = job.raw.get("Spells") or []
    return {s.get("Name") for s in spells if s.get("Name")}


# レベル別・黒白まとめ表示関数
def print_magic_menu_by_level(
    magic_list: List[Tuple[str, str, int]],
    char_state: BattleActorState,
):
    """
    魔法を Lv 単位で 1 行形式で表示する。
    例:
      Lv1 (3/9): (Black) 1: Blizzard, 2: Fire (White) 13: Cure, 14: Poisona
    """
    bucket = defaultdict(lambda: defaultdict(list))

    for idx, (name, mtype, lvl) in enumerate(magic_list, start=1):
        bucket[lvl][mtype].append((idx, name))

    type_label = {
        "Black Magic": "Black",
        "White Magic": "White",
        "Summon Magic": "Summon",
    }

    for lvl in sorted(bucket.keys()):
        remain = char_state.mp_pool.get(lvl, 0)
        maxmp = char_state.max_mp_pool.get(lvl, remain)

        # --- 行頭（LvX (a/b): ）
        line = f"Lv{lvl} ({remain}/{maxmp}): "

        parts = []
        for mtype in ("Black Magic", "White Magic", "Summon Magic"):
            if mtype not in bucket[lvl]:
                continue
            spells = bucket[lvl][mtype]
            s = ", ".join([f"{i}: {nm}" for i, nm in spells])
            parts.append(f"({type_label.get(mtype, mtype)}) {s}")

        # --- 1行でまとめて出力 ---
        line += " ".join(parts)
        print(line)


def expand_spells_for_summons(
    spells_by_name: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    spells.json 内の Summon Magic（親：Bahamut等）を、
    実戦で使う「子召喚魔法（Bahamut: Mega Flare等）」へ展開する。

    - 親(Type="Summon Magic" かつ Spellsを持つ) → 子を展開
    - すでに展開済みの子（Spellsを持たない Summon Magic）はそのまま残す
    - 子には Power/Accuracy/Element 等を保持させる
    - 子の Type は "Summon" にする（spell_from_json が子分岐に入るため）
    """
    expanded: Dict[str, Dict[str, Any]] = {}

    def norm_cast(x) -> List[str]:
        if not x:
            return []
        if isinstance(x, str):
            return [c.strip() for c in x.split(",") if c.strip()]
        if isinstance(x, list):
            return [str(c).strip() for c in x if str(c).strip()]
        return []

    for name, s in spells_by_name.items():
        raw_type = str(s.get("Type", "")).strip()
        child_list = s.get("Spells")

        # --- 親 Summon Magic（子配列を持つもの）だけ展開 ---
        if raw_type == "Summon Magic" and isinstance(child_list, list) and child_list:
            parent_cast = norm_cast(s.get("CastBy"))

            for child in child_list:
                child_name = child.get("Name") or child.get("name")
                if not child_name:
                    continue

                child_cast = norm_cast(child.get("CastBy") or child.get("Cast By"))
                cast_merged = sorted(set(parent_cast + child_cast))

                # 子の中身を基本そのまま使う（Power等を保持）
                new_child = dict(child)
                new_child["name"] = child_name  # load_spells 形式に合わせる
                new_child["Type"] = "Summon"  # ★ここ重要
                if cast_merged:
                    new_child["CastBy"] = cast_merged

                expanded[child_name] = new_child

        else:
            # 召喚親ではない or すでに子として展開済み → そのまま採用
            expanded[name] = s

    return expanded
