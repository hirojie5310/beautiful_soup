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
    assert "fetch(`./bootstrap_runtime.py?v=${RUNTIME_DATA_VERSION}`" in source
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


def test_boot_engine_explicit_empty_inventory_and_item_stock_override_base() -> None:
    path = Path("web_wasm/bootstrap_runtime.py")
    spec = importlib.util.spec_from_file_location("bootstrap_runtime_for_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_save = module._merge_save_data(None, module.state.save)
    original_boot = module.boot_engine_for_location

    def _fake_boot_engine_for_location(location_group, location, seed=7):
        return {
            "location_group": location_group,
            "location": location,
            "seed": seed,
        }

    module.boot_engine_for_location = _fake_boot_engine_for_location

    try:
        module.boot_engine_for_location_with_save_json(
            module.default_group,
            module.default_location,
            '{"schema_version":2,"inventory":{},"item_stock":{},"party":[]}',
            7,
        )
        assert module.state.save["inventory"] == {}
        assert module.state.save["item_stock"] == {}
    finally:
        module.state.save = original_save
        module.boot_engine_for_location = original_boot


def test_boot_engine_explicit_empty_magic_slots_override_base_party_magic() -> None:
    path = Path("web_wasm/bootstrap_runtime.py")
    spec = importlib.util.spec_from_file_location("bootstrap_runtime_for_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original_save = module._merge_save_data(None, module.state.save)
    original_boot = module.boot_engine_for_location

    def _fake_boot_engine_for_location(location_group, location, seed=7):
        return {
            "location_group": location_group,
            "location": location,
            "seed": seed,
        }

    module.boot_engine_for_location = _fake_boot_engine_for_location

    try:
        module.boot_engine_for_location_with_save_json(
            module.default_group,
            module.default_location,
            '{"schema_version":2,"party":[{"Magic":{"LV1":[null,null,null],"LV2":[null,null,null],"LV3":[null,null,null],"LV4":[null,null,null],"LV5":[null,null,null],"LV6":[null,null,null],"LV7":[null,null,null],"LV8":[null,null,null]}}]}',
            7,
        )
        assert module.state.save["party"][0]["Magic"] == {
            "LV1": [None, None, None],
            "LV2": [None, None, None],
            "LV3": [None, None, None],
            "LV4": [None, None, None],
            "LV5": [None, None, None],
            "LV6": [None, None, None],
            "LV7": [None, None, None],
            "LV8": [None, None, None],
        }
    finally:
        module.state.save = original_save
        module.boot_engine_for_location = original_boot


def test_boot_engine_for_location_uses_forced_enemy_names_when_provided() -> None:
    path = Path("web_wasm/bootstrap_runtime.py")
    spec = importlib.util.spec_from_file_location("bootstrap_runtime_for_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payload = module.boot_engine_for_location(
        module.default_group,
        module.default_location,
        7,
        '["Land Turtle"]',
    )

    parsed = module.json.loads(payload)
    enemies = parsed.get("session_status", {}).get("enemies", [])
    assert [enemy.get("name") for enemy in enemies] == ["Land Turtle"]
