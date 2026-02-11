# app_pygame.py
# Windowsアプリとしてのエントリーポイント（将来 exe 化（pyinstaller）する場所）
# Platform Entry Point（実行環境の入口）OS・ランタイム都合のコード置き場
# config:アプリ設定（論理名）
# app_pygame.py        ← 実行環境の入口（薄くてOK）
# ui_pygame/
#   ├─ app.py           ← pygame専用の起動ラッパ
#   ├─ game_loop.py     ← ゲーム進行（主役）
#   ├─ enemy_flow.py    ← エリア/敵選択
#   ├─ battle_flow.py   ← 戦闘処理（BattleContext依存）UI層は BattleAppContext依存
#   ├─ victory_flow.py  ← 戦闘勝利処理
#   ├─ gameover_flow.py ← 戦闘敗退処理

from ui_pygame.app import run_pygame_app
from ui_pygame.app_context import BattleAppConfig

if __name__ == "__main__":
    cfg = BattleAppConfig(
        fps=60,
        caption="FF3風 Battle Simulator (dev)",
    )
    run_pygame_app(config=cfg)
