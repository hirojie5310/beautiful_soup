const DEFAULT_ATTACK_EFFECT_SHEET_NAME = "ef_slash_frames.png";

function buildPlaybackPresentation({ side, index, kind, value = 0, displayValue = value, text = "", statusCategory = "", attackEffectSheetName = DEFAULT_ATTACK_EFFECT_SHEET_NAME }) {
  return {
    side,
    index,
    effect: kind === "damage" && value > 0
      ? {
        kind: "slash",
        sheetName: attackEffectSheetName,
      }
      : null,
    popup: kind === "status"
      ? {
        kind,
        text,
        statusCategory,
      }
      : {
        kind,
        value: kind === "damage" ? displayValue : value,
      },
  };
}

export function buildPlaybackStatusUpdateFromEvent(
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
    return {
      target: {
        side: targetSide,
        index: targetIndex,
      },
      patch: {
        hp: nextHp,
        out_of_battle: nextHp <= 0 ? true : Boolean(target.out_of_battle),
        status_hp: target?.status && typeof target.status === "object" ? nextHp : null,
      },
      presentation: buildPlaybackPresentation({
        side: targetSide,
        index: targetIndex,
        kind: amount > 0 ? "damage" : "miss",
        value: amount,
        displayValue,
        attackEffectSheetName,
      }),
    };
  }

  if (event.type === "status") {
    const existing = Array.isArray(target.status_icons) ? target.status_icons : [];
    const additions = Array.isArray(event?.names)
      ? event.names
        .map((name) => String(name || "").trim().toLowerCase().replace(/^status\./, ""))
        .filter(Boolean)
      : [];
    return {
      target: {
        side: targetSide,
        index: targetIndex,
      },
      patch: {
        status_icons: Array.from(new Set([...existing, ...additions])),
      },
      presentation: null,
    };
  }
  return null;
}

export function applyEventToPlaybackStatus(
  playbackStatus,
  event,
  { attackEffectSheetName = DEFAULT_ATTACK_EFFECT_SHEET_NAME } = {},
) {
  const update = buildPlaybackStatusUpdateFromEvent(
    playbackStatus,
    event,
    { attackEffectSheetName },
  );
  if (!update) return null;
  const side = String(update?.target?.side || "");
  const index = Number(update?.target?.index ?? -1);
  const collection = side === "enemy" ? playbackStatus.enemies : playbackStatus.party;
  const target = Array.isArray(collection) && index >= 0 && index < collection.length
    ? collection[index]
    : null;
  if (!target || typeof target !== "object") return null;
  if (Object.prototype.hasOwnProperty.call(update.patch || {}, "hp")) {
    target.hp = Number(update.patch.hp ?? target.hp ?? 0);
  }
  if (Object.prototype.hasOwnProperty.call(update.patch || {}, "out_of_battle")) {
    target.out_of_battle = Boolean(update.patch.out_of_battle);
  }
  if (Array.isArray(update.patch?.status_icons)) {
    target.status_icons = update.patch.status_icons;
  }
  if (target?.status && typeof target.status === "object" && update.patch?.status_hp != null) {
    target.status.hp = Number(update.patch.status_hp);
  }
  return update.presentation;
}

export function applyNamedPopupOverrides(activePopups, effects) {
  const nextPopups = activePopups && typeof activePopups === "object"
    ? activePopups
    : {};
  const rows = Array.isArray(effects) ? effects : [];
  rows.forEach((effect) => {
    const side = String(effect?.side || "");
    const index = Number(effect?.index ?? -1);
    if (!side || index < 0) return;
    const key = `${side}:${index}`;
    const current = nextPopups[key];
    if (!current || typeof current !== "object") return;
    const nextKind = String(effect?.kind || current.kind || "damage");
    // Event-derived popups already know the actual HP delta. Do not downgrade a
    // confirmed damage/heal popup into MISS based only on log text parsing.
    if (
      nextKind === "miss"
      && ["damage", "heal", "status"].includes(String(current.kind || ""))
    ) {
      return;
    }
    nextPopups[key] = {
      ...current,
      kind: nextKind,
      value: Number(effect?.value ?? current.value ?? 0),
      text: String(effect?.text ?? current.text ?? ""),
      statusCategory: String(effect?.statusCategory ?? current.statusCategory ?? ""),
    };
  });
  return nextPopups;
}

export function buildLogBlocks(logs) {
  const lines = Array.isArray(logs) ? logs : [];
  const blocks = [];
  let current = [];
  let type = "system";
  const flush = () => {
    if (!current.length) return;
    blocks.push({ type, lines: current });
    current = [];
  };
  lines.forEach((lineRaw) => {
    const line = String(lineRaw ?? "");
    const normalized = line.replace(/^[\s\u3000]+/, "");
    if (/^[▶◆]\s/.test(normalized)) {
      flush();
      type = "action";
      current.push(line);
      return;
    }
    if (normalized.startsWith("=== Battle Rewards ===")) {
      flush();
      type = "reward";
      current.push(line);
      return;
    }
    current.push(line);
  });
  flush();
  return blocks;
}

