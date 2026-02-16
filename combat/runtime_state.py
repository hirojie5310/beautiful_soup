# ============================================================
# runtime_state: 実行時状態

# RuntimeState	JSONデータ格納用Dictクラス
# init_runtime_state	アプリ起動時に1回だけ呼ぶ想定の初期化
# get_state	明示的に渡された RuntimeState を検証して返す
# ============================================================

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


def init_runtime_state(
    base_dir: Path = Path("."),
    *,
    allowed_names=None,
    cast_code=None,
) -> RuntimeState:
    """アプリ起動時に1回だけ呼ぶ想定の初期化"""

    monsters = load_monsters(base_dir / "assets/data/ffiii_monsters.json")
    weapons = load_weapons(base_dir / "assets/data/ffiii_weapons.json")
    armors = load_armors(base_dir / "assets/data/ffiii_armors.json")
    spells = load_spells(base_dir / "assets/data/ffiii_spells.json")
    items_by_name = load_items(base_dir / "assets/data/ffiii_items.json")
    jobs_by_name = load_jobs(base_dir / "assets/data/ffiii_jobs_compact.json")
    save = load_savedata(base_dir / "assets/data/ffiii_savedata.json")

    return RuntimeState(
        monsters=monsters,
        weapons=weapons,
        armors=armors,
        spells=spells,
        items_by_name=items_by_name,
        jobs_by_name=jobs_by_name,
        save=save,
    )


def get_state(state: Optional[RuntimeState]) -> RuntimeState:
    """グローバル参照を使わず、呼び出し側が保持する RuntimeState を受け取る。"""
    if state is None:
        raise StateNotInitializedError(
            "RuntimeState が未設定です。init_runtime_state() の戻り値を渡してください"
        )
    return state
