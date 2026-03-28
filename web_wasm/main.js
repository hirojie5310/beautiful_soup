import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

const battlePhase = document.getElementById("battlePhase");
const partyGrid = document.getElementById("partyGrid");
const enemyGrid = document.getElementById("enemyGrid");
const commandFrame = document.getElementById("commandFrame");
const battleLogFrame = document.getElementById("battleLogFrame");
const commandGrid = document.getElementById("commandGrid");
const statusLine = document.getElementById("statusLine");
const logView = document.getElementById("logView");
const plannedActionsView = document.getElementById("plannedActionsView");
const rewardPanel = document.getElementById("rewardPanel");
const locationGroupSelect = document.getElementById("locationGroupSelect");
const locationSelect = document.getElementById("locationSelect");
const locationApplyBtn = document.getElementById("locationApplyBtn");
const partyRecoverBtn = document.getElementById("partyRecoverBtn");
const enemyFrame = document.getElementById("enemyFrame");

let pyodide = null;
let sessionStatus = { party: [], enemies: [] };
let pendingActions = [];
let currentMemberIndex = 0;
let selectedEnemyIndex = 0;
let lifecycleState = "ready_for_actions";
let battleFinished = false;
let locationGroups = [];
let inputMode = "command";
let pendingActionDraft = null;
let currentSelectedLocationGroup = "";
const locationMapImageCache = {};
let activeLogPlaybackId = 0;

const COMMAND_LABELS = {
  Fight: "たたかう",
  Defend: "ぼうぎょ",
  Run: "にげる",
  Flee: "にげる",
  Item: "アイテム",
  Magic: "まほう",
  Cheer: "おうえん",
};

