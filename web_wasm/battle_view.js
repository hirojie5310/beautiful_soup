export function setBattleLogExpandedState({ expanded, battleLogFrame, battleLogToggleBtn }) {
  const isExpanded = Boolean(expanded);
  if (battleLogFrame) {
    battleLogFrame.classList.toggle("open", isExpanded);
  }
  if (battleLogToggleBtn) {
    battleLogToggleBtn.textContent = isExpanded ? "ログを閉じる" : "ログを開く";
    battleLogToggleBtn.setAttribute("aria-expanded", isExpanded ? "true" : "false");
  }
  return isExpanded;
}

export function setCommandLogLayoutState({
  showCommand,
  commandFrame,
  battleLogFrame,
  battleLogToggleBtn,
}) {
  if (commandFrame) {
    commandFrame.style.display = showCommand ? "" : "none";
  }
  return setBattleLogExpandedState({
    expanded: !showCommand,
    battleLogFrame,
    battleLogToggleBtn,
  });
}

export function renderPlannedActionsText(plannedActionsView, pendingActions) {
  if (!plannedActionsView) return;
  plannedActionsView.textContent = Array.isArray(pendingActions) && pendingActions.length
    ? JSON.stringify(pendingActions, null, 2)
    : "(none)";
}

export function renderRewardPanel(rewardPanel, payload) {
  if (!rewardPanel) return;
  if (payload?.victory_rewards) {
    const rewards = payload.victory_rewards;
    rewardPanel.classList.add("open");
    rewardPanel.innerHTML = `
      <strong>Victory Rewards</strong><br>
      EXP +${Number(rewards?.gained_exp ?? 0)} / Gil +${Number(rewards?.gained_gil ?? 0)} / CP +${Number(rewards?.gained_cp ?? 0)}<br>
      Drop: ${Array.isArray(rewards?.dropped_item) && rewards.dropped_item.length ? rewards.dropped_item.join(", ") : "(none)"}
    `;
    return;
  }
  rewardPanel.classList.remove("open");
  rewardPanel.textContent = "";
}

export function renderBattleStatusLine({
  statusLine,
  sessionStatus,
  currentMemberIndex,
  selectedEnemyIndex,
  inputMode,
  pendingActionDraft,
  battleFinished,
  selectedEnemySafeIndex,
  committedActionCount,
  requiredActionCount,
}) {
  if (!statusLine) return;
  const party = Array.isArray(sessionStatus?.party) ? sessionStatus.party : [];
  const enemies = Array.isArray(sessionStatus?.enemies) ? sessionStatus.enemies : [];
  if (battleFinished) {
    statusLine.textContent = "戦闘終了。Bootし直すと再開始できます。";
    return;
  }
  const actor = party[currentMemberIndex];
  const safeEnemyIndex = typeof selectedEnemySafeIndex === "function"
    ? selectedEnemySafeIndex({ sessionStatus, selectedEnemyIndex })
    : selectedEnemyIndex;
  const target = enemies[safeEnemyIndex];
  if (!actor) {
    statusLine.textContent = "操作可能なメンバーがいません。";
    return;
  }
  if (inputMode === "pick_magic") {
    statusLine.textContent = `行動入力: ${actor.name} / 魔法を選択してください`;
    return;
  }
  if (inputMode === "pick_item") {
    statusLine.textContent = `行動入力: ${actor.name} / アイテムを選択してください`;
    return;
  }
  if (inputMode === "pick_side") {
    statusLine.textContent = `行動入力: ${actor.name} / 対象サイドを選択してください`;
    return;
  }
  if (inputMode === "pick_target") {
    const sideLabel = pendingActionDraft?.target_side === "ally" ? "味方" : "敵";
    statusLine.textContent = `行動入力: ${actor.name} / ${sideLabel}対象を選択してください`;
    return;
  }
  const committed = typeof committedActionCount === "function" ? committedActionCount() : 0;
  const required = typeof requiredActionCount === "function" ? requiredActionCount() : 0;
  statusLine.textContent = `行動入力: ${actor.name} / 対象: ${target?.name ?? "(なし)"} / 入力済み ${committed}/${required}`;
}

function createSheetButton(label, { disabled = false, dataset = {} } = {}) {
  const button = document.createElement("button");
  button.className = "btn";
  button.type = "button";
  button.disabled = disabled;
  button.textContent = String(label || "");
  Object.entries(dataset).forEach(([key, value]) => {
    if (value == null) return;
    button.dataset[key] = String(value);
  });
  return button;
}

