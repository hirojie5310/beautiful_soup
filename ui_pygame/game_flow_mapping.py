# ui_pygame/game_flow_mapping.py
# 「BattleResult → GamePhase」の対応表

from combat.battle_result import BattleResult
from ui_pygame.game_phase import GamePhase

BATTLE_RESULT_TO_PHASE: dict[BattleResult, GamePhase] = {
    BattleResult.QUIT: GamePhase.QUIT,
    BattleResult.ENEMY_DEFEATED: GamePhase.VICTORY,
    BattleResult.PARTY_DEFEATED: GamePhase.GAMEOVER,  # ★追加
    BattleResult.ESCAPE: GamePhase.ENEMY_SELECT,
    BattleResult.PARTY_DEFEATED: GamePhase.ENEMY_SELECT,
}
