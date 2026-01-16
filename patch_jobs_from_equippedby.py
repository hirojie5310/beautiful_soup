"""
Jobデータにおける装備可能な武器・防具データを、装備データにより補完

装備データ（weapons/armors）の EquippedBy を正として、
job["Weapons"] には {"Name": weapon_name, "Type": weapon_type} を追加
job["Armors"] には {"Name": armor_name, "Type": armor_armorType} を追加
"""

import json
from pathlib import Path
from collections import defaultdict

WEAPONS_PATH = Path("assets/data/ffiii_weapons.json")
ARMORS_PATH = Path("assets/data/ffiii_armors.json")
JOBS_PATH = Path("assets/data/ffiii_jobs_compact.json")
OUT_PATH = Path("assets/data/ffiii_jobs_patched.json")


def load_json(p: Path):
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def ensure_list(obj: dict, key: str) -> list:
    v = obj.get(key)
    if isinstance(v, list):
        return v
    obj[key] = []
    return obj[key]


def job_code_from_job(job: dict) -> str | None:
    """
    jobs.json 内に BB/Ni のような略号が無い前提が多いので、
    ここでは基本使いません（manual_code_mapで与える）
    """
    return None


def extract_name_set(items: list) -> set[str]:
    """
    [{"Name":"X","Type":"Y"}, ...] から Name の集合を取る
    """
    out = set()
    for it in items:
        if isinstance(it, dict):
            n = it.get("Name") or it.get("name")
            if isinstance(n, str) and n.strip():
                out.add(n.strip())
        elif isinstance(it, str) and it.strip():
            out.add(it.strip())
    return out


def merge_items_by_name(dst_list: list, add_items: list[dict]) -> int:
    """
    dst_list: jobs.json の Weapons/Armors (dict配列)
    add_items: [{"Name":..., "Type":...}, ...]
    Name重複しないものだけ追加。戻り値=追加数
    """
    existing = extract_name_set(dst_list)
    added = 0
    for it in add_items:
        n = it.get("Name")
        t = it.get("Type")
        if not isinstance(n, str) or not n.strip():
            continue
        name = n.strip()
        if name in existing:
            continue
        dst_list.append({"Name": name, "Type": t})
        existing.add(name)
        added += 1
    return added


def main():
    weapons_json = load_json(WEAPONS_PATH)
    armors_json = load_json(ARMORS_PATH)
    jobs_json = load_json(JOBS_PATH)

    weapons = weapons_json.get("weapons", [])
    armors = armors_json.get(
        "armors", armors_json.get("Armors", armors_json.get("armor", []))
    )

    # job_code -> list of {"Name","Type"}
    allow_weapons_by_job: dict[str, list[dict]] = defaultdict(list)
    allow_armors_by_job: dict[str, list[dict]] = defaultdict(list)

    # ---- 武器集計（Nameベースで貯める）----
    if isinstance(weapons, list):
        for w in weapons:
            if not isinstance(w, dict):
                continue
            name = w.get("name") or w.get("Name")
            wtype = w.get("Type")
            eqby = w.get("EquippedBy", [])
            if not (
                isinstance(name, str)
                and isinstance(wtype, str)
                and isinstance(eqby, list)
            ):
                continue
            for code in eqby:
                if isinstance(code, str) and code.strip():
                    allow_weapons_by_job[code.strip()].append(
                        {"Name": name.strip(), "Type": wtype.strip()}
                    )

    # ---- 防具集計（ArmorType を jobs側 Type に入れる）----
    if isinstance(armors, list):
        for a in armors:
            if not isinstance(a, dict):
                continue
            name = a.get("name") or a.get("Name")
            atype = a.get("ArmorType")  # 重要
            eqby = a.get("EquippedBy", [])
            if not (
                isinstance(name, str)
                and isinstance(atype, str)
                and isinstance(eqby, list)
            ):
                continue
            for code in eqby:
                if isinstance(code, str) and code.strip():
                    allow_armors_by_job[code.strip()].append(
                        {"Name": name.strip(), "Type": atype.strip()}
                    )

    # jobsの配列取り出し
    if isinstance(jobs_json, dict) and isinstance(jobs_json.get("jobs"), list):
        jobs_list = jobs_json["jobs"]
    elif isinstance(jobs_json, list):
        jobs_list = jobs_json
    else:
        raise ValueError("jobs.json の構造が想定外（jobs配列が見つからない）")

    # ★ ここが必須：ジョブ名→略号（EquippedBy側のコード）
    manual_code_map = {
        # 例：必要分を全部埋める
        "Onion Knight": "OK",
        "Warrior": "Wa",
        "Monk": "Mo",
        "White Mage": "WM",
        "Black Mage": "BM",
        "Red Mage": "RM",
        "Ranger": "Ra",
        "Knight": "Kn",
        "Thief": "Th",
        "Scholar": "Sc",
        "Geomancer": "Ge",
        "Dragoon": "Dr",
        "Viking": "Vi",
        "Black Belt": "BB",
        "Evoker": "Ev",
        "Bard": "Ba",
        "Magus": "Ma",
        "Devout": "De",
        "Summoner": "Su",
        "Sage": "Sa",
        "Ninja": "Ni",
        "Mystic Knight": "MK",
        # ...あなたの環境の全ジョブ分を入れる
    }

    patched_jobs = 0
    added_w_total = 0
    added_a_total = 0
    missing = 0

    for job in jobs_list:
        if not isinstance(job, dict):
            continue

        job_name = job.get("Name") or job.get("name")
        if not isinstance(job_name, str) or not job_name.strip():
            continue

        # manual優先
        code = manual_code_map.get(job_name.strip())
        if code is None:
            # 取れないならスキップ（ここに来ないよう manual_map を埋める）
            missing += 1
            continue

        add_ws = allow_weapons_by_job.get(code, [])
        add_as = allow_armors_by_job.get(code, [])

        wlist = ensure_list(job, "Weapons")
        alist = ensure_list(job, "Armors")

        aw = merge_items_by_name(wlist, add_ws)
        aa = merge_items_by_name(alist, add_as)

        if aw or aa:
            patched_jobs += 1
            added_w_total += aw
            added_a_total += aa

    dump_json(OUT_PATH, jobs_json)
    print("=== done ===")
    print("patched jobs:", patched_jobs)
    print("added weapon items:", added_w_total)
    print("added armor items :", added_a_total)
    print("jobs missing code:", missing)
    print("output:", OUT_PATH)


if __name__ == "__main__":
    main()
