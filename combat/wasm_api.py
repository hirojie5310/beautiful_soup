# combat/wasm_api.py
from __future__ import annotations

import json
from dataclasses import dataclass
from random import Random
from typing import Any, Optional, Sequence

from combat.constants import STATUS_ICON_KEY_BY_ENUM
from combat.dto import (
    ExecuteRoundInputDTO,
    parse_execute_round_input_dict,
    to_json_ready_dict,
)
from combat.errors import InputValidationError
from combat.progression import apply_victory_rewards
from combat.usecases import BattleSession, build_battle_session, execute_round_dto
from combat.models import EquipmentSet
from combat.runtime_state import init_runtime_state


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_planned_actions_length(
    request_dto: ExecuteRoundInputDTO, *, expected_count: int
) -> ExecuteRoundInputDTO:
    actual_count = len(request_dto.planned_actions)
    if actual_count > expected_count:
        raise InputValidationError(
            "planned_actions has too many entries",
            details={"expected_max": expected_count, "actual": actual_count},
        )
    if actual_count == expected_count:
        return request_dto

    padded = list(request_dto.planned_actions) + [None] * (
        expected_count - actual_count
    )
    return ExecuteRoundInputDTO(
        planned_actions=padded,
        lifecycle_state=request_dto.lifecycle_state,
    )


def _build_party_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        state = getattr(member, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        statuses = getattr(state, "statuses", set())
        status_icons: list[str] = []
        if isinstance(statuses, (set, list, tuple)):
            for st in statuses:
                icon_key = STATUS_ICON_KEY_BY_ENUM.get(st)
                if icon_key:
                    status_icons.append(str(icon_key))

        snapshots.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "hp": hp,
                "max_hp": max_hp,
                "level": _safe_int(getattr(member, "level", 0), 0),
                "portrait_key": getattr(member, "portrait_key", None),
                "status_icons": sorted(set(status_icons)),
                "is_jumping": bool(getattr(state, "is_jumping", False)),
                "jump_target_index": getattr(state, "jump_target_index", None),
            }
        )
    return snapshots


