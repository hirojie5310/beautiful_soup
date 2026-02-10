# ui_pygame/audio/ui_bgm.py

from dataclasses import dataclass


@dataclass
class BattleBGM:
    normal: str
    boss: str
    victory: str
    requiem: str