export function alignEventBlocksToLogBlocks(blocks, eventBlocks) {
  const source = Array.isArray(eventBlocks) ? eventBlocks : [];
  let actionIndex = 0;
  return blocks.map((block) => {
    if (block?.type !== "action") return [];
    const eventsForBlock = Array.isArray(source[actionIndex]) ? source[actionIndex] : [];
    actionIndex += 1;
    return eventsForBlock;
  });
}

export function buildRewardLogBlock(payload) {
  if (!payload?.victory_rewards) {
    return null;
  }
  const rewards = payload.victory_rewards;
  const gilBefore = Number(rewards?.gil_before ?? 0);
  const gilAfter = Number(rewards?.gil_after ?? gilBefore + Number(rewards?.gained_gil ?? 0));
  const cpBefore = Number(rewards?.cp_before ?? 0);
  const cpAfter = Number(rewards?.cp_after ?? cpBefore + Number(rewards?.gained_cp ?? 0));
  const drops = Array.isArray(rewards?.dropped_item) && rewards.dropped_item.length
    ? rewards.dropped_item.join(", ")
    : "(none)";
  return {
    type: "reward",
    lines: [
      "=== Battle Rewards ===",
      `EXP +${Number(rewards?.gained_exp ?? 0)}`,
      `Gil +${Number(rewards?.gained_gil ?? 0)} (${gilBefore} -> ${gilAfter})`,
      `CP +${Number(rewards?.gained_cp ?? 0)} (${cpBefore} -> ${cpAfter})`,
      `Drop: ${drops}`,
    ],
  };
}

export function normalizeVictoryRewards(payload, beforeResources, afterResources) {
  if (!payload?.victory_rewards) return payload;
  const rewards = payload.victory_rewards;
  const gilBefore = Number(rewards?.gil_before ?? beforeResources?.gil ?? 0);
  const cpBefore = Number(rewards?.cp_before ?? beforeResources?.cp ?? 0);
  const gilAfter = Number(rewards?.gil_after ?? afterResources?.gil ?? (gilBefore + Number(rewards?.gained_gil ?? 0)));
  const cpAfter = Number(rewards?.cp_after ?? afterResources?.cp ?? (cpBefore + Number(rewards?.gained_cp ?? 0)));
  rewards.gil_before = gilBefore;
  rewards.gil_after = gilAfter;
  rewards.cp_before = cpBefore;
  rewards.cp_after = cpAfter;
  return payload;
}

export function injectResourceDiffsIntoRewardLogs(logs, rewards) {
  if (!Array.isArray(logs) || !rewards) return Array.isArray(logs) ? logs : [];
  const gilLine = `Gil +${Number(rewards?.gained_gil ?? 0)} (${Number(rewards?.gil_before ?? 0)} -> ${Number(rewards?.gil_after ?? 0)})`;
  const cpLine = `CP +${Number(rewards?.gained_cp ?? 0)} (${Number(rewards?.cp_before ?? 0)} -> ${Number(rewards?.cp_after ?? 0)})`;
  let inRewardBlock = false;
  let foundRewardHeader = false;
  return logs.map((lineRaw) => {
    const line = String(lineRaw ?? "");
    const normalized = line.replace(/^[\s\u3000]+/, "");
    if (normalized.startsWith("=== Battle Rewards ===")) {
      inRewardBlock = true;
      foundRewardHeader = true;
      return line;
    }
    if (inRewardBlock && normalized.startsWith("Gil +")) {
      return gilLine;
    }
    if (inRewardBlock && normalized.startsWith("CP +")) {
      return cpLine;
    }
    if (inRewardBlock && /^[▶◆]\s/.test(normalized)) {
      inRewardBlock = false;
    }
    return line;
  }).concat(foundRewardHeader ? [] : [
    "=== Battle Rewards ===",
    `EXP +${Number(rewards?.gained_exp ?? 0)}`,
    gilLine,
    cpLine,
    `Drop: ${Array.isArray(rewards?.dropped_item) && rewards.dropped_item.length ? rewards.dropped_item.join(", ") : "(none)"}`,
  ]);
}

