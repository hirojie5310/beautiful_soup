# ui_pygame/gameover_flow.py

import pygame


def show_gameover_screen(
    *,
    screen: pygame.Surface,
    font: pygame.font.Font,
) -> None:
    """
    GAME OVER 画面を描画するだけの関数
    入力待ち・フェーズ遷移は呼び出し側で行う
    """

    w, h = screen.get_size()

    # 背景
    screen.fill((0, 0, 0))

    # --- GAME OVER テキスト ---
    title_surf = font.render("GAME OVER", True, (200, 40, 40))
    title_rect = title_surf.get_rect(center=(w // 2, h // 2 - 40))
    screen.blit(title_surf, title_rect)

    # --- サブメッセージ ---
    sub_surf = font.render(
        "Press Enter to Continue / Esc to Quit",
        True,
        (180, 180, 180),
    )
    sub_rect = sub_surf.get_rect(center=(w // 2, h // 2 + 30))
    screen.blit(sub_surf, sub_rect)

    pygame.display.flip()
