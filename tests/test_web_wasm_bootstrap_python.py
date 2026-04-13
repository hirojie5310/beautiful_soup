# tests/test_web_wasm_bootstrap_python.py
from __future__ import annotations

import importlib.util
from pathlib import Path


def test_bootstrap_python_file_is_syntax_valid() -> None:
    source = Path("web_wasm/bootstrap_runtime.py").read_text(encoding="utf-8")
    compile(source, "<web_wasm_bootstrap>", "exec")


def test_main_js_loads_external_bootstrap_python_file() -> None:
    source = Path("web_wasm/pyodide_runtime.js").read_text(encoding="utf-8")
    assert 'loadPackage("jsonschema")' in source
    assert 'fetch("./bootstrap_runtime.py")' in source
    assert "runPythonAsync(bootstrapPython)" in source


def test_bootstrap_migrate_save_upgrades_v1_legacy_save_to_v2() -> None:
    path = Path("web_wasm/bootstrap_runtime.py")
    spec = importlib.util.spec_from_file_location("bootstrap_runtime_for_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    migrated = module.migrate_save(
        {
            "schema_version": 1,
            "party": [
                {
                    "name": "Refia",
                    "job": "Dragoon",
                    "mp": {"L1MP": 3, "L8MP": 1},
                }
            ],
            "inventory": {},
            "gil": 0,
            "CP": 0,
        }
    )

    assert migrated["schema_version"] == 2
    assert migrated["party"][0]["name"] == "Refia"
    assert migrated["party"][0]["current_job"] == "Dragoon"
    assert migrated["party"][0]["mp_levels"]["1"]["current"] == 3
    assert migrated["party"][0]["mp_levels"]["8"]["current"] == 1
