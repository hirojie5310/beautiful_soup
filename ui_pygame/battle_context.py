# ui_pygame/battle_context.py
# 唯一の ctx　戦闘全体の依存の束（アプリ層）
# （BattleAppContext は「UI入力・表示用の ctx」として残す）
# 戦闘ドメインの振る舞いを持ってよい Context
# 生やしてよいメソッド:（「3回出てきたら昇格」）
# ① 戦闘という文脈に意味がある“問い合わせ”（状態を変更しない, 「今どうなっているか」を返すだけ, UI非依存）
# ② BattleContext が持つ情報だけで完結する処理
# 生やしてはいけないメソッド:（戦闘の事実を知っていてもよいが、戦闘の演出や操作は知らない」）
# ① UI 状態を書き換えるもの
# ② pygame / 音 / 入力に触るもの

# BattleContext          ← アプリケーション層
#   ├─ enemies
#   ├─ spells_expanded
#   ├─ se_enter / confirm / invalid
#   ├─ normalize_battle_command
#   ├─ is_out_of_battle
#   └─ …

from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

import pygame

from combat.models import EnemyRuntime, PartyMemberRuntime
from combat.life_check import any_char_alive, any_enemy_alive

from ui_pygame.audio.ui_se import BattleSE


@dataclass
class BattleContext:
    # ===== データ =====
    enemies: list[EnemyRuntime]
    party_members: list[PartyMemberRuntime]
    spells_expanded: dict

    # ===== SE =====
    se: BattleSE

    # ===== ロジック関数群（関数ポインタの集合体） =====
    normalize_battle_command: Callable
    reset_target_flags: Callable
    is_out_of_battle: Callable
    get_job_commands: Callable
    build_magic_candidates_for_member: Callable
    build_item_candidates_for_battle: Callable
    make_planned_action: Callable

    # 複数の combat 関数を“束ねる”もの
    def is_battle_over(self) -> bool:
        return not any_char_alive(self.party_members) or not any_enemy_alive(
            self.enemies
        )

    # この戦闘インスタンス固有の問い合わせ（self.enemies という この戦闘の状態に依存）
    def alive_enemy_indices(self) -> list[int]:
        return [
            i for i, e in enumerate(self.enemies) if not self.is_out_of_battle(e.state)
        ]
