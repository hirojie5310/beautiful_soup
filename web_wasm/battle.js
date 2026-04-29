import { getPyodideRuntime } from "./pyodide_runtime.js";
import {
  alignEventBlocksToLogBlocks,
  applyEventToPlaybackStatus,
  applyNamedCombatEffect,
  applyNamedPopupOverrides,
  buildLogBlocks,
  buildNamedCombatEffects,
  buildPlaybackEventsByBlock,
  buildRewardLogBlock,
  injectResourceDiffsIntoRewardLogs,
  normalizeVictoryRewards,
} from "./battle_playback.js";
import {
  DEFAULT_BATTLE_RETURN_CONTEXT,
  resolveMountedBattleReturnContext,
} from "./battle_context.js";
import {
  buildActionFromCommand as buildActionFromCommandForState,
  commandLabel,
  isOutOfBattleEnemy,
  isOutOfBattleMember,
  selectedEnemySafeIndex as selectedEnemySafeIndexForState,
  targetSideForCommand,
} from "./battle_controller.js";
import {
  downloadSaveEnvelope,
  readBattleReturnContextFromSession,
  readBattleStartSelectionFromSession,
  syncRuntimeSaveToBrowser,
  persistFinishedBattleSave,
  writeBattleReturnContextToSession as persistBattleReturnContextToSession,
} from "./battle_persistence.js";
import {
  renderBattleActionSheet,
  renderBattleStatusLine,
  renderEnemyCards,
  renderPartyCards,
  renderPlannedActionsText,
  renderRewardPanel,
  setActionSheetOpenState,
  setBattleLogExpandedState,
  setCommandLogLayoutState,
} from "./battle_view.js";
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
  parseSaveEnvelope,
} from "./shared_storage.js";
import { saveRepository } from "./save_repository.js";
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

function writeBattleReturnContextToSession(nextContext) {
  battleReturnContext = persistBattleReturnContextToSession(nextContext)
    || { ...DEFAULT_BATTLE_RETURN_CONTEXT };
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
  return selectedEnemySafeIndexForState({ sessionStatus, selectedEnemyIndex });
}

