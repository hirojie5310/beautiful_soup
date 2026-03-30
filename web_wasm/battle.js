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
const locationBtn = document.getElementById("locationBtn");
const menuBtn = document.getElementById("menuBtn");
const loadSaveBtn = document.getElementById("loadSaveBtn");
const loadSaveInput = document.getElementById("loadSaveInput");
const downloadSaveBtn = document.getElementById("downloadSaveBtn");
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
let latestMenuState = null;
const locationMapImageCache = {};
let activeLogPlaybackId = 0;
let loadedSaveData = null;
let returnToLocationBound = false;

const LOCAL_SAVE_STORAGE_KEY = "ff3_wasm_savedata_v1";
const LOCAL_MENU_STORAGE_KEY = "ff3_wasm_menu_state_v1";
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";

function readBattleStartSelectionFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_START_SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return {
        selected_location_group: String(parsed.selected_location_group || ""),
        selected_location: String(parsed.selected_location || ""),
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}

const sessionBattleStartSelection = readBattleStartSelectionFromSession();
const hasSessionBattleStartSelection = Boolean(
  sessionBattleStartSelection?.selected_location_group || sessionBattleStartSelection?.selected_location,
);

let currentBattleSelection = sessionBattleStartSelection || {
  selected_location_group: "",
  selected_location: "",
};

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

