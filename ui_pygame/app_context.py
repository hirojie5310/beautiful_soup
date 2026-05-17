# ui_pygame/app_context.py
# ============================================================
# app_context: ui context data classes
# BattleAppContext: holds context data for the battle UI
# ============================================================

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Sequence, Optional, Protocol, List, Tuple

from combat.enums import BattleKind
from combat.models import PlannedAction, TargetSide
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import CommandCandidate


# UI専用 ctx（UI入力・表示用の ctx）
# UI振る舞いを持ってよい Context
# UI 状態（BattleUIState）を引数に取るメソッドを持つ
# BattleAppContext       ← UI層（既存）
#   ├─ config
#   ├─ party_members
#   ├─ enemies
#   ├─ get_job_commands
#   └─ …
@dataclass
class BattleAppContext:
    config: Any  # 本当は BattleAppConfig にしたいが循環があるなら Any でOK

    party_members: Sequence[Any]
    enemies: Sequence[Any]
    items_by_name: dict[str, dict[str, Any]]

    normalize_battle_command: Callable[[str], BattleKind]
    reset_target_flags: Callable[[BattleUIState], None]
    is_out_of_battle: Callable[[Any], bool]

    get_job_commands: Callable[[Any], Sequence[CommandCandidate]]
    build_magic_candidates_for_member: Callable[[int], list[tuple[str, int, int]]]
    build_item_candidates_for_battle: Callable[[], List[Tuple[str, str, int]]]

    make_planned_action: MakePlannedActionFn

    find_next_unfilled_member_index: Callable[[BattleUIState], int]

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
class BattleAppConfig:
    width: int = 960
    height: int = 540
    fps: int = 60
    caption: str = "FF3風 Battle Simulator"
    font_name: str = "meiryo"
    font_size: int = 18
    enemy_sprite_dir: str = "assets/images/enemy_sprites"
    motion_dir: str = "assets/images/motions"
    motion_frame_w: int = 55
    motion_frame_h: int = 60
    motion_attack_step_ms: int = 90
    motion_attack_gap_ms: int = 500
    attack_effect_dir: str = "assets/images/effects"
    attack_effect_frame_w: int = 41
    attack_effect_frame_h: int = 44
    attack_effect_frame_count: int = 2

    # ★追加
    audio_dir: str = "assets/sounds/"
    face_dir: str = "assets/images/portraits/"
    status_icon_dir: str = "assets/images/status_icons/"

    # ★BGM 定義（論理名 → ファイル名）
    bgm_enemy_select: str = "Fortune_Teller2"
    bgm_battle1: str = "battle1"
    bgm_battle2: str = "battle2"
    bgm_victory: str = "victory"
    bgm_requiem: str = "requiem"

    # ★SE 定義
    se_enter_path: str = "assets/sounds/se/se_enter.ogg"
    se_confirm_path: str = "assets/sounds/se/se_confirm.ogg"
    se_rareitem_path: str = "assets/sounds/se/se_rareitem.ogg"
    se_invalid: str = "assets/sounds/se/se_invalid.ogg"
    se_enter_volume: float = 0.35
    se_confirm_volume: float = 0.6
    se_rareitem_volume: float = 0.6
    se_invalid_volume: float = 0.6
