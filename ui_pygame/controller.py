# ui_pygame/controller.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, cast
from random import Random

from combat.runtime_state import RuntimeState
from combat.battle_sim import simulate_one_round_multi_party  # ←実際の場所に合わせて
from combat.models import PartyMemberRuntime  # ←実際の場所に合わせて

# EnemyRuntime / PlannedAction / SideTurnResult の import 先もあなたの構成に合わせて調整してください
from combat.models import (
    PlannedAction,
    EnemyRuntime,  # 例：あなたの実装に合わせる
    SideTurnResult,  # 例：あなたの実装に合わせる
)

from ui_pygame.ui_events import AudioEvent


@dataclass
class ResolveResult:
    logs: List[str]
    side_result: SideTurnResult
    events: List[Dict[str, Any]]


class BattleController:
    def __init__(self, rng: Optional[Random] = None):
        self.rng = rng or Random()
        self._bgm_started = False  # ★追加

    def update(
        self,
        ui,
        party_members: List[PartyMemberRuntime],
        enemies: List[EnemyRuntime],
        state: RuntimeState,
        *,
        ctx: Any,  # BattleAppContext を渡す（循環import避け）
        save: Optional[dict] = None,
        spells_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
        items_by_name: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        if getattr(ui, "battle_ended", False):
            return

        # ★戦闘BGM（初回だけ）
        if not self._bgm_started:
            if hasattr(ui, "events") and isinstance(ui.events, list):
                # ボス戦判定
                is_boss = self._is_boss_battle(enemies)
                bgm_name = ctx.config.bgm_battle2 if is_boss else ctx.config.bgm_battle1
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

        # ここはあなたの round_result の構造に合わせて
        end_reason = getattr(rr.side_result, "end_reason", "continue")
        if end_reason != "continue":
            ui.battle_ended = True
            ui.battle_end_reason = end_reason
            ui.phase = "end"
            ui.input_mode = "end"
            self._clear_planned_actions(ui, party_members)

            # ★終了BGM（勝利なら victory、敗北などは停止）
            if hasattr(ui, "events") and isinstance(ui.events, list):
                if end_reason == "enemy_defeated":
                    ui.events.append(
                        AudioEvent(
                            type="bgm",
                            payload={"name": ctx.config.bgm_victory, "fade_ms": 300},
                        )
                    )
                elif end_reason == "char_defeated":
                    ui.events.append(
                        AudioEvent(
                            type="bgm",
                            payload={"name": ctx.config.bgm_requiem, "fade_ms": 300},
                        )
                    )
                else:
                    ui.events.append(
                        AudioEvent(type="bgm_stop", payload={"fade_ms": 800})
                    )

            return

        # ===== continue: 次ターン入力開始の初期化 =====

        # ターン加算（ui.turn / ui.turn_count どちらでも）
        if hasattr(ui, "turn"):
            ui.turn += 1
        elif hasattr(ui, "turn_count"):
            ui.turn_count += 1

        # 入力フェーズに戻す
        ui.phase = "input"
        ui.input_mode = "member"

        # ターゲット選択状態を必ずクリア（ctxに既にあるならそれを使う）
        if hasattr(ctx, "reset_target_flags"):
            ctx.reset_target_flags(ui)

        # planned_actions をクリア
        self._clear_planned_actions(ui, party_members)

        # 「次に入力すべきキャラ」を再セット（あなたの既存関数を使う）
        # find_next_unfilled(ui) が app 側の関数なら ctx に渡しておくのが一番楽
        if hasattr(ctx, "find_next_unfilled"):
            ui.selected_member_idx = ctx.find_next_unfilled(ui) or 0
        else:
            # 保険：0に戻す
            ui.selected_member_idx = 0

        # そのキャラのコマンド候補を再計算
        if hasattr(ctx, "get_job_commands"):
            ui.command_candidates = ctx.get_job_commands(
                party_members[ui.selected_member_idx]
            )

        # ログ（任意）
        if hasattr(ui, "logs") and isinstance(ui.logs, list):
            t = getattr(ui, "turn", getattr(ui, "turn_count", "?"))
            ui.logs.append(f"--- Turn {t} 入力開始 ---")

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

    def _push_logs(self, ui, logs: List[str]) -> None:
        if not logs:
            return
        # ui.logs を持つならそこへ
        if hasattr(ui, "logs") and isinstance(ui.logs, list):
            ui.logs.extend(logs)
            return
        # LogWindow を持つならそちらへ（あなたの実装に合わせて）
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
        # 例：ui.events にためる / ui.floating_texts を作る…など
        if hasattr(ui, "events") and isinstance(ui.events, list):
            ui.events.extend(events)

    def _clear_planned_actions(
        self, ui, party_members: List[PartyMemberRuntime]
    ) -> None:
        if hasattr(ui, "planned_actions"):
            # len を揃えたいなら None 埋めが安全（参照箇所がある場合に備える）
            ui.planned_actions = [None] * len(party_members)
