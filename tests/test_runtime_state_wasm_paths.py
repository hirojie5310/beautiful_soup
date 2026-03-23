# tests/test_runtime_state_wasm_paths.py
from pathlib import Path
from combat.runtime_state import (
    RuntimeState,
    resolve_data_path,
    resolve_runtime_base_dir,
)
from combat.usecases import build_battle_session


BASE_DIR = Path(__file__).resolve().parents[1]


def test_resolve_runtime_base_dir_prefers_supplied_repo_path() -> None:
    assert resolve_runtime_base_dir(BASE_DIR) == BASE_DIR


def test_resolve_runtime_base_dir_falls_back_to_root_for_wasm(
    tmp_path: Path, monkeypatch
) -> None:
    wasm_root = tmp_path / "wasm-root"
    (wasm_root / "assets/data").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "combat.runtime_state.Path",
        lambda value=".": wasm_root if value == "/" else Path(value),
    )

    assert resolve_runtime_base_dir(Path(".")) == wasm_root


def test_resolve_data_path_uses_resolved_base_dir(tmp_path: Path, monkeypatch) -> None:
    wasm_root = tmp_path / "wasm-root"
    (wasm_root / "assets/data").mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "combat.runtime_state.Path",
        lambda value=".": wasm_root if value == "/" else Path(value),
    )

    assert (
        resolve_data_path("assets/data/level_exp.csv")
        == wasm_root / "assets/data/level_exp.csv"
    )


def test_build_battle_session_resolves_level_table_path(monkeypatch) -> None:
    state = RuntimeState(
        monsters={},
        weapons={},
        armors={},
        spells={},
        items_by_name={},
        jobs_by_name={},
        save={"party": []},
        base_dir=BASE_DIR,
    )

    captured: dict[str, str] = {}

    class DummyLevelTable:
        def __init__(self, csv_path: str):
            captured["csv_path"] = csv_path

    monkeypatch.setattr("combat.usecases.LevelTable", DummyLevelTable)
    monkeypatch.setattr("combat.usecases.build_party_magic_info", lambda state: {})
    monkeypatch.setattr("combat.usecases.build_party_magic_lists", lambda state: {})
    monkeypatch.setattr("combat.usecases.expand_spells_for_summons", lambda spells: {})
    monkeypatch.setattr(
        "combat.usecases.build_party_members_from_save",
        lambda **kwargs: [],
    )
    monkeypatch.setattr("combat.usecases.build_enemies", lambda **kwargs: [])

    build_battle_session(state=state, enemy_names=[])

    assert captured["csv_path"] == str(BASE_DIR / "assets/data/level_exp.csv")
