# tests/test_enemy_display_names.py
from combat.runtime_state import init_runtime_state
from combat.usecases import build_battle_session


def test_duplicate_enemy_names_receive_letter_suffixes():
    state = init_runtime_state()
    session = build_battle_session(
        state=state, enemy_names=["Goblin", "Goblin", "Darkface", "Goblin"]
    )

    labels = [enemy.label for enemy in session.enemies]

    assert labels == ["Goblin A", "Goblin B", "Darkface", "Goblin C"]
