from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

from typing_extensions import NotRequired

from assets.data.data_loader import (
    validate_save_data,
    load_monsters,
    load_weapons,
    load_armors,
    load_spells,
    load_items,
    load_jobs,
    load_savedata,
)
from combat.errors import StateNotInitializedError


class JobProgressState(TypedDict):
    level: int
    skill_point: int


class MpLevelState(TypedDict, total=False):
    current: int
    max: NotRequired[int]


class SavePartyMemberState(TypedDict, total=False):
    name: str
    level: int
    exp: int
    job: str
    current_job: NotRequired[str]
    job_level: JobProgressState
    job_levels: dict[str, JobProgressState]
    hp: int
    max_hp: int
    mp: dict[str, int]
    mp_levels: dict[str, MpLevelState]
    equipment: dict[str, str | None]
    Magic: dict[str, list[str | None]]
    status_effects: dict[str, bool]
    row: str
    portrait_key: str
    image_name: str


class SaveDataState(TypedDict, total=False):
    schema_version: int
    party: list[SavePartyMemberState]
    inventory: dict[str, Any]
    item_stock: NotRequired[dict[str, Any]]
    gil: int
    CP: int
    event_flag: NotRequired[dict[str, Any]]
    treasures: NotRequired[dict[str, Any]]


@dataclass
class RuntimeState:
    monsters: Dict[str, Dict[str, Any]]
    weapons: Dict[str, Dict[str, Any]]
    armors: Dict[str, Dict[str, Any]]
    spells: Dict[str, Dict[str, Any]]
    items_by_name: Dict[str, Dict[str, Any]]
    jobs_by_name: Dict[str, Any]  # Job 型があれば Job に
    save: Dict[str, Any]
    base_dir: Path

    def apply(self, patch: Any) -> None:
        """RuntimeState への保存差分適用入口。"""
        from combat.battle_save_patch import BattleSavePatch, apply_battle_save_patch

        if isinstance(patch, BattleSavePatch):
            apply_battle_save_patch(self.save, patch)
            validate_runtime_state(self)
            return
        raise TypeError(f"unsupported RuntimeState patch: {type(patch).__name__}")


class RuntimeStateInvariantError(ValueError):
    """RuntimeState の明文化された不変条件に違反したときの例外。"""


_DATA_DIR = Path("assets/data")
_MASTER_INDEX_FIELDS = (
    "monsters",
    "weapons",
    "armors",
    "spells",
    "items_by_name",
    "jobs_by_name",
)


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _raise_invariant(message: str) -> None:
    raise RuntimeStateInvariantError(message)


def _validate_non_negative_number(value: Any, path: str) -> None:
    if not _is_non_negative_int(value):
        _raise_invariant(f"{path} must be a non-negative integer")


def _validate_job_progress(progress: Any, path: str) -> None:
    if not isinstance(progress, dict):
        _raise_invariant(f"{path} must be an object")
    if not _is_positive_int(progress.get("level")):
        _raise_invariant(f"{path}.level must be a positive integer")
    _validate_non_negative_number(progress.get("skill_point"), f"{path}.skill_point")


def _validate_inventory_counts(value: Any, path: str) -> None:
    if value is None:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_inventory_counts(child, f"{path}.{key}")
        return
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 0:
            _raise_invariant(f"{path} must not contain negative counts")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_inventory_counts(child, f"{path}[{index}]")


def _validate_mp_levels(mp_levels: Any, path: str) -> None:
    if not isinstance(mp_levels, dict):
        _raise_invariant(f"{path} must be an object")
    for level, row in mp_levels.items():
        row_path = f"{path}.{level}"
        if not isinstance(row, dict):
            _raise_invariant(f"{row_path} must be an object")
        current = row.get("current", 0)
        max_value = row.get("max")
        _validate_non_negative_number(current, f"{row_path}.current")
        if max_value is not None:
            _validate_non_negative_number(max_value, f"{row_path}.max")
            if current > max_value:
                _raise_invariant(f"{row_path}.current must be <= max")


