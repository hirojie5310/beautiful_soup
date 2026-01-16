from __future__ import annotations

from typing import Optional
import pygame

from combat.models import PlannedAction
from combat.enums import BattleKind
from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


SPECIAL_NO_TARGET = {"Cheer", "Scare", "Flee", "Terrain", "Boost"}


def _play_se(se: Optional[pygame.mixer.Sound]) -> None:
    if se is not None:
        se.play()


def _alive_enemy_indices(enemies) -> list[int]:
    return [i for i, e in enumerate(enemies) if getattr(e, "hp", 0) > 0]


def _confirm_self_action(
    *,
    ui: BattleUIState,
    ctx: BattleAppContext,
    kind: BattleKind,
    command: str,
) -> None:
    # defend/run/special(no target) 用
    ui.planned_actions[ui.selected_member_idx] = PlannedAction(
        kind=kind,
        command=command,
        spell_name=None,
        item_name=None,
        target_side="self",
        target_index=ui.selected_member_idx,
    )

    member = ctx.party_members[ui.selected_member_idx]
    ui.logs.append(f"[確定] {getattr(member, 'name', 'member')}: {command}")

    _play_se(getattr(ui, "se_confirm", None))
    ui.input_mode = "member"
    ctx.on_committed(ui)


def _enter_magic_menu(ui: BattleUIState, ctx: BattleAppContext) -> None:
    ui.magic_candidates = ctx.build_magic_candidates_for_member(ui.selected_member_idx)
    ui.selected_magic_idx = 0
    ui.input_mode = "magic"

    member = ctx.party_members[ui.selected_member_idx]
    ui.logs.append(f"[入力] 魔法を選択: {getattr(member, 'name', 'member')}")


def _enter_item_menu(ui: BattleUIState, ctx: BattleAppContext) -> None:
    ui.item_candidates = ctx.build_item_candidates_for_battle()
    ui.selected_item_idx = 0
    ui.input_mode = "item"

    member = ctx.party_members[ui.selected_member_idx]
    ui.logs.append(f"[入力] アイテムを選択: {getattr(member, 'name', 'member')}")


def _enter_target_enemy_for_attack(
    ui: BattleUIState, ctx: BattleAppContext, *, kind: BattleKind, command: str
) -> None:
    alive = _alive_enemy_indices(ctx.enemies)

    # 生存敵0なら戻す（保険）
    if not alive:
        ui.logs.append("[入力] 敵がいません")
        ui.input_mode = "member"
        ctx.reset_target_flags(ui)
        return

    # 生存敵が1体だけなら即確定（元の挙動）
    if len(alive) == 1:
        target_enemy_index = alive[0]
        member = ctx.party_members[ui.selected_member_idx]
        enemy_name = getattr(
            ctx.enemies[target_enemy_index], "name", f"enemy[{target_enemy_index}]"
        )

        ui.planned_actions[ui.selected_member_idx] = PlannedAction(
            kind=kind,
            command=command,
            spell_name=None,
            item_name=None,
            target_side="enemy",
            target_index=target_enemy_index,
        )
        _play_se(getattr(ui, "se_confirm", None))
        ui.logs.append(
            f"[自動] {getattr(member, 'name', 'member')}: {command} → {enemy_name}"
        )

        ui.input_mode = "member"
        ctx.on_committed(ui)
        return

    # 通常：ターゲット選択へ
    ui.selected_target_all = False  # 物理/特殊は AoE なし
    ui.selected_target_idx = 0
    ui.input_mode = "target_enemy"
    ui.logs.append(f"[入力] ターゲット(敵)選択: {command}")


def handle_command_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    """
    command input_mode の処理
    返り値: 行動が確定したら True（後段で共通後処理したい場合に使える）
    ※ここでは確定時の後処理は ctx.on_committed(ui) で完結させる設計
    """
    if not ui.command_candidates:
        # ここに来る前にセットされている想定だが保険
        member = ctx.party_members[ui.selected_member_idx]
        ui.command_candidates = ctx.get_job_commands(member)
        ui.selected_command_idx = 0

    if event.key in (pygame.K_LEFT, pygame.K_UP):
        ui.selected_command_idx = (ui.selected_command_idx - 1) % len(
            ui.command_candidates
        )
        return False

    if event.key in (pygame.K_RIGHT, pygame.K_DOWN):
        ui.selected_command_idx = (ui.selected_command_idx + 1) % len(
            ui.command_candidates
        )
        return False

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = "member"
        ctx.reset_target_flags(ui)
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    # Enter
    _play_se(getattr(ui, "se_enter", None))

    cand = ui.command_candidates[ui.selected_command_idx]
    cmd = cand.cmd
    kind = cand.kind

    # 直前の選択内容をクリア
    ui.selected_spell_name = None
    ui.selected_item_name = None
    ui.target_side = "enemy"  # type: ignore[assignment]
    ui.selected_target_idx = 0

    if kind in ("defend", "run"):
        _confirm_self_action(ui=ui, ctx=ctx, kind=kind, command=cmd)
        return True

    if kind == "magic":
        _enter_magic_menu(ui, ctx)
        return False

    if kind == "item":
        _enter_item_menu(ui, ctx)
        return False

    # special の対象なし
    if kind == "special" and cmd in SPECIAL_NO_TARGET:
        _confirm_self_action(ui=ui, ctx=ctx, kind="special", command=cmd)
        return True

    # physical/special(対象あり) → 敵ターゲットへ
    _enter_target_enemy_for_attack(ui, ctx, kind=kind, command=cmd)
    return False
