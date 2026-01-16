# ============================================================
# runtime_state: 実行時状態

# RuntimeState	JSONデータ格納用Dictクラス
# STATE	JSONデータを保持するためのグローバル（宣言）
# init_runtime_state	アプリ起動時に1回だけ呼ぶ想定の初期化（import runtime_state した瞬間に JSON を読み始める）
# get_state	STATE（JSONデータ）参照用（グローバル・サービスロケータ）
# ============================================================

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from combat.data_loader import (
    load_monsters,
    load_weapons,
    load_armors,
    load_spells,
    load_items,
    load_jobs,
    load_savedata,
)


@dataclass
class RuntimeState:
    monsters: Dict[str, Dict[str, Any]]
    weapons: Dict[str, Dict[str, Any]]
    armors: Dict[str, Dict[str, Any]]
    spells: Dict[str, Dict[str, Any]]
    items_by_name: Dict[str, Dict[str, Any]]
    jobs_by_name: Dict[str, Any]  # Job 型があれば Job に
    save: Dict[str, Any]


STATE: Optional[RuntimeState] = None


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

    global STATE
    STATE = RuntimeState(
        monsters=monsters,
        weapons=weapons,
        armors=armors,
        spells=spells,
        items_by_name=items_by_name,
        jobs_by_name=jobs_by_name,
        save=save,
    )
    return STATE


def get_state() -> RuntimeState:
    if STATE is None:
        raise RuntimeError("runtime_state.init_runtime_state() を先に呼んでください")
    return STATE
