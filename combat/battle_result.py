# combat/battle_result.py
from enum import Enum, auto


class BattleResult(Enum):
    CONTINUE = auto()  # 戦闘継続
    ENEMY_DEFEATED = auto()  # 勝利
    PARTY_DEFEATED = auto()  # 全滅
    ESCAPE = auto()  # 逃走
    QUIT = auto()  # アプリ終了