function createActionSheetGrid() {
  const grid = document.createElement("div");
  grid.className = "action-sheet-grid";
  return grid;
}

function createActionSheetSection(label, { magicLevel = false } = {}) {
  const section = document.createElement("section");
  section.className = "action-sheet-section";
  if (label) {
    const heading = document.createElement("div");
    heading.className = "action-sheet-section-label";
    heading.textContent = label;
    section.appendChild(heading);
  }
  const grid = createActionSheetGrid();
  if (magicLevel) {
    grid.classList.add("magic-level-grid");
  }
  section.appendChild(grid);
  return { section, grid };
}

export function setActionSheetOpenState({ open, actionSheet, actionSheetBackdrop, actionSheetBody }) {
  const isOpen = Boolean(open);
  if (actionSheet) {
    actionSheet.classList.toggle("open", isOpen);
    actionSheet.setAttribute("aria-hidden", isOpen ? "false" : "true");
  }
  if (actionSheetBackdrop) {
    actionSheetBackdrop.classList.toggle("open", isOpen);
  }
  if (!isOpen && actionSheetBody) {
    actionSheetBody.innerHTML = "";
  }
}

export function renderBattleActionSheet({
  mode,
  actionSheetTitle,
  actionSheetBody,
  actorName,
  magicCandidates,
  itemCandidates,
  pendingActionDraft,
  sessionStatus,
  canAct,
  isOutOfBattleEnemy,
}) {
  if (!actionSheetBody || !actionSheetTitle) return;
  const safeActorName = String(actorName || "");
  actionSheetBody.innerHTML = "";

  if (mode === "pick_magic") {
    actionSheetTitle.textContent = safeActorName ? `${safeActorName} の魔法` : "魔法を選択";
    const backGrid = createActionSheetGrid();
    backGrid.appendChild(createSheetButton("← コマンドにもどる", {
      dataset: { actionSheetAction: "back_to_command" },
    }));
    actionSheetBody.appendChild(backGrid);

    const groupedCandidates = [];
    let currentGroup = null;
    (Array.isArray(magicCandidates) ? magicCandidates : []).forEach((cand) => {
      const groupLabel = String(cand?.group_label || "").trim();
      if (!groupLabel) {
        groupedCandidates.push({ header: "", spells: [cand] });
        currentGroup = null;
        return;
      }
      if (!currentGroup || currentGroup.header !== groupLabel) {
        currentGroup = { header: groupLabel, spells: [] };
        groupedCandidates.push(currentGroup);
      }
      currentGroup.spells.push(cand);
    });

    groupedCandidates.forEach((group) => {
      const { section, grid } = createActionSheetSection(group.header, { magicLevel: true });
      group.spells.forEach((cand) => {
        grid.appendChild(createSheetButton(
          String(cand?.label || cand?.name || "(magic)"),
          {
            disabled: !canAct,
            dataset: {
              actionSheetAction: "choose_magic",
              spellName: String(cand?.name || ""),
            },
          },
        ));
      });
      actionSheetBody.appendChild(section);
    });
    return;
  }

  if (mode === "pick_item") {
    actionSheetTitle.textContent = safeActorName ? `${safeActorName} のアイテム` : "アイテムを選択";
    const grid = createActionSheetGrid();
    grid.appendChild(createSheetButton("← コマンドにもどる", {
      dataset: { actionSheetAction: "back_to_command" },
    }));
    (Array.isArray(itemCandidates) ? itemCandidates : []).forEach((cand) => {
      grid.appendChild(createSheetButton(
        String(cand?.label || cand?.name || "(item)"),
        {
          disabled: !canAct,
          dataset: {
            actionSheetAction: "choose_item",
            itemName: String(cand?.name || ""),
          },
        },
      ));
    });
    actionSheetBody.appendChild(grid);
    return;
  }

  if (mode === "pick_side") {
    actionSheetTitle.textContent = safeActorName ? `${safeActorName} の対象サイド` : "対象サイドを選択";
    const grid = createActionSheetGrid();
    grid.appendChild(createSheetButton("← まほう・アイテム選択にもどる", {
      dataset: { actionSheetAction: "return_to_source" },
    }));
    grid.appendChild(createSheetButton("敵を対象にする", {
      dataset: { actionSheetAction: "choose_side", side: "enemy" },
    }));
    grid.appendChild(createSheetButton("味方を対象にする", {
      dataset: { actionSheetAction: "choose_side", side: "ally" },
    }));
    actionSheetBody.appendChild(grid);
    return;
  }

  if (mode !== "pick_target") return;

  const side = pendingActionDraft?.target_side || "enemy";
  const sideLabel = side === "ally" ? "味方" : "敵";
  actionSheetTitle.textContent = safeActorName ? `${safeActorName} の対象選択` : `${sideLabel}対象を選択`;
  const grid = createActionSheetGrid();
  const shouldReturnToSide = Boolean(pendingActionDraft?.requires_side_choice);
  grid.appendChild(createSheetButton(
    shouldReturnToSide ? "← 対象サイド選択にもどる" : "← まほう・アイテム選択にもどる",
    {
      dataset: { actionSheetAction: "back_from_target" },
    },
  ));

  const targetNorm = String(pendingActionDraft?.target_norm || "");
  const canSelectAll = Boolean(pendingActionDraft?.can_select_all);
  const canSelectAllForSide =
    canSelectAll && (
      pendingActionDraft?.kind === "item" ||
      targetNorm === "one/all" ||
      (side === "enemy" && targetNorm === "one/all enemies") ||
      (side === "ally" && targetNorm === "one/all allies") ||
      (
        pendingActionDraft?.kind === "magic" &&
        pendingActionDraft?.target_mode === "any" &&
        side === "ally" &&
        targetNorm === "one/all enemies"
      )
    );
  if (canSelectAllForSide) {
    grid.appendChild(createSheetButton(
      side === "ally" ? "味方全体" : "敵全体",
      {
        dataset: {
          actionSheetAction: "finalize_target",
          targetIndex: 0,
          targetAll: "true",
        },
      },
    ));
  }

  if (side === "ally") {
    const party = Array.isArray(sessionStatus?.party) ? sessionStatus.party : [];
    party.forEach((member, idx) => {
      grid.appendChild(createSheetButton(
        `味方: ${member?.name || `Member ${idx + 1}`}`,
        {
          dataset: {
            actionSheetAction: "finalize_target",
            targetIndex: idx,
          },
        },
      ));
    });
  } else {
    const enemies = Array.isArray(sessionStatus?.enemies) ? sessionStatus.enemies : [];
    enemies.forEach((enemy, idx) => {
      if (typeof isOutOfBattleEnemy === "function" && isOutOfBattleEnemy(enemy)) return;
      grid.appendChild(createSheetButton(
        `敵: ${enemy?.name || `Enemy ${idx + 1}`}`,
        {
          dataset: {
            actionSheetAction: "finalize_target",
            targetIndex: idx,
          },
        },
      ));
    });
  }

  actionSheetBody.appendChild(grid);
}

