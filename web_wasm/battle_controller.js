const COMMAND_LABELS = {
  Fight: "たたかう",
  Defend: "ぼうぎょ",
  Run: "にげる",
  Flee: "にげる",
  Item: "アイテム",
  Magic: "まほう",
  Cheer: "おうえん",
};

export function isOutOfBattleMember(member) {
  if (!member || typeof member !== "object") return true;
  if (member.out_of_battle === true) return true;
  const hp = Number(member.hp ?? 0);
  if (hp <= 0) return true;
  const icons = Array.isArray(member.status_icons) ? member.status_icons : [];
  const normalized = icons.map((icon) => String(icon || "").toLowerCase());
  return (
    normalized.includes("ko")
    || normalized.includes("petrify")
    || normalized.includes("petrification")
  );
}

export function isOutOfBattleEnemy(enemy) {
  if (!enemy || typeof enemy !== "object") return true;
  if (enemy.out_of_battle === true) return true;
  const hp = Number(enemy.hp ?? 0);
  if (hp <= 0) return true;
  const icons = Array.isArray(enemy.status_icons) ? enemy.status_icons : [];
  const normalized = icons.map((icon) => String(icon || "").toLowerCase());
  return (
    normalized.includes("ko")
    || normalized.includes("petrify")
    || normalized.includes("petrification")
  );
}

export function selectedEnemySafeIndex({ sessionStatus, selectedEnemyIndex }) {
  const enemies = Array.isArray(sessionStatus?.enemies) ? sessionStatus.enemies : [];
  if (!enemies.length) return 0;
  const aliveIndices = enemies
    .map((enemy, idx) => ({ enemy, idx }))
    .filter(({ enemy }) => !isOutOfBattleEnemy(enemy))
    .map(({ idx }) => idx);
  if (!aliveIndices.length) return 0;
  if (aliveIndices.includes(selectedEnemyIndex)) return selectedEnemyIndex;
  return aliveIndices[0];
}

export function buildActionFromCommand(def, { currentMemberIndex, sessionStatus, selectedEnemyIndex }) {
  const enemyIndex = selectedEnemySafeIndex({ sessionStatus, selectedEnemyIndex });
  if (def.targetSide === "self") {
    return {
      kind: def.kind,
      command: def.command,
      target_side: "self",
      target_index: currentMemberIndex,
      target_all: false,
    };
  }
  if (def.targetSide === "ally") {
    return {
      kind: def.kind,
      command: def.command,
      target_side: "ally",
      target_index: currentMemberIndex,
      target_all: false,
    };
  }
  return {
    kind: def.kind,
    command: def.command,
    target_side: "enemy",
    target_index: enemyIndex,
    target_all: false,
  };
}

export function targetSideForCommand(def) {
  if (def?.kind === "defend" || def?.kind === "run") {
    return "self";
  }
  if (def?.kind === "item" || def?.kind === "magic") {
    return "enemy";
  }
  if (def?.command === "Cheer") {
    return "ally";
  }
  return "enemy";
}

export function commandLabel(command) {
  const key = String(command || "").trim();
  return COMMAND_LABELS[key] || key || "(unknown)";
}
