# combat/wasm_api.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Optional, Sequence

from assets.data.data_loader import load_explicit_groups, save_savedata
from combat.constants import STATUS_ENUM_BY_KEY, STATUS_ICON_KEY_BY_ENUM
from combat.dto import (
    ExecuteRoundInputDTO,
    parse_execute_round_input_dict,
    to_json_ready_dict,
)
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names
from combat.errors import InputValidationError
from combat.input_ui import normalize_battle_command
from combat.inventory import build_item_list, is_item_visible_in_context
from combat.item_effects import infer_battle_item_target_side
from combat.life_check import is_out_of_battle
from combat.magic_damage import healing_spell_kind
from combat.progression import apply_item_stock_to_inventory, apply_victory_rewards
from combat.usecases import BattleSession, build_battle_session, execute_round_dto
from combat.models import EquipmentSet
from combat.runtime_state import init_runtime_state, resolve_data_path
from utils.text_normalize import normalize_text_basic


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


def _status_icon_keys(statuses: Any) -> list[str]:
    keys: list[str] = []
    if not isinstance(statuses, (set, list, tuple)):
        return keys

    for st in statuses:
        icon_key = STATUS_ICON_KEY_BY_ENUM.get(st)
        if icon_key:
            keys.append(str(icon_key))
            continue

        raw = str(st).strip().lower()
        if raw.startswith("status."):
            raw = raw.split(".", 1)[1]
        raw = raw.replace("_", " ")
        st_enum = STATUS_ENUM_BY_KEY.get(raw)
        if st_enum is None:
            continue
        fallback_key = STATUS_ICON_KEY_BY_ENUM.get(st_enum)
        if fallback_key:
            keys.append(str(fallback_key))

    return sorted(set(keys))


