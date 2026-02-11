from typing import Sequence, cast

from combat.models import BattleEvent as CombatBattleEvent

from ui_pygame.state import BattleUIState, FloatingText
from ui_pygame.ui_events import UiEvent, AudioEvent


def _append_floating_text_from_combat_event(
    ui: BattleUIState, combat_ev: CombatBattleEvent
):
    if combat_ev["type"] == "damage":
        idx = combat_ev["target_index"]
        side = combat_ev.get("target_side", "enemy")
        val = combat_ev["value"]
        if val > 0:
            ui.floating_texts.append(
                FloatingText(target_side=str(side), target_index=idx, text=str(val))
            )
        return

    if combat_ev["type"] == "status":
        idx = combat_ev["target_index"]
        side = combat_ev.get("target_side", "enemy")
        names = combat_ev["names"]
        if names:
            name_texts = [str(getattr(n, "value", n)) for n in names]
            ui.floating_texts.append(
                FloatingText(
                    target_side=str(side),
                    target_index=idx,
                    text=" ".join(name_texts),
                )
            )


# フローティングテキストの描画
def draw_floating_texts(screen, font, ui: BattleUIState):
    # 更新 & 生存
    alive = []
    for ft in ui.floating_texts:
        rects = (
            ui.party_sprite_rects
            if getattr(ft, "target_side", "enemy") == "char"
            else ui.enemy_sprite_rects
        )
        if not rects:
            continue
        if ft.target_index < 0 or ft.target_index >= len(rects):
            continue
        if ft.update(ui.dt_ms):  # ui.dt_ms を毎フレーム入れる運用
            alive.append(ft)
    ui.floating_texts = alive

    for ft in ui.floating_texts:
        rects = (
            ui.party_sprite_rects
            if getattr(ft, "target_side", "enemy") == "char"
            else ui.enemy_sprite_rects
        )
        if not rects or ft.target_index < 0 or ft.target_index >= len(rects):
            continue

        r = rects[ft.target_index]
        a = ft.alpha()

        color = (
            (255, 190, 190)
            if getattr(ft, "target_side", "enemy") == "char"
            else (255, 255, 255)
        )
        surf = font.render(ft.text, True, color)
        surf = surf.convert_alpha()
        surf.set_alpha(a)

        x = r.centerx - surf.get_width() // 2
        y = r.top - 18 + int(ft.y_offset)
        screen.blit(surf, (x, y))


# events → FloatingText に追加する関数
def apply_battle_events_to_ui(ui: BattleUIState, events: Sequence[UiEvent]):
    pending_events = list(getattr(ui, "pending_floating_events", []))
    active_actor = getattr(ui, "party_attack_anim_active", None)

    def should_hold_for_actor_sync(combat_ev: CombatBattleEvent) -> bool:
        actor_side = combat_ev.get("actor_side")
        actor_index = combat_ev.get("actor_index")
        if actor_index is None:
            return False

        # アクター未アクティブ時は「これから表示予定の行動アニメ」がある場合のみ保留する。
        # （1ターン目のようにアニメ処理完了後にイベントが来たケースは即表示する）
        if active_actor is None:
            return bool(getattr(ui, "party_attack_anim_queue", []))

        active_side, active_idx = active_actor
        return not (
            str(active_side) == str(actor_side) and int(active_idx) == int(actor_index)
        )

    for ev in events:
        if isinstance(ev, AudioEvent):
            continue  # 音は別途 AudioManager が処理

        combat_ev = cast(CombatBattleEvent, ev)
        if should_hold_for_actor_sync(combat_ev):
            pending_events.append(ev)
            continue

        _append_floating_text_from_combat_event(ui, combat_ev)

    if pending_events:
        active_actor = getattr(ui, "party_attack_anim_active", None)
        still_pending: list[UiEvent] = []
        for pending_ev in pending_events:
            combat_ev = cast(CombatBattleEvent, pending_ev)
            if should_hold_for_actor_sync(combat_ev):
                still_pending.append(pending_ev)
                continue
            _append_floating_text_from_combat_event(ui, combat_ev)
        ui.pending_floating_events = still_pending
    else:
        ui.pending_floating_events = []
