# ============================================================
# app_context: ui context data classes

# BattleAppContext: holds context data for the battle UI
# ============================================================

# ui_pygame/app_context.py

from dataclasses import dataclass
from typing import Any, Callable, Sequence, Optional, Protocol, List, Tuple

from combat.enums import BattleKind
from combat.models import PlannedAction, TargetSide
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import CommandCandidate


class MakePlannedActionFn(Protocol):
    def __call__(
        self,
        *,
        kind: BattleKind,
        command: str,
        member_idx: int,
        target_side: TargetSide,
        target_index: Optional[int],
        spell_name: Optional[str] = None,
        item_name: Optional[str] = None,
        target_all: bool = False,
    ) -> PlannedAction: ...


@dataclass
class BattleAppContext:
    config: Any  # 本当は BattleAppConfig にしたいが循環があるなら Any でOK

    party_members: Sequence[Any]
    enemies: Sequence[Any]

    normalize_battle_command: Callable[[str], BattleKind]
    reset_target_flags: Callable[[BattleUIState], None]
    is_out_of_battle: Callable[[Any], bool]

    get_job_commands: Callable[[Any], Sequence[CommandCandidate]]
    build_magic_candidates_for_member: Callable[[int], list[tuple[str, int, int]]]
    build_item_candidates_for_battle: Callable[[], List[Tuple[str, str, int]]]

    make_planned_action: MakePlannedActionFn

    def on_committed(self, ui: BattleUIState) -> None:
        self.reset_target_flags(ui)
        if self.all_actions_committed(ui):
            ui.phase = "resolve"
            ui.input_mode = "resolve"  # 必要なら
            ui.logs.append("[入力] 全員入力完了 → 行動解決へ")

    def all_actions_committed(self, ui: BattleUIState) -> bool:
        for i, act in enumerate(ui.planned_actions):
            if act is not None:
                continue
            # 戦闘外（KO等で入力不要）ならOK
            if self.is_out_of_battle(self.party_members[i].state):
                continue
            return False
        return True
