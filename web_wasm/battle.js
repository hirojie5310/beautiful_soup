import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";
import { resolveFaceImageCandidates } from "./shared_party.js";
import {
  LOCAL_MENU_STORAGE_KEY,
  LOCAL_SAVE_STORAGE_KEY,
  parseSaveEnvelope,
  restoreSaveEnvelopeFromStorage,
  parseMenuStateFromStorage,
  makeSaveEnvelope,
  persistSaveEnvelopeToStorage,
  syncRuntimeSaveToStorage,
} from "./shared_storage.js";

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
let activeCombatPopups = {};
let activeCombatEffects = {};
let suppressMenuStateSync = false;
const PYTHON_BUNDLE_VERSION = "20260402b";
const ATTACK_EFFECT_SHEET_NAME = "ef_slash_frames.png";

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
  const response = await fetch(`./python_bundle.zip?v=${PYTHON_BUNDLE_VERSION}`, { cache: "no-store" });
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

function appendCombatPopup(card, popup) {
  if (!card || !popup) return;
  const layer = document.createElement("div");
  layer.className = "combat-popup-layer";
  const bubble = document.createElement("div");
  const value = Number(popup?.value ?? 0);
  const kind = String(popup?.kind || "");
  let text = String(value);
  let extraClass = "";
  if (kind === "heal") {
    text = `+${Math.abs(value)}`;
    extraClass = " heal";
  } else if (kind === "miss") {
    text = "MISS";
    extraClass = " miss";
  } else if (value > 0) {
    text = `-${value}`;
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
  if (candidates.length) {
    slash.style.setProperty("--slash-image", `url("${candidates[0]}")`);
  }

  layer.appendChild(slash);
  card.appendChild(layer);
}

function normalizeStatusIconKey(raw) {
  return String(raw || "").trim().toLowerCase().replace(/^status\./, "");
}

function applyEventToPlaybackStatus(playbackStatus, event) {
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
    const currentHp = Number(target?.hp ?? 0);
    const nextHp = Math.max(0, currentHp - amount);
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
          sheetName: ATTACK_EFFECT_SHEET_NAME,
        }
        : null,
      popup: {
        kind: amount > 0 ? "damage" : "miss",
        value: amount,
      },
    };
  }

  if (event.type === "status") {
    const existing = Array.isArray(target.status_icons) ? target.status_icons : [];
    const additions = Array.isArray(event?.names)
      ? event.names.map((name) => normalizeStatusIconKey(name)).filter(Boolean)
      : [];
    target.status_icons = Array.from(new Set([...existing, ...additions]));
  }
  return null;
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
    popup: {
      kind,
      value,
    },
  };
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
    appendCombatEffect(card, effectForTarget("char", idx));
    appendCombatPopup(card, popupForTarget("char", idx));
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
    appendCombatEffect(card, effectForTarget("enemy", idx));
    appendCombatPopup(card, popupForTarget("enemy", idx));
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
    ? sessionStatus.party.map((member, index) => ({
      index: Number(member?.index ?? index),
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
  if (suppressMenuStateSync) return;
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
  return syncRuntimeSaveToStorage({
    pyodide,
    buildEnvelopeOptions: () => {
      const storedEnvelope = restoreSaveEnvelopeFromStorage();
      return {
        selectedLocationGroup: currentBattleSelection?.selected_location_group || storedEnvelope?.selected_location_group || "",
        selectedLocation: currentBattleSelection?.selected_location || storedEnvelope?.selected_location || "",
        menuState: getCurrentMenuStateForPersistence(),
      };
    },
  });
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
  const playbackId = ++activeLogPlaybackId;
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
