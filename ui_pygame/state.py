# ============================================================
# state: UI状態管理
# BattleUIState / FloatingText / LogWindow などdataclass群

# BattleUIState: UIのカーソル、入力モード、ログ、floating_texts 等
# FloatingText: 敵の上に表示するダメージ等のテキスト
# LogWindow: 画面下部のログウィンドウ
# ModeResult: input_mode処理の結果
# ============================================================

from __future__ import annotations
import pygame
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple, Sequence

from combat.models import PlannedAction, TargetSide
from combat.battle_result import BattleResult

from ui_pygame.ui_types import CommandCandidate
from ui_pygame.ui_events import UiEvent


def add_logs(ui: BattleUIState, new_logs: List[str]) -> None:
    """
    ログ追加（最大保持数も管理）
    ※自動で最下部へ追従（log_scroll=0）させたいので、基本はスクロールをリセット。
    """
    if not new_logs:
        return
    ui.logs.extend(str(x) for x in new_logs)
    if len(ui.logs) > ui.log_max_keep:
        # 古いログを捨てる
        drop = len(ui.logs) - ui.log_max_keep
        ui.logs = ui.logs[drop:]

    # 新しいログが来たら最下部に戻す（好みでコメントアウト可）
    ui.log_scroll = 0


# -------------------------
# UI State (Define only once)
# -------------------------
@dataclass
class BattleUIState:
    turn: int = 1
    phase: str = "input"  # "input" / "resolve" / "end"

    # Input Phase
    # member -> command -> (magic/item) -> target_side -> target_enemy/target_ally -> back to member
    input_mode: str = (
        "member"  # "member" | "command" | "magic" | "item" | "target_side" | "target_enemy" | "target_ally"
    )

    selected_member_idx: int = 0

    # command selection
    command_candidates: Sequence[CommandCandidate] = field(default_factory=list)
    selected_command_idx: int = 0

    # magic selection (show party_magic_lists[member_idx])
    magic_candidates: list[tuple[str, int, int]] = field(default_factory=list)
    selected_magic_idx: int = 0
    selected_spell_name: Optional[str] = None

    # item selection
    item_candidates: List[Tuple[str, str, int]] = field(
        default_factory=list
    )  # [(name, itype, qty), ...]
    selected_item_idx: int = 0
    selected_item_name: Optional[str] = None

    # target selection
    target_side: TargetSide | None = None
    selected_target_idx: int = 0  # enemy/ally list index
    selected_target_side_idx: int = 0  # 笘・0=enemy, 1=ally, 2=self

    # One/All
    aoe_choice_candidates: List[str] = field(default_factory=lambda: ["One", "All"])
    selected_aoe_idx: int = 0
    selected_target_all: bool = False

    # -> simulate
    planned_actions: List[Optional[PlannedAction]] = field(default_factory=list)

    logs: List[str] = field(default_factory=list)

    # event from battle_sim / controller
    events: list[UiEvent] = field(default_factory=list)
    pending_floating_events: list[UiEvent] = field(default_factory=list)

    # log scroll
    scroll: int = 0

    # state for scroll
    menu_scroll: int = 0  # scroll position
    menu_visible_rows: int = 8  # column number for display

    spells_by_name: dict = field(default_factory=dict)  # spell_name -> spell_json

    # floating text
    dt_ms: int = 0
    floating_texts: List[FloatingText] = field(default_factory=list)
    enemy_sprite_rects: List[pygame.Rect] = field(default_factory=list)
    party_sprite_rects: List[pygame.Rect] = field(default_factory=list)
    sprite_cache: dict = field(default_factory=dict)  # sprite cache
    party_motion_frame_indices: List[int] = field(default_factory=list)
    party_attack_anim_queue: List[tuple[str, int]] = field(default_factory=list)
    party_attack_anim_active: Optional[tuple[str, int]] = None
    enemy_acting_highlight_idx: Optional[int] = None
    party_attack_anim_elapsed_ms: int = 0
    party_attack_anim_step_ms: int = 90
    party_attack_anim_gap_ms: int = 500
    party_attack_anim_gap_elapsed_ms: int = 0
    resolve_snapshot_ready: bool = False
    resolve_result_cache: Any = None
    resolve_events_enqueued: bool = False

    # log window
    log_scroll: int = 0  # scroll position for LogWindow
    log_max_keep: int = 100  # max column number for LogWindow

    # Sound effects
    se_enter: Optional[pygame.mixer.Sound] = None
    se_confirm: Optional[pygame.mixer.Sound] = None
    se_invalid: Optional[pygame.mixer.Sound] = None
    se_rareitem: Optional[pygame.mixer.Sound] = None

    # BGM state
    current_bgm: str | None = None  # "battle", "victory", "requiem"

    # ===== battle result =====
    battle_result: BattleResult = BattleResult.CONTINUE
    battle_ended: bool = False