function buildActionFromCommand(def) {
  return buildActionFromCommandForState(def, {
    currentMemberIndex,
    sessionStatus,
    selectedEnemyIndex,
  });
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

function enterCommandMode() {
  inputMode = "command";
  pendingActionDraft = null;
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
  setActionSheetOpenState({
    open,
    actionSheet,
    actionSheetBackdrop,
    actionSheetBody,
  });
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

function currentActorName() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  const actor = party[currentMemberIndex];
  return String(actor?.name || "");
}

function renderMagicActionSheet() {
  renderCurrentActionSheet("pick_magic");
}

function renderItemActionSheet() {
  renderCurrentActionSheet("pick_item");
}

function renderTargetSideActionSheet() {
  renderCurrentActionSheet("pick_side");
}

function renderTargetActionSheet() {
  renderCurrentActionSheet("pick_target");
}

function renderCurrentActionSheet(mode) {
  renderBattleActionSheet({
    mode,
    actionSheetTitle,
    actionSheetBody,
    actorName: currentActorName(),
    magicCandidates: currentMemberMagicCandidates(),
    itemCandidates: currentItemCandidates(),
    pendingActionDraft,
    sessionStatus,
    canAct: Boolean(pyodide && !battleFinished),
    isOutOfBattleEnemy,
    onBackToCommand: closeActionSheetToCommand,
    onReturnToSource: returnToSourceSelection,
    onChooseMagic: chooseMagic,
    onChooseItem: chooseItem,
    onChooseSide: (side) => {
      pendingActionDraft = { ...(pendingActionDraft || {}), target_side: side };
      inputMode = "pick_target";
      rerenderAll();
    },
    onBackFromTarget: () => {
      if (shouldReturnToSideSelection()) {
        inputMode = "pick_side";
      } else {
        inputMode = sourceSelectionModeForDraft();
        if (inputMode === "command") {
          pendingActionDraft = null;
        }
      }
      rerenderAll();
    },
    onFinalizeTarget: finalizeDraftAction,
  });
}

function cloneJsonValue(value) {
  return JSON.parse(JSON.stringify(value ?? null));
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

function renderParty() {
  const party = Array.isArray(sessionStatus.party) ? sessionStatus.party : [];
  renderPartyCards({
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
  });
}

function renderEnemies() {
  const enemies = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies : [];
  renderEnemyCards({
    enemyGrid,
    enemyFrame,
    enemies,
    enemyCardCache,
    selectedEnemyIndex,
    selectedEnemySafeIndex: selectedEnemySafeIndexForState,
    currentSelectedLocationGroup,
    resolveLocationMapImageUrl,
    resolveEnemyImageCandidates,
    statusIconRowCache,
    resolveStatusIconCandidates,
    applyCachedImageSource,
    effectForTarget,
    popupForTarget,
    resolveAttackEffectImageCandidates,
    onEnemyClick: (idx) => {
      if (battleFinished) return;
      const enemy = Array.isArray(sessionStatus.enemies) ? sessionStatus.enemies[idx] : null;
      if (isOutOfBattleEnemy(enemy)) return;
      selectedEnemyIndex = idx;
      renderEnemies();
      renderStatus();
    },
    onMapImageResolved: () => {
      renderEnemies();
    },
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
  renderPlannedActionsText(plannedActionsView, pendingActions);
}

function setBattleLogExpanded(expanded) {
  battleLogExpanded = setBattleLogExpandedState({
    expanded,
    battleLogFrame,
    battleLogToggleBtn,
  });
}

function renderStatus() {
  renderBattleStatusLine({
    statusLine,
    sessionStatus,
    currentMemberIndex,
    selectedEnemyIndex,
    inputMode,
    pendingActionDraft,
    battleFinished,
    selectedEnemySafeIndex: selectedEnemySafeIndexForState,
    committedActionCount,
    requiredActionCount,
  });
}

function maybeShowRewards(payload) {
  renderRewardPanel(rewardPanel, payload);
}

function buildMenuViewState() {
  const storedMenuState = saveRepository.loadMenuState();
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
  saveRepository.saveMenuState(nextState);
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
  const result = syncRuntimeSaveToBrowser({
    pyodide,
    appStore,
    cachedStoredEnvelope,
    currentBattleSelection,
    menuState: getCurrentMenuStateForPersistence(),
  });
  if (result.envelope && !appStore) {
    cachedStoredEnvelope = result.envelope;
  }
  return result.persisted;
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
  battleLogExpanded = setCommandLogLayoutState({
    showCommand,
    commandFrame,
    battleLogFrame,
    battleLogToggleBtn,
  });
}

async function playBattleLogBlocks(logs, payload) {
  resetBattleLogInteractionState();
  const playbackId = activeLogPlaybackId;
  const blocks = buildLogBlocks(logs);
  const blockEvents = Array.isArray(payload?.event_blocks)
    ? alignEventBlocksToLogBlocks(blocks, payload.event_blocks)
    : buildPlaybackEventsByBlock(blocks, payload?.events, sessionStatus);
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

  const storedEnvelope = appStore?.getState()?.saveEnvelope || await saveRepository.load();
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
  const storedEnvelope = cachedStoredEnvelope || saveRepository.loadLocalMirror();
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
    const saveResult = await persistFinishedBattleSave({
      pyodide,
      appStore,
      result,
      menuState: getCurrentMenuStateForPersistence(),
    });
    if (saveResult.envelope && !appStore) {
      cachedStoredEnvelope = saveResult.envelope;
    }
    if (saveResult.envelope) {
      if (saveResult.persisted) {
        statusLine.textContent = saveResult.autosaved
          ? "戦闘終了データをブラウザに保存し、オートセーブを更新しました。"
          : "戦闘終了データをブラウザに保存しました。";
        setSaveButtonsEnabled(true);
      } else {
        statusLine.textContent = "ブラウザ保存に失敗しました。";
      }
    } else {
      statusLine.textContent = "保存データの生成に失敗しました。";
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
        : saveRepository.saveLocalMirror(envelope);
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
      const envelope = appStore?.getState()?.saveEnvelope || cachedStoredEnvelope || saveRepository.loadLocalMirror();
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