function parseActionHeaderMeta(line, actorOccurrenceMap, sessionStatus) {
  const header = String(line || "").trim();
  let match = header.match(/^▶\s(.+?)\sの行動/);
  if (match) {
    const actorName = String(match[1] || "");
    const occurrenceKey = `char:${actorName}`;
    const occurrence = actorOccurrenceMap.get(occurrenceKey) || 0;
    actorOccurrenceMap.set(occurrenceKey, occurrence + 1);
    const party = Array.isArray(sessionStatus?.party) ? sessionStatus.party : [];
    const candidateIndexes = party
      .map((member, index) => ({ name: String(member?.name || ""), index }))
      .filter((row) => row.name === actorName)
      .map((row) => row.index);
    return {
      actorSide: "char",
      actorIndex: candidateIndexes[occurrence] ?? candidateIndexes[0] ?? null,
    };
  }

  match = header.match(/^◆\s(.+?)\sの行動/);
  if (match) {
    const actorName = String(match[1] || "");
    const occurrenceKey = `enemy:${actorName}`;
    const occurrence = actorOccurrenceMap.get(occurrenceKey) || 0;
    actorOccurrenceMap.set(occurrenceKey, occurrence + 1);
    const enemies = Array.isArray(sessionStatus?.enemies) ? sessionStatus.enemies : [];
    const candidateIndexes = enemies
      .map((enemy, index) => ({ name: String(enemy?.name || ""), index }))
      .filter((row) => row.name === actorName)
      .map((row) => row.index);
    return {
      actorSide: "enemy",
      actorIndex: candidateIndexes[occurrence] ?? candidateIndexes[0] ?? null,
    };
  }

  return { actorSide: null, actorIndex: null };
}

export function buildPlaybackEventsByBlock(blocks, events, sessionStatus) {
  const actorOccurrenceMap = new Map();
  const pendingEvents = Array.isArray(events) ? [...events] : [];
  let cursor = 0;
  return blocks.map((block) => {
    if (block.type !== "action") return [];
    const firstLine = Array.isArray(block.lines) ? block.lines[0] : "";
    const { actorSide, actorIndex } = parseActionHeaderMeta(firstLine, actorOccurrenceMap, sessionStatus);
    if (actorSide == null || actorIndex == null) {
      return [];
    }
    const blockEvents = [];
    let probe = cursor;
    while (probe < pendingEvents.length) {
      const nextEvent = pendingEvents[probe];
      const nextActorSide = String(nextEvent?.actor_side || "");
      const nextActorIndex = Number(nextEvent?.actor_index ?? -1);
      if (!nextActorSide || Number.isNaN(nextActorIndex) || nextActorIndex < 0) {
        probe += 1;
        continue;
      }
      if (nextActorSide !== actorSide || nextActorIndex !== Number(actorIndex)) {
        break;
      }
      blockEvents.push(nextEvent);
      probe += 1;
    }
    if (blockEvents.length > 0) {
      cursor = probe;
    }
    return blockEvents;
  });
}

function resolveNamedTarget(name, playbackStatus, preferredSide, usageMap) {
  const targetName = String(name || "").trim();
  if (!targetName || !playbackStatus || typeof playbackStatus !== "object") {
    return null;
  }
  const collections = preferredSide === "enemy"
    ? [
      ["enemy", Array.isArray(playbackStatus.enemies) ? playbackStatus.enemies : []],
      ["char", Array.isArray(playbackStatus.party) ? playbackStatus.party : []],
    ]
    : [
      ["char", Array.isArray(playbackStatus.party) ? playbackStatus.party : []],
      ["enemy", Array.isArray(playbackStatus.enemies) ? playbackStatus.enemies : []],
    ];

  for (const [side, rows] of collections) {
    const key = `${side}:${targetName}`;
    const occurrence = usageMap.get(key) || 0;
    const matchedIndexes = rows
      .map((row, index) => ({ name: String(row?.name || "").trim(), index }))
      .filter((row) => row.name === targetName)
      .map((row) => row.index);
    if (matchedIndexes.length > occurrence) {
      usageMap.set(key, occurrence + 1);
      return { side, index: matchedIndexes[occurrence] };
    }
  }
  return null;
}

