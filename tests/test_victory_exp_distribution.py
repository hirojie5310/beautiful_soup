# tests/test_victory_exp_distribution.py
from types import SimpleNamespace

import combat.progression as progression


def _member(name: str, hp: int):
    return SimpleNamespace(
        name=name,
        state=SimpleNamespace(hp=hp),
        base=SimpleNamespace(level=1, total_exp=0),
    )


def test_apply_victory_exp_rewards_distributes_remainder(monkeypatch):
    members = [_member("Runeth", 100), _member("Arc", 100), _member("Refia", 100)]
    enemies = [SimpleNamespace(json={"Experience": 4088})]

    gained_by_name: dict[str, int] = {}

    def _fake_apply_battle_exp_and_refresh(
        member, gained_exp, level_table, weapons, armors
    ):
        gained_by_name[member.name] = gained_exp
        return member.base.level, member.base.level

    monkeypatch.setattr(
        progression,
        "apply_battle_exp_and_refresh",
        _fake_apply_battle_exp_and_refresh,
    )

    progression.apply_victory_exp_rewards(
        members,
        enemies,
        level_table=object(),
        weapons={},
        armors={},
    )

    assert gained_by_name == {
        "Runeth": 1363,
        "Arc": 1363,
        "Refia": 1362,
    }


def test_apply_victory_exp_rewards_skips_ko_members(monkeypatch):
    members = [_member("Runeth", 100), _member("Arc", 0), _member("Refia", 1)]
    enemies = [SimpleNamespace(json={"Experience": 11})]

    gained_by_name: dict[str, int] = {}

    def _fake_apply_battle_exp_and_refresh(
        member, gained_exp, level_table, weapons, armors
    ):
        gained_by_name[member.name] = gained_exp
        return member.base.level, member.base.level

    monkeypatch.setattr(
        progression,
        "apply_battle_exp_and_refresh",
        _fake_apply_battle_exp_and_refresh,
    )

    progression.apply_victory_exp_rewards(
        members,
        enemies,
        level_table=object(),
        weapons={},
        armors={},
    )

    assert gained_by_name == {
        "Runeth": 6,
        "Refia": 5,
    }
