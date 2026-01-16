# ============================================================
# logic: target_side input_modeの処理

# reset_target_flags: ターゲット関連のフラグをリセット
# make_planned_action: プランされた行動を作成
# build_magic_candidates_for_member: メンバーの魔法候補リストを構築
# build_item_candidates_for_battle: 戦闘中のアイテム候補リストを構築
# normalize_battle_command: 戦闘コマンドを正規化
# get_job_commands: ジョブから戦闘コマンドリストを取得
# find_next_unfilled: 次の未入力キャラを探す
# to_int: 任意の値を整数に変換
# ============================================================

from typing import Any, List, Optional, Tuple, cast, Callable, Dict
from combat.constants import COMMAND_TO_KIND
from combat.models import PlannedAction, TargetSide
from combat.enums import BattleKind
from combat.inventory import build_item_list, is_item_visible_in_context
from combat.input_ui import normalize_battle_command
from ui_pygame.state import BattleUIState
from ui_pygame.ui_types import CommandCandidate


SPECIAL_NO_TARGET = {"Cheer", "Scare", "Flee", "Terrain", "Boost"}
SPECIAL_ENEMY_TARGET = {"Steal", "Peep", "Study"}  # 必要なら増やす


def command_needs_target(cmd: str, kind: BattleKind) -> bool:
    if kind in ("physical", "magic", "item", "jump"):
        return True
    if kind in ("defend", "run"):
        return False
    if kind == "special":
        if cmd in SPECIAL_NO_TARGET:
            return False
        # 未分類 special はとりあえず「敵単体扱い」に寄せる（安全側）
        return True
    return True


def reset_target_flags(ui: BattleUIState) -> None:
    # ターゲット関連
    ui.selected_target_all = False
    ui.selected_target_idx = 0
    ui.selected_target_side_idx = 0
    ui.target_side = cast(TargetSide, "enemy")

    # 直前の選択内容（重要）
    ui.selected_spell_name = None
    ui.selected_item_name = None


def make_planned_action(
    *,
    kind: BattleKind,
    command: str,
    member_idx: int,
    target_side: TargetSide,
    target_index: Optional[int],
    spell_name: Optional[str] = None,
    item_name: Optional[str] = None,
    target_all: bool = False,  # ★追加
) -> PlannedAction:
    return PlannedAction(
        kind=kind,
        command=command,
        spell_name=spell_name,
        item_name=item_name,
        target_side=target_side,
        target_index=target_index,
        target_all=target_all,  # ★追加
    )


# メンバーの魔法候補リストを構築
def build_magic_candidates_for_member(
    party_magic_lists, member_idx: int
) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for row in party_magic_lists[member_idx] or []:
        name = str(row[0])
        lv = to_int(row[1], 0)
        mp = to_int(row[2], 0)
        out.append((name, lv, mp))
    return out


# 戦闘中のアイテム候補リストを構築
def build_item_candidates_for_battle(items_by_name, save) -> List[Tuple[str, str, int]]:
    item_list = build_item_list(items_by_name, save, in_battle=True)
    item_list = [
        (name, itype, qty)
        for (name, itype, qty) in item_list
        if is_item_visible_in_context(items_by_name.get(name, {}), in_combat=True)
    ]
    return item_list


def get_job_commands(member) -> List[CommandCandidate]:
    """ジョブ定義の BattleCommand1..4 を読む。cmd と kind をここで確定する。"""
    job_data = member.job
    cmds: List[CommandCandidate] = []
    raw = getattr(job_data, "raw", {}) or {}

    for i in range(1, 5):
        bc = raw.get(f"BattleCommand{i}")
        if not bc:
            continue
        c = (bc.get("Command") or "").strip()
        if c:
            k: BattleKind = normalize_battle_command(c)
            cmds.append(CommandCandidate(cmd=c, kind=k))

    # 保険：空ならFF基本セット
    if not cmds:
        base = ["Fight", "Defend", "Item", "Run"]
        cmds = [CommandCandidate(cmd=c, kind=normalize_battle_command(c)) for c in base]

    return cmds


# 次の未入力キャラを探す
def find_next_unfilled(ui: BattleUIState) -> Optional[int]:
    n = len(ui.planned_actions)
    if n == 0:
        return None
    for offset in range(0, n):  # ★0から探す（現在位置も含めたい場合）
        i = (ui.selected_member_idx + offset) % n
        if ui.planned_actions[i] is None:
            return i
    return None


def to_int(x: Any, default: int = 0) -> int:
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, int):
        return x
    if isinstance(x, str):
        try:
            return int(x)
        except ValueError:
            return default
    return default


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))
