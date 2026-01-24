# system/cp_system.py
from dataclasses import dataclass
import csv

CP_MAX = 255


# 1. CP 状態
@dataclass(frozen=True)
class CPStatus:
    value: int
    is_max: bool


# 2. 正規化（必須）
def normalize_cp(value: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    return max(0, min(CP_MAX, v))


# 3. 加算（戦闘勝利など）
def add_cp(current: int, gained: int) -> int:
    return normalize_cp(current + max(0, gained))


# 4. 消費（ジョブチェンジ）
def can_spend_cp(current: int, cost: int) -> bool:
    return current >= max(0, cost)


def spend_cp(current: int, cost: int) -> int:
    if cost <= 0:
        return current
    if current < cost:
        raise ValueError("Not enough CP")
    return normalize_cp(current - cost)


# 5. 状態取得（UI用）
def cp_status(value: int) -> CPStatus:
    v = normalize_cp(value)
    return CPStatus(value=v, is_max=(v >= CP_MAX))


# 6. ジョブアトリビューション読み込み
def load_job_attribution(csv_path: str) -> dict[str, dict[str, int]]:
    """
    job_attribution.csv を読み込み、
    job_attr[job_name] = {
        "magic_battle": int,
        "right_wrong": int,
    }
    の形式で返す。
    """
    job_attr: dict[str, dict[str, int]] = {}

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            job_name = row.get("job")
            if not job_name:
                continue

            try:
                magic_battle = int(row.get("magic_battle", 0))
            except (TypeError, ValueError):
                magic_battle = 0

            try:
                right_wrong = int(row.get("right_wrong", 0))
            except (TypeError, ValueError):
                right_wrong = 0

            job_attr[job_name] = {
                "magic_battle": magic_battle,
                "right_wrong": right_wrong,
            }

    return job_attr


# 7. CP計算
def compute_job_change_cp_cost(
    *,
    from_job: str,
    to_job: str,
    to_job_level: int,
    job_attr: dict,
) -> int:
    """
    CP cost = (Δmagic_battle + Δright_wrong) * 4 - (to_job_level - 1)
    最低 0
    """
    a = job_attr[from_job]
    b = job_attr[to_job]

    diff = abs(b["magic_battle"] - a["magic_battle"]) + abs(
        b["right_wrong"] - a["right_wrong"]
    )

    cost = diff * 4 - (to_job_level - 1)
    return max(0, cost)
