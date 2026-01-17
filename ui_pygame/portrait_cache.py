# assets_py/portrait_cache.py

from typing import Dict
import pygame
from pathlib import Path


class PortraitCache:
    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)
        self._cache: Dict[str, pygame.Surface] = {}

    def get(self, key: str) -> pygame.Surface:
        if key not in self._cache:
            path = self.base_dir / f"{key}.png"
            self._cache[key] = pygame.image.load(path).convert_alpha()
        return self._cache[key]

    def preload(self, keys: list[str]) -> None:
        for k in keys:
            self.get(k)
