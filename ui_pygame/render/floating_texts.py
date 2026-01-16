from typing import Sequence, cast

from combat.models import BattleEvent as CombatBattleEvent

from ui_pygame.state import BattleUIState, FloatingText
from ui_pygame.ui_events import UiEvent, AudioEvent


# フローティングテキストの描画
def draw_floating_texts(screen, font, ui: BattleUIState):
    if not ui.enemy_sprite_rects:
        return

    # 更新 & 生存
    alive = []
    for ft in ui.floating_texts:
        if ft.enemy_index < 0 or ft.enemy_index >= len(ui.enemy_sprite_rects):
            continue
        if ft.update(ui.dt_ms):  # ui.dt_ms を毎フレーム入れる運用
            alive.append(ft)
    ui.floating_texts = alive

    for ft in ui.floating_texts:
        r = ui.enemy_sprite_rects[ft.enemy_index]
        a = ft.alpha()

        surf = font.render(ft.text, True, (255, 255, 255))
        surf = surf.convert_alpha()
        surf.set_alpha(a)

        x = r.centerx - surf.get_width() // 2
        y = r.top - 18 + int(ft.y_offset)
        screen.blit(surf, (x, y))


# events → FloatingText に追加する関数
def apply_battle_events_to_ui(ui, events: Sequence[UiEvent]):
    for ev in events:
        if isinstance(ev, AudioEvent):
            continue  # 音は別途 AudioManager が処理

        # ここで ev は CombatBattleEvent のはず（TypedDict union）
        combat_ev = cast(CombatBattleEvent, ev)

        if combat_ev["type"] == "damage":
            idx = combat_ev["enemy_index"]
            val = combat_ev["value"]
            if val > 0:
                ui.floating_texts.append(FloatingText(enemy_index=idx, text=str(val)))

        elif combat_ev["type"] == "status":
            idx = combat_ev["enemy_index"]
            names = combat_ev["names"]
            if names:
                ui.floating_texts.append(
                    FloatingText(enemy_index=idx, text=" ".join(names))
                )