function resolveBattleSelection(selectionPayload) {
  const fallbackGroup = String(selectionPayload?.selected_group || "");
  const fallbackLocation = String(selectionPayload?.selected_location || "");
  const requestedGroup = String(currentBattleSelection.selected_location_group || "");
  const requestedLocation = String(currentBattleSelection.selected_location || "");
  const group = locationGroups.find((entry) => entry.group_name === requestedGroup);
  if (!group) {
    return {
      selected_location_group: fallbackGroup,
      selected_location: fallbackLocation,
    };
  }
  const locations = Array.isArray(group.locations) ? group.locations : [];
  const hasLocation = locations.includes(requestedLocation);
  return {
    selected_location_group: requestedGroup,
    selected_location: hasLocation ? requestedLocation : String(locations[0] || fallbackLocation || ""),
  };
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
    nameRow.className = "name party-name-row";
    nameRow.textContent = String(member?.name ?? `Member ${idx + 1}`);
    content.appendChild(nameRow);

    const hpRow = document.createElement("div");
    hpRow.className = "hp party-hp-row";
    hpRow.textContent = `HP ${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}`;
    content.appendChild(hpRow);

    const levelRow = document.createElement("div");
    levelRow.className = "status party-level-row";
    levelRow.textContent = `Lv ${Number(member?.level ?? 0)}`;
    content.appendChild(levelRow);

    const memberStatusIcons = Array.isArray(member?.status_icons) ? member.status_icons : [];
    if (memberStatusIcons.length) {
      const iconRow = document.createElement("div");
      iconRow.className = "status-icon-row party-status-icons-row";
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

function makeSaveEnvelope(saveObj, options = {}) {
  return {
    version: 1,
    saved_at: new Date().toISOString(),
    selected_location_group: String(options?.selectedLocationGroup || currentSelectedLocationGroup || ""),
    selected_location: String(
      options?.selectedLocation || currentBattleSelection.selected_location || "",
    ),
    save: saveObj,
    menu_state: options?.menuState && typeof options.menuState === "object"
      ? options.menuState
      : null,
  };
}

function parseSaveEnvelope(raw) {
  if (!raw || typeof raw !== "object") return null;
  if (raw?.version === 1 && raw?.save && typeof raw.save === "object") {
    return {
      version: 1,
      saved_at: String(raw.saved_at || ""),
      selected_location_group: String(raw.selected_location_group || ""),
      selected_location: String(raw.selected_location || ""),
      save: raw.save,
      menu_state: raw?.menu_state && typeof raw.menu_state === "object"
        ? raw.menu_state
        : null,
    };
  }
  if (raw?.party && Array.isArray(raw.party)) {
    return makeSaveEnvelope(raw);
  }
  return null;
}

function restoreSaveEnvelopeFromStorage() {
  try {
    const text = localStorage.getItem(LOCAL_SAVE_STORAGE_KEY);
    if (!text) return null;
    const parsed = JSON.parse(text);
    return parseSaveEnvelope(parsed);
  } catch (_error) {
    return null;
  }
}

function parseMenuStateFromStorage() {
  try {
    const text = localStorage.getItem(LOCAL_MENU_STORAGE_KEY);
    if (!text) return {};
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function buildMenuViewState() {
  const storedMenuState = parseMenuStateFromStorage();
  const menuState = latestMenuState && typeof latestMenuState === "object" ? latestMenuState : {};
  const equipmentByMember = Array.isArray(menuState?.equipment_by_member)
    ? menuState.equipment_by_member
    : [];
  const party = Array.isArray(sessionStatus?.party)
    ? sessionStatus.party.map((member, index) => ({
      name: String(member?.name || ""),
      portrait_key: member?.portrait_key ?? null,
      image_name: member?.image_name ?? null,
      job: String(member?.job || "Unknown"),
      level: Number(member?.level ?? 0),
      row: String(member?.row || "front"),
      hp: Number(member?.hp ?? 0),
      max_hp: Number(member?.max_hp ?? 0),
      mp_levels: member?.mp_levels && typeof member.mp_levels === "object"
        ? member.mp_levels
        : {},
      status: member?.status && typeof member.status === "object"
        ? member.status
        : {},
      status_icons: Array.isArray(member?.status_icons)
        ? member.status_icons
        : [],
      equipment: member?.equipment && typeof member.equipment === "object"
        ? member.equipment
        : (equipmentByMember[index] && typeof equipmentByMember[index] === "object"
          ? equipmentByMember[index]
          : {}),
    }))
    : [];
  const resources = sessionStatus?.resources && typeof sessionStatus.resources === "object"
    ? sessionStatus.resources
    : {};
  const jobs = Array.isArray(menuState?.jobs)
    ? menuState.jobs.filter((jobName) => typeof jobName === "string" && jobName)
    : [];
  const jobCandidatesByMember = Array.isArray(menuState?.job_candidates_by_member)
    ? menuState.job_candidates_by_member
      .map((rows) => Array.isArray(rows)
        ? rows
          .filter((row) => row && typeof row === "object")
          .map((row) => ({
            job_name: String(row?.job_name || ""),
            cp_cost: Number(row?.cp_cost ?? 0),
            saved_job_level: Number(row?.saved_job_level ?? 1),
            is_current: Boolean(row?.is_current),
          }))
          .filter((row) => row.job_name)
        : [])
    : [];
  const equipCandidatesByMember = Array.isArray(menuState?.equip_candidates_by_member)
    ? menuState.equip_candidates_by_member
    : [];
  const magicSetup = menuState?.magic_setup && typeof menuState.magic_setup === "object"
    ? menuState.magic_setup
    : { stock_by_level: {}, equipped_by_member: [] };
  const magicCandidatesByMember = Array.isArray(sessionStatus?.magic_command_candidates_by_member)
    ? sessionStatus.magic_command_candidates_by_member
    : [];
  const magicSpellMetaByName = sessionStatus?.magic_spell_meta && typeof sessionStatus.magic_spell_meta === "object"
    ? sessionStatus.magic_spell_meta
    : {};
  return {
    ...storedMenuState,
    ...menuState,
    version: 1,
    updated_at: new Date().toISOString(),
    party,
    jobs,
    job_candidates_by_member: jobCandidatesByMember,
    equip_candidates_by_member: equipCandidatesByMember,
    magic_setup: magicSetup,
    magic_candidates_by_member: magicCandidatesByMember,
    magic_spell_meta_by_name: magicSpellMetaByName,
    resources: {
      cp: Number(resources?.cp ?? 0),
      cp_max: Number(resources?.cp_max ?? 255),
      gil: Number(resources?.gil ?? 0),
    },
  };
}

function syncMenuViewStateToStorage() {
  try {
    localStorage.setItem(
      LOCAL_MENU_STORAGE_KEY,
      JSON.stringify(buildMenuViewState()),
    );
  } catch (_error) {
    // ignore storage write failure in wasm runner.
  }
}

function parseMenuStateCandidate(raw) {
  if (!raw || typeof raw !== "object") return null;
  const jobs = Array.isArray(raw?.jobs) ? raw.jobs : [];
  const candidates = Array.isArray(raw?.job_candidates_by_member) ? raw.job_candidates_by_member : [];
  const equipCandidates = Array.isArray(raw?.equip_candidates_by_member)
    ? raw.equip_candidates_by_member
    : [];
  const magicSetup = raw?.magic_setup && typeof raw.magic_setup === "object"
    ? raw.magic_setup
    : { stock_by_level: {}, equipped_by_member: [] };
  const equipmentByMember = Array.isArray(raw?.equipment_by_member)
    ? raw.equipment_by_member
    : [];
  const magicCandidatesByMember = Array.isArray(raw?.magic_candidates_by_member)
    ? raw.magic_candidates_by_member
    : [];
  const magicSpellMetaByName = raw?.magic_spell_meta_by_name && typeof raw.magic_spell_meta_by_name === "object"
    ? raw.magic_spell_meta_by_name
    : {};
  const resources = raw?.resources && typeof raw.resources === "object" ? raw.resources : {};
  return {
    ...raw,
    jobs,
    job_candidates_by_member: candidates,
    equip_candidates_by_member: equipCandidates,
    magic_setup: magicSetup,
    equipment_by_member: equipmentByMember,
    magic_candidates_by_member: magicCandidatesByMember,
    magic_spell_meta_by_name: magicSpellMetaByName,
    resources: {
      cp: Number(resources?.cp ?? 0),
      cp_max: Number(resources?.cp_max ?? 255),
      gil: Number(resources?.gil ?? 0),
    },
  };
}

function refreshMenuStateFromPyodide() {
  if (!pyodide) return null;
  const getter = pyodide.globals.get("get_menu_state_json");
  if (!getter) return null;
  try {
    const raw = JSON.parse(String(getter() || "{}"));
    const next = parseMenuStateCandidate(raw);
    if (next) latestMenuState = next;
    return next;
  } catch (_error) {
    return null;
  }
}

function getCurrentMenuStateForPersistence() {
  const fromStorage = parseMenuStateFromStorage();
  const fromRuntime = latestMenuState && typeof latestMenuState === "object" ? latestMenuState : {};
  return {
    ...fromStorage,
    ...fromRuntime,
  };
}

function persistSaveEnvelopeToStorage(envelope) {
  if (!envelope) return false;
  try {
    localStorage.setItem(LOCAL_SAVE_STORAGE_KEY, JSON.stringify(envelope));
    return true;
  } catch (_error) {
    return false;
  }
}

function downloadSaveEnvelope(envelope) {
  if (!envelope) return false;
  const payload = JSON.stringify(envelope, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  anchor.href = url;
  anchor.download = `ffiii_savedata_${stamp}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return true;
}

function setSaveButtonsEnabled(enabled) {
  if (downloadSaveBtn) {
    downloadSaveBtn.disabled = !enabled;
  }
}

function bindReturnToLocationOnClick() {
  if (returnToLocationBound || !battleLogFrame) return;
  returnToLocationBound = true;
  battleLogFrame.classList.add("is-clickable-next");
  const onClick = () => {
    window.location.href = "./index.html";
  };
  battleLogFrame.addEventListener("click", onClick, { once: true });
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
  syncMenuViewStateToStorage();
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
    const bootstrapResponse = await fetch("./bootstrap_runtime.py");
  if (!bootstrapResponse.ok) {
    throw new Error(`bootstrap_runtime.py fetch failed: ${bootstrapResponse.status}`);
  }
  const bootstrapPython = await bootstrapResponse.text();
  await pyodide.runPythonAsync(bootstrapPython);

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];
  currentBattleSelection = resolveBattleSelection(selectionPayload);

  const storedEnvelope = restoreSaveEnvelopeFromStorage();
  if (storedEnvelope?.save) {
    loadedSaveData = storedEnvelope.save;
    if (!hasSessionBattleStartSelection && storedEnvelope.selected_location_group) {
      currentBattleSelection.selected_location_group = String(storedEnvelope.selected_location_group);
    }
    if (!hasSessionBattleStartSelection && storedEnvelope.selected_location) {
      currentBattleSelection.selected_location = String(storedEnvelope.selected_location);
    }
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
  setSaveButtonsEnabled(Boolean(storedEnvelope?.save));
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
  refreshMenuStateFromPyodide();
}

function resolveSaveDataForBoot() {
  if (loadedSaveData && typeof loadedSaveData === "object") {
    return loadedSaveData;
  }
  const storedEnvelope = restoreSaveEnvelopeFromStorage();
  if (storedEnvelope?.save && typeof storedEnvelope.save === "object") {
    return storedEnvelope.save;
  }
  return null;
}

function bootLocationAndSyncSession() {
  if (!pyodide) return null;
  const bootForLocation = pyodide.globals.get("boot_engine_for_location");
  const bootWithSave = pyodide.globals.get("boot_engine_for_location_with_save_json");
  const saveDataForBoot = resolveSaveDataForBoot();
  const selectedGroup = String(currentBattleSelection.selected_location_group || "");
  const selectedLocation = String(currentBattleSelection.selected_location || "");
  const payload = JSON.parse(saveDataForBoot
    ? bootWithSave(
      selectedGroup,
      selectedLocation,
      JSON.stringify(saveDataForBoot),
      7,
    )
    : bootForLocation(
      selectedGroup,
      selectedLocation,
      7,
    ));
  loadedSaveData = null;
  currentSelectedLocationGroup = String(
    payload?.selected_location_group || selectedGroup || "",
  );
  currentBattleSelection = {
    selected_location_group: String(payload?.selected_location_group || selectedGroup || ""),
    selected_location: String(payload?.selected_location || selectedLocation || ""),
  };
  sessionStatus = payload?.session_status ?? { party: [], enemies: [] };
  latestMenuState = parseMenuStateCandidate(payload?.menu_state) || latestMenuState;
  lifecycleState = "ready_for_actions";
  battleFinished = false;
  applyFullRecoverParty();
  refreshMenuStateFromPyodide();
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
  latestMenuState = parseMenuStateCandidate(result?.menu_state) || latestMenuState;
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
  if (battleFinished) {
    const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
    const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
    if (saveJson) {
      try {
        const saveObj = JSON.parse(saveJson);
        const envelope = makeSaveEnvelope(saveObj, {
          selectedLocationGroup: result?.selected_location_group,
          selectedLocation: result?.selected_location,
          menuState: getCurrentMenuStateForPersistence(),
        });
        if (persistSaveEnvelopeToStorage(envelope)) {
          statusLine.textContent = "戦闘終了データをブラウザに保存しました。";
          setSaveButtonsEnabled(true);
        } else {
          statusLine.textContent = "ブラウザ保存に失敗しました。";
        }
      } catch (_error) {
        statusLine.textContent = "保存データの生成に失敗しました。";
      }
    }
    statusLine.textContent = "戦闘終了。クリックでLocation選択画面に戻ります。";
    bindReturnToLocationOnClick();
  }

  refreshMenuStateFromPyodide();
  rerenderAll();
}

if (menuBtn) {
  menuBtn.addEventListener("click", () => {
    refreshMenuStateFromPyodide();
    syncMenuViewStateToStorage();
    window.location.href = "./menu.html";
  });
}

if (locationBtn) {
  locationBtn.addEventListener("click", () => {
    refreshMenuStateFromPyodide();
    syncMenuViewStateToStorage();
    window.location.href = "./index.html";
  });
}

if (loadSaveBtn) {
  loadSaveBtn.addEventListener("click", () => {
    if (!loadSaveInput) return;
    loadSaveInput.value = "";
    loadSaveInput.click();
  });
}

if (loadSaveInput) {
  loadSaveInput.addEventListener("change", async (event) => {
    const file = event?.target?.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      const envelope = parseSaveEnvelope(parsed);
      if (!envelope?.save) {
        statusLine.textContent = "ロード失敗: セーブデータ形式が不正です。";
        return;
      }
      loadedSaveData = envelope.save;
      if (envelope.selected_location_group) {
        currentBattleSelection.selected_location_group = String(envelope.selected_location_group);
      }
      if (envelope.selected_location) {
        currentBattleSelection.selected_location = String(envelope.selected_location);
      }
      if (persistSaveEnvelopeToStorage(envelope)) {
        setSaveButtonsEnabled(true);
      }
      if (envelope?.menu_state && typeof envelope.menu_state === "object") {
        latestMenuState = parseMenuStateCandidate(envelope.menu_state) || latestMenuState;
        syncMenuViewStateToStorage();
      }
      bootLocationAndSyncSession();
      resetPendingActionsForParty();
      currentMemberIndex = firstActionableMemberIndex();
      selectedEnemyIndex = 0;
      enterCommandMode();
      battlePhase.textContent = "セーブデータをロードしました。";
      logView.textContent = "(not executed)";
      setCommandLogLayout({ showCommand: true });
      rewardPanel.classList.remove("open");
      rewardPanel.textContent = "";
      rerenderAll();
    } catch (_error) {
      statusLine.textContent = "ロード失敗: JSON を読み込めませんでした。";
    }
  });
}

if (downloadSaveBtn) {
  downloadSaveBtn.addEventListener("click", () => {
    const envelope = restoreSaveEnvelopeFromStorage();
    if (!envelope) {
      statusLine.textContent = "保存できるセーブデータがありません。";
      return;
    }
    if (downloadSaveEnvelope(envelope)) {
      statusLine.textContent = "セーブデータをローカルに保存しました。";
    } else {
      statusLine.textContent = "セーブデータの保存に失敗しました。";
    }
  });
}

rerenderAll();
bootEngine().catch((error) => {
  battlePhase.textContent = `起動失敗: ${String(error)}`;
  statusLine.textContent = "エンジン起動に失敗しました。ページを再読み込みしてください。";
});
