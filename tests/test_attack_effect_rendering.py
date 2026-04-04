from __future__ import annotations

from types import ModuleType, SimpleNamespace
from typing import Any
import sys

if "pygame" not in sys.modules:
    pygame_stub: Any = ModuleType("pygame")

    class _Rect:
        def __init__(self, x: int, y: int, w: int, h: int) -> None:
            self.x = x
            self.y = y
            self.w = w
            self.h = h
            self.left = x
            self.top = y
            self.width = w
            self.height = h
            self.right = x + w
            self.bottom = y + h
            self.centerx = x + w // 2
            self.centery = y + h // 2

    class _Surface:
        def __init__(self, size: tuple[int, int]) -> None:
            self._w, self._h = size

        def get_width(self) -> int:
            return self._w

        def get_height(self) -> int:
            return self._h

    pygame_stub.Rect = _Rect
    pygame_stub.Surface = _Surface
    pygame_stub.font = SimpleNamespace(Font=object)
    pygame_stub.mixer = SimpleNamespace(Sound=object)
    pygame_stub.event = SimpleNamespace(Event=object)
    sys.modules["pygame"] = pygame_stub

import pygame

from ui_pygame.render.floating_texts import (
    _attack_effect_alpha,
    _attack_effect_draw_position,
)
from ui_pygame.state import AttackEffect


def test_attack_effect_moves_left_to_right_across_target() -> None:
    effect = AttackEffect(target_side="enemy", target_index=0, ttl_ms=220)
    target_rect = pygame.Rect(100, 40, 90, 60)
    frame = pygame.Surface((41, 44))

    effect.age_ms = 0
    start_x, start_y = _attack_effect_draw_position(effect, target_rect, frame)

    effect.age_ms = 110
    middle_x, middle_y = _attack_effect_draw_position(effect, target_rect, frame)

    effect.age_ms = 220
    end_x, end_y = _attack_effect_draw_position(effect, target_rect, frame)

    assert start_x < middle_x < end_x
    assert abs(start_y - end_y) > 0
    assert middle_y != start_y


def test_attack_effect_alpha_fades_only_near_end() -> None:
    assert _attack_effect_alpha(0.0) == 255
    assert _attack_effect_alpha(0.79) == 255
    assert 0 < _attack_effect_alpha(0.9) < 255
    assert _attack_effect_alpha(1.0) == 0
