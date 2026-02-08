# ui_pygame/app.py
# pygame専用の起動ラッパ
# 「画面・時間・設定」だけを渡す（ゲーム進行に最低限必要な「環境」だけ）
# screen:描画先, clock:フレーム管理, font:表示リソース（pygame依存）
# config:アプリ設定（論理名）

import pygame
from ui_pygame.game_loop import run_game_loop
from ui_pygame.app_context import BattleAppConfig


def run_pygame_app(*, config: BattleAppConfig) -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.width, config.height))
    pygame.display.set_caption(config.caption)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont(config.font_name, config.font_size)

    run_game_loop(
        screen=screen,
        clock=clock,
        font=font,
        config=config,
    )

    pygame.quit()
