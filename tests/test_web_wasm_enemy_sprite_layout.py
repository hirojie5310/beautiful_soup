from __future__ import annotations

from pathlib import Path


def _battle_screen_source() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / "web_wasm" / "screens" / "battle_screen.js").read_text(
        encoding="utf-8",
    )


def test_enemy_grid_keeps_six_stable_slots_across_counts() -> None:
    source = _battle_screen_source()

    assert source.count("grid-template-columns: repeat(3, minmax(0, 1fr));") >= 8
    assert source.count("grid-template-rows: repeat(2, minmax(0, 1fr));") >= 8
    assert 'enemy-grid[data-count="1"]' in source
    assert 'enemy-grid[data-count="4"]' in source


def test_enemy_sprite_uses_full_card_width_while_fitting_height() -> None:
    source = _battle_screen_source()
    enemy_sprite_rule = source.rsplit(".battle-screen .enemy-sprite {", 1)[1].split("}", 1)[0]

    assert "inset: 0;" in enemy_sprite_rule
    assert "width: 100%;" in enemy_sprite_rule
    assert "height: 100%;" in enemy_sprite_rule
    assert "max-height:" not in enemy_sprite_rule
    assert "margin: auto;" not in enemy_sprite_rule
    assert "object-fit: contain;" in enemy_sprite_rule
    assert "object-position: center 48%;" in enemy_sprite_rule
    assert "image-rendering: pixelated;" in enemy_sprite_rule


def test_battle_screen_uses_vertical_enemy_party_command_frames() -> None:
    source = _battle_screen_source()

    assert '<section class="frame battle-party-panel">' in source
    assert '<section id="commandFrame" class="frame command-panel">' in source
    assert "dock-panels" not in source
    assert "dock-panel" not in source
    assert "grid-template-rows: minmax(220px, 1fr) minmax(112px, auto) minmax(150px, auto);" in source
    assert "grid-template-rows: minmax(210px, 1fr) minmax(104px, auto) minmax(144px, auto);" in source
    assert "grid-template-rows: minmax(194px, 1fr) minmax(92px, auto) minmax(132px, auto);" in source
