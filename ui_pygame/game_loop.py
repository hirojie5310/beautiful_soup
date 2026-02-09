# ui_pygame/game_loop.py
# アプリケーションの中身（OSとは無関係）ゲーム進行（主役）
# 「画面・時間・設定」だけを受け取る（ゲーム進行に最低限必要な「環境」だけ）
# screen:描画先, clock:フレーム管理, font:表示リソース（pygame依存）
# config:アプリ設定（論理名）

# ui_pygame/
#   ├─ app.py          ← pygame専用の起動ラッパ
#   ├─ game_loop.py    ← ゲーム進行（主役）
#   ├─ enemy_flow.py
#   ├─ battle_flow.py
#   ├─ victory_flow.py

from __future__ import annotations

from ui_pygame.app_context import BattleAppConfig
from ui_pygame.game_flow_controller import GameFlowController


def run_game_loop(
    *,
    screen,
    clock,
    font,
    config: BattleAppConfig,
) -> None:
    """
    ゲーム全体の進行を管理するメインループ
    - 敵選択
    - 戦闘
    - 勝利処理
    - セーブ確認
    """
    controller = GameFlowController(
        screen=screen,
        clock=clock,
        font=font,
        config=config,
    )
    controller.run()