@dataclass
class FloatingText:
    target_side: str
    target_index: int
    text: str
    ttl_ms: int = 900  # display time
    age_ms: int = 0  # progress
    y_offset: float = 0.0  # flow to upper

    def update(self, dt_ms: int) -> bool:
        self.age_ms += dt_ms
        self.y_offset -= 0.03 * dt_ms  # move to upper
        return self.age_ms < self.ttl_ms

    def alpha(self) -> int:
        # fade out
        remain = max(0, self.ttl_ms - self.age_ms)
        if remain >= 250:
            return 255
        return int(255 * (remain / 250))


@dataclass
class LogWindow:
    rect: pygame.Rect
    font: pygame.font.Font
    text_color: Tuple[int, int, int] = (230, 230, 230)
    bg_color: Tuple[int, int, int] = (10, 10, 20)
    border_color: Tuple[int, int, int] = (120, 120, 160)

    padding: int = 8
    line_gap: int = 4

    # max column number
    max_lines: int = 200

    # scroll
    scroll: int = 0

    lines: List[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        """
        text: can contain \n
        """
        for raw_line in text.splitlines():
            wrapped = self._wrap_line(raw_line)
            self.lines.extend(wrapped)

        # block over stock
        if len(self.lines) > self.max_lines:
            over = len(self.lines) - self.max_lines
            self.lines = self.lines[over:]

        # if new logs come, back to most below position
        self.scroll = 0

    def add_many(self, texts: List[str]) -> None:
        for t in texts:
            self.add(t)

    def handle_event(self, event: pygame.event.Event) -> None:
        # scroll by mouse wheel
        if event.type == pygame.MOUSEWHEEL:
            self.scroll += -event.y * 3  # 3陦後★縺､
            self.scroll = max(0, self.scroll)

        # scroll by key
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PAGEUP:
                self.scroll += 10
            elif event.key == pygame.K_PAGEDOWN:
                self.scroll = max(0, self.scroll - 10)

    def draw(self, screen: pygame.Surface) -> None:
        # back ground and flame
        pygame.draw.rect(screen, self.bg_color, self.rect)
        pygame.draw.rect(screen, self.border_color, self.rect, width=2)

        inner = self.rect.inflate(-self.padding * 2, -self.padding * 2)

        # calculate max column
        line_h = self.font.get_height()
        step = line_h + self.line_gap
        visible_lines = max(1, inner.height // step)

        # display range
        total = len(self.lines)
        end = total - self.scroll
        start = max(0, end - visible_lines)
        view = self.lines[start:end]

        # draw
        y = inner.bottom - step
        for s in reversed(view):
            surf = self.font.render(s, True, self.text_color)
            screen.blit(surf, (inner.left, y))
            y -= step

        # safety guard for scroll
        self.scroll = min(self.scroll, max(0, total - visible_lines))

    def _wrap_line(self, line: str) -> List[str]:
        """
        rect内幅に収まるように、スペース区切り優先で簡易wrap。
        日本語のようにスペースが少ない場合は“文字単位”でも割ります。
        """
        max_w = self.rect.width - self.padding * 2
        if self.font.size(line)[0] <= max_w:
            return [line]

        # space divide
        words = line.split(" ")
        if len(words) > 1:
            out, buf = [], ""
            for w in words:
                trial = (buf + " " + w).strip()
                if self.font.size(trial)[0] <= max_w:
                    buf = trial
                else:
                    if buf:
                        out.append(buf)
                    buf = w
            if buf:
                out.append(buf)
            return out

        # no space
        out, buf = [], ""
        for ch in line:
            trial = buf + ch
            if self.font.size(trial)[0] <= max_w:
                buf = trial
            else:
                if buf:
                    out.append(buf)
                buf = ch
        if buf:
            out.append(buf)
        return out


@dataclass
class ModeResult:
    committed: bool
    request_resolve: bool
