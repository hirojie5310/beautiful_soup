# ui_pygame/game_phase.py
# 「今、ゲームは何をしているか」を 明示的にするための列挙型
# ロジックを整理するための“名札”
# 名前は 「画面」ではなく「意味」
# 今ある flow に 1対1で対応
from enum import Enum, auto


class GamePhase(Enum):
    ENEMY_SELECT = auto()
    BATTLE = auto()
    VICTORY = auto()
    GAMEOVER = auto()
    QUIT = auto()
