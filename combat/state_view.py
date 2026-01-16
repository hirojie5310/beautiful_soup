# ============================================================
# state_view: 状態を表示

# format_state_line	BattleActorStateを1行の状態表示テキストに整形
# ============================================================

from combat.models import BattleActorState

from combat.enums import Status


# 状態を文字列化するヘルパー
def format_state_line(name: str, state: BattleActorState) -> str:
    """
    表示例:
      ルーネス: 219/260 (SLEEP, PartialPetrify:0.33)
      Flyer: 140/190
    """
    hpmax = state.max_hp if state.max_hp is not None else state.hp

    # 状態異常名（KO/PETRIFY なども必要なら含める）
    status_names = [s.name for s in sorted(state.statuses, key=lambda x: x.name)]

    # ★ 部分石化ゲージ表示の追加
    g = getattr(state, "partial_petrify_gauge", 0.0) or 0.0
    # 完全石化済みならゲージ表示は不要（好みで残してもOK）
    if g > 0 and Status.PETRIFY not in state.statuses:
        status_names.append(f"PartialPetrify:{g:.2f}")

    # ★追加：Reflect が張られていたら表示
    if getattr(state, "reflect_charges", 0) > 0:
        status_names.append("Reflect")

    if status_names:
        return f"{name}: {state.hp}/{hpmax} ({', '.join(status_names)})"
    else:
        return f"{name}: {state.hp}/{hpmax}"
