# ui_pygame/controller.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, cast
from random import Random

from combat.runtime_state import RuntimeState
from combat.battle_sim import simulate_one_round_multi_party  # ←実際の場所に合わせて
from combat.battle_result import BattleResult
from combat.life_check import first_alive_enemy_index, is_out_of_battle

# EnemyRuntime / PlannedAction / SideTurnResult の import 先もあなたの構成に合わせて調整してください
from combat.models import (
    PartyMemberRuntime,
    PlannedAction,
    EnemyRuntime,  # 例：あなたの実装に合わせる
    SideTurnResult,  # 例：あなたの実装に合わせる
)

from ui_pygame.ui_events import AudioEvent
from ui_pygame.battle_context import BattleContext
from ui_pygame.app_context import BattleAppContext


@dataclass
class ResolveResult:
    logs: List[str]
    side_result: SideTurnResult
    events: List[Dict[str, Any]]


class BattleController:
    def __init__(self, rng: Optional[Random] = None):
        self.rng = rng or Random()
        self._bgm_started = False

    def update(
        self,
        ui,
        party_members: List[PartyMemberRuntime],
        enemies: List[EnemyRuntime],
        state: RuntimeState,
        *,
        battle_ctx: BattleContext,
        app_ctx: BattleAppContext,
        save: Optional[dict] = None,
        spells_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
        items_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        if getattr(ui, "battle_ended", False):
            return

        # Battle BGM (At First Time)
        if not self._bgm_started:
            if hasattr(ui, "events") and isinstance(ui.events, list):
                # Judge Boss Battle
                is_boss = self._is_boss_battle(enemies)
                bgm_name = battle_ctx.bgm.boss if is_boss else battle_ctx.bgm.normal
                ui.events.append(
                    AudioEvent(
                        type="bgm",
                        payload={"name": bgm_name, "fade_ms": 800},
                    )
                )
            self._bgm_started = True

        if getattr(ui, "phase", None) != "resolve":
            return

        planned_actions_any = getattr(ui, "planned_actions", None)
        if planned_actions_any is None:
            planned_actions: List[Optional[PlannedAction]] = [None] * len(party_members)
        else:
            planned_actions = cast(List[Optional[PlannedAction]], planned_actions_any)

        for i, a in enumerate(planned_actions):
            if a is None:
                continue
            print(
                f"[DBG planned] i={i} kind={a.kind} cmd={a.command} target={a.target_side}:{a.target_index} all={getattr(a,'target_all',False)}"
            )

        if self._update_party_attack_animation(ui, party_members, planned_actions):
            return

        rr = self._resolve_one_round(
            party_members=party_members,
            enemies=enemies,
            planned_actions=planned_actions,
            state=state,
            save=save,
            spells_by_name=spells_by_name,
            items_by_name=items_by_name,
        )

        self._push_logs(ui, rr.logs)
        self._push_events(ui, rr.events)

        end_reason = getattr(rr.side_result, "end_reason", "continue")
        ui.battle_result = self._map_end_reason_to_result(end_reason)
        if ui.battle_result != BattleResult.CONTINUE:
            ui.battle_ended = True
            ui.phase = "end"
            ui.input_mode = "end"
            self._reset_party_attack_animation(ui, len(party_members))
            self._clear_planned_actions(ui, party_members)

            # Battle End BGM
            if hasattr(ui, "events") and isinstance(ui.events, list):
                if ui.battle_result == BattleResult.ENEMY_DEFEATED:
                    ui.events.append(
                        AudioEvent(
                            type="bgm",
                            payload={"name": battle_ctx.bgm.victory, "fade_ms": 300},
                        )
                    )
                elif ui.battle_result == BattleResult.PARTY_DEFEATED:
                    ui.events.append(
                        AudioEvent(
                            type="bgm",
                            payload={"name": battle_ctx.bgm.requiem, "fade_ms": 300},
                        )
                    )
                else:
                    ui.events.append(
                        AudioEvent(type="bgm_stop", payload={"fade_ms": 800})
                    )

            return

        # ===== continue =====

        # Add Turn (ui.turn / ui.turn_count)
        if hasattr(ui, "turn"):
            ui.turn += 1
        elif hasattr(ui, "turn_count"):
            ui.turn_count += 1

        # Back to Input Phase
        ui.phase = "input"
        ui.input_mode = "member"
        self._reset_party_attack_animation(ui, len(party_members))

        # Clear the State of Target Selection
        if hasattr(app_ctx, "reset_target_flags"):
            app_ctx.reset_target_flags(ui)

        # Clear planned_actions
        self._clear_planned_actions(ui, party_members)
        self._auto_fill_jump_actions(ui, party_members, enemies)
        if app_ctx.all_actions_committed(ui):
            ui.phase = "resolve"
            ui.input_mode = "resolve"
            return
        # ReSet Next Command Input Character
        # If find_next_unfilled(ui) is app function -> ctx
        if hasattr(app_ctx, "find_next_unfilled_member_index"):
            ui.selected_member_idx = app_ctx.find_next_unfilled_member_index(ui)
        else:
            # Return to 0
            ui.selected_member_idx = 0

        # Recalc the Candidate Comamnd
        if hasattr(app_ctx, "get_job_commands"):
            ui.command_candidates = app_ctx.get_job_commands(
                party_members[ui.selected_member_idx]
            )

        # Log
        if hasattr(ui, "logs") and isinstance(ui.logs, list):
            t = getattr(ui, "turn", getattr(ui, "turn_count", "?"))
            ui.logs.append(f"--- Turn {t} Start Input ---")
            self._append_auto_filled_action_logs(ui, party_members)

    def _is_boss_battle(self, enemies: List[EnemyRuntime]) -> bool:
        return any(getattr(e, "is_boss", False) for e in enemies)

    def _resolve_one_round(
        self,
        *,
        party_members: List[PartyMemberRuntime],
        enemies: List[EnemyRuntime],
        planned_actions: List[Optional[PlannedAction]],
        state: RuntimeState,
        save: Optional[dict],
        spells_by_name: Optional[Dict[str, Dict[str, Any]]],
        items_by_name: Optional[Dict[str, Dict[str, Any]]],
    ) -> ResolveResult:
        logs, side_result, events = simulate_one_round_multi_party(
            party_members=party_members,
            enemies=enemies,
            planned_actions=planned_actions,
            state=state,
            rng=self.rng,
            save=save,
            spells_by_name=spells_by_name,
            items_by_name=items_by_name,
        )
        return ResolveResult(logs=logs, side_result=side_result, events=events)

    def _reset_party_attack_animation(self, ui, member_count: int) -> None:
        if member_count < 0:
            member_count = 0
        ui.party_motion_frame_indices = [0] * member_count
        ui.party_attack_anim_queue = []
        ui.party_attack_anim_active_idx = None
        ui.party_attack_anim_elapsed_ms = 0

    def _collect_attack_anim_queue(
        self,
        party_members: List[PartyMemberRuntime],
        planned_actions: List[Optional[PlannedAction]],
    ) -> List[int]:
        queue: List[int] = []
        for idx, action in enumerate(planned_actions):
            if action is None:
                continue
            if action.kind != "physical":
                continue
            if idx >= len(party_members):
                continue
            if is_out_of_battle(party_members[idx].state):
                continue
            queue.append(idx)
        return queue

    def _update_party_attack_animation(
        self,
        ui,
        party_members: List[PartyMemberRuntime],
        planned_actions: List[Optional[PlannedAction]],
    ) -> bool:
        member_count = len(party_members)
        if len(getattr(ui, "party_motion_frame_indices", [])) != member_count:
            self._reset_party_attack_animation(ui, member_count)

        if (
            not getattr(ui, "party_attack_anim_queue", None)
            and getattr(ui, "party_attack_anim_active_idx", None) is None
        ):
            ui.party_attack_anim_queue = self._collect_attack_anim_queue(
                party_members, planned_actions
            )
            ui.party_attack_anim_elapsed_ms = 0

        if not ui.party_attack_anim_queue and ui.party_attack_anim_active_idx is None:
            return False

        if ui.party_attack_anim_active_idx is None:
            next_idx = int(ui.party_attack_anim_queue.pop(0))
            ui.party_attack_anim_active_idx = next_idx
            ui.party_attack_anim_elapsed_ms = 0
            if 0 <= next_idx < len(ui.party_motion_frame_indices):
                ui.party_motion_frame_indices[next_idx] = 1
            return True

        dt_ms = max(0, int(getattr(ui, "dt_ms", 0)))
        ui.party_attack_anim_elapsed_ms += dt_ms
        step_ms = max(1, int(getattr(ui, "party_attack_anim_step_ms", 90)))
        if ui.party_attack_anim_elapsed_ms < step_ms:
            return True
        ui.party_attack_anim_elapsed_ms = 0

        active_idx = int(ui.party_attack_anim_active_idx)
        if active_idx < 0 or active_idx >= len(ui.party_motion_frame_indices):
            ui.party_attack_anim_active_idx = None
            return bool(ui.party_attack_anim_queue)

        frame_idx = int(ui.party_motion_frame_indices[active_idx])
        if frame_idx <= 1:
            ui.party_motion_frame_indices[active_idx] = 2
            return True

        ui.party_motion_frame_indices[active_idx] = 0
        ui.party_attack_anim_active_idx = None
        if ui.party_attack_anim_queue:
            next_idx = int(ui.party_attack_anim_queue.pop(0))
            ui.party_attack_anim_active_idx = next_idx
            ui.party_attack_anim_elapsed_ms = 0
            if 0 <= next_idx < len(ui.party_motion_frame_indices):
                ui.party_motion_frame_indices[next_idx] = 1
            return True
        return False

    def _push_logs(self, ui, logs: List[str]) -> None:
        if not logs:
            return
        # ui.logs
        if hasattr(ui, "logs") and isinstance(ui.logs, list):
            ui.logs.extend(logs)
            return
        # LogWindow
        if hasattr(ui, "log_window"):
            lw = ui.log_window
            if hasattr(lw, "extend"):
                lw.extend(logs)
            elif hasattr(lw, "append_many"):
                lw.append_many(logs)
            else:
                for line in logs:
                    if hasattr(lw, "append"):
                        lw.append(line)

    def _push_events(self, ui, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        # example: Stock to ui.events / Make ui.floating_texts
        if hasattr(ui, "events") and isinstance(ui.events, list):
            ui.events.extend(events)

    def _clear_planned_actions(
        self, ui, party_members: List[PartyMemberRuntime]
    ) -> None:
        if hasattr(ui, "planned_actions"):
            ui.planned_actions = [None] * len(party_members)

    def _resolve_jump_target_index(
        self, member: PartyMemberRuntime, enemies: List[EnemyRuntime]
    ) -> Optional[int]:
        t_idx = getattr(member.state, "jump_target_index", None)
        if (
            t_idx is not None
            and 0 <= t_idx < len(enemies)
            and not is_out_of_battle(enemies[t_idx].state)
        ):
            return t_idx
        return first_alive_enemy_index(enemies)

    def _auto_fill_jump_actions(
        self,
        ui,
        party_members: List[PartyMemberRuntime],
        enemies: List[EnemyRuntime],
    ) -> None:
        if not hasattr(ui, "planned_actions"):
            return

        for i, member in enumerate(party_members):
            if is_out_of_battle(member.state):
                continue
            if not getattr(member.state, "is_jumping", False):
                continue

            target_idx = self._resolve_jump_target_index(member, enemies)
            if target_idx is None:
                continue

            ui.planned_actions[i] = PlannedAction(
                kind="jump",
                command="Jump",
                target_side="enemy",
                target_index=target_idx,
            )

    def _append_auto_filled_action_logs(
        self, ui, party_members: List[PartyMemberRuntime]
    ) -> None:
        if not hasattr(ui, "planned_actions"):
            return

        for i, action in enumerate(ui.planned_actions):
            if action is None or action.kind != "jump":
                continue
            member_name = getattr(party_members[i], "name", f"member[{i}]")
            ui.logs.append(f"{member_name} prepares to land from Jump this turn.")

    def _map_end_reason_to_result(self, end_reason: str) -> BattleResult:
        match end_reason:
            case "enemy_defeated":
                return BattleResult.ENEMY_DEFEATED
            case "char_defeated":
                return BattleResult.PARTY_DEFEATED
            case "escape":
                return BattleResult.ESCAPE
            case _:
                return BattleResult.CONTINUE
