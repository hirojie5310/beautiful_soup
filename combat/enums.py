# ============================================================
# enums: 変数のような機能を持つ一意の定数

# ElementRelation: 属性相性の結果を表すための型定義（通常/弱点/耐性/吸収/無効の5種）で、ダメージ補正やログ表示の基準となる
# BattleKind: 戦闘コマンドの大分類（物理/魔法/アイテム/防御/逃走/特殊）を表す型定義で、行動分岐の基準に使われる
# BattleEndReason: 戦闘処理全体の終了理由（継続/敵全滅/味方全滅/逃走/強制終了）を統一的に扱うための型定義
# Status: 戦闘中に付与される状態異常の種類（毒・ブラインド・石化・KO・混乱・睡眠など）を列挙するEnum
# ============================================================

from typing import Literal, TypeAlias
from enum import Enum, auto


ElementRelation = Literal["normal", "weak", "resist", "absorb", "null"]

# 既存3種 + 新規2種 + 将来拡張用 "special"
BattleKind: TypeAlias = Literal[
    "physical", "magic", "item", "defend", "jump", "run", "special"
]

ENEMY_SINGLE_TARGET_KINDS: set[BattleKind] = {
    "physical",
    "special",
    "jump",
}

# 戦闘終了理由の一般化
BattleEndReason = Literal[
    "continue",
    "enemy_defeated",
    "char_defeated",
    "escaped",
    "enemy_escaped",
    "forced_end",  # イベントなどで強制終了したい時用（将来拡張）
]


class MagicType(str, Enum):
    BLACK = "Black Magic"
    WHITE = "White Magic"
    SUMMON = "Summon Magic"


class Status(Enum):
    """戦闘中に付与される状態異常の種類"""

    POISON = auto()
    BLIND = auto()
    MINI = auto()
    SILENCE = auto()
    TOAD = auto()  # 追加：トード
    PETRIFY = auto()  # 追加：石化（完全／一部をまとめて扱う）
    KO = auto()
    CONFUSION = auto()
    SLEEP = auto()
    PARALYZE = auto()  # ★追加：麻痺（Tranquilizer 用）
    PARTIAL_PETRIFY = auto()

    # 必要に応じて SLEEP などを追加
