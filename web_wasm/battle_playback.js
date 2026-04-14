const DEFAULT_ATTACK_EFFECT_SHEET_NAME = "ef_slash_frames.png";

export function applyEventToPlaybackStatus(
  playbackStatus,
  event,
  { attackEffectSheetName = DEFAULT_ATTACK_EFFECT_SHEET_NAME } = {},
) {
  if (!playbackStatus || typeof playbackStatus !== "object" || !event || typeof event !== "object") {
    return null;
  }
  const targetSide = String(event?.target_side || "");
  const collection = targetSide === "enemy" ? playbackStatus.enemies : playbackStatus.party;
  if (!Array.isArray(collection)) return null;
  const targetIndex = Number(event?.target_index ?? -1);
  if (targetIndex < 0 || targetIndex >= collection.length) return null;
  const target = collection[targetIndex];
  if (!target || typeof target !== "object") return null;

  if (event.type === "damage") {
    const amount = Number(event?.value ?? 0);
    // value is the actual HP delta; display_value is the raw damage number
    // shown in logs so overkill popups can match the log text.
    const displayValue = Number(event?.display_value ?? amount);
    const currentHp = Number(target?.hp ?? 0);
    const oldHp = Number(event?.old_hp ?? currentHp);
    const nextHp = Math.max(0, Number(event?.new_hp ?? (oldHp - amount)));
    target.hp = nextHp;
    target.out_of_battle = nextHp <= 0 ? true : Boolean(target.out_of_battle);
    if (target?.status && typeof target.status === "object") {
      target.status.hp = nextHp;
    }
    return {
      side: targetSide,
      index: targetIndex,
      effect: amount > 0
        ? {
          kind: "slash",
          sheetName: attackEffectSheetName,
        }
        : null,
      popup: {
        kind: amount > 0 ? "damage" : "miss",
        value: displayValue,
      },
    };
  }

  if (event.type === "status") {
    const existing = Array.isArray(target.status_icons) ? target.status_icons : [];
    const additions = Array.isArray(event?.names)
      ? event.names
        .map((name) => String(name || "").trim().toLowerCase().replace(/^status\./, ""))
        .filter(Boolean)
      : [];
    target.status_icons = Array.from(new Set([...existing, ...additions]));
  }
  return null;
}
