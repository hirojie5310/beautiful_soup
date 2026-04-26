import { getPyodideRuntime } from "./pyodide_runtime.js";
import {
  applyEventToPlaybackStatus,
  applyNamedPopupOverrides,
} from "./battle_playback.js";
import {
  DEFAULT_BATTLE_RETURN_CONTEXT,
  resolveMountedBattleReturnContext,
} from "./battle_context.js";
import {
  normalizeMemberIndexedRows,
  normalizePartyIdentityOrder,
  resolveFaceImageCandidates,
} from "./shared_party.js";
import {
  readCachedImageUrl,
  resolveCachedImageUrl,
} from "./image_cache.js";
import {
  AUTO_SAVE_SLOT_ID,
  LOCAL_MENU_STORAGE_KEY,
  parseSaveEnvelope,
  persistSaveEnvelopeToIndexedDB,
  restoreSaveEnvelopeFromStorage,
  restoreSaveEnvelopeFromStorageAsync,
  parseMenuStateFromStorage,
  makeSaveEnvelope,
  persistSaveEnvelopeToStorage,
} from "./shared_storage.js";
import { resolveLocationMapImageUrl } from "./map_images.js";

let battlePhase = null;
let partyGrid = null;
let enemyGrid = null;
let commandFrame = null;
let battleLogFrame = null;
let commandGrid = null;
let statusLine = null;
let logView = null;
let plannedActionsView = null;
let rewardPanel = null;
let battleLogToggleBtn = null;
let actionSheet = null;
let actionSheetBackdrop = null;
let actionSheetTitle = null;
let actionSheetBody = null;
let actionSheetCloseBtn = null;
let locationBtn = null;
let menuBtn = null;
let loadSaveBtn = null;
let loadSaveInput = null;
let downloadSaveBtn = null;
let enemyFrame = null;
let appStore = null;
let appNavigate = null;

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
let activeLogPlaybackId = 0;
let loadedSaveData = null;
let cachedStoredEnvelope = null;
let returnToLocationBound = false;
let activeCombatPopups = {};
let activeCombatEffects = {};
let suppressMenuStateSync = false;
let battleLogExpanded = false;
const partyCardCache = new Map();
const enemyCardCache = new Map();
const statusIconRowCache = new WeakMap();
const PYTHON_BUNDLE_VERSION = "20260406c";
const ATTACK_EFFECT_SHEET_NAME = "ef_slash_frames.png";

const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";
const BATTLE_BOOT_DEBUG_TAG = "[battle-boot-debug]";

function summarizePartyForBattleBoot(party) {
  if (!Array.isArray(party)) return [];
  return party.map((member, index) => {
    const jobLevels = member?.job_levels && typeof member.job_levels === "object"
      ? Object.fromEntries(
        Object.entries(member.job_levels).map(([jobName, row]) => [
          String(jobName || ""),
          {
            level: Number(row?.level ?? row ?? 0),
            skill_point: Number(row?.skill_point ?? 0),
          },
        ]),
      )
      : {};
    return {
      index,
      name: String(member?.name || ""),
      job: String(member?.job || ""),
      current_job: String(member?.current_job || ""),
      job_level: member?.job_level && typeof member.job_level === "object"
        ? {
          level: Number(member.job_level.level ?? 0),
          skill_point: Number(member.job_level.skill_point ?? 0),
        }
        : member?.job_level ?? null,
      job_levels: jobLevels,
      equipment: member?.equipment && typeof member.equipment === "object"
        ? {
          main_hand: member.equipment.main_hand ?? null,
          off_hand: member.equipment.off_hand ?? null,
          head: member.equipment.head ?? null,
          body: member.equipment.body ?? null,
          arms: member.equipment.arms ?? null,
        }
        : null,
      Magic: member?.Magic && typeof member.Magic === "object"
        ? member.Magic
        : null,
      magic_setup: member?.magic_setup && typeof member.magic_setup === "object"
        ? member.magic_setup
        : null,
    };
  });
}

function logBattleBootDebug(label, party) {
  try {
    console.info(BATTLE_BOOT_DEBUG_TAG, label, summarizePartyForBattleBoot(party));
  } catch (_error) {
    // ignore debug logging failure
  }
}

function bindDom(root = document) {
  battlePhase = root.querySelector("#battlePhase");
  partyGrid = root.querySelector("#partyGrid");
  enemyGrid = root.querySelector("#enemyGrid");
  commandFrame = root.querySelector("#commandFrame");
  battleLogFrame = root.querySelector("#battleLogFrame");
  commandGrid = root.querySelector("#commandGrid");
  statusLine = root.querySelector("#statusLine");
  logView = root.querySelector("#logView");
  plannedActionsView = root.querySelector("#plannedActionsView");
  rewardPanel = root.querySelector("#rewardPanel");
  battleLogToggleBtn = root.querySelector("#battleLogToggleBtn");
  actionSheet = root.querySelector("#actionSheet");
  actionSheetBackdrop = root.querySelector("#actionSheetBackdrop");
  actionSheetTitle = root.querySelector("#actionSheetTitle");
  actionSheetBody = root.querySelector("#actionSheetBody");
  actionSheetCloseBtn = root.querySelector("#actionSheetCloseBtn");
  locationBtn = root.querySelector("#locationBtn");
  menuBtn = root.querySelector("#menuBtn");
  loadSaveBtn = root.querySelector("#loadSaveBtn");
  loadSaveInput = root.querySelector("#loadSaveInput");
  downloadSaveBtn = root.querySelector("#downloadSaveBtn");
  enemyFrame = root.querySelector("#enemyFrame");
}

function readBattleStartSelectionFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_START_SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return {
        selected_location_group: String(parsed.selected_location_group || ""),
        selected_location: String(parsed.selected_location || ""),
        enemy_names: Array.isArray(parsed.enemy_names)
          ? parsed.enemy_names.map((name) => String(name || "")).filter((name) => Boolean(name))
          : [],
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}

function readBattleReturnContextFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_RETURN_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function writeBattleReturnContextToSession(nextContext) {
  try {
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify(nextContext || {}));
    battleReturnContext = nextContext && typeof nextContext === "object"
      ? nextContext
      : { ...DEFAULT_BATTLE_RETURN_CONTEXT };
  } catch (_error) {
    // ignore session persistence failures
  }
}

function readBattleSelectionFromStore() {
  if (!appStore) return null;
  const state = appStore.getState();
  return {
    selected_location_group: String(state?.selectedLocationGroup || ""),
    selected_location: String(state?.selectedLocation || ""),
  };
}

const sessionBattleStartSelection = readBattleStartSelectionFromSession();
const storeBattleStartSelection = readBattleSelectionFromStore();
const hasSessionBattleStartSelection = Boolean(
  sessionBattleStartSelection?.selected_location_group || sessionBattleStartSelection?.selected_location,
);

let currentBattleSelection = sessionBattleStartSelection || storeBattleStartSelection || {
  selected_location_group: "",
  selected_location: "",
  enemy_names: [],
};
let battleReturnContext = resolveMountedBattleReturnContext(readBattleReturnContextFromSession());

