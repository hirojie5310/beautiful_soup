from __future__ import annotations

from pathlib import Path


def test_location_index_links_to_split_shop_and_inn_pages() -> None:
    source = Path("web_wasm/index.html").read_text(encoding="utf-8")

    assert 'id="app"' in source
    assert "./app.js" in source
    assert 'id="shopMapSelect"' not in source
    assert 'id="stayInnBtn"' not in source


def test_phase1_spa_shell_files_exist() -> None:
    assert Path("web_wasm/app.js").exists()
    assert Path("web_wasm/router.js").exists()
    assert Path("web_wasm/store/app_store.js").exists()
    assert Path("web_wasm/screens/location_screen.js").exists()
    assert Path("web_wasm/screens/menu_screen.js").exists()
    assert Path("web_wasm/screens/shop_screen.js").exists()
    assert Path("web_wasm/screens/inn_screen.js").exists()
    assert Path("web_wasm/screens/battle_screen.js").exists()
    assert Path("web_wasm/screens/item_screen.js").exists()
    assert Path("web_wasm/screens/equip_screen.js").exists()
    assert Path("web_wasm/screens/magic_screen.js").exists()
    assert Path("web_wasm/screens/status_screen.js").exists()
    assert Path("web_wasm/screens/job_screen.js").exists()


def test_legacy_shop_and_inn_pages_redirect_to_spa_routes() -> None:
    shop_html = Path("web_wasm/shop.html").read_text(encoding="utf-8")
    inn_html = Path("web_wasm/inn.html").read_text(encoding="utf-8")

    assert "./index.html#/shop" in shop_html
    assert "window.location.replace" in shop_html
    assert "./index.html#/inn" in inn_html
    assert "window.location.replace" in inn_html


def test_battle_screen_resets_click_to_return_state_on_reentry() -> None:
    source = Path("web_wasm/battle.js").read_text(encoding="utf-8")

    assert "function resetBattleLogInteractionState()" in source
    assert "returnToLocationBound = false;" in source
    assert "activeLogPlaybackId += 1;" in source
    assert source.count("resetBattleLogInteractionState();") >= 3


def test_app_store_prefers_save_envelope_menu_state_on_boot() -> None:
    source = Path("web_wasm/store/app_store.js").read_text(encoding="utf-8")

    assert "const initialMenuStateSource = (" in source
    assert "storedEnvelope?.menu_state" in source
    assert "normalizeMenuState(initialMenuStateSource)" in source
