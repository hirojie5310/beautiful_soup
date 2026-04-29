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

export function buildMagicIntent(cand, { sessionStatus, currentMemberIndex }) {
  const spellName = String(cand?.name || "");
  if (!spellName) return null;
  const spellMeta = sessionStatus?.magic_spell_meta?.[spellName] || {};
  const mode = String(spellMeta?.target_mode || "enemy_only");
  const targetNorm = String(spellMeta?.target_norm || "");
  const canSelectAll = Boolean(spellMeta?.can_select_all);

  if (targetNorm === "all enemies") {
    return {
      type: "action",
      action: {
        kind: "magic",
        command: "Magic",
        spell_name: spellName,
        target_side: "enemy",
        target_index: 0,
        target_all: true,
      },
    };
  }
  if (targetNorm === "all allies") {
    return {
      type: "action",
      action: {
        kind: "magic",
        command: "Magic",
        spell_name: spellName,
        target_side: "ally",
        target_index: currentMemberIndex,
        target_all: true,
      },
    };
  }
  if (mode === "ally_only") {
    return {
      type: "draft",
      inputMode: "pick_target",
      draft: {
        kind: "magic",
        command: "Magic",
        spell_name: spellName,
        target_side: "ally",
        can_select_all: canSelectAll,
        target_norm: targetNorm,
        requires_side_choice: false,
      },
    };
  }
  if (mode === "any") {
    return {
      type: "draft",
      inputMode: "pick_side",
      draft: {
        kind: "magic",
        command: "Magic",
        spell_name: spellName,
        can_select_all: canSelectAll,
        target_norm: targetNorm,
        target_mode: mode,
        requires_side_choice: true,
      },
    };
  }
  return {
    type: "draft",
    inputMode: "pick_target",
    draft: {
      kind: "magic",
      command: "Magic",
      spell_name: spellName,
      target_side: "enemy",
      can_select_all: canSelectAll,
      target_norm: targetNorm,
      requires_side_choice: false,
    },
  };
}

export function buildItemIntent(cand, { sessionStatus, currentMemberIndex }) {
  const itemName = String(cand?.name || "");
  if (!itemName) return null;
  const itemMeta = sessionStatus?.item_meta?.[itemName] || {};
  const targetSide = itemMeta?.target_side;
  const canSelectAll = Boolean(itemMeta?.can_select_all);
  const autoAllTarget = Boolean(itemMeta?.auto_all_target);

  if (autoAllTarget && (targetSide === "ally" || targetSide === "enemy")) {
    return {
      type: "action",
      action: {
        kind: "item",
        command: "Item",
        item_name: itemName,
        target_side: targetSide,
        target_index: targetSide === "ally" ? currentMemberIndex : 0,
        target_all: true,
      },
    };
  }

  const draft = {
    kind: "item",
    command: "Item",
    item_name: itemName,
    can_select_all: canSelectAll,
    requires_side_choice: !(targetSide === "ally" || targetSide === "enemy"),
  };
  if (targetSide === "ally" || targetSide === "enemy") {
    draft.target_side = targetSide;
  }
  return {
    type: "draft",
    inputMode: targetSide === "ally" || targetSide === "enemy" ? "pick_target" : "pick_side",
    draft,
  };
}
