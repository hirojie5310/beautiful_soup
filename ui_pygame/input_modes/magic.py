from __future__ import annotations
from typing import Any, Dict

import pygame

from ui_pygame.state import BattleUIState
from ui_pygame.app_context import BattleAppContext


def _play_se(se) -> None:
    if se is not None:
        se.play()


def handle_magic_keydown(
    *,
    event: pygame.event.Event,
    ui: BattleUIState,
    ctx: BattleAppContext,
) -> bool:
    if not ui.magic_candidates:
        ui.logs.append("[入力] 使用可能な魔法がありません")
        ui.input_mode = "command"
        return False

    if event.key == pygame.K_UP:
        ui.selected_magic_idx = (ui.selected_magic_idx - 1) % len(ui.magic_candidates)
        return False

    if event.key == pygame.K_DOWN:
        ui.selected_magic_idx = (ui.selected_magic_idx + 1) % len(ui.magic_candidates)
        return False

    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
        ui.input_mode = "command"
        ui.selected_target_all = False
        return False

    if event.key not in (pygame.K_RETURN, pygame.K_KP_ENTER):
        return False

    # -------------------------
    # ★残回数チェック（SEを鳴らす前）
    # -------------------------
    cand = ui.magic_candidates[ui.selected_magic_idx]
    spell_name = str(cand[0])

    # -------------------------
    # ★魔法レベルを「確実に」取る
    #   cand の例: ('Blizzard', 0, 1) → Lv=1 は cand[2]
    # -------------------------
    spell_lv = None

    # 1) cand 内の数値から「1..8」を探す（順序が違っても耐える）
    if isinstance(cand, (tuple, list)):
        for v in cand[1:]:
            try:
                iv = int(v)
            except Exception:
                continue
            if 1 <= iv <= 8:
                spell_lv = iv
                break

    # 2) フォールバック：spells_by_name から Level
    if spell_lv is None:
        spells = getattr(ui, "spells_by_name", {}) or {}
        sj = spells.get(spell_name) or {}
        try:
            iv = int(sj.get("Level"))
            if 1 <= iv <= 8:
                spell_lv = iv
        except Exception:
            pass

    # 3) さらに保険：job raw の Spells から Level
    if spell_lv is None:
        member = ctx.party_members[ui.selected_member_idx]
        for sp in member.job.raw.get("Spells", []):
            if isinstance(sp, dict) and sp.get("Name") == spell_name:
                try:
                    iv = int(sp.get("Level"))
                    if 1 <= iv <= 8:
                        spell_lv = iv
                except Exception:
                    pass
                break

    member = ctx.party_members[ui.selected_member_idx]

    # -------------------------
    # ★残回数チェック（SEを鳴らす前）
    # -------------------------
    if spell_lv is not None:
        remain = member.state.mp_pool.get(spell_lv, 0)
        if remain <= 0:
            ui.logs.append(f"[入力] {spell_name}: 残回数がありません")
            if hasattr(ui, "play_error_sound"):
                ui.play_error_sound()
            return False

    # OKならここで Enter SE
    _play_se(getattr(ui, "se_enter", None))

    ui.selected_spell_name = spell_name

    spells: Dict[str, Any] = getattr(ui, "spells_by_name", {}) or {}
    spell_json = spells.get(spell_name) or {}
    target_raw = str((spell_json.get("Target") or "")).strip().lower()

    ui.selected_target_all = False  # デフォルト単体

    if target_raw == "all enemies":
        # ★全体固定：即確定
        ui.selected_target_all = True
        member = ctx.party_members[ui.selected_member_idx]

        act = ctx.make_planned_action(
            kind="magic",
            command="Magic",
            member_idx=ui.selected_member_idx,
            target_side="enemy",
            target_index=None,  # 全体なので None 推奨
            spell_name=ui.selected_spell_name,
            target_all=ui.selected_target_all,  # ★これが重要
        )
        ui.planned_actions[ui.selected_member_idx] = act

        _play_se(getattr(ui, "se_confirm", None))
        ui.logs.append(
            f"[確定] {getattr(member, 'name', 'member')}: Magic {spell_name} → 敵全体"
        )

        ui.input_mode = "member"
        return True  # ★ committed=True → input_handler が ctx.on_committed を呼ぶ

    if target_raw == "one/all enemies":
        ui.input_mode = "aoe_choice"
        ui.selected_aoe_idx = 0
        ui.logs.append(f"[入力] {spell_name}: 単体/全体を選択")
        return False

    ui.selected_target_side_idx = 0
    ui.input_mode = "target_side"
    ui.logs.append(f"[入力] 対象(敵/味方/自分)選択: {spell_name}")
    return False