function candidateListCacheKey(candidates) {
  return Array.isArray(candidates)
    ? candidates.map((candidate) => String(candidate || "")).filter(Boolean).join("\n")
    : "";
}

function clearCardOverlayLayers(card) {
  if (!card) return;
  card.querySelectorAll(".combat-popup-layer,.combat-effect-layer").forEach((node) => node.remove());
}

function renderStatusIcons(iconRow, iconKeys, { statusIconRowCache, resolveStatusIconCandidates, applyCachedImageSource }) {
  if (!iconRow) return;
  const normalizedKeys = Array.isArray(iconKeys)
    ? iconKeys.map((iconKey) => String(iconKey || "").trim()).filter(Boolean)
    : [];
  const previousState = statusIconRowCache.get(iconRow) || {
    order: [],
    nodes: new Map(),
  };
  const nextNodes = new Map();
  const nextOrder = [];
  const occurrenceCounts = new Map();

  normalizedKeys.forEach((iconKey) => {
    const occurrence = occurrenceCounts.get(iconKey) || 0;
    occurrenceCounts.set(iconKey, occurrence + 1);
    const nodeKey = `${iconKey}#${occurrence}`;
    nextOrder.push(nodeKey);
    let icon = previousState.nodes.get(nodeKey);
    if (!icon) {
      const candidates = resolveStatusIconCandidates(iconKey);
      if (!candidates.length) return;
      icon = document.createElement("img");
      icon.className = "status-icon";
      icon.alt = iconKey;
      icon.loading = "lazy";
      icon.decoding = "async";
      icon.addEventListener("error", () => {
        icon.remove();
      });
      applyCachedImageSource(icon, candidates, {
        onError: () => {
          icon.remove();
        },
      });
    }
    nextNodes.set(nodeKey, icon);
    iconRow.appendChild(icon);
  });

  previousState.nodes.forEach((icon, nodeKey) => {
    if (nextNodes.has(nodeKey)) return;
    icon.remove();
  });

  statusIconRowCache.set(iconRow, {
    order: nextOrder,
    nodes: nextNodes,
  });
  iconRow.style.display = iconRow.childElementCount > 0 ? "" : "none";
}

