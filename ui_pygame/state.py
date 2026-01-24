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
# UI状態（★1回だけ定義）
# -------------------------
@dataclass
class BattleUIState:
    turn: int = 1
    phase: str = "input"  # "input" / "resolve" / "end"

    # 入力段階
    # member -> command -> (magic/item) -> target_side -> target_enemy/target_ally -> back to member
    input_mode: str = (
        "member"  # "member" | "command" | "magic" | "item" | "target_side" | "target_enemy" | "target_ally"
    )

    selected_member_idx: int = 0

    # command 選択
    command_candidates: Sequence[CommandCandidate] = field(default_factory=list)
    selected_command_idx: int = 0

    # magic 選択（party_magic_lists[member_idx] のリストをそのまま表示）
    magic_candidates: list[tuple[str, int, int]] = field(default_factory=list)
    selected_magic_idx: int = 0
    selected_spell_name: Optional[str] = None

    # item 選択
    item_candidates: List[Tuple[str, str, int]] = field(
        default_factory=list
    )  # [(name, itype, qty), ...]
    selected_item_idx: int = 0
    selected_item_name: Optional[str] = None

    # target 選択
    target_side: TargetSide | None = None
    selected_target_idx: int = 0  # enemy/ally list index
    selected_target_side_idx: int = 0  # ★ 0=敵, 1=味方, 2=自分

    # ★One/All 用：単体/全体の選択
    aoe_choice_candidates: List[str] = field(default_factory=lambda: ["単体", "全体"])
    selected_aoe_idx: int = 0
    selected_target_all: bool = False

    # simulate に渡す
    planned_actions: List[Optional[PlannedAction]] = field(default_factory=list)

    logs: List[str] = field(default_factory=list)

    # ★追加：battle_sim / controller から渡されるイベント
    events: list[UiEvent] = field(default_factory=list)

    # ログスクロール
    scroll: int = 0

    # スクロール用の状態
    menu_scroll: int = 0  # ★ スクロール位置（行単位）
    menu_visible_rows: int = 8  # ★ 一度に表示する行数

    spells_by_name: dict = field(default_factory=dict)  # spell_name -> spell_json

    # フローティングテキスト
    dt_ms: int = 0
    floating_texts: List[FloatingText] = field(default_factory=list)
    enemy_sprite_rects: List[pygame.Rect] = field(default_factory=list)
    sprite_cache: dict = field(default_factory=dict)  # 使うなら

    # ログウィンドウ
    log_scroll: int = 0  # LogWindow用スクロール位置
    log_max_keep: int = 100  # LogWindow用最大保持行数

    # サウンドエフェクト
    se_enter: Any | None = None  # pygame.mixer.Sound オブジェクトなど
    se_confirm: Any | None = None  # pygame.mixer.Sound オブジェクトなど
    se_rareitem: Any | None = None  # pygame.mixer.Sound オブジェクトなど

    # BGM 状態
    current_bgm: str | None = None  # "battle", "victory", "requiem"


@dataclass
class FloatingText:
    enemy_index: int
    text: str
    ttl_ms: int = 900  # 表示時間
    age_ms: int = 0  # 経過
    y_offset: float = 0.0  # 上に流す

    def update(self, dt_ms: int) -> bool:
        self.age_ms += dt_ms
        self.y_offset -= 0.03 * dt_ms  # 上に移動（調整OK）
        return self.age_ms < self.ttl_ms

    def alpha(self) -> int:
        # 終盤でフェードアウト
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

    # 画面に残す最大“行数”（wrap後の行数基準）
    max_lines: int = 200

    # スクロール（0=最下部、正の値で上へ）
    scroll: int = 0

    lines: List[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        """
        text: 1行でも複数行でもOK（\n を含んでよい）
        """
        for raw_line in text.splitlines():
            wrapped = self._wrap_line(raw_line)
            self.lines.extend(wrapped)

        # ためすぎ防止
        if len(self.lines) > self.max_lines:
            over = len(self.lines) - self.max_lines
            self.lines = self.lines[over:]

        # 新しいログが来たら基本は最下部に戻す（好みで無効化可）
        self.scroll = 0

    def add_many(self, texts: List[str]) -> None:
        for t in texts:
            self.add(t)

    def handle_event(self, event: pygame.event.Event) -> None:
        # マウスホイールでスクロール（Windowsでもpygame2ならMOUSEWHEELが普通に来ます）
        if event.type == pygame.MOUSEWHEEL:
            # 上に回すと event.y=1（上へスクロールしたいので scroll を増やす）
            self.scroll += -event.y * 3  # 3行ずつ
            self.scroll = max(0, self.scroll)

        # キーでもスクロール（任意）
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PAGEUP:
                self.scroll += 10
            elif event.key == pygame.K_PAGEDOWN:
                self.scroll = max(0, self.scroll - 10)

    def draw(self, screen: pygame.Surface) -> None:
        # 背景と枠
        pygame.draw.rect(screen, self.bg_color, self.rect)
        pygame.draw.rect(screen, self.border_color, self.rect, width=2)

        inner = self.rect.inflate(-self.padding * 2, -self.padding * 2)

        # 表示可能行数を計算
        line_h = self.font.get_height()
        step = line_h + self.line_gap
        visible_lines = max(1, inner.height // step)

        # 表示範囲（最下部基準 + scroll）
        total = len(self.lines)
        end = total - self.scroll
        start = max(0, end - visible_lines)
        view = self.lines[start:end]

        # 描画（下から上に積むとFFっぽい）
        y = inner.bottom - step
        for s in reversed(view):
            surf = self.font.render(s, True, self.text_color)
            screen.blit(surf, (inner.left, y))
            y -= step

        # スクロールが大きすぎたときの安全策
        self.scroll = min(self.scroll, max(0, total - visible_lines))

    def _wrap_line(self, line: str) -> List[str]:
        """
        rect内幅に収まるように、スペース区切り優先で簡易wrap。
        日本語のようにスペースが少ない場合は“文字単位”でも割ります。
        """
        max_w = self.rect.width - self.padding * 2
        if self.font.size(line)[0] <= max_w:
            return [line]

        # まずはスペース区切りで試す
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

        # スペースがない（日本語など）→文字単位でwrap
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
