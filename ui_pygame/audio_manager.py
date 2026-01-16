from __future__ import annotations
import pygame
from pathlib import Path
from typing import Sequence

from ui_pygame.ui_events import AudioEvent, UiEvent


class AudioManager:
    def __init__(self, base_dir: str = "assets/audio"):
        self.base_dir = Path(base_dir)

        self.current_bgm: str | None = None
        self.bgm_volume: float = 0.8

        # SE キャッシュ
        self.se_cache: dict[str, pygame.mixer.Sound] = {}

    # ---------- BGM ----------
    def play_bgm(self, name: str | None, fade_ms: int = 0, loop: int = -1):
        """
        name: None → stop
        """
        if name == self.current_bgm:
            return

        if name is None:
            pygame.mixer.music.fadeout(fade_ms)
            self.current_bgm = None
            return

        path = self.base_dir / "bgm" / f"{name}.ogg"
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(self.bgm_volume)
        pygame.mixer.music.play(loop, fade_ms=fade_ms)

        self.current_bgm = name

    def stop_bgm(self, fade_ms: int = 0):
        pygame.mixer.music.fadeout(fade_ms)
        self.current_bgm = None

    # ---------- SE ----------
    def play_se(self, name: str, volume: float = 1.0):
        if name not in self.se_cache:
            path = self.base_dir / "se" / f"{name}.wav"
            self.se_cache[name] = pygame.mixer.Sound(path)

        se = self.se_cache[name]
        se.set_volume(volume)
        se.play()

    def handle_events(self, events: Sequence[UiEvent]):
        for ev in events:
            if not isinstance(ev, AudioEvent):
                continue  # Combat系は無視

            t = ev.type
            payload = ev.payload or {}

            if t == "bgm":
                name = payload.get("name")
                if name is None or isinstance(name, str):
                    self.play_bgm(name, fade_ms=int(payload.get("fade_ms", 0) or 0))

            elif t == "bgm_stop":
                self.stop_bgm(fade_ms=int(payload.get("fade_ms", 0) or 0))

            elif t == "se":
                name = payload.get("name")
                if isinstance(name, str) and name:
                    self.play_se(name, volume=float(payload.get("volume", 1.0)))