function syncManagedCardImage(state, candidates, applyCachedImageSource) {
  if (!state?.image || !state?.fallback) return;
  const nextCandidateKey = candidateListCacheKey(candidates);
  if (!nextCandidateKey) {
    state.image.removeAttribute("src");
    state.image.style.display = "none";
    state.fallback.style.display = "";
    state.currentCandidateKey = "";
    return;
  }
  if (state.currentCandidateKey === nextCandidateKey) return;
  state.currentCandidateKey = nextCandidateKey;
  state.image.style.display = "";
  state.fallback.style.display = "";
  applyCachedImageSource(state.image, candidates, {
    onLoad: () => {
      if (state.currentCandidateKey !== nextCandidateKey) return;
      state.fallback.style.display = "none";
      state.image.style.display = "";
    },
    onError: () => {
      if (state.currentCandidateKey !== nextCandidateKey) return;
      state.image.removeAttribute("src");
      state.image.style.display = "none";
      state.fallback.style.display = "";
    },
  });
}

function createPartyCardState(idx) {
  const card = document.createElement("article");
  card.className = "card party-card";

  const faceImage = document.createElement("img");
  faceImage.className = "party-face";
  faceImage.alt = "";
  faceImage.loading = "eager";
  faceImage.decoding = "async";
  card.appendChild(faceImage);

  const faceFallback = document.createElement("div");
  faceFallback.className = "party-face-fallback";
  faceFallback.textContent = "NO PORTRAIT";
  card.appendChild(faceFallback);

  const content = document.createElement("div");
  content.className = "party-card-content";

  const nameRow = document.createElement("div");
  nameRow.className = "name party-name-row";
  content.appendChild(nameRow);

  const hpRow = document.createElement("div");
  hpRow.className = "hp party-hp-row";
  content.appendChild(hpRow);

  const hpBarRow = document.createElement("div");
  hpBarRow.className = "party-hp-bar-row";
  const hpBar = document.createElement("div");
  hpBar.className = "hp-bar";
  const hpBarFill = document.createElement("div");
  hpBarFill.className = "hp-bar-fill";
  hpBar.appendChild(hpBarFill);
  hpBarRow.appendChild(hpBar);
  content.appendChild(hpBarRow);

  const levelRow = document.createElement("div");
  levelRow.className = "status party-level-row";
  content.appendChild(levelRow);

  const iconRow = document.createElement("div");
  iconRow.className = "status-icon-row party-status-icons-row";
  content.appendChild(iconRow);

  card.appendChild(content);

  return {
    card,
    image: faceImage,
    fallback: faceFallback,
    content,
    nameRow,
    hpRow,
    hpBarRow,
    hpBar,
    hpBarFill,
    levelRow,
    iconRow,
    currentCandidateKey: "",
    index: idx,
  };
}

function clampPercent(value) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function applyHudHpBar(barFill, member) {
  if (!barFill) return;
  const hp = Number(member?.hp ?? 0);
  const maxHp = Math.max(0, Number(member?.max_hp ?? 0));
  const ratio = maxHp > 0 ? (hp / maxHp) * 100 : 0;
  const normalizedRatio = clampPercent(ratio);
  barFill.style.setProperty("--hp-ratio", `${normalizedRatio}%`);
  barFill.classList.remove("is-caution", "is-danger");
  if (normalizedRatio <= 25) {
    barFill.classList.add("is-danger");
  } else if (normalizedRatio <= 55) {
    barFill.classList.add("is-caution");
  }
}