export function buildNamedCombatEffects(block, playbackStatus) {
  const firstLine = Array.isArray(block?.lines) ? String(block.lines[0] || "") : "";
  const { actorSide } = parseActionHeaderMeta(firstLine, new Map(), playbackStatus);
  const preferredSide = actorSide === "char" ? "enemy" : "char";
  const usageMap = new Map();
  const effects = [];

  (Array.isArray(block?.lines) ? block.lines : []).forEach((lineRaw) => {
    const line = String(lineRaw || "").trim();
    let match = line.match(/(?:^|[！。]\s*)([^！。]+?)に(\d+)のダメージ/);
    if (!match) match = line.match(/(?:^|[！。]\s*)([^！。]+?)は(\d+)のダメージを受けた/);
    if (!match) match = line.match(/(?:^|[！。]\s*)([^！。]+?)は(\d+)のダメージ/);
    if (match) {
      const target = resolveNamedTarget(match[1], playbackStatus, preferredSide, usageMap);
      if (target) {
        effects.push({ ...target, kind: "damage", value: Number(match[2]) });
      }
      return;
    }

    match = line.match(/(?:^|[！。]\s*)([^！。]+?)のHPが(\d+)回復/);
    if (!match) match = line.match(/(?:^|[！。]\s*)([^！。]+?)はHPを(\d+)回復した/);
    if (!match) match = line.match(/(?:^|[！。]\s*)([^！。]+?)はHPが(\d+)回復/);
    if (match) {
      const target = resolveNamedTarget(match[1], playbackStatus, preferredSide, usageMap);
      if (target) {
        effects.push({ ...target, kind: "heal", value: Number(match[2]) });
      }
      return;
    }

    match = line.match(/(?:^|[！。]\s*)([^！。]+?)は《?([^》！。]+?)》?状態になった/);
    if (!match) match = line.match(/(?:^|[！。]\s*)([^！。]+?)は([^！。]+?)状態になった/);
    if (match) {
      const target = resolveNamedTarget(match[1], playbackStatus, preferredSide, usageMap);
      if (target) {
        effects.push({
          ...target,
          kind: "status",
          text: String(match[2] || "").trim(),
          statusCategory: "inflict",
        });
      }
      return;
    }

    match = line.match(/(?:^|[！。]\s*)([^！。]+?)の([^！。]+?)が解けた/);
    if (match) {
      const target = resolveNamedTarget(match[1], playbackStatus, preferredSide, usageMap);
      if (target) {
        effects.push({
          ...target,
          kind: "status",
          text: `${String(match[2] || "").trim()}解除`,
          statusCategory: "cure",
        });
      }
      return;
    }

    match = line.match(/しかし([^！。]+?)には効かなかった/);
    if (match) {
      const target = resolveNamedTarget(match[1], playbackStatus, preferredSide, usageMap);
      if (target) {
        effects.push({ ...target, kind: "miss", value: 0 });
      }
    }
  });

  return effects;
}

export function buildPlaybackStatusUpdateFromNamedEffect(playbackStatus, effect, { attackEffectSheetName = DEFAULT_ATTACK_EFFECT_SHEET_NAME } = {}) {
  if (!effect || !playbackStatus || typeof playbackStatus !== "object") return null;
  const side = String(effect.side || "");
  const index = Number(effect.index ?? -1);
  const value = Number(effect.value ?? 0);
  const kind = String(effect.kind || "");
  const collection = side === "enemy" ? playbackStatus.enemies : playbackStatus.party;
  if (!Array.isArray(collection) || index < 0 || index >= collection.length) return null;
  const target = collection[index];
  if (!target || typeof target !== "object") return null;

  let patch = {};
  if (kind === "damage") {
    const currentHp = Number(target?.hp ?? 0);
    const nextHp = Math.max(0, currentHp - value);
    patch = {
      hp: nextHp,
      out_of_battle: nextHp <= 0 ? true : Boolean(target.out_of_battle),
      status_hp: target?.status && typeof target.status === "object" ? nextHp : null,
    };
  } else if (kind === "heal") {
    const currentHp = Number(target?.hp ?? 0);
    const maxHp = Number(target?.max_hp ?? currentHp);
    const nextHp = Math.min(maxHp, currentHp + value);
    patch = {
      hp: nextHp,
      out_of_battle: false,
      status_hp: target?.status && typeof target.status === "object" ? nextHp : null,
    };
  }

  return {
    target: { side, index },
    patch,
    presentation: buildPlaybackPresentation({
      side,
      index,
      kind,
      value,
      text: String(effect?.text || ""),
      statusCategory: String(effect?.statusCategory || "inflict"),
      attackEffectSheetName,
    }),
  };
}

export function applyNamedCombatEffect(playbackStatus, effect, { attackEffectSheetName = DEFAULT_ATTACK_EFFECT_SHEET_NAME } = {}) {
  const update = buildPlaybackStatusUpdateFromNamedEffect(
    playbackStatus,
    effect,
    { attackEffectSheetName },
  );
  if (!update) return null;
  const side = String(update?.target?.side || "");
  const index = Number(update?.target?.index ?? -1);
  const collection = side === "enemy" ? playbackStatus.enemies : playbackStatus.party;
  const target = Array.isArray(collection) && index >= 0 && index < collection.length
    ? collection[index]
    : null;
  if (!target || typeof target !== "object") return null;
  if (Object.prototype.hasOwnProperty.call(update.patch || {}, "hp")) {
    target.hp = Number(update.patch.hp ?? target.hp ?? 0);
  }
  if (Object.prototype.hasOwnProperty.call(update.patch || {}, "out_of_battle")) {
    target.out_of_battle = Boolean(update.patch.out_of_battle);
  }
  if (target?.status && typeof target.status === "object" && update.patch?.status_hp != null) {
    target.status.hp = Number(update.patch.status_hp);
  }
  return update.presentation;
}
