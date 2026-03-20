# ============================================================
# data_loader: JSON読込み + マスタ定義

# _load_named_index	共通：JSONを読み込み、top_key配下をname_keyでdict化
# load_monsters	モンスターJSONをname→dictにして返す
# load_weapons	武器JSONをname→dictにして返す
# load_armors	防具JSONをname→dictにして返す
# load_spells	魔法JSONをname→dictにして返す
# load_items	アイテムJSONをName→dictにして返す
# load_jobs	ジョブJSONを読み込み、Jobオブジェクトの辞書を作成
# load_savedata	セーブデータJSONを読み込む
# MASTER_SPELLS_BY_NAME(代入)	ff3_calc内部から魔法定義を名前で引けるようにするための共有キャッシュ
# ============================================================

import json
from pathlib import Path
from typing import Dict, Any, Sequence, TypedDict
from typing_extensions import NotRequired

from combat.models import Job, JobLevelStats, EquipmentSet, PartyMemberRuntime


class ExplicitGroupDef(TypedDict):
    locations: list[str]
    world: NotRequired[str]
    order: NotRequired[int]


# ============================================================
# JSON ロード
# ============================================================


def _load_named_index(
    path: Path, top_key: str, name_key: str = "name"
) -> Dict[str, Dict[str, Any]]:
    """共通：JSON を読み込み、top_key 配下を name_key で dict 化"""
    raw = _load_json_file(path)
    items = raw.get(top_key, [])
    return {item[name_key]: item for item in items}


def _load_json_file(path: Path) -> Any:
    """JSON ファイルを読み込む。構文エラー時はパスと位置を付けて投げ直す。"""
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"JSON parse error in {path} (line {e.lineno}, column {e.colno}): {e.msg}"
        ) from e


def load_monsters(path: Path) -> Dict[str, Dict[str, Any]]:
    """モンスター JSON を name → dict にして返す"""
    return _load_named_index(path, top_key="monsters")


def load_weapons(path: Path) -> Dict[str, Dict[str, Any]]:
    """武器 JSON を name → dict にして返す"""
    return _load_named_index(path, top_key="weapons")


def load_armors(path: Path) -> Dict[str, Dict[str, Any]]:
    """防具 JSON を name → dict にして返す"""
    return _load_named_index(path, top_key="armors")


def load_spells(path: Path) -> Dict[str, Dict[str, Any]]:
    """魔法 JSON を name → dict にして返す"""
    return _load_named_index(path, top_key="spells")


def load_items(path: Path) -> Dict[str, Dict[str, Any]]:
    """アイテム JSON を Name → dict にして返す"""
    return _load_named_index(path, top_key="items", name_key="Name")


# ジョブJSONを読み込み、Jobオブジェクトの辞書を作成（データの“ロード”というより“ドメインモデルの組み立て）
def load_jobs(path: Path) -> Dict[str, Job]:
    data = _load_json_file(path)  # ffiii_jobs_compact.json の中身
    jobs: Dict[str, Job] = {}

    for j in data["jobs"]:
        stats_by_level: Dict[int, JobLevelStats] = {}
        for row in j["StatsByLevel"]:
            lvl = row["Level"]
            # L1MP〜L8MP っぽいキーだけ抜き出す
            mp = {k: v for k, v in row.items() if k.endswith("MP") and v is not None}

            stats_by_level[lvl] = JobLevelStats(
                level=lvl,
                strength=row["Str"],
                agility=row["Agi"],
                vitality=row["Vit"],
                intelligence=row["Int"],
                mind=row["Mnd"],
                mp=mp,
            )

        jobs[j["Name"]] = Job(
            name=j["Name"],
            slug=j["Slug"],
            earned=j.get("Earned", ""),
            stats_by_level=stats_by_level,
            raw=j,
        )

    return jobs


def load_savedata(path: Path) -> dict:
    return _load_json_file(path)


def save_savedata(path: Path, save: dict) -> None:
    """
    savedata を JSON として保存する（UTF-8、整形あり）
    ensure_ascii=False：日本語が \\uXXXX" にならない
    indent=2：読みやすい
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(save, f, ensure_ascii=False, indent=2)


def apply_party_equipment_to_save(
    save: Dict[str, Any], party: Sequence[PartyMemberRuntime]
) -> None:
    """
    party(Runtime) の装備を save(dict) の party[].equipment に反映する（破壊的更新）
    照合は name で行う（savedataにも name があるため）:contentReference[oaicite:1]{index=1}
    """
    save_party = save.get("party", [])
    by_name = {p.get("name"): p for p in save_party}

    for actor in party:
        sp = by_name.get(actor.name)
        if sp is None:
            continue  # セーブ側にいない（念のため）

        eq = actor.equipment or EquipmentSet()

        sp["equipment"] = {
            "main_hand": eq.main_hand,
            "off_hand": eq.off_hand,
            "head": eq.head,
            "body": eq.body,
            "arms": eq.arms,
        }


def apply_party_job_to_save(save, party):
    save_party = save.get("party", [])
    by_name = {p.get("name"): p for p in save_party}

    for a in party:
        sp = by_name.get(a.name)
        if sp is None:
            continue

        # 現在ジョブ
        sp["job"] = a.job.name
        sp["job_level"] = {
            "level": int(a.base.job_level),
            "skill_point": int(a.base.job_skill_point),
        }

        # job_levels（辞書）にも同期
        jl = sp.get("job_levels")
        if not isinstance(jl, dict):
            jl = {}
            sp["job_levels"] = jl
        jl[a.job.name] = {
            "level": int(a.base.job_level),
            "skill_point": int(a.base.job_skill_point),
        }


# Mapグループ読み込み
from typing import cast


def load_explicit_groups(path: str | Path) -> dict[str, ExplicitGroupDef]:
    path = Path(path)
    raw = _load_json_file(path)

    if not isinstance(raw, dict):
        raise ValueError("explicit_groups.json must be an object")

    # 軽い検証（すでにやっている通り）
    for gname, entry in raw.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{gname} must be an object")
        if "locations" not in entry or not isinstance(entry["locations"], list):
            raise ValueError(f"{gname}.locations must be a list")

    # ★ ここで型を確定させる
    return cast(dict[str, ExplicitGroupDef], raw)