const COMMAND_LABELS = {
  Fight: "たたかう",
  Defend: "ぼうぎょ",
  Run: "にげる",
  Flee: "にげる",
  Item: "アイテム",
  Magic: "まほう",
  Cheer: "おうえん",
};

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
      enemy_names: Array.isArray(currentBattleSelection.enemy_names)
        ? currentBattleSelection.enemy_names
        : [],
    };
  }
  const locations = Array.isArray(group.locations) ? group.locations : [];
  const hasLocation = locations.includes(requestedLocation);
  return {
    selected_location_group: requestedGroup,
    selected_location: hasLocation ? requestedLocation : String(locations[0] || fallbackLocation || ""),
    enemy_names: Array.isArray(currentBattleSelection.enemy_names)
      ? currentBattleSelection.enemy_names
      : [],
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

function applyCachedImageSource(target, candidates, { onLoad, onError } = {}) {
  if (!target) return;
  const cachedUrl = readCachedImageUrl(candidates);
  if (cachedUrl !== null) {
    if (cachedUrl) {
      if ("src" in target) {
        target.src = cachedUrl;
      } else {
        target.style.backgroundImage = `url("${cachedUrl}")`;
      }
      if (typeof onLoad === "function") onLoad(cachedUrl);
      return;
    }
    if (typeof onError === "function") onError();
    return;
  }

  resolveCachedImageUrl(candidates, {
    onResolved: (resolvedUrl) => {
      if (resolvedUrl) {
        if ("src" in target) {
          target.src = resolvedUrl;
        } else {
          target.style.backgroundImage = `url("${resolvedUrl}")`;
        }
        if (typeof onLoad === "function") onLoad(resolvedUrl);
        return;
      }
      if (typeof onError === "function") onError();
    },
  });
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

function renderStatusIcons(iconRow, iconKeys) {
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

function syncManagedCardImage(state, candidates) {
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
  card.addEventListener("click", () => {
    if (battleFinished) return;
    const enemy = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies[idx] : null;
    if (isOutOfBattleEnemy(enemy)) return;
    selectedEnemyIndex = idx;
    renderEnemies();
    renderStatus();
  });

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

function getPartyCardState(idx) {
  if (!partyCardCache.has(idx)) {
    partyCardCache.set(idx, createPartyCardState(idx));
  }
  return partyCardCache.get(idx);
}

function getEnemyCardState(idx) {
  if (!enemyCardCache.has(idx)) {
    enemyCardCache.set(idx, createEnemyCardState(idx));
  }
  return enemyCardCache.get(idx);
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

function findPreviousCommittedMemberIndex(startIdx) {
  const actionable = actionableMemberIndices();
  if (!actionable.length) return null;
  const rawStartPos = actionable.indexOf(startIdx);
  const startPos = rawStartPos >= 0 ? rawStartPos : 0;
  for (let step = 1; step <= actionable.length; step += 1) {
    const idx = actionable[(startPos - step + actionable.length) % actionable.length];
    if (pendingActions[idx]) return idx;
  }
  return null;
}

function canGoBackToPreviousMember() {
  if (battleFinished) return false;
  return findPreviousCommittedMemberIndex(currentMemberIndex) !== null;
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

function setActionSheetOpen(open) {
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

function closeActionSheetToCommand() {
  enterCommandMode();
  rerenderAll();
}

function handleActionSheetDismiss() {
  if (inputMode === "pick_magic" || inputMode === "pick_item") {
    closeActionSheetToCommand();
    return;
  }
  if (inputMode === "pick_side") {
    returnToSourceSelection();
    return;
  }
  if (inputMode === "pick_target") {
    if (shouldReturnToSideSelection()) {
      inputMode = "pick_side";
    } else {
      inputMode = sourceSelectionModeForDraft();
      if (inputMode === "command") {
        pendingActionDraft = null;
      }
    }
    rerenderAll();
  }
}

function sourceSelectionModeForDraft() {
  if (pendingActionDraft?.kind === "magic") return "pick_magic";
  if (pendingActionDraft?.kind === "item") return "pick_item";
  return "command";
}

function returnToSourceSelection() {
  inputMode = sourceSelectionModeForDraft();
  if (inputMode === "command") {
    pendingActionDraft = null;
  }
  rerenderAll();
}

function shouldReturnToSideSelection() {
  return Boolean(pendingActionDraft?.requires_side_choice);
}

function createSheetButton(label, onClick, { disabled = false } = {}) {
  const button = document.createElement("button");
  button.className = "btn";
  button.type = "button";
  button.disabled = disabled;
  button.textContent = String(label || "");
  button.addEventListener("click", onClick);
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

function currentActorName() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const actor = party[currentMemberIndex];
  return String(actor?.name || "");
}

function renderMagicActionSheet() {
  if (!actionSheetBody || !actionSheetTitle) return;
  const actorName = currentActorName();
  actionSheetTitle.textContent = actorName
    ? `${actorName} の魔法`
    : "魔法を選択";
  actionSheetBody.innerHTML = "";

  const backGrid = createActionSheetGrid();
  backGrid.appendChild(createSheetButton("← コマンドにもどる", () => {
    closeActionSheetToCommand();
  }));
  actionSheetBody.appendChild(backGrid);

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
    const { section, grid } = createActionSheetSection(group.header, { magicLevel: true });
    group.spells.forEach((cand) => {
      grid.appendChild(createSheetButton(
        String(cand?.label || cand?.name || "(magic)"),
        () => chooseMagic(cand),
        { disabled: !pyodide || battleFinished },
      ));
    });
    actionSheetBody.appendChild(section);
  });
}

function renderItemActionSheet() {
  if (!actionSheetBody || !actionSheetTitle) return;
  const actorName = currentActorName();
  actionSheetTitle.textContent = actorName
    ? `${actorName} のアイテム`
    : "アイテムを選択";
  actionSheetBody.innerHTML = "";

  const grid = createActionSheetGrid();
  grid.appendChild(createSheetButton("← コマンドにもどる", () => {
    closeActionSheetToCommand();
  }));
  currentItemCandidates().forEach((cand) => {
    grid.appendChild(createSheetButton(
      String(cand?.label || cand?.name || "(item)"),
      () => chooseItem(cand),
      { disabled: !pyodide || battleFinished },
    ));
  });
  actionSheetBody.appendChild(grid);
}

function renderTargetSideActionSheet() {
  if (!actionSheetBody || !actionSheetTitle) return;
  const actorName = currentActorName();
  actionSheetTitle.textContent = actorName
    ? `${actorName} の対象サイド`
    : "対象サイドを選択";
  actionSheetBody.innerHTML = "";

  const grid = createActionSheetGrid();
  grid.appendChild(createSheetButton("← まほう・アイテム選択にもどる", () => {
    returnToSourceSelection();
  }));
  grid.appendChild(createSheetButton("敵を対象にする", () => {
    pendingActionDraft = { ...(pendingActionDraft || {}), target_side: "enemy" };
    inputMode = "pick_target";
    rerenderAll();
  }));
  grid.appendChild(createSheetButton("味方を対象にする", () => {
    pendingActionDraft = { ...(pendingActionDraft || {}), target_side: "ally" };
    inputMode = "pick_target";
    rerenderAll();
  }));
  actionSheetBody.appendChild(grid);
}

function renderTargetActionSheet() {
  if (!actionSheetBody || !actionSheetTitle) return;
  const actorName = currentActorName();
  const side = pendingActionDraft?.target_side || "enemy";
  const sideLabel = side === "ally" ? "味方" : "敵";
  actionSheetTitle.textContent = actorName
    ? `${actorName} の対象選択`
    : `${sideLabel}対象を選択`;
  actionSheetBody.innerHTML = "";

  const grid = createActionSheetGrid();
  const backLabel = shouldReturnToSideSelection()
    ? "← 対象サイド選択にもどる"
    : "← まほう・アイテム選択にもどる";
  grid.appendChild(createSheetButton(backLabel, () => {
    if (shouldReturnToSideSelection()) {
      inputMode = "pick_side";
    } else {
      inputMode = sourceSelectionModeForDraft();
      if (inputMode === "command") {
        pendingActionDraft = null;
      }
    }
    rerenderAll();
  }));

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
      () => finalizeDraftAction(0, { targetAll: true }),
    ));
  }

  if (side === "ally") {
    const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
    party.forEach((member, idx) => {
      grid.appendChild(createSheetButton(
        `味方: ${member?.name || `Member ${idx + 1}`}`,
        () => finalizeDraftAction(idx),
      ));
    });
  } else {
    const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
    enemies.forEach((enemy, idx) => {
      if (isOutOfBattleEnemy(enemy)) return;
      grid.appendChild(createSheetButton(
        `敵: ${enemy?.name || `Enemy ${idx + 1}`}`,
        () => finalizeDraftAction(idx),
      ));
    });
  }

  actionSheetBody.appendChild(grid);
}

function cloneJsonValue(value) {
  return JSON.parse(JSON.stringify(value ?? null));
}

function asPlainObject(value) {
  return value && typeof value === "object" ? value : {};
}

function asArrayValue(value) {
  return Array.isArray(value) ? value : [];
}

function combatPopupKey(side, index) {
  return `${String(side || "")}:${Number(index ?? -1)}`;
}

function popupForTarget(side, index) {
  return activeCombatPopups[combatPopupKey(side, index)] || null;
}

function effectForTarget(side, index) {
  return activeCombatEffects[combatPopupKey(side, index)] || null;
}

function resolveAttackEffectImageCandidates(fileName = ATTACK_EFFECT_SHEET_NAME) {
  const safeName = encodeURIComponent(String(fileName || ATTACK_EFFECT_SHEET_NAME).trim());
  if (!safeName) return [];
  return [
    `/web_wasm/effects/${safeName}`,
    `./effects/${safeName}`,
    `../assets/images/effects/${safeName}`,
    new URL(`../assets/images/effects/${safeName}`, import.meta.url).href,
    `/assets/images/effects/${safeName}`,
  ];
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

function appendCombatEffect(card, effect) {
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

function normalizeStatusIconKey(raw) {
  return String(raw || "").trim().toLowerCase().replace(/^status\./, "");
}

function parseActionHeaderMeta(line, actorOccurrenceMap) {
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

function buildPlaybackEventsByBlock(blocks, events) {
  const actorOccurrenceMap = new Map();
  const pendingEvents = Array.isArray(events) ? [...events] : [];
  let cursor = 0;
  return blocks.map((block) => {
    if (block.type !== "action") return [];
    const firstLine = Array.isArray(block.lines) ? block.lines[0] : "";
    const { actorSide, actorIndex } = parseActionHeaderMeta(firstLine, actorOccurrenceMap);
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
      if (
        nextActorSide !== actorSide
        || nextActorIndex !== Number(actorIndex)
      ) {
        if (blockEvents.length === 0) {
          break;
        }
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

function extractPopupValueQueue(block) {
  const queue = [];
  (Array.isArray(block?.lines) ? block.lines : []).forEach((lineRaw) => {
    const line = String(lineRaw || "").trim();
    let match = line.match(/(?:に|は)(\d+)のダメージ(?:を受けた)?[。！]?/);
    if (match) {
      queue.push({ kind: "damage", value: Number(match[1]) });
      return;
    }

    match = line.match(/HP(?:が|を)(\d+)回復(?:した)?[。！]?/);
    if (match) {
      queue.push({ kind: "heal", value: Number(match[1]) });
      return;
    }

    if (line.includes("ダメージを与えられなかった") || line.includes("（ミス）") || line.endsWith("ミス")) {
      queue.push({ kind: "miss", value: 0 });
    }
  });
  return queue;
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

function buildNamedCombatEffects(block, playbackStatus) {
  const firstLine = Array.isArray(block?.lines) ? String(block.lines[0] || "") : "";
  const { actorSide } = parseActionHeaderMeta(firstLine, new Map());
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

function applyNamedCombatEffect(playbackStatus, effect) {
  if (!effect || !playbackStatus || typeof playbackStatus !== "object") return null;
  const side = String(effect.side || "");
  const index = Number(effect.index ?? -1);
  const value = Number(effect.value ?? 0);
  const kind = String(effect.kind || "");
  const collection = side === "enemy" ? playbackStatus.enemies : playbackStatus.party;
  if (!Array.isArray(collection) || index < 0 || index >= collection.length) return null;
  const target = collection[index];
  if (!target || typeof target !== "object") return null;

  if (kind === "damage") {
    const currentHp = Number(target?.hp ?? 0);
    const nextHp = Math.max(0, currentHp - value);
    target.hp = nextHp;
    target.out_of_battle = nextHp <= 0 ? true : Boolean(target.out_of_battle);
    if (target?.status && typeof target.status === "object") {
      target.status.hp = nextHp;
    }
  } else if (kind === "heal") {
    const currentHp = Number(target?.hp ?? 0);
    const maxHp = Number(target?.max_hp ?? currentHp);
    const nextHp = Math.min(maxHp, currentHp + value);
    target.hp = nextHp;
    target.out_of_battle = false;
    if (target?.status && typeof target.status === "object") {
      target.status.hp = nextHp;
    }
  }

  return {
    side,
    index,
    effect: kind === "damage" && value > 0
      ? {
        kind: "slash",
        sheetName: ATTACK_EFFECT_SHEET_NAME,
      }
      : null,
    popup: kind === "status"
      ? {
        kind,
        text: String(effect?.text || ""),
        statusCategory: String(effect?.statusCategory || "inflict"),
      }
      : {
        kind,
        value,
      },
  };
}

function renderParty() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const activeKeys = new Set();
  party.forEach((member, idx) => {
    const activeClass = idx === currentMemberIndex && !battleFinished ? " active" : "";
    const cardState = getPartyCardState(idx);
    activeKeys.add(idx);
    cardState.card.className = `card party-card${activeClass}`;
    cardState.nameRow.textContent = String(member?.name ?? `Member ${idx + 1}`);
    cardState.hpRow.textContent = `${Number(member?.hp ?? 0)} / ${Number(member?.max_hp ?? 0)}`;
    cardState.levelRow.textContent = `Lv ${Number(member?.level ?? 0)}`;
    applyHudHpBar(cardState.hpBarFill, member);
    syncManagedCardImage(cardState, resolveFaceImageCandidates(member, idx));
    renderStatusIcons(cardState.iconRow, member?.status_icons);
    clearCardOverlayLayers(cardState.card);
    appendCombatEffect(cardState.card, effectForTarget("char", idx));
    appendCombatPopup(cardState.card, popupForTarget("char", idx));
    partyGrid.appendChild(cardState.card);
  });
  partyCardCache.forEach((cardState, key) => {
    if (activeKeys.has(key)) return;
    cardState.card.remove();
  });
}

function renderEnemies() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  if (enemyGrid) {
    enemyGrid.dataset.count = String(enemies.length);
  }
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
  const activeKeys = new Set();
  enemies.forEach((enemy, idx) => {
    const selectedClass = idx === selectedEnemySafeIndex() ? " selected" : "";
    const cardState = getEnemyCardState(idx);
    activeKeys.add(idx);
    cardState.card.className = `card target enemy-card${selectedClass}`;
    cardState.nameRow.textContent = String(enemy?.name ?? `Enemy ${idx + 1}`);
    cardState.hpRow.textContent = `HP ${Number(enemy?.hp ?? 0)} / ${Number(enemy?.max_hp ?? 0)}`;
    applyHudHpBar(cardState.hpBarFill, enemy);
    syncManagedCardImage(cardState, resolveEnemyImageCandidates(enemy));
    renderStatusIcons(cardState.iconRow, enemy?.status_icons);
    clearCardOverlayLayers(cardState.card);
    appendCombatEffect(cardState.card, effectForTarget("enemy", idx));
    appendCombatPopup(cardState.card, popupForTarget("enemy", idx));
    enemyGrid.appendChild(cardState.card);
  });
  enemyCardCache.forEach((cardState, key) => {
    if (activeKeys.has(key)) return;
    cardState.card.remove();
  });
}

function renderCommandButtons() {
  commandGrid.innerHTML = "";
  if (inputMode === "pick_magic") {
    setActionSheetOpen(true);
    renderMagicActionSheet();
  } else if (inputMode === "pick_item") {
    setActionSheetOpen(true);
    renderItemActionSheet();
  } else if (inputMode === "pick_side") {
    setActionSheetOpen(true);
    renderTargetSideActionSheet();
  } else if (inputMode === "pick_target") {
    setActionSheetOpen(true);
    renderTargetActionSheet();
  } else {
    setActionSheetOpen(false);
  }
  if (commandFrame) {
    const expanded = inputMode === "pick_side"
      || inputMode === "pick_target";
    commandFrame.classList.toggle("command-frame-expanded", expanded);
  }
  commandGrid.classList.toggle("command-mode", inputMode === "command");
  if (inputMode === "pick_magic") {
    return;
  }

  if (inputMode === "pick_item") {
    return;
  }

  if (inputMode === "pick_side") {
    return;
  }

  if (inputMode === "pick_target") {
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

  if (canGoBackToPreviousMember()) {
    const backBtn = document.createElement("button");
    backBtn.className = "btn";
    backBtn.type = "button";
    backBtn.textContent = "← 戻る";
    backBtn.addEventListener("click", () => {
      goBackToPreviousMemberAction();
    });
    commandGrid.appendChild(backBtn);
  }
}

function goBackToPreviousMemberAction() {
  const prevIndex = findPreviousCommittedMemberIndex(currentMemberIndex);
  if (prevIndex === null) return;
  pendingActions[prevIndex] = null;
  currentMemberIndex = prevIndex;
  enterCommandMode();
  battlePhase.textContent = `${committedActionCount()}/${requiredActionCount()} 入力済み`;
  rerenderAll();
}

function renderPlannedActions() {
  if (!plannedActionsView) return;
  plannedActionsView.textContent = pendingActions.length
    ? JSON.stringify(pendingActions, null, 2)
    : "(none)";
}

function setBattleLogExpanded(expanded) {
  battleLogExpanded = Boolean(expanded);
  if (battleLogFrame) {
    battleLogFrame.classList.toggle("open", battleLogExpanded);
  }
  if (battleLogToggleBtn) {
    battleLogToggleBtn.textContent = battleLogExpanded ? "ログを閉じる" : "ログを開く";
    battleLogToggleBtn.setAttribute("aria-expanded", battleLogExpanded ? "true" : "false");
  }
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

function normalizeVictoryRewards(payload, beforeResources, afterResources) {
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

function injectResourceDiffsIntoRewardLogs(logs, rewards) {
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

function compactSaveEnvelope(envelope) {
  if (!envelope || typeof envelope !== "object") return null;
  if (!envelope.save || typeof envelope.save !== "object") return null;
  return {
    version: 1,
    saved_at: String(envelope.saved_at || ""),
    selected_location_group: String(envelope.selected_location_group || ""),
    selected_location: String(envelope.selected_location || ""),
    save: envelope.save,
    menu_state: null,
  };
}

function buildMenuViewState() {
  const storedMenuState = parseMenuStateFromStorage();
  const menuState = latestMenuState && typeof latestMenuState === "object" ? latestMenuState : {};
  const equipmentByMember = Array.isArray(menuState?.equipment_by_member)
    ? menuState.equipment_by_member
    : [];
  const party = Array.isArray(sessionStatus?.party)
    ? sessionStatus.party.map((member, index) => {
      const status = member?.status && typeof member.status === "object"
        ? member.status
        : {};
      return {
        index: Number(member?.index ?? index),
        name: String(member?.name || ""),
        portrait_key: member?.portrait_key ?? null,
        image_name: member?.image_name ?? null,
        job: String(member?.job || "Unknown"),
        level: Number(status?.level ?? member?.level ?? 0),
        exp: Number(status?.exp ?? member?.exp ?? 0),
        row: String(member?.row || "front"),
        hp: Number(member?.hp ?? 0),
        max_hp: Number(member?.max_hp ?? 0),
        mp_levels: member?.mp_levels && typeof member.mp_levels === "object"
          ? member.mp_levels
          : {},
        status,
        status_icons: Array.isArray(member?.status_icons)
          ? member.status_icons
          : [],
        equipment: member?.equipment && typeof member.equipment === "object"
          ? member.equipment
          : (equipmentByMember[index] && typeof equipmentByMember[index] === "object"
            ? equipmentByMember[index]
            : {}),
      };
    })
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
  if (suppressMenuStateSync) return;
  const nextState = buildMenuViewState();
  if (appStore) {
    appStore.updateMenuState(nextState);
    return;
  }
  try {
    localStorage.setItem(
      LOCAL_MENU_STORAGE_KEY,
      JSON.stringify(nextState),
    );
  } catch (_error) {
    // ignore storage write failure in wasm runner.
  }
}

function parseMenuStateCandidate(raw) {
  if (!raw || typeof raw !== "object") return null;
  const sourceParty = Array.isArray(raw?.party) ? raw.party : [];
  const normalizedParty = normalizePartyIdentityOrder(sourceParty);
  const jobs = Array.isArray(raw?.jobs) ? raw.jobs : [];
  const candidates = Array.isArray(raw?.job_candidates_by_member)
    ? normalizeMemberIndexedRows(sourceParty, raw.job_candidates_by_member)
    : [];
  const equipCandidates = Array.isArray(raw?.equip_candidates_by_member)
    ? normalizeMemberIndexedRows(sourceParty, raw.equip_candidates_by_member)
    : [];
  const magicSetup = raw?.magic_setup && typeof raw.magic_setup === "object"
    ? {
      ...raw.magic_setup,
      equipped_by_member: normalizeMemberIndexedRows(
        sourceParty,
        raw.magic_setup.equipped_by_member,
      ),
    }
    : { stock_by_level: {}, equipped_by_member: [] };
  const equipmentByMember = Array.isArray(raw?.equipment_by_member)
    ? normalizeMemberIndexedRows(sourceParty, raw.equipment_by_member)
    : [];
  const magicCandidatesByMember = Array.isArray(raw?.magic_candidates_by_member)
    ? normalizeMemberIndexedRows(sourceParty, raw.magic_candidates_by_member)
    : [];
  const magicSpellMetaByName = raw?.magic_spell_meta_by_name && typeof raw.magic_spell_meta_by_name === "object"
    ? raw.magic_spell_meta_by_name
    : {};
  const resources = raw?.resources && typeof raw.resources === "object" ? raw.resources : {};
  return {
    ...raw,
    party: normalizedParty,
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
  const currentView = buildMenuViewState();
  const fromRuntime = latestMenuState && typeof latestMenuState === "object" ? latestMenuState : {};
  return {
    ...currentView,
    ...fromRuntime,
    party: currentView.party,
    resources: currentView.resources,
  };
}

function syncNormalizedRuntimeSaveToStorage() {
  if (!pyodide) return false;
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return false;
  try {
    const saveObj = JSON.parse(saveJson);
    const storedEnvelope = appStore?.getState()?.saveEnvelope || cachedStoredEnvelope || restoreSaveEnvelopeFromStorage();
    const envelope = makeSaveEnvelope(saveObj, {
      selectedLocationGroup: currentBattleSelection?.selected_location_group || storedEnvelope?.selected_location_group || "",
      selectedLocation: currentBattleSelection?.selected_location || storedEnvelope?.selected_location || "",
      menuState: getCurrentMenuStateForPersistence(),
    });
    if (appStore) {
      return appStore.updateSaveEnvelope(envelope);
    }
    cachedStoredEnvelope = envelope;
    return persistSaveEnvelopeToStorage(envelope);
  } catch (_error) {
    return false;
  }
}

function downloadSaveEnvelope(envelope) {
  const exportEnvelope = compactSaveEnvelope(envelope);
  if (!exportEnvelope) return false;
  const payload = JSON.stringify(exportEnvelope, null, 2);
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

function resetBattleLogInteractionState() {
  activeLogPlaybackId += 1;
  returnToLocationBound = false;
  if (battleLogFrame) {
    battleLogFrame.classList.remove("is-clickable-next");
  }
}

function bindReturnToLocationOnClick() {
  if (returnToLocationBound || !battleLogFrame) return;
  returnToLocationBound = true;
  setBattleLogExpanded(true);
  battleLogFrame.classList.add("is-clickable-next");
  const onClick = () => {
    const returnRoute = String(battleReturnContext?.return_route || "location");
    if (appNavigate) {
      appNavigate(returnRoute === "map" ? "map" : "location");
      return;
    }
    window.location.href = returnRoute === "map" ? "./index.html#/map" : "./index.html";
  };
  battleLogFrame.addEventListener("click", onClick, { once: true });
}

function setCommandLogLayout({ showCommand }) {
  if (commandFrame) {
    commandFrame.style.display = showCommand ? "" : "none";
  }
  setBattleLogExpanded(!showCommand);
}

function buildLogBlocks(logs) {
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

function alignEventBlocksToLogBlocks(blocks, eventBlocks) {
  const source = Array.isArray(eventBlocks) ? eventBlocks : [];
  let actionIndex = 0;
  return blocks.map((block) => {
    if (block?.type !== "action") return [];
    const eventsForBlock = Array.isArray(source[actionIndex]) ? source[actionIndex] : [];
    actionIndex += 1;
    return eventsForBlock;
  });
}

function buildRewardLogBlock(payload) {
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

async function playBattleLogBlocks(logs, payload) {
  resetBattleLogInteractionState();
  const playbackId = activeLogPlaybackId;
  const blocks = buildLogBlocks(logs);
  const blockEvents = Array.isArray(payload?.event_blocks)
    ? alignEventBlocksToLogBlocks(blocks, payload.event_blocks)
    : buildPlaybackEventsByBlock(blocks, payload?.events);
  const playbackStatus = cloneJsonValue(payload?.playback_initial_status || sessionStatus);
  const hasRewardBlock = blocks.some((block) => block.type === "reward");
  if (!hasRewardBlock) {
    const rewardBlock = buildRewardLogBlock(payload);
    if (rewardBlock) {
      blocks.push(rewardBlock);
      blockEvents.push([]);
    }
  }
  suppressMenuStateSync = true;
  try {
    if (playbackStatus && typeof playbackStatus === "object") {
      sessionStatus = playbackStatus;
      activeCombatPopups = {};
      activeCombatEffects = {};
      rerenderAll();
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
      activeCombatPopups = {};
      activeCombatEffects = {};
      const eventsForBlock = Array.isArray(blockEvents[i]) ? blockEvents[i] : [];
      eventsForBlock.forEach((event) => {
        const applied = applyEventToPlaybackStatus(playbackStatus, event);
        if (!applied) return;
        const key = combatPopupKey(applied.side, applied.index);
        activeCombatPopups[key] = applied.popup;
        if (applied.effect) {
          activeCombatEffects[key] = applied.effect;
        }
      });
      if (eventsForBlock.length === 0) {
        const namedEffects = buildNamedCombatEffects(block, playbackStatus);
        namedEffects.forEach((effect) => {
          const applied = applyNamedCombatEffect(playbackStatus, effect);
          if (!applied) return;
          const key = combatPopupKey(applied.side, applied.index);
          activeCombatPopups[key] = applied.popup;
          if (applied.effect) {
            activeCombatEffects[key] = applied.effect;
          }
        });
      } else {
        activeCombatPopups = applyNamedPopupOverrides(
          activeCombatPopups,
          buildNamedCombatEffects(block, playbackStatus),
        );
      }
      rerenderAll();
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
  } finally {
    suppressMenuStateSync = false;
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
      requires_side_choice: false,
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
      requires_side_choice: true,
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
    requires_side_choice: false,
  };
  inputMode = "pick_target";
  rerenderAll();
}

function chooseItem(cand) {
  const itemName = String(cand?.name || "");
  if (!itemName) return;
  const itemMeta = sessionStatus?.item_meta?.[itemName] || {};
  const targetSide = itemMeta?.target_side;
  const canSelectAll = Boolean(itemMeta?.can_select_all);
  const autoAllTarget = Boolean(itemMeta?.auto_all_target);
  if (autoAllTarget && (targetSide === "ally" || targetSide === "enemy")) {
    appendPendingAction({
      kind: "item",
      command: "Item",
      item_name: itemName,
      target_side: targetSide,
      target_index: targetSide === "ally" ? currentMemberIndex : 0,
      target_all: true,
    });
    return;
  }
  pendingActionDraft = {
    kind: "item",
    command: "Item",
    item_name: itemName,
    can_select_all: canSelectAll,
    requires_side_choice: !(targetSide === "ally" || targetSide === "enemy"),
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

  pyodide = await getPyodideRuntime();

  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const selectionPayload = JSON.parse(getSelectionJson());
  locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];
  const selectionFromStore = readBattleSelectionFromStore();
  if (selectionFromStore?.selected_location_group || selectionFromStore?.selected_location) {
    currentBattleSelection = selectionFromStore;
  }
  currentBattleSelection = resolveBattleSelection(selectionPayload);

  const storedEnvelope = appStore?.getState()?.saveEnvelope || await restoreSaveEnvelopeFromStorageAsync();
  cachedStoredEnvelope = storedEnvelope;
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

function resolveSaveDataForBoot() {
  if (appStore?.getState()?.saveEnvelope?.save && typeof appStore.getState().saveEnvelope.save === "object") {
    // Battle boot trusts saveEnvelope.save as the source of truth.
    // Menu actions already persist into saveEnvelope.save, while menuState can lag
    // behind and accidentally overwrite newer job changes during a boot-time merge.
    return appStore.getState().saveEnvelope.save;
  }
  if (loadedSaveData && typeof loadedSaveData === "object") {
    return loadedSaveData;
  }
  const storedEnvelope = cachedStoredEnvelope || restoreSaveEnvelopeFromStorage();
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
  logBattleBootDebug("saveDataForBoot.party.before_python_boot", saveDataForBoot?.party);
  const selectedGroup = String(currentBattleSelection.selected_location_group || "");
  const selectedLocation = String(currentBattleSelection.selected_location || "");
  const enemyNamesJson = JSON.stringify(
    Array.isArray(currentBattleSelection.enemy_names) ? currentBattleSelection.enemy_names : [],
  );
  const payload = JSON.parse(saveDataForBoot
    ? bootWithSave(
      selectedGroup,
      selectedLocation,
      JSON.stringify(saveDataForBoot),
      7,
      enemyNamesJson,
    )
    : bootForLocation(
      selectedGroup,
      selectedLocation,
      7,
      enemyNamesJson,
    ));
  loadedSaveData = null;
  currentSelectedLocationGroup = String(
    payload?.selected_location_group || selectedGroup || "",
  );
  currentBattleSelection = {
    selected_location_group: String(payload?.selected_location_group || selectedGroup || ""),
    selected_location: String(payload?.selected_location || selectedLocation || ""),
    enemy_names: Array.isArray(currentBattleSelection.enemy_names)
      ? currentBattleSelection.enemy_names
      : [],
  };
  if (appStore) {
    appStore.patch({
      selectedLocationGroup: currentBattleSelection.selected_location_group,
      selectedLocation: currentBattleSelection.selected_location,
    });
  }
  sessionStatus = payload?.session_status ?? { party: [], enemies: [] };
  latestMenuState = parseMenuStateCandidate(payload?.menu_state) || latestMenuState;
  lifecycleState = "ready_for_actions";
  battleFinished = false;
  resetBattleLogInteractionState();
  refreshMenuStateFromPyodide();
  syncNormalizedRuntimeSaveToStorage();
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
  const sessionStatusBeforeRound = cloneJsonValue(sessionStatus);
  const payload = {
    planned_actions: pendingActions,
    lifecycle_state: lifecycleState,
  };
  const resourcesBeforeRound = sessionStatus?.resources && typeof sessionStatus.resources === "object"
    ? {
      gil: Number(sessionStatus.resources?.gil ?? 0),
      cp: Number(sessionStatus.resources?.cp ?? 0),
    }
    : { gil: 0, cp: 0 };
  const resultJson = runRound(JSON.stringify(payload));
  const result = JSON.parse(resultJson);
  const resourcesAfterRound = result?.session_status?.resources && typeof result.session_status.resources === "object"
    ? {
      gil: Number(result.session_status.resources?.gil ?? 0),
      cp: Number(result.session_status.resources?.cp ?? 0),
    }
    : resourcesBeforeRound;
  normalizeVictoryRewards(result, resourcesBeforeRound, resourcesAfterRound);
  sessionStatus = result?.session_status ?? sessionStatus;
  latestMenuState = parseMenuStateCandidate(result?.menu_state) || latestMenuState;
  currentSelectedLocationGroup = String(
    result?.selected_location_group || currentSelectedLocationGroup || "",
  );
  lifecycleState = result?.lifecycle?.after === "ready_for_next_round"
    ? "ready_for_actions"
    : (result?.lifecycle?.after ?? "ready_for_actions");
  battleFinished = Boolean(result?.lifecycle?.battle_finished);

  const logs = injectResourceDiffsIntoRewardLogs(
    Array.isArray(result?.logs) ? result.logs : [],
    result?.victory_rewards,
  );
  result.playback_initial_status = sessionStatusBeforeRound;
  await playBattleLogBlocks(logs, result);

  sessionStatus = result?.session_status ?? sessionStatus;
  activeCombatPopups = {};
  activeCombatEffects = {};
  resetPendingActionsForParty();
  currentMemberIndex = firstActionableMemberIndex();
  selectedEnemyIndex = 0;
  enterCommandMode();
  setCommandLogLayout({ showCommand: !battleFinished });
  battlePhase.textContent = battleFinished
    ? `戦闘終了: ${result?.end_reason ?? "finished"}`
    : "次ターンの入力を開始してください。";
  if (battleFinished) {
    const shouldQueuePostVictoryOverlay = Boolean(
      result?.victory_rewards
      && battleReturnContext?.return_route === "map"
      && Array.isArray(battleReturnContext?.post_victory_overlay_indices)
      && battleReturnContext.post_victory_overlay_indices.length,
    );
    if (shouldQueuePostVictoryOverlay) {
      writeBattleReturnContextToSession({
        ...battleReturnContext,
        pending_overlay_indices: battleReturnContext.post_victory_overlay_indices,
      });
    }
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
        const persisted = appStore
          ? appStore.updateSaveEnvelope(envelope)
          : persistSaveEnvelopeToStorage(envelope);
        const autosaved = await persistSaveEnvelopeToIndexedDB(envelope, {
          slotId: AUTO_SAVE_SLOT_ID,
          kind: "auto",
          rememberSelection: false,
        });
        if (persisted) {
          statusLine.textContent = autosaved
            ? "戦闘終了データをブラウザに保存し、オートセーブを更新しました。"
            : "戦闘終了データをブラウザに保存しました。";
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

function attachBattleEventHandlers() {
  if (actionSheetBackdrop) {
    actionSheetBackdrop.addEventListener("click", () => {
      handleActionSheetDismiss();
    });
  }

  if (actionSheetCloseBtn) {
    actionSheetCloseBtn.addEventListener("click", () => {
      handleActionSheetDismiss();
    });
  }

  if (battleLogToggleBtn) {
    battleLogToggleBtn.addEventListener("click", () => {
      setBattleLogExpanded(!battleLogExpanded);
    });
  }

  if (menuBtn) {
    menuBtn.addEventListener("click", () => {
      refreshMenuStateFromPyodide();
      syncMenuViewStateToStorage();
      if (appStore) {
        const currentState = appStore.getState();
        if (battleReturnContext?.return_route === "map" && battleReturnContext?.resume_map) {
          appStore.updateMenuState({
            ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
            map_return_pending: true,
          });
        }
      }
      if (appNavigate) {
        appNavigate("menu");
        return;
      }
      window.location.href = "./menu.html";
    });
  }

  if (locationBtn) {
    locationBtn.addEventListener("click", () => {
      refreshMenuStateFromPyodide();
      syncMenuViewStateToStorage();
      if (appNavigate) {
        appNavigate("location");
        return;
      }
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
      const persisted = appStore
        ? appStore.updateSaveEnvelope(envelope)
        : persistSaveEnvelopeToStorage(envelope);
      if (persisted) {
        setSaveButtonsEnabled(true);
      }
      cachedStoredEnvelope = envelope;
      if (envelope?.menu_state && typeof envelope.menu_state === "object") {
        latestMenuState = parseMenuStateCandidate(envelope.menu_state) || latestMenuState;
        if (appStore) {
          appStore.updateMenuState(envelope.menu_state);
        } else {
          syncMenuViewStateToStorage();
        }
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
      const envelope = appStore?.getState()?.saveEnvelope || cachedStoredEnvelope || restoreSaveEnvelopeFromStorage();
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
}

export async function initializeBattleApp({ root = document, store = null, navigate = null } = {}) {
  bindDom(root);
  setBattleLogExpanded(false);
  resetBattleLogInteractionState();
  appStore = store;
  appNavigate = navigate;
  battleReturnContext = resolveMountedBattleReturnContext(
    readBattleReturnContextFromSession(),
    battleReturnContext,
  );
  const storeSelection = readBattleSelectionFromStore();
  if (storeSelection?.selected_location_group || storeSelection?.selected_location) {
    currentBattleSelection = storeSelection;
  }
  attachBattleEventHandlers();
  rerenderAll();
  try {
    await bootEngine();
  } catch (error) {
    battlePhase.textContent = `起動失敗: ${String(error)}`;
    statusLine.textContent = "エンジン起動に失敗しました。ページを再読み込みしてください。";
    throw error;
  }
}

if (typeof document !== "undefined" && document.getElementById("battlePhase")) {
  initializeBattleApp().catch(() => {});
}