def _validate_party_member(member: Any, index: int) -> None:
    path = f"save.party[{index}]"
    if not isinstance(member, dict):
        _raise_invariant(f"{path} must be an object")
    if not isinstance(member.get("name"), str) or not member.get("name"):
        _raise_invariant(f"{path}.name must be a non-empty string")

    if "level" in member and not _is_positive_int(member.get("level")):
        _raise_invariant(f"{path}.level must be a positive integer")
    if "exp" in member:
        _validate_non_negative_number(member.get("exp"), f"{path}.exp")

    if "hp" in member:
        _validate_non_negative_number(member.get("hp"), f"{path}.hp")
    if "max_hp" in member:
        _validate_non_negative_number(member.get("max_hp"), f"{path}.max_hp")
    if "hp" in member and "max_hp" in member and member["hp"] > member["max_hp"]:
        _raise_invariant(f"{path}.hp must be <= max_hp")

    if "row" in member and member.get("row") not in {"front", "back"}:
        _raise_invariant(f"{path}.row must be 'front' or 'back'")

    if "job_level" in member:
        _validate_job_progress(member.get("job_level"), f"{path}.job_level")
    job_levels = member.get("job_levels")
    if job_levels is not None:
        if not isinstance(job_levels, dict):
            _raise_invariant(f"{path}.job_levels must be an object")
        for job_name, progress in job_levels.items():
            _validate_job_progress(progress, f"{path}.job_levels.{job_name}")

    mp = member.get("mp")
    if mp is not None:
        if not isinstance(mp, dict):
            _raise_invariant(f"{path}.mp must be an object")
        for key, value in mp.items():
            _validate_non_negative_number(value, f"{path}.mp.{key}")

    if "mp_levels" in member:
        _validate_mp_levels(member.get("mp_levels"), f"{path}.mp_levels")


def validate_runtime_state(state: RuntimeState) -> None:
    """
    RuntimeState の境界契約を検証する。

    型契約:
    - マスタデータは name -> row の dict として保持する。
    - save は SaveDataState 相当の JSON 化可能な dict として保持する。
    - base_dir は Path として保持する。

    不変条件:
    - save.gil / save.CP / inventory counts は負にならない。
    - party member の name は空文字不可。
    - hp, max_hp, exp, mp は負にならず、hp <= max_hp。
    - row は front/back のみ。
    - job_level / job_levels は level >= 1, skill_point >= 0。
    """

    if not isinstance(state, RuntimeState):
        _raise_invariant("state must be RuntimeState")
    for field_name in _MASTER_INDEX_FIELDS:
        value = getattr(state, field_name, None)
        if not isinstance(value, dict):
            _raise_invariant(f"{field_name} must be a dictionary")
    if not isinstance(state.base_dir, Path):
        _raise_invariant("base_dir must be a Path")
    if not isinstance(state.save, dict):
        _raise_invariant("save must be a dictionary")

    _validate_non_negative_number(state.save.get("gil"), "save.gil")
    _validate_non_negative_number(state.save.get("CP"), "save.CP")

    party = state.save.get("party")
    if not isinstance(party, list):
        _raise_invariant("save.party must be a list")
    for index, member in enumerate(party):
        _validate_party_member(member, index)

    _validate_inventory_counts(state.save.get("inventory", {}), "save.inventory")
    _validate_inventory_counts(state.save.get("item_stock", {}), "save.item_stock")
    try:
        validate_save_data(state.save)
    except ValueError as exc:
        _raise_invariant(str(exc))




def resolve_runtime_base_dir(base_dir: Path = Path(".")) -> Path:
    """実行環境に応じてマスタデータの基準ディレクトリを解決する。"""

    candidates = [base_dir]
    if not base_dir.is_absolute():
        candidates.append(Path("/"))

    for candidate in candidates:
        if (candidate / _DATA_DIR).exists():
            return candidate
    return base_dir


def resolve_data_path(path: str | Path, *, base_dir: Path = Path(".")) -> Path:
    """相対データパスを、実行環境に応じた基準ディレクトリ配下へ解決する。"""

    path = Path(path)
    if path.is_absolute():
        return path
    return resolve_runtime_base_dir(base_dir) / path


def init_runtime_state(
    base_dir: Path = Path("."),
    *,
    allowed_names=None,
    cast_code=None,
) -> RuntimeState:
    """アプリ起動時に1回だけ呼ぶ想定の初期化"""

    resolved_base_dir = resolve_runtime_base_dir(base_dir)

    monsters = load_monsters(resolved_base_dir / "assets/data/ffiii_monsters.json")
    weapons = load_weapons(resolved_base_dir / "assets/data/ffiii_weapons.json")
    armors = load_armors(resolved_base_dir / "assets/data/ffiii_armors.json")
    spells = load_spells(resolved_base_dir / "assets/data/ffiii_spells.json")
    items_by_name = load_items(resolved_base_dir / "assets/data/ffiii_items.json")
    jobs_by_name = load_jobs(resolved_base_dir / "assets/data/ffiii_jobs_compact.json")
    save = load_savedata(resolved_base_dir / "assets/data/ffiii_savedata.json")

    state = RuntimeState(
        monsters=monsters,
        weapons=weapons,
        armors=armors,
        spells=spells,
        items_by_name=items_by_name,
        jobs_by_name=jobs_by_name,
        save=save,
        base_dir=resolved_base_dir,
    )
    validate_runtime_state(state)
    return state


def get_state(state: Optional[RuntimeState]) -> RuntimeState:
    """グローバル参照を使わず、呼び出し側が保持する RuntimeState を受け取る。"""
    if state is None:
        raise StateNotInitializedError(
            "RuntimeState が未設定です。init_runtime_state() の戻り値を渡してください"
        )
    return state
