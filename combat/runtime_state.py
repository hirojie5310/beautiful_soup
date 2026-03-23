from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from assets.data.data_loader import (
    load_monsters,
    load_weapons,
    load_armors,
    load_spells,
    load_items,
    load_jobs,
    load_savedata,
)
from combat.errors import StateNotInitializedError


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


_DATA_DIR = Path("assets/data")


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

    return RuntimeState(
        monsters=monsters,
        weapons=weapons,
        armors=armors,
        spells=spells,
        items_by_name=items_by_name,
        jobs_by_name=jobs_by_name,
        save=save,
        base_dir=resolved_base_dir,
    )


def get_state(state: Optional[RuntimeState]) -> RuntimeState:
    """グローバル参照を使わず、呼び出し側が保持する RuntimeState を受け取る。"""
    if state is None:
        raise StateNotInitializedError(
            "RuntimeState が未設定です。init_runtime_state() の戻り値を渡してください"
        )
    return state