function createEnemyCardState(idx) {
  const card = document.createElement("article");
  card.className = "card target enemy-card";
  card.dataset.enemyIndex = String(idx);

  const spriteImage = document.createElement("img");
  spriteImage.className = "enemy-sprite";
  spriteImage.alt = "";
  spriteImage.loading = "eager";
  spriteImage.decoding = "async";
  card.appendChild(spriteImage);

  const spriteFallback = document.createElement("div");
  spriteFallback.className = "enemy-sprite-fallback";
  spriteFallback.textContent = "NO SPRITE";
  card.appendChild(spriteFallback);

  const content = document.createElement("div");
  content.className = "enemy-card-content";

  const nameRow = document.createElement("div");
  nameRow.className = "name enemy-name-row";
  content.appendChild(nameRow);

  const hpWrap = document.createElement("div");
  hpWrap.className = "enemy-hp-wrap";

  const hpRow = document.createElement("div");
  hpRow.className = "hp";
  hpWrap.appendChild(hpRow);

  const hpBarRow = document.createElement("div");
  hpBarRow.className = "enemy-hp-bar-row";
  const hpBar = document.createElement("div");
  hpBar.className = "hp-bar";
  const hpBarFill = document.createElement("div");
  hpBarFill.className = "hp-bar-fill";
  hpBar.appendChild(hpBarFill);
  hpBarRow.appendChild(hpBar);
  hpWrap.appendChild(hpBarRow);
  content.appendChild(hpWrap);

  const iconRow = document.createElement("div");
  iconRow.className = "status-icon-row enemy-status-icons-row";
  content.appendChild(iconRow);

  card.appendChild(content);

  return {
    card,
    image: spriteImage,
    fallback: spriteFallback,
    content,
    nameRow,
    hpWrap,
    hpRow,
    hpBarRow,
    hpBar,
    hpBarFill,
    iconRow,
    currentCandidateKey: "",
    index: idx,
  };
}

function getPartyCardState(cache, idx) {
  if (!cache.has(idx)) {
    cache.set(idx, createPartyCardState(idx));
  }
  return cache.get(idx);
}

function getEnemyCardState(cache, idx) {
  if (!cache.has(idx)) {
    cache.set(idx, createEnemyCardState(idx));
  }
  return cache.get(idx);
}

function appendCombatPopup(card, popup) {
  if (!card || !popup) return;
  const layer = document.createElement("div");
  layer.className = "combat-popup-layer";
  const bubble = document.createElement("div");
  const value = Number(popup?.value ?? 0);
  const kind = String(popup?.kind || "");
  let text = String(popup?.text || value);
  let extraClass = "";
  if (kind === "status") {
    text = String(popup?.text || "");
    extraClass = popup?.statusCategory === "cure" ? " status cure" : " status";
  } else if (kind === "heal") {
    text = `+${Math.abs(value)}`;
    extraClass = " heal";
  } else if (kind === "miss") {
    text = "MISS";
    extraClass = " miss";
  } else if (value > 0) {
    text = `${value}`;
  } else if (value < 0) {
    text = `+${Math.abs(value)}`;
    extraClass = " heal";
  } else {
    text = "0";
    extraClass = " miss";
  }
  bubble.className = `combat-popup${extraClass}`;
  bubble.textContent = text;
  layer.appendChild(bubble);
  card.appendChild(layer);
}

function appendCombatEffect(card, effect, { resolveAttackEffectImageCandidates, applyCachedImageSource }) {
  if (!card || !effect || effect.kind !== "slash") return;

  const layer = document.createElement("div");
  layer.className = "combat-effect-layer";

  const slash = document.createElement("div");
  slash.className = "combat-slash";

  const targetWidth = Math.max(1, card.clientWidth || card.offsetWidth || 120);
  const targetHeight = Math.max(1, card.clientHeight || card.offsetHeight || 112);
  const frameWidth = 41;
  const frameHeight = 44;
  const startX = Math.round(targetWidth * 0.16);
  const endX = Math.round(targetWidth - frameWidth - targetWidth * 0.16);
  const startY = Math.round(targetHeight * 0.48 - frameHeight / 2 - targetHeight * 0.06);
  const endY = Math.round(targetHeight * 0.48 - frameHeight / 2 + targetHeight * 0.06);
  const candidates = resolveAttackEffectImageCandidates(effect.sheetName);

  slash.style.setProperty("--slash-start-x", `${startX}px`);
  slash.style.setProperty("--slash-end-x", `${Math.max(startX, endX)}px`);
  slash.style.setProperty("--slash-start-y", `${startY}px`);
  slash.style.setProperty("--slash-end-y", `${endY}px`);
  applyCachedImageSource(slash, candidates, {
    onLoad: (resolvedUrl) => {
      slash.style.setProperty("--slash-image", `url("${resolvedUrl}")`);
    },
  });

  layer.appendChild(slash);
  card.appendChild(layer);
}

