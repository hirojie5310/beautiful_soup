# main.py
from ui_pygame.app import run_battle_app, BattleAppConfig

if __name__ == "__main__":
    cfg = BattleAppConfig(
        fps=60,
        caption="FF3風 Battle Simulator (dev)",
    )

    # enemy_names を渡さない → pygame側で場所選択 & 抽選
    run_battle_app(config=cfg)
