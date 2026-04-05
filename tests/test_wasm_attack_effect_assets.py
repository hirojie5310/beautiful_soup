from __future__ import annotations

from pathlib import Path


def test_wasm_app_serves_effect_assets_from_web_wasm_alias() -> None:
    source = Path("wasm_app.py").read_text(encoding="utf-8")
    assert '"/web_wasm/effects/": "effects"' in source
    assert 'def do_HEAD(self) -> None:' in source
    assert "super().do_HEAD()" in source


def test_battle_ui_references_attack_effect_sheet() -> None:
    battle_js = Path("web_wasm/battle.js").read_text(encoding="utf-8")
    battle_screen = Path("web_wasm/screens/battle_screen.js").read_text(encoding="utf-8")

    assert 'const ATTACK_EFFECT_SHEET_NAME = "ef_slash_frames.png";' in battle_js
    assert "appendCombatEffect(card, effectForTarget(" in battle_js
    assert "@keyframes combat-slash-sweep" in battle_screen