export function renderPartyCards({
  partyGrid,
  party,
  partyCardCache,
  currentMemberIndex,
  battleFinished,
  resolveFaceImageCandidates,
  statusIconRowCache,
  resolveStatusIconCandidates,
  applyCachedImageSource,
  effectForTarget,
  popupForTarget,
  resolveAttackEffectImageCandidates,
}) {
  if (!partyGrid) return;
  const activeKeys = new Set();
  (Array.isArray(party) ? party : []).forEach((member, idx) => {
    const activeClass = idx === currentMemberIndex && !battleFinished ? " active" : "";
    const cardState = getPartyCardState(partyCardCache, idx);
    activeKeys.add(idx);
    cardState.card.className = `card party-card${activeClass}`;
    cardState.nameRow.textContent = String(member?.name ?? `Member ${idx + 1}`);
    cardState.hpRow.textContent = `${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}`;
    cardState.levelRow.textContent = `Lv ${Number(member?.level ?? 0)}`;
    applyHudHpBar(cardState.hpBarFill, member);
    syncManagedCardImage(cardState, resolveFaceImageCandidates(member, idx), applyCachedImageSource);
    renderStatusIcons(cardState.iconRow, member?.status_icons, {
      statusIconRowCache,
      resolveStatusIconCandidates,
      applyCachedImageSource,
    });
    const card = cardState.card;
    clearCardOverlayLayers(card);
    appendCombatEffect(card, effectForTarget("char", idx), {
      resolveAttackEffectImageCandidates,
      applyCachedImageSource,
    });
    appendCombatPopup(card, popupForTarget("char", idx));
    partyGrid.appendChild(card);
  });
  partyCardCache.forEach((cardState, key) => {
    if (activeKeys.has(key)) return;
    cardState.card.remove();
  });
}

export function renderEnemyCards({
  enemyGrid,
  enemyFrame,
  enemies,
  enemyCardCache,
  selectedEnemyIndex,
  selectedEnemySafeIndex,
  currentSelectedLocationGroup,
  resolveLocationMapImageUrl,
  resolveEnemyImageCandidates,
  statusIconRowCache,
  resolveStatusIconCandidates,
  applyCachedImageSource,
  effectForTarget,
  popupForTarget,
  resolveAttackEffectImageCandidates,
  onMapImageResolved,
}) {
  const enemyRows = Array.isArray(enemies) ? enemies : [];
  if (enemyGrid) {
    enemyGrid.dataset.count = String(enemyRows.length);
  }
  const mapImageUrl = resolveLocationMapImageUrl(currentSelectedLocationGroup, onMapImageResolved);
  if (enemyFrame) {
    if (mapImageUrl) {
      enemyFrame.style.backgroundImage = `linear-gradient(rgba(8,14,34,0.68), rgba(8,14,34,0.68)), url("${mapImageUrl}")`;
    } else {
      enemyFrame.style.backgroundImage = "none";
    }
  }
  if (!enemyGrid) return;
  const activeKeys = new Set();
  const safeEnemyIndex = typeof selectedEnemySafeIndex === "function"
    ? selectedEnemySafeIndex({ sessionStatus: { enemies: enemyRows }, selectedEnemyIndex })
    : selectedEnemyIndex;
  enemyRows.forEach((enemy, idx) => {
    const selectedClass = idx === safeEnemyIndex ? " selected" : "";
    const cardState = getEnemyCardState(enemyCardCache, idx);
    activeKeys.add(idx);
    cardState.card.className = `card target enemy-card${selectedClass}`;
    cardState.card.dataset.enemyIndex = String(idx);
    cardState.nameRow.textContent = String(enemy?.name ?? `Enemy ${idx + 1}`);
    cardState.hpRow.textContent = `HP ${Number(enemy?.hp ?? 0)} / ${Number(enemy?.max_hp ?? 0)}`;
    applyHudHpBar(cardState.hpBarFill, enemy);
    syncManagedCardImage(cardState, resolveEnemyImageCandidates(enemy), applyCachedImageSource);
    renderStatusIcons(cardState.iconRow, enemy?.status_icons, {
      statusIconRowCache,
      resolveStatusIconCandidates,
      applyCachedImageSource,
    });
    const card = cardState.card;
    clearCardOverlayLayers(card);
    appendCombatEffect(card, effectForTarget("enemy", idx), {
      resolveAttackEffectImageCandidates,
      applyCachedImageSource,
    });
    appendCombatPopup(card, popupForTarget("enemy", idx));
    enemyGrid.appendChild(card);
  });
  enemyCardCache.forEach((cardState, key) => {
    if (activeKeys.has(key)) return;
    cardState.card.remove();
  });
}