def _build_party_status_snapshot(session: BattleSession) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for idx, member in enumerate(session.party_members):
        state = getattr(member, "state", None)
        hp = _safe_int(getattr(state, "hp", 0), 0)
        max_hp_raw = getattr(state, "max_hp", None)
        max_hp = _safe_int(max_hp_raw, hp) if max_hp_raw is not None else hp
        statuses = getattr(state, "statuses", set())
        status_icons = _status_icon_keys(statuses)

        snapshots.append(
            {
                "index": idx,
                "name": str(getattr(member, "name", f"Ally {idx + 1}")),
                "hp": hp,
                "max_hp": max_hp,
                "level": _safe_int(getattr(member, "level", 0), 0),
                "portrait_key": getattr(member, "portrait_key", None),
                "status_icons": status_icons,
                "out_of_battle": bool(
                    is_out_of_battle(state) if state is not None else True
                ),
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
        statuses = getattr(state, "statuses", set())
        status_icons = _status_icon_keys(statuses)
        snapshots.append(
            {
                "index": idx,
                "name": str(
                    getattr(enemy, "label", getattr(enemy, "name", f"Enemy {idx + 1}"))
                ),
                "sprite_id": getattr(enemy, "sprite_id", None),
                "hp": hp,
                "max_hp": max_hp,
                "status_icons": status_icons,
                "out_of_battle": bool(
                    is_out_of_battle(state) if state is not None else True
                ),
            }
        )
    return snapshots


def _build_battle_commands_by_member(
    session: BattleSession,
) -> list[list[dict[str, str]]]:
    candidates: list[list[dict[str, str]]] = []
    for member in session.party_members:
        member_candidates: list[dict[str, str]] = []
        job_raw = getattr(getattr(member, "job", None), "raw", {})
        if isinstance(job_raw, dict):
            for i in range(1, 5):
                command_row = job_raw.get(f"BattleCommand{i}")
                if not isinstance(command_row, dict):
                    continue
                command = command_row.get("Command")
                if not isinstance(command, str) or not command.strip():
                    continue
                command_name = command.strip()
                member_candidates.append(
                    {
                        "command": command_name,
                        "kind": normalize_battle_command(command_name),
                    }
                )

        if not member_candidates:
            fallback = ["Fight", "Defend", "Item", "Run"]
            member_candidates = [
                {"command": cmd, "kind": normalize_battle_command(cmd)}
                for cmd in fallback
            ]
        candidates.append(member_candidates)
    return candidates


def _item_type_label_prefix(item_type: Any) -> str:
    raw = str(item_type).strip() if item_type is not None else ""
    if not raw:
        return "?"
    return raw[0].upper()


def _build_battle_item_command_candidates(
    session: BattleSession,
) -> list[dict[str, Any]]:
    state = getattr(session, "state", None)
    items_by_name = getattr(state, "items_by_name", {}) if state is not None else {}
    save = getattr(state, "save", {}) if state is not None else {}
    if not isinstance(items_by_name, dict):
        return []
    if not isinstance(save, dict):
        save = {}

    item_list = build_item_list(items_by_name, save, in_battle=True)
    candidates: list[dict[str, Any]] = []
    for item_name, item_type, qty in item_list:
        item_json = items_by_name.get(item_name, {})
        if not is_item_visible_in_context(item_json, in_combat=True):
            continue
        candidates.append(
            {
                "name": item_name,
                "item_type": item_type,
                "qty": _safe_int(qty, 0),
                "label": f"{_item_type_label_prefix(item_type)}: {item_name} ×{_safe_int(qty, 0)}",
            }
        )
    return candidates


def _build_battle_item_meta(
    items_by_name: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for item_name, item_json in items_by_name.items():
        if not isinstance(item_json, dict):
            continue
        meta[item_name] = {
            "target_side": infer_battle_item_target_side(item_json),
        }
    return meta


def _magic_type_prefix(magic_type: Any) -> str:
    raw_label = getattr(magic_type, "value", magic_type)
    label = str(raw_label or "").strip()
    if label == "Black Magic":
        return "●"
    if label == "White Magic":
        return "〇"
    if label == "Summon Magic":
        return "◎"
    return ""


def _build_magic_command_candidates_by_member(
    session: BattleSession,
) -> list[list[dict[str, Any]]]:
    candidates: list[list[dict[str, Any]]] = []
    party_magic_lists = getattr(session, "party_magic_lists", [])
    party_members = list(getattr(session, "party_members", []))
    for member_idx, row in enumerate(party_magic_lists):
        member = party_members[member_idx] if member_idx < len(party_members) else None
        state = getattr(member, "state", None)
        mp_pool = getattr(state, "mp_pool", {}) if state is not None else {}
        max_mp_pool = getattr(state, "max_mp_pool", {}) if state is not None else {}
        if not isinstance(mp_pool, dict):
            mp_pool = {}
        if not isinstance(max_mp_pool, dict):
            max_mp_pool = {}

        names: list[dict[str, Any]] = []
        for cand in row or []:
            if not isinstance(cand, (list, tuple)) or len(cand) < 3:
                continue
            name = cand[0]
            if not isinstance(name, str) or not name:
                continue
            magic_type = cand[1]
            level = max(1, _safe_int(cand[2], 1))
            remain = _safe_int(mp_pool.get(level, 0), 0)
            max_uses = _safe_int(max_mp_pool.get(level, remain), remain)
            names.append(
                {
                    "name": name,
                    "type": str(getattr(magic_type, "value", magic_type)),
                    "level": level,
                    "remaining_uses": remain,
                    "max_uses": max_uses,
                    "label": f"{_magic_type_prefix(magic_type)}{name}",
                    "group_label": (
                        f"LV{level} ({remain}/{max_uses})"
                        if max_uses > 0
                        else f"LV{level} ({remain})"
                    ),
                }
            )
        candidates.append(names)
    return candidates


def _build_magic_spell_meta(session: BattleSession) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for name, raw in getattr(session, "spells_expanded", {}).items():
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(raw, dict):
            continue
        target_norm = str(raw.get("Target") or "").strip().lower()
        can_select_all = target_norm in {
            "one/all enemies",
            "one/all allies",
            "one/all",
        }
        healing_type = str(healing_spell_kind(raw) or "")
        target_mode = "enemy_only"
        if healing_type in {"hp", "status", "revive", "protect", "haste", "reflect"}:
            target_mode = "any" if healing_type == "hp" else "ally_only"
        rows[name] = {
            "target": str(raw.get("Target") or ""),
            "target_norm": target_norm,
            "can_select_all": can_select_all,
            "healing_type": healing_type,
            "target_mode": target_mode,
            "type": str(raw.get("Type") or ""),
            "level": _safe_int(raw.get("Level", 1), 1),
        }

    # Evoker では親召喚名（例: Leviathan）がメニューに表示されるため、
    # spells_expanded に親がない場合でも、元の spells 定義から最低限の対象情報を補完する。
    state = getattr(session, "state", None)
    raw_spells = getattr(state, "spells", {}) if state is not None else {}
    if isinstance(raw_spells, dict):
        for parent_name, parent_raw in raw_spells.items():
            if not isinstance(parent_name, str) or not parent_name:
                continue
            if parent_name in rows:
                continue
            if not isinstance(parent_raw, dict):
                continue
            if normalize_text_basic(parent_raw.get("Type") or "") != "summon magic":
                continue

            child_rows = parent_raw.get("Spells")
            if not isinstance(child_rows, list) or not child_rows:
                continue
            child_targets = [
                normalize_text_basic(
                    child.get("Target") if isinstance(child, dict) else ""
                )
                for child in child_rows
            ]
            child_targets = [target for target in child_targets if target]

            target_norm = normalize_text_basic(parent_raw.get("Target") or "")
            if child_targets and len(set(child_targets)) == 1:
                target_norm = child_targets[0]

            can_select_all = target_norm in {
                "one/all enemies",
                "one/all allies",
                "one/all",
            }
            healing_type = str(healing_spell_kind(parent_raw) or "")
            target_mode = "enemy_only"
            if target_norm == "all allies":
                target_mode = "ally_only"
            if healing_type in {
                "hp",
                "status",
                "revive",
                "protect",
                "haste",
                "reflect",
            }:
                target_mode = "any" if healing_type == "hp" else "ally_only"
            rows[parent_name] = {
                "target": str(parent_raw.get("Target") or ""),
                "target_norm": target_norm,
                "can_select_all": can_select_all,
                "healing_type": healing_type,
                "target_mode": target_mode,
                "type": str(parent_raw.get("Type") or ""),
                "level": _safe_int(parent_raw.get("Level", 1), 1),
            }
    return rows


def build_session_status_snapshot(session: BattleSession) -> dict[str, Any]:
    state = getattr(session, "state", None)
    items_by_name = getattr(state, "items_by_name", {}) if state is not None else {}
    if not isinstance(items_by_name, dict):
        items_by_name = {}
    return {
        "party": _build_party_status_snapshot(session),
        "enemies": _build_enemy_status_snapshot(session),
        "command_candidates_by_member": _build_battle_commands_by_member(session),
        "magic_command_candidates_by_member": _build_magic_command_candidates_by_member(
            session
        ),
        "magic_spell_meta": _build_magic_spell_meta(session),
        "item_command_candidates": _build_battle_item_command_candidates(session),
        "item_meta": _build_battle_item_meta(items_by_name),
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


def build_location_selection_context(state: Any) -> dict[str, Any]:
    location_entries = build_location_index(state.monsters)
    location_groups = build_groups(
        location_entries,
        explicit_groups=load_explicit_groups("assets/data/explicit_groups.json"),
    )
    groups_payload: list[dict[str, Any]] = []
    location_to_entry: dict[str, Any] = {}
    for group in location_groups:
        locations: list[str] = []
        for child in group.children:
            locations.append(str(child.location))
            location_to_entry[str(child.location)] = child
        groups_payload.append(
            {
                "group_name": str(group.group_name),
                "locations": locations,
            }
        )

    selected_group = groups_payload[0]["group_name"] if groups_payload else ""
    selected_location = (
        groups_payload[0]["locations"][0]
        if groups_payload and groups_payload[0]["locations"]
        else ""
    )

    return {
        "groups": groups_payload,
        "selected_group": selected_group,
        "selected_location": selected_location,
        "location_to_entry": location_to_entry,
    }


def pick_enemy_names_for_location(state: Any, location: str) -> list[str]:
    selection = build_location_selection_context(state)
    location_to_entry = selection["location_to_entry"]
    entry = location_to_entry.get(location)
    if entry is None:
        return sorted(state.monsters.keys())[:3]
    return pick_enemy_names(entry, state.monsters, k_min=2, k_max=6)


def _build_random_enemy_selection(state: Any) -> tuple[list[str], str, str]:
    selection = build_location_selection_context(state)
    selected_group = selection["selected_group"]
    selected_location = selection["selected_location"]
    if not selected_location:
        return sorted(state.monsters.keys())[:3], selected_group, selected_location

    selected_enemy_names = pick_enemy_names_for_location(state, selected_location)
    return selected_enemy_names, selected_group, selected_location


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
        selected_location_group: str | None = None,
        selected_location: str | None = None,
    ) -> "WasmBattleEngine":
        state = init_runtime_state()
        if enemy_names:
            selected_enemy_names = list(enemy_names)
            selected_group = selected_location_group or ""
            selected_loc = selected_location or ""
        else:
            (
                selected_enemy_names,
                auto_group,
                auto_location,
            ) = _build_random_enemy_selection(state)
            selected_group = (
                selected_location_group
                if selected_location_group is not None
                else auto_group
            )
            selected_loc = (
                selected_location if selected_location is not None else auto_location
            )

        session = build_battle_session(state=state, enemy_names=selected_enemy_names)
        return cls(
            session=session,
            rng=Random(seed),
            selected_location_group=selected_group,
            selected_location=selected_loc,
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

    def persist_runtime_save(self) -> None:
        state = getattr(self.session, "state", None)
        if state is None:
            return
        save = getattr(state, "save", None)
        if not isinstance(save, dict):
            return
        base_dir = getattr(state, "base_dir", Path("."))
        if not isinstance(base_dir, Path):
            base_dir = Path(base_dir)
        save_path = resolve_data_path(
            "assets/data/ffiii_savedata.json",
            base_dir=base_dir,
        )
        save_savedata(save_path, save)

    def full_recover_party_payload(self) -> dict[str, Any]:
        for member in self.session.party_members:
            state = getattr(member, "state", None)
            if state is None:
                continue

            max_hp_raw = getattr(state, "max_hp", None)
            if max_hp_raw is not None:
                state.hp = _safe_int(max_hp_raw, _safe_int(getattr(state, "hp", 0), 0))

            mp_pool = getattr(state, "mp_pool", None)
            max_mp_pool = getattr(state, "max_mp_pool", None)
            if isinstance(mp_pool, dict) and isinstance(max_mp_pool, dict):
                for level, max_uses in max_mp_pool.items():
                    mp_pool[level] = _safe_int(
                        max_uses, _safe_int(mp_pool.get(level, 0), 0)
                    )

        return {
            "selected_location_group": self.selected_location_group,
            "selected_location": self.selected_location,
            "session_status": build_session_status_snapshot(self.session),
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
            apply_item_stock_to_inventory(self.session.state.save)

        response_payload["session_status"] = build_session_status_snapshot(self.session)
        response_payload["selected_location_group"] = self.selected_location_group
        response_payload["selected_location"] = self.selected_location

        if output_dto.lifecycle.battle_finished:
            self.persist_runtime_save()
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