def _build_enemy_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, enemy in enumerate(session.enemies):
        state = getattr(enemy, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        snapshots.append(
            {
                "index": idx,
                "name": str(
                    getattr(enemy, "label", getattr(enemy, "name", f"Enemy {idx + 1}"))
                ),
                "sprite_id": getattr(enemy, "sprite_id", None),
                "hp": hp,
                "max_hp": max_hp,
            }
        )
    return snapshots


def build_session_status_snapshot(session: BattleSession) -> dict[str, Any]:
    return {
        "party": _build_party_status_snapshot(session),
        "enemies": _build_enemy_status_snapshot(session),
    }


def _build_member_progress_snapshot(member: Any) -> dict[str, Any]:
    base = getattr(member, "base", None)
    return {
        "name": str(getattr(member, "name", "")),
        "level": _safe_int(getattr(base, "level", 0), 0),
        "exp": _safe_int(getattr(base, "total_exp", 0), 0),
        "job_level": _safe_int(getattr(base, "job_level", 0), 0),
        "job_skill_point": _safe_int(getattr(base, "job_skill_point", 0), 0),
    }


def _build_party_progress_snapshot(session: BattleSession) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for member in session.party_members:
        snap = _build_member_progress_snapshot(member)
        rows[snap["name"]] = snap
    return rows


def _format_victory_progress_logs(
    *,
    before_progress: dict[str, dict[str, Any]],
    after_progress: dict[str, dict[str, Any]],
    rewards: dict[str, Any],
) -> list[str]:
    lines: list[str] = ["=== Battle Rewards ==="]
    lines.append(f"EXP +{_safe_int(rewards.get('gained_exp', 0), 0)}")
    lines.append(f"Gil +{_safe_int(rewards.get('gained_gil', 0), 0)}")
    lines.append(f"CP +{_safe_int(rewards.get('gained_cp', 0), 0)}")

    for name, after in after_progress.items():
        before = before_progress.get(name, {})
        level_before = _safe_int(before.get("level", after.get("level", 0)), 0)
        level_after = _safe_int(after.get("level", level_before), level_before)
        exp_before = _safe_int(before.get("exp", after.get("exp", 0)), 0)
        exp_after = _safe_int(after.get("exp", exp_before), exp_before)
        if level_after != level_before:
            lines.append(f"{name}: Level {level_before} -> {level_after}")
        if exp_after != exp_before:
            lines.append(f"{name}: EXP {exp_before} -> {exp_after}")

        job_before = _safe_int(before.get("job_level", after.get("job_level", 0)), 0)
        job_after = _safe_int(after.get("job_level", job_before), job_before)
        sp_before = _safe_int(
            before.get("job_skill_point", after.get("job_skill_point", 0)),
            0,
        )
        sp_after = _safe_int(after.get("job_skill_point", sp_before), sp_before)
        sp_delta = sp_after - sp_before

        if job_after != job_before:
            lines.append(
                f"{name}: Job Lv {job_before} -> {job_after} (SP {sp_before} -> {sp_after}, +{sp_delta})"
            )
        elif sp_delta > 0:
            lines.append(f"{name}: Skill Point +{sp_delta} ({sp_before} -> {sp_after})")

    dropped = rewards.get("dropped_item", [])
    if isinstance(dropped, list) and dropped:
        lines.append("Drop: " + ", ".join(str(x) for x in dropped))
    return lines


def _member_export(member: Any) -> dict[str, Any]:
    stats = getattr(member, "stats", None)
    eq = getattr(member, "equipment", None) or EquipmentSet()
    return {
        "name": str(getattr(member, "name", "")),
        "job": str(getattr(getattr(member, "base", None), "job", "")),
        "hp": _safe_int(getattr(member, "hp", 0), 0),
        "max_hp": _safe_int(getattr(member, "max_hp", 0), 0),
        "strength": _safe_int(getattr(stats, "strength", 0), 0),
        "agility": _safe_int(getattr(stats, "agility", 0), 0),
        "vitality": _safe_int(getattr(stats, "vitality", 0), 0),
        "intellect": _safe_int(getattr(stats, "intellect", 0), 0),
        "mind": _safe_int(getattr(stats, "mind", 0), 0),
        "attack": _safe_int(getattr(stats, "attack", 0), 0),
        "defense": _safe_int(getattr(stats, "defense", 0), 0),
        "hit_rate": _safe_int(getattr(stats, "hit_rate", 0), 0),
        "evasion": _safe_int(getattr(stats, "evasion", 0), 0),
        "magic_defense": _safe_int(getattr(stats, "magic_defense", 0), 0),
        "equipment": {
            "main_hand": getattr(eq, "main_hand", None),
            "off_hand": getattr(eq, "off_hand", None),
            "head": getattr(eq, "head", None),
            "body": getattr(eq, "body", None),
            "arms": getattr(eq, "arms", None),
            "accessory": getattr(eq, "accessory", None),
        },
    }


def build_wasm_bootstrap_python() -> str:
    return (
        "from combat.wasm_api import WasmBattleEngine\n"
        "engine = WasmBattleEngine.create_default()\n"
        "def run_battle_round_wasm(js_input_json):\n"
        "    return engine.execute_round_json(js_input_json)\n"
    )


@dataclass
class WasmBattleEngine:
    session: BattleSession
    rng: Random
    selected_location_group: str = ""
    selected_location: str = ""
    battle_start_progress: dict[str, dict[str, Any]] | None = None

    @classmethod
    def create_default(
        cls,
        *,
        enemy_names: Optional[Sequence[str]] = None,
        seed: Optional[int] = None,
        selected_location_group: str = "",
        selected_location: str = "",
    ) -> "WasmBattleEngine":
        state = init_runtime_state()
        selected_enemy_names = (
            list(enemy_names) if enemy_names else sorted(state.monsters.keys())[:3]
        )
        session = build_battle_session(state=state, enemy_names=selected_enemy_names)
        return cls(
            session=session,
            rng=Random(seed),
            selected_location_group=selected_location_group,
            selected_location=selected_location,
            battle_start_progress=_build_party_progress_snapshot(session),
        )

    def build_initial_payload(self) -> dict[str, Any]:
        return {
            "selected_location_group": self.selected_location_group,
            "selected_location": self.selected_location,
            "session_status": build_session_status_snapshot(self.session),
            "party_members": [
                _member_export(member) for member in self.session.party_members
            ],
        }

    def execute_round_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_dto = parse_execute_round_input_dict(payload)
        request_dto = _normalize_planned_actions_length(
            request_dto,
            expected_count=len(self.session.party_members),
        )
        output_dto = execute_round_dto(
            session=self.session,
            request=request_dto,
            rng=self.rng,
        )
        response_payload = to_json_ready_dict(output_dto)

        if (
            output_dto.end_reason == "enemy_defeated"
            and hasattr(self.session, "level_table")
            and self.battle_start_progress is not None
        ):
            rewards = apply_victory_rewards(
                party_members=self.session.party_members,
                enemies=self.session.enemies,
                state=self.session.state,
                level_table=self.session.level_table,
            )
            after_progress = _build_party_progress_snapshot(self.session)
            response_payload["logs"] = list(
                response_payload.get("logs", [])
            ) + _format_victory_progress_logs(
                before_progress=self.battle_start_progress,
                after_progress=after_progress,
                rewards=rewards,
            )
            response_payload["victory_rewards"] = rewards

        response_payload["session_status"] = build_session_status_snapshot(self.session)
        response_payload["selected_location_group"] = self.selected_location_group
        response_payload["selected_location"] = self.selected_location

        if output_dto.lifecycle.battle_finished:
            self.battle_start_progress = _build_party_progress_snapshot(self.session)

        return response_payload

    def execute_round_json(self, payload_json: str) -> str:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise InputValidationError(
                "request body must be JSON object",
                details={"actual": type(payload).__name__},
            )
        return json.dumps(self.execute_round_payload(payload), ensure_ascii=False)
