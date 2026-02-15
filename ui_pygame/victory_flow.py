# ui_pygame/victory_flow.py

import pygame
from collections import Counter

from ui_pygame.state import BattleUIState
from ui_pygame.save_prompt_adapter import _toast_pygame


RARE_ITEMS = {
    "Elixir",
    "Yoichi Arrow",
    "Onion Shield",
    "Onion Helm",
    "Onion Armor",
    "Onion Sword",
}


# ★戦闘勝利結果表示
def show_victory_result_pygame(
    screen,
    font,
    victory,
    battle_ui_se,
):
    ui = BattleUIState()
    ui.se_rareitem = pygame.mixer.Sound(battle_ui_se["rareitem"])

    # ① EXP
    _toast_pygame(
        screen,
        font,
        f"EXP +{victory['gained_exp']}",
        ms=1000,
    )

    # ② LvUP
    for name, old_lv, new_lv in victory["levelups"]:
        _toast_pygame(
            screen,
            font,
            f"{name} Lv{old_lv} → Lv{new_lv}!",
            ms=1000,
        )

    # ③ Gil
    if victory["gained_gil"] > 0:
        _toast_pygame(
            screen,
            font,
            f"{victory['gained_gil']} ギルを手に入れた！",
            ms=1000,
        )

    # ④ CP
    if victory["gained_cp"] > 0:
        _toast_pygame(
            screen,
            font,
            f"{victory['gained_cp']} CPを手に入れた！",
            ms=1000,
        )

    # ⑤ Drop Item
    dropped_items = victory.get("dropped_item", [])
    if dropped_items:
        loot_counter = Counter(dropped_items)

        for item, count in loot_counter.items():
            if item not in RARE_ITEMS:
                if count == 1:
                    msg = f"{item} を手に入れた！"
                else:
                    msg = f"{item} を{count}こ手に入れた！"

                _toast_pygame(
                    screen,
                    font,
                    msg,
                    ms=1000,
                )

        for item, count in loot_counter.items():
            if item in RARE_ITEMS:
                ui.se_rareitem.play()
                if count == 1:
                    msg = f"✨ {item} を手に入れた！ ✨"
                else:
                    msg = f"✨ {item} を{count}こ手に入れた！ ✨"

                _toast_pygame(
                    screen,
                    font,
                    msg,
                    ms=1500,
                )
