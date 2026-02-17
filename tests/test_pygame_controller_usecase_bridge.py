# teststest_pygame_controller_usecase_bridge.py
# Pygame コントローラが execute_round に委譲し、
# セッションや planned actions を期待通り渡していることを固定
from __future__ import annotations

from types import SimpleNamespace
import sys

if "pygame" not in sys.modules:
    class _DummySound:
        def __init__(self, *args, **kwargs):
            pass

        def set_volume(self, *args, **kwargs):
            return None

        def play(self):
            return None

    sys.modules["pygame"] = SimpleNamespace(
        mixer=SimpleNamespace(Sound=_DummySound)
    )

from ui_pygame.controller import BattleController


def test_resolve_one_round_uses_execute_round_usecase(monkeypatch):
    controller = BattleController()

    captured = {}

    def _fake_execute_round(*, session, planned_actions, rng):
        captured["session"] = session
        captured["planned_actions"] = planned_actions
        captured["rng"] = rng
        return SimpleNamespace(
            logs=["ok"],
            round_result=SimpleNamespace(end_reason="continue"),
            event=[{"type": "noop"}],
        )

    monkeypatch.setattr("ui_pygame.controller.execute_round", _fake_execute_round)

    party_members = [SimpleNamespace()]
    enemies = [SimpleNamespace()]
    planned_actions = [None]
    state = SimpleNamespace(spells={"Fire": {"name": "Fire"}})

    result = controller._resolve_one_round(
        party_members=party_members,
        enemies=enemies,
        planned_actions=planned_actions,
        state=state,
        save=None,
        spells_by_name={"Firaga": {"name": "Firaga"}},
        items_by_name={},
    )

    assert result.logs == ["ok"]
    assert result.side_result.end_reason == "continue"
    assert result.events == [{"type": "noop"}]

    assert captured["planned_actions"] is planned_actions
    assert captured["rng"] is controller.rng

    session = captured["session"]
    assert session.state is state
    assert session.party_members is party_members
    assert session.enemies is enemies
    assert session.spells_expanded == {"Firaga": {"name": "Firaga"}}