async function preparePythonBundle(instance) {
  const response = await fetch("./python_bundle.zip");
  if (!response.ok) {
    throw new Error(`python_bundle.zip fetch failed: ${response.status}`);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/python_bundle.zip", bytes);
  await instance.runPythonAsync(`
import sys
import zipfile

with zipfile.ZipFile("/tmp/python_bundle.zip", "r") as bundle:
    bundle.extractall("/")

if "/" not in sys.path:
    sys.path.insert(0, "/")
`);
}

async function prepareExplicitGroups(instance) {
  const response = await fetch("../assets/data/explicit_groups.json");
  if (!response.ok) {
    instance.FS.writeFile("/tmp/explicit_groups.json", new Uint8Array());
    return;
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  instance.FS.writeFile("/tmp/explicit_groups.json", bytes);
}

function renderLocationSelectors() {
  if (!locationGroupSelect || !locationSelect) return;

  const selectedGroupName = locationGroupSelect.value;
  locationGroupSelect.innerHTML = "";
  locationGroups.forEach((group) => {
    const option = document.createElement("option");
    option.value = group.group_name;
    option.textContent = group.group_name;
    if (group.group_name === selectedGroupName) {
      option.selected = true;
    }
    locationGroupSelect.appendChild(option);
  });

  const currentGroup = locationGroups.find((g) => g.group_name === locationGroupSelect.value)
    || locationGroups[0];
  const locations = Array.isArray(currentGroup?.locations) ? currentGroup.locations : [];
  const selectedLocation = locationSelect.value;
  locationSelect.innerHTML = "";
  locations.forEach((loc) => {
    const option = document.createElement("option");
    option.value = loc;
    option.textContent = loc;
    if (loc === selectedLocation) {
      option.selected = true;
    }
    locationSelect.appendChild(option);
  });
  if (locations.length && !locationSelect.value) {
    locationSelect.value = locations[0];
  }
}

function selectedEnemySafeIndex() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  if (!enemies.length) return 0;
  const aliveIndices = enemies
    .map((enemy, idx) => ({ enemy, idx }))
    .filter(({ enemy }) => !isOutOfBattleEnemy(enemy))
    .map(({ idx }) => idx);
  if (!aliveIndices.length) return 0;
  if (aliveIndices.includes(selectedEnemyIndex)) return selectedEnemyIndex;
  return aliveIndices[0];
}

function locationGroupToMapKey(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_");
}

function resolveLocationMapImageCandidates(locationGroupName) {
  const key = locationGroupToMapKey(locationGroupName);
  if (!key) return [];
  return [
    `/web_wasm/maps/${key}.jpg`,
    `/web_wasm/maps/${key}.jpeg`,
    `/web_wasm/maps/${key}.png`,
    `../assets/images/maps/${key}.jpg`,
    `../assets/images/maps/${key}.jpeg`,
    `../assets/images/maps/${key}.png`,
  ];
}

function resolveLocationMapImageUrl(locationGroupName, onResolved) {
  const key = locationGroupToMapKey(locationGroupName);
  if (!key) return "";

  const cached = locationMapImageCache[key];
  if (typeof cached === "string") {
    return cached;
  }
  if (cached === "__loading__") {
    return "";
  }

  const candidates = resolveLocationMapImageCandidates(locationGroupName);
  if (!candidates.length) {
    locationMapImageCache[key] = "";
    return "";
  }

  locationMapImageCache[key] = "__loading__";

  const tryLoad = (index) => {
    if (index >= candidates.length) {
      locationMapImageCache[key] = "";
      if (typeof onResolved === "function") onResolved("");
      return;
    }
    const image = new Image();
    const url = candidates[index];
    image.addEventListener("load", () => {
      locationMapImageCache[key] = url;
      if (typeof onResolved === "function") onResolved(url);
    });
    image.addEventListener("error", () => {
      tryLoad(index + 1);
    });
    image.src = url;
  };

  tryLoad(0);
  return "";
}

function buildActionFromCommand(def) {
  const enemyIndex = selectedEnemySafeIndex();
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

function targetSideForCommand(def) {
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

function commandLabel(command) {
  const key = String(command || "").trim();
  return COMMAND_LABELS[key] || key || "(unknown)";
}

function normalizeFaceKey(raw) {
  return String(raw || "")
    .trim()
    .toLowerCase()
    .replace(/^ch_/, "")
    .replace(/\.(png|jpg|jpeg|webp)$/i, "")
    .replace(/\s+/g, "_")
    .replace(/-/g, "_");
}

function resolveFaceImageCandidates(member, memberIndex = -1) {
  const portraitKey = normalizeFaceKey(member?.portrait_key);
  const nameKey = normalizeFaceKey(member?.name);
  const imageNameKey = normalizeFaceKey(member?.image_name);
  const fixedPartyOrderFallback = ["runeth", "arc", "refia", "ingus"];
  const slotKey = fixedPartyOrderFallback[memberIndex] || "";
  const aliasMap = {
    luneth: "runeth",
  };
  const rawKeys = [portraitKey, imageNameKey, nameKey, slotKey];
  const keys = rawKeys
    .map((key) => aliasMap[key] || key)
    .filter((value, index, arr) => value && arr.indexOf(value) === index);
  if (!keys.length) return [];
  const paths = [];
  const exts = ["png", "webp", "jpg", "jpeg"];
  keys.forEach((key) => {
    const variants = [key, key.charAt(0).toUpperCase() + key.slice(1)];
    variants.forEach((variantKey) => {
      const safeKey = encodeURIComponent(variantKey);
      exts.forEach((ext) => {
        paths.push(`/web_wasm/faces/${safeKey}.${ext}`);
        paths.push(`./faces/${safeKey}.${ext}`);
        paths.push(`../assets/images/faces/${safeKey}.${ext}`);
        paths.push(new URL(`../assets/images/faces/${safeKey}.${ext}`, import.meta.url).href);
        paths.push(`/assets/images/faces/${safeKey}.${ext}`);

        paths.push(`../assets/images/motions/${safeKey}.${ext}`);
        paths.push(new URL(`../assets/images/motions/${safeKey}.${ext}`, import.meta.url).href);
        paths.push(`/assets/images/motions/${safeKey}.${ext}`);
      });
    });
  });
  return paths.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

function normalizeSpriteKey(raw) {
  return String(raw || "")
    .trim()
    .replace(/\.(png|jpg|jpeg|webp)$/i, "")
    .replace(/\s+/g, "_");
}

function resolveEnemyImageCandidates(enemy) {
  const spriteKey = normalizeSpriteKey(enemy?.sprite_id);
  if (!spriteKey) return [];
  const safeKey = encodeURIComponent(spriteKey);
  const exts = ["png", "webp", "jpg", "jpeg"];
  const paths = [];
  exts.forEach((ext) => {
    paths.push(`/web_wasm/enemy_sprites/${safeKey}.${ext}`);
    paths.push(`./enemy_sprites/${safeKey}.${ext}`);
    paths.push(`../assets/images/enemy_sprites/${safeKey}.${ext}`);
    paths.push(new URL(`../assets/images/enemy_sprites/${safeKey}.${ext}`, import.meta.url).href);
    paths.push(`/assets/images/enemy_sprites/${safeKey}.${ext}`);
  });
  return paths.filter((value, index, arr) => value && arr.indexOf(value) === index);
}

function resolveStatusIconCandidates(iconKey) {
  const key = String(iconKey || "").trim().toLowerCase();
  if (!key) return [];
  const safeKey = encodeURIComponent(key);
  return [
    `../assets/images/status_icons/${safeKey}.png`,
    new URL(`../assets/images/status_icons/${safeKey}.png`, import.meta.url).href,
    `/assets/images/status_icons/${safeKey}.png`,
  ];
}

function enterCommandMode() {
  inputMode = "command";
  pendingActionDraft = null;
}

function isOutOfBattleMember(member) {
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

function isOutOfBattleEnemy(enemy) {
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

function actionableMemberIndices() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const rows = [];
  party.forEach((member, idx) => {
    if (isOutOfBattleMember(member)) return;
    if (member?.is_jumping) return;
    rows.push(idx);
  });
  return rows;
}

function requiredActionCount() {
  return actionableMemberIndices().length;
}

function committedActionCount() {
  const actionable = new Set(actionableMemberIndices());
  let count = 0;
  pendingActions.forEach((action, idx) => {
    if (!actionable.has(idx)) return;
    if (action) count += 1;
  });
  return count;
}

function resetPendingActionsForParty() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  pendingActions = Array(party.length).fill(null);
}

function firstActionableMemberIndex() {
  const actionable = actionableMemberIndices();
  return actionable.length ? actionable[0] : 0;
}

function findNextPendingMemberIndex(startIdx) {
  const actionable = actionableMemberIndices();
  if (!actionable.length) return null;
  const total = actionable.length;
  const rawStartPos = actionable.indexOf(startIdx);
  const startPos = rawStartPos >= 0 ? rawStartPos : 0;
  for (let step = 1; step <= total; step += 1) {
    const idx = actionable[(startPos + step) % total];
    if (!pendingActions[idx]) return idx;
  }
  return null;
}

function syncCurrentMemberToActionable() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  if (!party.length) {
    currentMemberIndex = 0;
    return;
  }
  if (isOutOfBattleMember(party[currentMemberIndex])) {
    currentMemberIndex = firstActionableMemberIndex();
  }
}

function currentMemberCommandDefs() {
  const all = Array.isArray(sessionStatus?.command_candidates_by_member)
    ? sessionStatus.command_candidates_by_member
    : [];
  const rows = Array.isArray(all[currentMemberIndex]) ? all[currentMemberIndex] : [];
  if (rows.length) return rows;
  return [
    { kind: "physical", command: "Fight" },
    { kind: "defend", command: "Defend" },
    { kind: "item", command: "Item" },
    { kind: "run", command: "Run" },
  ];
}

function currentMemberMagicCandidates() {
  const all = Array.isArray(sessionStatus?.magic_command_candidates_by_member)
    ? sessionStatus.magic_command_candidates_by_member
    : [];
  const rows = Array.isArray(all[currentMemberIndex]) ? all[currentMemberIndex] : [];
  return rows;
}

function currentItemCandidates() {
  return Array.isArray(sessionStatus?.item_command_candidates)
    ? sessionStatus.item_command_candidates
    : [];
}

function renderParty() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  partyGrid.innerHTML = "";
  party.forEach((member, idx) => {
    const card = document.createElement("article");
    const activeClass = idx === currentMemberIndex && !battleFinished ? " active" : "";
    card.className = `card party-card${activeClass}`;
    const faceFallback = document.createElement("div");
    faceFallback.className = "party-face-fallback";
    faceFallback.textContent = "NO PORTRAIT";
    const faceImageCandidates = resolveFaceImageCandidates(member, idx);
    if (faceImageCandidates.length) {
      const faceImage = document.createElement("img");
      faceImage.className = "party-face";
      faceImage.alt = "";
      faceImage.loading = "eager";
      faceImage.decoding = "async";
      let imageIndex = 0;
      faceImage.addEventListener("load", () => {
        faceFallback.remove();
      });
      faceImage.src = faceImageCandidates[imageIndex];
      faceImage.addEventListener("error", () => {
        imageIndex += 1;
        if (imageIndex < faceImageCandidates.length) {
          faceImage.src = faceImageCandidates[imageIndex];
          return;
        }
        faceImage.remove();
        if (!card.contains(faceFallback)) {
          card.insertBefore(faceFallback, card.firstChild);
        }
      });
      card.appendChild(faceImage);
    } else {
      card.appendChild(faceFallback);
    }

    const content = document.createElement("div");
    content.className = "party-card-content";
    const nameRow = document.createElement("div");
    nameRow.className = "name";
    nameRow.textContent = String(member?.name ?? `Member ${idx + 1}`);
    content.appendChild(nameRow);

    const memberStatusIcons = Array.isArray(member?.status_icons) ? member.status_icons : [];
    if (memberStatusIcons.length) {
      const iconRow = document.createElement("div");
      iconRow.className = "status-icon-row";
      memberStatusIcons.forEach((iconKey) => {
        const icon = document.createElement("img");
        icon.className = "status-icon";
        icon.alt = String(iconKey || "");
        icon.loading = "lazy";
        icon.decoding = "async";
        const candidates = resolveStatusIconCandidates(iconKey);
        let iconIndex = 0;
        const tryNextIcon = () => {
          iconIndex += 1;
          if (iconIndex >= candidates.length) {
            icon.remove();
            return;
          }
          icon.src = candidates[iconIndex];
        };
        icon.addEventListener("error", tryNextIcon);
        if (candidates.length) {
          icon.src = candidates[iconIndex];
          iconRow.appendChild(icon);
        }
      });
      if (iconRow.childElementCount > 0) {
        content.appendChild(iconRow);
      }
    }

    const hpRow = document.createElement("div");
    hpRow.className = "hp";
    hpRow.textContent = `HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}`;
    content.appendChild(hpRow);

    const levelRow = document.createElement("div");
    levelRow.className = "status";
    levelRow.textContent = `Lv ${Number(member?.level ?? 0)}`;
    content.appendChild(levelRow);

    card.appendChild(content);
    partyGrid.appendChild(card);
  });
}

function renderEnemies() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  const mapImageUrl = resolveLocationMapImageUrl(currentSelectedLocationGroup, () => {
    renderEnemies();
  });
  if (enemyFrame) {
    if (mapImageUrl) {
      enemyFrame.style.backgroundImage = `linear-gradient(rgba(8,14,34,0.68), rgba(8,14,34,0.68)), url("${mapImageUrl}")`;
    } else {
      enemyFrame.style.backgroundImage = "none";
    }
  }
  enemyGrid.innerHTML = "";
  enemies.forEach((enemy, idx) => {
    const card = document.createElement("article");
    const selectedClass = idx === selectedEnemySafeIndex() ? " selected" : "";
    card.className = `card target enemy-card${selectedClass}`;

    const spriteFallback = document.createElement("div");
    spriteFallback.className = "enemy-sprite-fallback";
    spriteFallback.textContent = "NO SPRITE";
    const spriteImageCandidates = resolveEnemyImageCandidates(enemy);
    if (spriteImageCandidates.length) {
      const spriteImage = document.createElement("img");
      spriteImage.className = "enemy-sprite";
      spriteImage.alt = "";
      spriteImage.loading = "eager";
      spriteImage.decoding = "async";
      let imageIndex = 0;
      spriteImage.addEventListener("load", () => {
        spriteFallback.remove();
      });
      spriteImage.src = spriteImageCandidates[imageIndex];
      spriteImage.addEventListener("error", () => {
        imageIndex += 1;
        if (imageIndex < spriteImageCandidates.length) {
          spriteImage.src = spriteImageCandidates[imageIndex];
          return;
        }
        spriteImage.remove();
        if (!card.contains(spriteFallback)) {
          card.insertBefore(spriteFallback, card.firstChild);
        }
      });
      card.appendChild(spriteImage);
    } else {
      card.appendChild(spriteFallback);
    }

    const content = document.createElement("div");
    content.className = "enemy-card-content";
    content.innerHTML = `
      <div class="name">${enemy?.name ?? `Enemy ${idx + 1}`}</div>
      <div class="hp">HP ${Number(enemy?.hp ?? 0)} / ${Number(enemy?.max_hp ?? 0)}</div>
    `;
    const enemyStatusIcons = Array.isArray(enemy?.status_icons) ? enemy.status_icons : [];
    if (enemyStatusIcons.length) {
      const iconRow = document.createElement("div");
      iconRow.className = "status-icon-row";
      enemyStatusIcons.forEach((iconKey) => {
        const icon = document.createElement("img");
        icon.className = "status-icon";
        icon.alt = String(iconKey || "");
        icon.loading = "lazy";
        icon.decoding = "async";
        const candidates = resolveStatusIconCandidates(iconKey);
        let iconIndex = 0;
        const tryNextIcon = () => {
          iconIndex += 1;
          if (iconIndex >= candidates.length) {
            icon.remove();
            return;
          }
          icon.src = candidates[iconIndex];
        };
        icon.addEventListener("error", tryNextIcon);
        if (candidates.length) {
          icon.src = candidates[iconIndex];
          iconRow.appendChild(icon);
        }
      });
      if (iconRow.childElementCount > 0) {
        content.appendChild(iconRow);
      }
    }
    card.appendChild(content);
    card.addEventListener("click", () => {
      if (battleFinished) return;
      if (isOutOfBattleEnemy(enemy)) return;
      selectedEnemyIndex = idx;
      renderEnemies();
      renderStatus();
    });
    enemyGrid.appendChild(card);
  });
}

function renderCommandButtons() {
  commandGrid.innerHTML = "";
  commandGrid.classList.toggle("command-mode", inputMode === "command");
  if (inputMode === "pick_magic") {
    const backBtn = document.createElement("button");
    backBtn.className = "btn";
    backBtn.type = "button";
    backBtn.textContent = "← コマンドにもどる";
    backBtn.addEventListener("click", () => {
      enterCommandMode();
      rerenderAll();
    });
    commandGrid.appendChild(backBtn);

    const candidates = currentMemberMagicCandidates();
    const groupedCandidates = [];
    let currentGroup = null;
    candidates.forEach((cand) => {
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
      if (!group.header) {
        group.spells.forEach((cand) => {
          const button = document.createElement("button");
          button.className = "btn";
          button.type = "button";
          button.disabled = !pyodide || battleFinished;
          button.textContent = String(cand?.label || cand?.name || "(magic)");
          button.addEventListener("click", () => chooseMagic(cand));
          commandGrid.appendChild(button);
        });
        return;
      }

      const row = document.createElement("div");
      row.className = "magic-group-row";

      const header = document.createElement("div");
      header.className = "magic-group-header";
      header.textContent = group.header;
      row.appendChild(header);

      const spells = document.createElement("div");
      spells.className = "magic-group-spells";
      group.spells.forEach((cand) => {
        const button = document.createElement("button");
        button.className = "btn";
        button.type = "button";
        button.disabled = !pyodide || battleFinished;
        button.textContent = String(cand?.label || cand?.name || "(magic)");
        button.addEventListener("click", () => chooseMagic(cand));
        spells.appendChild(button);
      });
      row.appendChild(spells);
      commandGrid.appendChild(row);
    });
    return;
  }

  if (inputMode === "pick_item") {
    const backBtn = document.createElement("button");
    backBtn.className = "btn";
    backBtn.type = "button";
    backBtn.textContent = "← コマンドにもどる";
    backBtn.addEventListener("click", () => {
      enterCommandMode();
      rerenderAll();
    });
    commandGrid.appendChild(backBtn);

    currentItemCandidates().forEach((cand) => {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.disabled = !pyodide || battleFinished;
      button.textContent = String(cand?.label || cand?.name || "(item)");
      button.addEventListener("click", () => chooseItem(cand));
      commandGrid.appendChild(button);
    });
    return;
  }

  if (inputMode === "pick_side") {
    const backBtn = document.createElement("button");
    backBtn.className = "btn";
    backBtn.type = "button";
    backBtn.textContent = "← えらびなおす";
    backBtn.addEventListener("click", () => {
      inputMode = pendingActionDraft?.kind === "magic" ? "pick_magic" : "pick_item";
      pendingActionDraft = null;
      rerenderAll();
    });
    commandGrid.appendChild(backBtn);

    ["enemy", "ally"].forEach((side) => {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.textContent = side === "enemy" ? "敵を対象にする" : "味方を対象にする";
      button.addEventListener("click", () => {
        pendingActionDraft = { ...(pendingActionDraft || {}), target_side: side };
        inputMode = "pick_target";
        rerenderAll();
      });
      commandGrid.appendChild(button);
    });
    return;
  }

  if (inputMode === "pick_target") {
    const backBtn = document.createElement("button");
    backBtn.className = "btn";
    backBtn.type = "button";
    backBtn.textContent = "← えらびなおす";
    backBtn.addEventListener("click", () => {
      if (pendingActionDraft?.target_side === "ally" || pendingActionDraft?.target_side === "enemy") {
        inputMode = "pick_side";
      } else {
        enterCommandMode();
      }
      rerenderAll();
    });
    commandGrid.appendChild(backBtn);

    const side = pendingActionDraft?.target_side || "enemy";
    const targetNorm = String(pendingActionDraft?.target_norm || "");
    const canSelectAll = Boolean(pendingActionDraft?.can_select_all);
    const canSelectAllForSide =
      canSelectAll && (
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
      const allButton = document.createElement("button");
      allButton.className = "btn";
      allButton.type = "button";
      allButton.textContent = side === "ally" ? "味方全体" : "敵全体";
      allButton.addEventListener("click", () => finalizeDraftAction(0, { targetAll: true }));
      commandGrid.appendChild(allButton);
    }
    if (side === "ally") {
      const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
      party.forEach((member, idx) => {
        const button = document.createElement("button");
        button.className = "btn";
        button.type = "button";
        button.textContent = `味方: ${member?.name || `Member ${idx + 1}`}`;
        button.addEventListener("click", () => finalizeDraftAction(idx));
        commandGrid.appendChild(button);
      });
      return;
    }
    const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
    enemies.forEach((enemy, idx) => {
      if (isOutOfBattleEnemy(enemy)) return;
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.textContent = `敵: ${enemy?.name || `Enemy ${idx + 1}`}`;
      button.addEventListener("click", () => finalizeDraftAction(idx));
      commandGrid.appendChild(button);
    });
    return;
  }

  currentMemberCommandDefs().forEach((def) => {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = commandLabel(def?.command);
    button.disabled = !pyodide || battleFinished;
    button.addEventListener("click", () => {
      chooseCommand({
        kind: String(def?.kind || "physical"),
        command: String(def?.command || "Fight"),
        targetSide: targetSideForCommand(def),
      });
    });
    commandGrid.appendChild(button);
  });
}

function renderPlannedActions() {
  plannedActionsView.textContent = pendingActions.length
    ? JSON.stringify(pendingActions, null, 2)
    : "(none)";
}

function renderStatus() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  if (battleFinished) {
    statusLine.textContent = "戦闘終了。Bootし直すと再開始できます。";
    return;
  }
  const actor = party[currentMemberIndex];
  const target = enemies[selectedEnemySafeIndex()];
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
  const committed = committedActionCount();
  const required = requiredActionCount();
  statusLine.textContent = `行動入力: ${actor.name} / 対象: ${target?.name ?? "(なし)"} / 入力済み ${committed}/${required}`;
}

