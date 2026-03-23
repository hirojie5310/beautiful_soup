# tests/test_build_wasm_bundle.py
from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from scripts.build_wasm_bundle import build_wasm_bundle


def test_build_wasm_bundle_writes_expected_sources(tmp_path: Path) -> None:
    output_path = tmp_path / "python_bundle.zip"

    built_path = build_wasm_bundle(output_path=output_path)

    assert built_path == output_path
    assert output_path.exists()

    with ZipFile(output_path) as zip_file:
        names = set(zip_file.namelist())

    assert "combat/wasm_api.py" in names
    assert "combat/dto.py" in names
    assert "assets/data/ffiii_monsters.json" in names
    assert "system/exp_system.py" in names
    assert "utils/safe_int_float.py" in names
