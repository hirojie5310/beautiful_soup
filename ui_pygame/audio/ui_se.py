# ui_pygame/audio/ui_se.py
# UI用SE（効果音）を構築する
# app_pygame.py → ui_pygame.app → ui_pygame.game_loop → ui_pygame.audio.ui_se

from dataclasses import dataclass
import pygame

from ui_pygame.app_context import BattleAppConfig


@dataclass
class BattleSE:
    enter: pygame.mixer.Sound | None = None
    confirm: pygame.mixer.Sound | None = None
    cancel: pygame.mixer.Sound | None = None
    invalid: pygame.mixer.Sound | None = None
    rareitem: pygame.mixer.Sound | None = None


def build_ui_se(cfg: BattleAppConfig) -> dict[str, pygame.mixer.Sound]:
    ui_se = {
        "enter": pygame.mixer.Sound(cfg.se_enter_path),
        "confirm": pygame.mixer.Sound(cfg.se_confirm_path),
        "rareitem": pygame.mixer.Sound(cfg.se_rareitem_path),
        "invalid": pygame.mixer.Sound(cfg.se_invalid),
    }

    ui_se["enter"].set_volume(cfg.se_enter_volume)
    ui_se["confirm"].set_volume(cfg.se_confirm_volume)
    ui_se["rareitem"].set_volume(cfg.se_rareitem_volume)
    ui_se["invalid"].set_volume(cfg.se_rareitem_volume)

    return ui_se


def play_se(ui_se: dict | None, key: str):
    if not ui_se:
        return
    snd = ui_se.get(key)
    if snd:
        snd.play()