function maybeShowRewards(payload) {
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

function setCommandLogLayout({ showCommand }) {
  if (commandFrame) {
    commandFrame.style.display = showCommand ? "" : "none";
  }
  if (battleLogFrame) {
    battleLogFrame.style.display = showCommand ? "none" : "";
  }
}

function buildLogBlocks(logs) {
  const lines = Array.isArray(logs) ? logs : [];
  const blocks = [];
  let current = [];
  let type = "action";
  const flush = () => {
    if (!current.length) return;
    blocks.push({ type, lines: current });
    current = [];
  };
  lines.forEach((lineRaw) => {
    const line = String(lineRaw ?? "");
    if (line.startsWith("▶ ") || line.startsWith("◆ ")) {
      flush();
      type = "action";
      current.push(line);
      return;
    }
    if (line.startsWith("=== Battle Rewards ===")) {
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

function buildRewardLogBlock(payload) {
  if (!payload?.victory_rewards) {
    return null;
  }
  const rewards = payload.victory_rewards;
  const drops = Array.isArray(rewards?.dropped_item) && rewards.dropped_item.length
    ? rewards.dropped_item.join(", ")
    : "(none)";
  return {
    type: "reward",
    lines: [
      "=== Battle Rewards ===",
      `EXP +${Number(rewards?.gained_exp ?? 0)}`,
      `Gil +${Number(rewards?.gained_gil ?? 0)}`,
      `CP +${Number(rewards?.gained_cp ?? 0)}`,
      `Drop: ${drops}`,
    ],
  };
}

async function playBattleLogBlocks(logs, payload) {
  const playbackId = ++activeLogPlaybackId;
  const blocks = buildLogBlocks(logs);
  const hasRewardBlock = blocks.some((block) => block.type === "reward");
  if (!hasRewardBlock) {
    const rewardBlock = buildRewardLogBlock(payload);
    if (rewardBlock) {
      blocks.push(rewardBlock);
    }
  }
  logView.textContent = "";
  rewardPanel.classList.remove("open");
  rewardPanel.textContent = "";

  if (!blocks.length) {
    logView.textContent = "(no logs)";
    return;
  }

  for (let i = 0; i < blocks.length; i += 1) {
    if (playbackId !== activeLogPlaybackId) return;
    const block = blocks[i];
    logView.textContent = block.lines.join("\n");
    if (block.type === "reward") {
      maybeShowRewards(payload);
    } else {
      rewardPanel.classList.remove("open");
      rewardPanel.textContent = "";
    }
    if (i < blocks.length - 1) {
      await waitForBattleLogClick(playbackId);
    }
  }
}

function waitForBattleLogClick(playbackId) {
  return new Promise((resolve) => {
    if (!battleLogFrame) {
      resolve();
      return;
    }
    battleLogFrame.classList.add("is-clickable-next");
    const onClick = () => {
      if (playbackId !== activeLogPlaybackId) {
        battleLogFrame.classList.remove("is-clickable-next");
        battleLogFrame.removeEventListener("click", onClick);
        resolve();
        return;
      }
      battleLogFrame.classList.remove("is-clickable-next");
      battleLogFrame.removeEventListener("click", onClick);
      resolve();
    };
    battleLogFrame.addEventListener("click", onClick);
  });
}

function rerenderAll() {
  renderParty();
  renderEnemies();
  renderCommandButtons();
  renderPlannedActions();
  renderStatus();
}

function chooseCommand(def) {
  if (battleFinished) return;
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  if (!party.length) return;
  syncCurrentMemberToActionable();
  if (!party[currentMemberIndex] || isOutOfBattleMember(party[currentMemberIndex])) {
    statusLine.textContent = "行動可能なメンバーがいません。";
    return;
  }
  if (def.kind === "magic") {
    inputMode = "pick_magic";
    rerenderAll();
    return;
  }
  if (def.kind === "item") {
    inputMode = "pick_item";
    rerenderAll();
    return;
  }
  appendPendingAction(buildActionFromCommand(def));
}

function appendPendingAction(action) {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  if (!party.length) return;
  if (pendingActions.length !== party.length) {
    resetPendingActionsForParty();
  }
  pendingActions[currentMemberIndex] = action;
  enterCommandMode();
  const nextIndex = findNextPendingMemberIndex(currentMemberIndex);
  if (nextIndex === null) {
    battlePhase.textContent = "全員入力済み。ラウンド実行中...";
    rerenderAll();
    executeRound().catch((error) => {
      logView.textContent = String(error);
      setCommandLogLayout({ showCommand: true });
      battlePhase.textContent = `ラウンド実行失敗: ${String(error)}`;
    });
    return;
  } else {
    currentMemberIndex = nextIndex;
    battlePhase.textContent = `${committedActionCount()}/${requiredActionCount()} 入力済み`;
  }
  rerenderAll();
}

function chooseMagic(cand) {
  const spellName = String(cand?.name || "");
  if (!spellName) return;
  const spellMeta = sessionStatus?.magic_spell_meta?.[spellName] || {};
  const mode = String(spellMeta?.target_mode || "enemy_only");
  const targetNorm = String(spellMeta?.target_norm || "");
  const canSelectAll = Boolean(spellMeta?.can_select_all);
  if (targetNorm === "all enemies") {
    appendPendingAction({
      kind: "magic",
      command: "Magic",
      spell_name: spellName,
      target_side: "enemy",
      target_index: 0,
      target_all: true,
    });
    return;
  }
  if (targetNorm === "all allies") {
    appendPendingAction({
      kind: "magic",
      command: "Magic",
      spell_name: spellName,
      target_side: "ally",
      target_index: currentMemberIndex,
      target_all: true,
    });
    return;
  }
  if (mode === "ally_only") {
    pendingActionDraft = {
      kind: "magic",
      command: "Magic",
      spell_name: spellName,
      target_side: "ally",
      can_select_all: canSelectAll,
      target_norm: targetNorm,
    };
    inputMode = "pick_target";
    rerenderAll();
    return;
  }
  if (mode === "any") {
    pendingActionDraft = {
      kind: "magic",
      command: "Magic",
      spell_name: spellName,
      can_select_all: canSelectAll,
      target_norm: targetNorm,
      target_mode: mode,
    };
    inputMode = "pick_side";
    rerenderAll();
    return;
  }
  pendingActionDraft = {
    kind: "magic",
    command: "Magic",
    spell_name: spellName,
    target_side: "enemy",
    can_select_all: canSelectAll,
    target_norm: targetNorm,
  };
  inputMode = "pick_target";
  rerenderAll();
}

function chooseItem(cand) {
  const itemName = String(cand?.name || "");
  if (!itemName) return;
  const targetSide = sessionStatus?.item_meta?.[itemName]?.target_side;
  pendingActionDraft = {
    kind: "item",
    command: "Item",
    item_name: itemName,
  };
  if (targetSide === "ally" || targetSide === "enemy") {
    pendingActionDraft.target_side = targetSide;
    inputMode = "pick_target";
  } else {
    inputMode = "pick_side";
  }
  rerenderAll();
}

function finalizeDraftAction(targetIndex, options = {}) {
  if (!pendingActionDraft) return;
  const action = {
    kind: pendingActionDraft.kind || "physical",
    command: pendingActionDraft.command || "Fight",
    target_side: pendingActionDraft.target_side || "enemy",
    target_index: Number(targetIndex || 0),
    target_all: Boolean(options?.targetAll),
  };
  if (pendingActionDraft.spell_name) {
    action.spell_name = pendingActionDraft.spell_name;
  }
  if (pendingActionDraft.item_name) {
    action.item_name = pendingActionDraft.item_name;
  }
  appendPendingAction(action);
}

async function bootEngine() {
  battlePhase.textContent = "Pyodide 起動中...";

  pyodide = await loadPyodide();
  await pyodide.loadPackage("typing-extensions");
  await preparePythonBundle(pyodide);
  await prepareExplicitGroups(pyodide);
  await pyodide.runPythonAsync(`
import json
from combat.wasm_api import WasmBattleEngine
from combat.runtime_state import init_runtime_state
from assets.data.data_loader import load_explicit_groups
from combat.enemy_selection import build_groups, build_location_index, pick_enemy_names

state = init_runtime_state()

location_entries = build_location_index(state.monsters)
explicit_groups = {}
try:
    explicit_groups = load_explicit_groups("/tmp/explicit_groups.json")
except (OSError, ValueError):
    explicit_groups = {}
location_groups = build_groups(
    location_entries,
    explicit_groups=explicit_groups,
)
groups_payload = []
location_to_entry = {}
for group in location_groups:
    locations = []
    for child in group.children:
        locations.append(str(child.location))
        location_to_entry[str(child.location)] = child
    groups_payload.append({
        "group_name": str(group.group_name),
        "locations": locations,
    })

default_group = groups_payload[0]["group_name"] if groups_payload else ""
default_location = (
    groups_payload[0]["locations"][0]
    if groups_payload and groups_payload[0]["locations"]
    else ""
)

engine = None

def get_location_selection_json():
    payload = {
        "groups": groups_payload,
        "selected_group": default_group,
        "selected_location": default_location,
    }
    return json.dumps(payload, ensure_ascii=False)

def boot_engine_for_location(location_group, location, seed=7):
    global engine
    selected_group = str(location_group or "")
    selected_location = str(location or "")
    entry = location_to_entry.get(selected_location)
    if entry is None:
        enemy_names = sorted(state.monsters.keys())[:3]
    else:
        enemy_names = pick_enemy_names(entry, state.monsters, k_min=2, k_max=6)
    engine = WasmBattleEngine.create_default(
        enemy_names=enemy_names,
        seed=seed,
        selected_location_group=selected_group,
        selected_location=selected_location,
    )
    engine.full_recover_party_payload()
    return json.dumps(engine.build_initial_payload(), ensure_ascii=False)

def get_initial_payload_json():
    return json.dumps(engine.build_initial_payload(), ensure_ascii=False)

def run_battle_round_wasm(js_input_json):
    return engine.execute_round_json(js_input_json)

def full_recover_party_json():
    if engine is None:
        return json.dumps({"session_status": None}, ensure_ascii=False)
    return json.dumps(engine.full_recover_party_payload(), ensure_ascii=False)
`);

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];
  renderLocationSelectors();
  if (selectionPayload?.selected_group) {
    locationGroupSelect.value = selectionPayload.selected_group;
    renderLocationSelectors();
  }
  if (selectionPayload?.selected_location) {
    locationSelect.value = selectionPayload.selected_location;
  }

  bootLocationAndSyncSession();
  resetPendingActionsForParty();
  currentMemberIndex = firstActionableMemberIndex();
  selectedEnemyIndex = 0;
  enterCommandMode();

  battlePhase.textContent = "起動完了。コマンド入力を開始してください。";
  logView.textContent = "(not executed)";
  setCommandLogLayout({ showCommand: true });
  rewardPanel.classList.remove("open");
  rewardPanel.textContent = "";
  rerenderAll();
}

function applyFullRecoverParty() {
  if (!pyodide) return;
  const fullRecover = pyodide.globals.get("full_recover_party_json");
  if (!fullRecover) return;
  const payload = JSON.parse(fullRecover());
  const nextStatus = payload?.session_status;
  if (nextStatus && typeof nextStatus === "object") {
    sessionStatus = nextStatus;
  }
}

function bootLocationAndSyncSession() {
  if (!pyodide) return null;
  const bootForLocation = pyodide.globals.get("boot_engine_for_location");
  const payload = JSON.parse(
    bootForLocation(
      locationGroupSelect.value || "",
      locationSelect.value || "",
      7,
    ),
  );
  currentSelectedLocationGroup = String(
    payload?.selected_location_group || locationGroupSelect.value || "",
  );
  sessionStatus = payload?.session_status ?? { party: [], enemies: [] };
  lifecycleState = "ready_for_actions";
  battleFinished = false;
  applyFullRecoverParty();
  return payload;
}

async function executeRound() {
  if (!pyodide || battleFinished) return;
  const runRound = pyodide.globals.get("run_battle_round_wasm");
  const required = requiredActionCount();
  const committed = committedActionCount();
  if (committed < required) {
    statusLine.textContent = `まだ ${required - committed} 人分の入力が必要です。`;
    return;
  }

  battlePhase.textContent = "ラウンド解決中...";
  setCommandLogLayout({ showCommand: false });
  const payload = {
    planned_actions: pendingActions,
    lifecycle_state: lifecycleState,
  };
  const resultJson = runRound(JSON.stringify(payload));
  const result = JSON.parse(resultJson);

  sessionStatus = result?.session_status ?? sessionStatus;
  currentSelectedLocationGroup = String(
    result?.selected_location_group || currentSelectedLocationGroup || "",
  );
  lifecycleState = result?.lifecycle?.after === "ready_for_next_round"
    ? "ready_for_actions"
    : (result?.lifecycle?.after ?? "ready_for_actions");
  battleFinished = Boolean(result?.lifecycle?.battle_finished);

  const logs = Array.isArray(result?.logs) ? result.logs : [];
  await playBattleLogBlocks(logs, result);

  resetPendingActionsForParty();
  currentMemberIndex = firstActionableMemberIndex();
  selectedEnemyIndex = 0;
  enterCommandMode();
  setCommandLogLayout({ showCommand: !battleFinished });
  battlePhase.textContent = battleFinished
    ? `戦闘終了: ${result?.end_reason ?? "finished"}`
    : "次ターンの入力を開始してください。";

  rerenderAll();
}

if (locationGroupSelect) {
  locationGroupSelect.addEventListener("change", () => {
    renderLocationSelectors();
  });
}

if (locationApplyBtn) {
  locationApplyBtn.addEventListener("click", () => {
    if (!pyodide) {
      statusLine.textContent = "エンジン起動中です。完了後に再実行してください。";
      return;
    }
    bootLocationAndSyncSession();
    resetPendingActionsForParty();
    currentMemberIndex = firstActionableMemberIndex();
    selectedEnemyIndex = 0;
    enterCommandMode();
    battlePhase.textContent = "敵編成を更新しました。コマンド入力を開始してください。";
    logView.textContent = "(not executed)";
    setCommandLogLayout({ showCommand: true });
    rewardPanel.classList.remove("open");
    rewardPanel.textContent = "";
    rerenderAll();
  });
}

if (partyRecoverBtn) {
  partyRecoverBtn.addEventListener("click", () => {
    if (!pyodide) {
      statusLine.textContent = "エンジン起動中です。完了後に再実行してください。";
      return;
    }
    applyFullRecoverParty();
    enterCommandMode();
    rerenderAll();
    statusLine.textContent = "パーティーを全回復しました。";
  });
}

rerenderAll();
bootEngine().catch((error) => {
  battlePhase.textContent = `起動失敗: ${String(error)}`;
  statusLine.textContent = "エンジン起動に失敗しました。ページを再読み込みしてください。";
});
