import {
  buildRenderRows,
  buildEncounterSelection,
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
  shouldTriggerEncounter,
} from "../map_data.js";
import { triggerAutoSaveFromEnvelope } from "./screen_shared.js";

const DISPLAY_TILE_SIZE = 22;
const HOLD_MOVE_INITIAL_DELAY_MS = 220;
const HOLD_MOVE_REPEAT_MS = 110;
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";
const MAP_ENTRY_CONTEXT_KEY = "ff3_wasm_map_entry_context_v1";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function createDirectionalHoldRepeater(
  runStep,
  scheduler = globalThis,
  options = {},
) {
  const initialDelay = Math.max(0, Number(options.initialDelay ?? HOLD_MOVE_INITIAL_DELAY_MS));
  const repeatInterval = Math.max(1, Number(options.repeatInterval ?? HOLD_MOVE_REPEAT_MS));
  let timeoutId = null;
  let intervalId = null;
  let activeDirection = "";

  function clearTimers() {
    if (timeoutId !== null) {
      scheduler.clearTimeout(timeoutId);
      timeoutId = null;
    }
    if (intervalId !== null) {
      scheduler.clearInterval(intervalId);
      intervalId = null;
    }
  }

  function stop(direction = "") {
    if (direction && direction !== activeDirection) return false;
    const hadActiveDirection = Boolean(activeDirection);
    activeDirection = "";
    clearTimers();
    return hadActiveDirection;
  }

  function start(direction) {
    const normalizedDirection = String(direction || "");
    if (!normalizedDirection) return false;
    if (normalizedDirection === activeDirection) return false;
    stop();
    activeDirection = normalizedDirection;
    void runStep(normalizedDirection);
    timeoutId = scheduler.setTimeout(() => {
      if (activeDirection !== normalizedDirection) return;
      intervalId = scheduler.setInterval(() => {
        if (activeDirection !== normalizedDirection) return;
        void runStep(normalizedDirection);
      }, repeatInterval);
    }, initialDelay);
    return true;
  }

  return {
    start,
    stop,
    isActive(direction = "") {
      return direction ? activeDirection === direction : Boolean(activeDirection);
    },
  };
}

function asNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function normalizeSwitchStates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, enabled]) => [String(key || ""), Boolean(enabled)])
      .filter(([key]) => Boolean(key)),
  );
}

function normalizeTreasureStates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, opened]) => [String(key || ""), Boolean(opened)])
      .filter(([key]) => Boolean(key)),
  );
}

function treasureKey(row) {
  return String(row?.treasure_id || row?.name || `${row?.x},${row?.y}`);
}

function addItemToInventory(save, bucketName, itemName, quantity = 1) {
  if (!save || typeof save !== "object") return false;
  if (!save.inventory || typeof save.inventory !== "object") {
    save.inventory = {};
  }
  if (!save.inventory[bucketName] || typeof save.inventory[bucketName] !== "object") {
    save.inventory[bucketName] = {};
  }
  const current = asNumber(save.inventory[bucketName][itemName], 0);
  save.inventory[bucketName][itemName] = current + quantity;
  return true;
}

function normalizeMapSaveShape(mapState, mapDefinition) {
  return {
    map: String(mapState?.current_map_id || mapDefinition.id || DEFAULT_MAP_ID),
    surface: String(mapDefinition?.name || mapState?.surface || mapState?.current_map_id || DEFAULT_MAP_ID),
    x: asNumber(mapState?.tile_x, mapDefinition?.spawn?.x ?? 0),
    y: asNumber(mapState?.tile_y, mapDefinition?.spawn?.y ?? 0),
  };
}

export function deriveInitialMapState(appState, mapDefinition, options = {}) {
  const menuState = appState?.menuState && typeof appState.menuState === "object"
    ? appState.menuState
    : {};
  const envelopeMap = appState?.saveEnvelope?.save?.map && typeof appState.saveEnvelope.save.map === "object"
    ? appState.saveEnvelope.save.map
    : {};
  const menuMapState = menuState?.map_state && typeof menuState.map_state === "object"
    ? menuState.map_state
    : {};
  const wantedMapId = String(
    menuMapState.current_map_id
    || envelopeMap.map
    || mapDefinition?.id
    || DEFAULT_MAP_ID,
  );
  const shouldResumeFromSavedPosition = Boolean(options?.resumeFromSavedPosition);
  if (shouldResumeFromSavedPosition) {
    return {
      current_map_id: wantedMapId,
      tile_x: asNumber(menuMapState.tile_x, asNumber(envelopeMap.x, asNumber(mapDefinition?.spawn?.x, 0))),
      tile_y: asNumber(menuMapState.tile_y, asNumber(envelopeMap.y, asNumber(mapDefinition?.spawn?.y, 0))),
      steps_since_reset: asNumber(menuMapState.steps_since_reset, 0),
      switch_states: normalizeSwitchStates(menuMapState.switch_states),
      opened_treasures: normalizeTreasureStates(menuMapState.opened_treasures),
    };
  }
  return {
    current_map_id: wantedMapId,
    tile_x: asNumber(mapDefinition?.spawn?.x, 0),
    tile_y: asNumber(mapDefinition?.spawn?.y, 0),
    steps_since_reset: 0,
    switch_states: {},
    opened_treasures: {},
  };
}

export function canOccupyTile(mapDefinition, x, y) {
  if (!mapDefinition) return false;
  if (x < 0 || y < 0 || x >= mapDefinition.width || y >= mapDefinition.height) {
    return false;
  }
  const gid = Number(mapDefinition.rows?.[y]?.[x] ?? 0);
  return !mapDefinition.collisionGids.has(gid);
}

export function moveMapPosition(mapDefinition, mapState, direction) {
  const delta = {
    up: { x: 0, y: -1 },
    down: { x: 0, y: 1 },
    left: { x: -1, y: 0 },
    right: { x: 1, y: 0 },
  }[direction];
  if (!delta) {
    return { moved: false, nextState: mapState, reason: "invalid" };
  }
  const nextX = asNumber(mapState?.tile_x, 0) + delta.x;
  const nextY = asNumber(mapState?.tile_y, 0) + delta.y;
  if (!canOccupyTile(mapDefinition, nextX, nextY)) {
    return { moved: false, nextState: mapState, reason: "blocked" };
  }
  return {
    moved: true,
    nextState: {
      ...mapState,
      tile_x: nextX,
      tile_y: nextY,
      steps_since_reset: asNumber(mapState?.steps_since_reset, 0) + 1,
    },
    reason: "moved",
  };
}

function buildEnvelopeWithMapState(store, nextMapState, mapDefinition) {
  const currentState = store.getState();
  const currentEnvelope = currentState.saveEnvelope && typeof currentState.saveEnvelope === "object"
    ? currentState.saveEnvelope
    : {
      version: 1,
      save: {},
      menu_state: {},
      selected_location_group: currentState.selectedLocationGroup,
      selected_location: currentState.selectedLocation,
      saved_at: new Date().toISOString(),
    };
  const nextMenuState = {
    ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
    map_state: {
      ...nextMapState,
    },
  };
  const nextSave = {
    ...(currentEnvelope.save && typeof currentEnvelope.save === "object" ? currentEnvelope.save : {}),
    map: normalizeMapSaveShape(nextMapState, mapDefinition),
  };
  return {
    ...currentEnvelope,
    save: nextSave,
    menu_state: nextMenuState,
    selected_location_group: currentState.selectedLocationGroup,
    selected_location: currentState.selectedLocation,
    saved_at: new Date().toISOString(),
  };
}

function renderLayout() {
  return `
    <style>
      [data-screen="map"] {
        --map-tile-size: ${DISPLAY_TILE_SIZE}px;
      }
      [data-screen="map"] .map-frame {
        display: grid;
        gap: 12px;
      }
      [data-screen="map"] .map-toolbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
      }
      [data-screen="map"] .map-toolbar-actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      [data-screen="map"] .map-viewport {
        position: relative;
        width: min(92vw, 440px);
        aspect-ratio: 1 / 1;
        overflow: hidden;
        border: 1px solid rgba(255, 255, 255, 0.22);
        border-radius: 14px;
        background:
          radial-gradient(circle at top, rgba(255, 255, 255, 0.08), transparent 40%),
          linear-gradient(180deg, rgba(7, 13, 30, 0.94), rgba(8, 14, 34, 0.98));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        margin: 0 auto;
      }
      [data-screen="map"] .map-layer {
        position: absolute;
        left: 0;
        top: 0;
        transform-origin: top left;
        will-change: transform;
      }
      [data-screen="map"] .map-tile {
        position: absolute;
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        background-repeat: no-repeat;
        image-rendering: pixelated;
      }
      [data-screen="map"] .map-object {
        position: absolute;
        width: var(--map-tile-size);
        height: var(--map-tile-size);
        display: grid;
        place-items: center;
        font-size: 0.6rem;
        font-weight: 700;
        color: #f7f2cc;
        text-shadow: 0 1px 0 rgba(0, 0, 0, 0.8);
        pointer-events: none;
      }
      [data-screen="map"] .map-object::before {
        content: "";
        position: absolute;
        inset: 3px;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.55);
        background: rgba(0, 0, 0, 0.28);
      }
      [data-screen="map"] .map-object > span {
        position: relative;
        z-index: 1;
      }
      [data-screen="map"] .map-player {
        position: absolute;
        left: 50%;
        top: 50%;
        width: calc(var(--map-tile-size) * 0.86);
        height: calc(var(--map-tile-size) * 0.86);
        transform: translate(-50%, -50%) translateY(calc(var(--map-tile-size) * 0.14));
        border-radius: 8px;
        background:
          linear-gradient(180deg, rgba(255, 241, 176, 0.95), rgba(228, 148, 61, 0.95));
        border: 1px solid rgba(255, 255, 255, 0.78);
        box-shadow:
          0 0 0 3px rgba(9, 13, 31, 0.55),
          0 0 20px rgba(255, 207, 86, 0.22);
        z-index: 2;
      }
      [data-screen="map"] .map-player::after {
        content: "";
        position: absolute;
        inset: 22% 28% 34%;
        border-radius: 999px 999px 40% 40%;
        background: rgba(32, 37, 72, 0.35);
      }
      [data-screen="map"] .map-hud {
        display: grid;
        gap: 10px;
      }
      [data-screen="map"] .map-meta {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        flex-wrap: wrap;
        color: rgba(255, 255, 255, 0.84);
      }
      [data-screen="map"] .map-pad {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 18px;
        flex-wrap: wrap;
      }
      [data-screen="map"] .map-pad-dpad {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 68px));
        gap: 8px;
      }
      [data-screen="map"] .map-pad-actions {
        display: grid;
        align-items: center;
      }
      [data-screen="map"] .map-pad-spacer {
        visibility: hidden;
      }
      [data-screen="map"] .map-pad-btn {
        min-height: 54px;
        font-size: 1rem;
        font-weight: 700;
        touch-action: manipulation;
        user-select: none;
        -webkit-user-select: none;
      }
      [data-screen="map"] .map-pad-confirm {
        min-width: 88px;
        min-height: 54px;
        border-radius: 999px;
        letter-spacing: 0.08em;
      }
      @media (max-width: 480px) {
        [data-screen="map"] .map-toolbar,
        [data-screen="map"] .map-meta {
          flex-direction: column;
          align-items: stretch;
        }
        [data-screen="map"] .map-toolbar-actions {
          justify-content: stretch;
        }
        [data-screen="map"] .map-toolbar-actions .btn {
          flex: 1 1 auto;
        }
      }
    </style>
    <div class="screen medium" data-screen="map">
      <section class="frame map-frame">
        <div class="map-toolbar">
          <div>
            <h1 class="title" style="margin:0;">MAP</h1>
            <div id="mapStatus" class="status" style="margin-top:6px;">マップを読み込み中...</div>
          </div>
          <div class="map-toolbar-actions">
            <button id="locationBtn" class="btn" type="button">Location</button>
            <button id="menuBtn" class="btn" type="button">メニュー</button>
            <button id="battleBtn" class="btn" type="button">戦闘</button>
          </div>
        </div>

        <div id="mapViewport" class="map-viewport" aria-label="map viewport">
          <div id="mapLayer" class="map-layer"></div>
          <div class="map-player" aria-hidden="true"></div>
        </div>

        <div class="map-hud">
          <div id="mapMeta" class="map-meta"></div>
          <div class="map-pad">
            <div class="map-pad-dpad">
              <span class="map-pad-spacer"></span>
              <button class="btn map-pad-btn" type="button" data-dir="up">↑</button>
              <span class="map-pad-spacer"></span>
              <button class="btn map-pad-btn" type="button" data-dir="left">←</button>
              <button class="btn map-pad-btn" type="button" data-dir="down">↓</button>
              <button class="btn map-pad-btn" type="button" data-dir="right">→</button>
            </div>
            <div class="map-pad-actions">
              <button id="confirmBtn" class="btn map-pad-btn map-pad-confirm" type="button">決定</button>
            </div>
          </div>
        </div>
      </section>
    </div>
  `;
}

function objectLabel(type) {
  if (type === "exit") return "EXIT";
  if (type === "switch") return "SW";
  if (type === "chest" || type === "treasure") return "宝";
  return "OBJ";
}

export function findStandingObject(mapDefinition, mapState) {
  return (mapDefinition?.objects || []).find((row) => (
    Number(row?.x) === Number(mapState?.tile_x) && Number(row?.y) === Number(mapState?.tile_y)
  ));
}

export function findAdjacentObject(mapDefinition, mapState, predicate = () => true) {
  const tileX = Number(mapState?.tile_x);
  const tileY = Number(mapState?.tile_y);
  return (mapDefinition?.objects || []).find((row) => {
    const objectX = Number(row?.x);
    const objectY = Number(row?.y);
    return Math.abs(tileX - objectX) + Math.abs(tileY - objectY) === 1 && predicate(row);
  }) || null;
}

function describeStandingObject(mapDefinition, mapState) {
  const hit = findStandingObject(mapDefinition, mapState);
  if (!hit) return "";
  if (hit.type === "exit") {
    return `出口: ${hit.name || hit.target_map || "-"}`;
  }
  if (hit.type === "switch") {
    return `スイッチ: ${hit.name || hit.switch_id || "-"}`;
  }
  if (hit.type === "chest") {
    return `宝箱: ${hit.name || "Treasure"}`;
  }
  return `オブジェクト: ${hit.name || hit.type || "-"}`;
}

function renderMapTiles(mapLayer, mapDefinition) {
  const tileSize = DISPLAY_TILE_SIZE;
  const tilesetRows = Math.max(1, Math.ceil(mapDefinition.tileset.tileCount / mapDefinition.tileset.columns));
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  mapLayer.innerHTML = "";
  mapLayer.style.width = `${mapDefinition.renderWidth * tileSize}px`;
  mapLayer.style.height = `${mapDefinition.renderHeight * tileSize}px`;

  mapDefinition.renderRows.forEach((row, y) => {
    row.forEach((gid, x) => {
      const tile = document.createElement("div");
      tile.className = "map-tile";
      tile.style.left = `${x * tileSize}px`;
      tile.style.top = `${y * tileSize}px`;

      const localId = Math.max(0, Number(gid || 0) - 1);
      const col = localId % mapDefinition.tileset.columns;
      const tileRow = Math.floor(localId / mapDefinition.tileset.columns);
      tile.style.backgroundImage = `url("${mapDefinition.tileset.imageUrl}")`;
      tile.style.backgroundSize = `${mapDefinition.tileset.columns * tileSize}px ${tilesetRows * tileSize}px`;
      tile.style.backgroundPosition = `${-col * tileSize}px ${-tileRow * tileSize}px`;
      mapLayer.appendChild(tile);
    });
  });

  (mapDefinition.objects || []).forEach((row) => {
    const marker = document.createElement("div");
    marker.className = "map-object";
    marker.style.left = `${(Number(row.x || 0) + renderPadding.left) * tileSize}px`;
    marker.style.top = `${(Number(row.y || 0) + renderPadding.top) * tileSize}px`;
    marker.title = String(row?.name || row?.type || "");
    marker.innerHTML = `<span>${objectLabel(row?.type)}</span>`;
    mapLayer.appendChild(marker);
  });
}

export function applySwitchStateToMap(mapDefinition, switchStates = {}) {
  const normalizedSwitchStates = normalizeSwitchStates(switchStates);
  const normalizedOpenedTreasures = normalizeTreasureStates(mapDefinition?.openedTreasures);
  const baseRows = Array.isArray(mapDefinition?.baseRows) ? mapDefinition.baseRows : mapDefinition?.rows;
  const nextRows = Array.isArray(baseRows) ? baseRows.map((row) => row.slice()) : [];

  (mapDefinition?.objects || []).forEach((row) => {
    if (row?.type !== "barrier" || !row?.trigger_by) return;
    if (!normalizedSwitchStates[String(row.trigger_by)]) return;
    const x = Number(row?.x);
    const y = Number(row?.y);
    if (!Array.isArray(nextRows[y])) return;
    const current = Number(nextRows[y][x] ?? 0);
    if (current === 1) nextRows[y][x] = 49;
    else if (current === 49) nextRows[y][x] = 1;
  });

  (mapDefinition?.objects || []).forEach((row) => {
    if (row?.type !== "treasure") return;
    const key = treasureKey(row);
    if (!normalizedOpenedTreasures[key]) return;
    const x = Number(row?.x);
    const y = Number(row?.y);
    const closedGid = Number(row?.closed_gid || 125);
    const openGid = Number(row?.open_gid || 126);
    if (!Array.isArray(nextRows[y])) return;
    if (Number(nextRows[y][x] ?? 0) === closedGid) {
      nextRows[y][x] = openGid;
    }
  });

  const renderPadding = mapDefinition?.renderPadding || { top: 0, right: 0, bottom: 0, left: 0, fillGid: 0 };
  return {
    ...mapDefinition,
    rows: nextRows,
    openedTreasures: normalizedOpenedTreasures,
    renderRows: buildRenderRows(nextRows, mapDefinition.width, mapDefinition.height, {
      top: renderPadding.top,
      right: renderPadding.right,
      bottom: renderPadding.bottom,
      left: renderPadding.left,
      fill_gid: renderPadding.fillGid,
    }),
  };
}

export function toggleAdjacentSwitch(mapDefinition, mapState) {
  const adjacentSwitch = findAdjacentObject(
    mapDefinition,
    mapState,
    (row) => row?.type === "switch" && row?.switch_id,
  );
  if (!adjacentSwitch) {
    return { toggled: false, mapDefinition, mapState };
  }
  const switchId = String(adjacentSwitch.switch_id);
  const currentSwitchStates = normalizeSwitchStates(mapState?.switch_states);
  const nextSwitchStates = {
    ...currentSwitchStates,
    [switchId]: !currentSwitchStates[switchId],
  };
  return {
    toggled: true,
    switchId,
    enabled: nextSwitchStates[switchId],
    mapDefinition: applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: normalizeTreasureStates(mapState?.opened_treasures) },
      nextSwitchStates,
    ),
    mapState: {
      ...mapState,
      switch_states: nextSwitchStates,
    },
  };
}

export function openAdjacentTreasure(mapDefinition, mapState, saveEnvelope) {
  const adjacentTreasure = findAdjacentObject(
    mapDefinition,
    mapState,
    (row) => row?.type === "treasure",
  );
  if (!adjacentTreasure) {
    return { opened: false, mapDefinition, mapState, saveEnvelope };
  }
  const key = treasureKey(adjacentTreasure);
  const currentOpenedTreasures = normalizeTreasureStates(mapState?.opened_treasures);
  if (currentOpenedTreasures[key]) {
    return { opened: false, alreadyOpened: true, mapDefinition, mapState, saveEnvelope };
  }
  const nextOpenedTreasures = {
    ...currentOpenedTreasures,
    [key]: true,
  };
  const itemName = String(adjacentTreasure.item_name || "Potion");
  const bucketName = String(adjacentTreasure.inventory_bucket || "Anywhere");
  const quantity = Math.max(1, asNumber(adjacentTreasure.quantity, 1));
  const nextEnvelope = typeof structuredClone === "function"
    ? structuredClone(saveEnvelope || { save: {} })
    : JSON.parse(JSON.stringify(saveEnvelope || { save: {} }));
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = {};
  }
  addItemToInventory(nextEnvelope.save, bucketName, itemName, quantity);
  return {
    opened: true,
    itemName,
    quantity,
    mapDefinition: applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: nextOpenedTreasures },
      mapState?.switch_states,
    ),
    mapState: {
      ...mapState,
      opened_treasures: nextOpenedTreasures,
    },
    saveEnvelope: nextEnvelope,
  };
}

function updateViewportTransform(mapViewport, mapLayer, mapDefinition, mapState) {
  const viewportWidth = mapViewport.clientWidth;
  const viewportHeight = mapViewport.clientHeight;
  const renderPadding = mapDefinition.renderPadding || { left: 0, top: 0 };
  const mapPixelWidth = mapDefinition.renderWidth * DISPLAY_TILE_SIZE;
  const mapPixelHeight = mapDefinition.renderHeight * DISPLAY_TILE_SIZE;
  const centeredX = viewportWidth / 2 - (mapState.tile_x + renderPadding.left + 0.5) * DISPLAY_TILE_SIZE;
  const centeredY = viewportHeight / 2 - (mapState.tile_y + renderPadding.top + 0.5) * DISPLAY_TILE_SIZE;
  const minX = Math.min(0, viewportWidth - mapPixelWidth);
  const minY = Math.min(0, viewportHeight - mapPixelHeight);
  const translateX = clamp(centeredX, minX, 0);
  const translateY = clamp(centeredY, minY, 0);
  mapLayer.style.transform = `translate(${translateX}px, ${translateY}px)`;
}

function updateMeta(mapMeta, mapDefinition, mapState) {
  const standing = describeStandingObject(mapDefinition, mapState);
  mapMeta.innerHTML = [
    `<div>Map: ${mapDefinition.name}</div>`,
    `<div>座標: (${mapState.tile_x}, ${mapState.tile_y})</div>`,
    `<div>${standing || "足元に特別なオブジェクトはありません。"}</div>`,
  ].join("");
}

function readBattleReturnContext() {
  try {
    const raw = sessionStorage.getItem(BATTLE_RETURN_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function readMapEntryContext() {
  try {
    const raw = sessionStorage.getItem(MAP_ENTRY_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

export function shouldResumeMapPosition(appState, battleReturnContext = null) {
  if (battleReturnContext?.return_route === "map" && battleReturnContext?.resume_map) {
    return true;
  }
  return Boolean(appState?.menuState?.map_return_pending);
}

function isBattleReturnToMap(battleReturnContext) {
  return Boolean(
    battleReturnContext?.return_route === "map"
    && battleReturnContext?.resume_map,
  );
}

export function deriveMapLaunchContext(appState, battleReturnContext = null, mapEntryContext = null) {
  const freshLocationEntry = Boolean(
    mapEntryContext?.entry_route === "location"
    && mapEntryContext?.fresh_start,
  );
  const resumeFromSavedPosition = freshLocationEntry
    ? false
    : shouldResumeMapPosition(appState, battleReturnContext);
  const returningFromBattle = freshLocationEntry ? false : isBattleReturnToMap(battleReturnContext);
  const requestedMapId = String(
    (freshLocationEntry && mapEntryContext?.map_id)
    || (returningFromBattle && battleReturnContext?.map_id)
    || appState?.menuState?.map_state?.current_map_id
    || appState?.saveEnvelope?.save?.map?.map
    || DEFAULT_MAP_ID,
  );
  return {
    freshLocationEntry,
    resumeFromSavedPosition,
    returningFromBattle,
    requestedMapId,
  };
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const mapStatus = mountNode.querySelector("#mapStatus");
  const mapViewport = mountNode.querySelector("#mapViewport");
  const mapLayer = mountNode.querySelector("#mapLayer");
  const mapMeta = mountNode.querySelector("#mapMeta");
  const confirmBtn = mountNode.querySelector("#confirmBtn");
  const locationBtn = mountNode.querySelector("#locationBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");
  const battleBtn = mountNode.querySelector("#battleBtn");
  const padButtons = Array.from(mountNode.querySelectorAll("[data-dir]"));

  let mapDefinition = null;
  let mapState = null;
  let resizeObserver = null;
  let encounterLocked = false;
  let mapTransitionLocked = false;
  const holdRepeater = createDirectionalHoldRepeater((direction) => tryMove(direction));

  function patchMapMenuState(partialMenuState) {
    const currentState = store.getState();
    const currentEnvelope = currentState.saveEnvelope && typeof currentState.saveEnvelope === "object"
      ? currentState.saveEnvelope
      : {
        version: 1,
        save: {},
        menu_state: {},
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
        saved_at: new Date().toISOString(),
      };
    const nextMenuState = {
      ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
      ...(partialMenuState && typeof partialMenuState === "object" ? partialMenuState : {}),
    };
    const nextEnvelope = {
      ...currentEnvelope,
      menu_state: nextMenuState,
      selected_location_group: currentState.selectedLocationGroup,
      selected_location: currentState.selectedLocation,
      saved_at: new Date().toISOString(),
    };
    store.updateMenuState(nextMenuState);
    store.updateSaveEnvelope(nextEnvelope);
  }

  function persistCurrentMapState(nextMapState) {
    if (!mapDefinition) return false;
    const nextEnvelope = buildEnvelopeWithMapState(store, nextMapState, mapDefinition);
    store.updateMenuState(nextEnvelope.menu_state);
    const persisted = store.updateSaveEnvelope(nextEnvelope);
    if (persisted) {
      triggerAutoSaveFromEnvelope(nextEnvelope);
    }
    return persisted;
  }

  function redraw() {
    if (!mapDefinition || !mapState) return;
    updateViewportTransform(mapViewport, mapLayer, mapDefinition, mapState);
    updateMeta(mapMeta, mapDefinition, mapState);
  }

  function tryConfirm() {
    if (!mapDefinition || !mapState || mapTransitionLocked) return;
    const switchResult = toggleAdjacentSwitch(mapDefinition, mapState);
    if (switchResult.toggled) {
      mapDefinition = switchResult.mapDefinition;
      mapState = switchResult.mapState;
      renderMapTiles(mapLayer, mapDefinition);
      persistCurrentMapState(mapState);
      redraw();
      mapStatus.textContent = `${switchResult.switchId} を ${switchResult.enabled ? "ON" : "OFF"} にしました。`;
      return;
    }
    const treasureResult = openAdjacentTreasure(mapDefinition, mapState, store.getState().saveEnvelope);
    if (treasureResult.opened) {
      mapDefinition = treasureResult.mapDefinition;
      mapState = treasureResult.mapState;
      renderMapTiles(mapLayer, mapDefinition);
      const currentState = store.getState();
      const nextEnvelope = {
        ...(treasureResult.saveEnvelope || currentState.saveEnvelope || { save: {}, menu_state: {} }),
        menu_state: {
          ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
          map_state: {
            ...mapState,
          },
        },
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
        saved_at: new Date().toISOString(),
      };
      store.updateMenuState(nextEnvelope.menu_state);
      const persisted = store.updateSaveEnvelope(nextEnvelope);
      if (persisted) {
        triggerAutoSaveFromEnvelope(nextEnvelope);
      }
      redraw();
      mapStatus.textContent = `${treasureResult.itemName} を手に入れた！`;
      return;
    }
    mapStatus.textContent = treasureResult.alreadyOpened
      ? "その宝箱はすでに開いています。"
      : "反応するギミックは近くにありません。";
  }

  async function applyMapTransition(targetMapId, targetSpawn = null) {
    if (!targetMapId || mapTransitionLocked) return false;
    mapTransitionLocked = true;
    try {
      const nextMapDefinition = await loadMapDefinition(String(targetMapId));
      const storeState = store.getState();
      const nextSelection = buildEncounterSelection(nextMapDefinition, {
        selected_location_group: storeState.selectedLocationGroup,
        selected_location: storeState.selectedLocation,
      });
      store.patch({
        selectedLocationGroup: nextSelection.selected_location_group,
        selectedLocation: nextSelection.selected_location,
      });
      mapDefinition = nextMapDefinition;
      mapState = {
        current_map_id: nextMapDefinition.id,
        tile_x: asNumber(targetSpawn?.x, asNumber(nextMapDefinition.spawn?.x, 0)),
        tile_y: asNumber(targetSpawn?.y, asNumber(nextMapDefinition.spawn?.y, 0)),
        steps_since_reset: 0,
        switch_states: {},
        opened_treasures: {},
      };
      if (!canOccupyTile(mapDefinition, mapState.tile_x, mapState.tile_y)) {
        mapState = {
          current_map_id: nextMapDefinition.id,
          tile_x: asNumber(nextMapDefinition.spawn?.x, 0),
          tile_y: asNumber(nextMapDefinition.spawn?.y, 0),
          steps_since_reset: 0,
          switch_states: {},
          opened_treasures: {},
        };
      }
      mapDefinition = applySwitchStateToMap(
        { ...mapDefinition, openedTreasures: mapState.opened_treasures },
        mapState.switch_states,
      );
      renderMapTiles(mapLayer, mapDefinition);
      persistCurrentMapState(mapState);
      redraw();
      mapStatus.textContent = `${mapDefinition.name} に移動しました。`;
      return true;
    } finally {
      mapTransitionLocked = false;
    }
  }

  function navigateToEncounter() {
    if (!mapDefinition || encounterLocked) return;
    encounterLocked = true;
    const storeState = store.getState();
    const encounterSelection = buildEncounterSelection(mapDefinition, {
      selected_location_group: storeState.selectedLocationGroup,
      selected_location: storeState.selectedLocation,
    });
    sessionStorage.setItem(BATTLE_START_SELECTION_KEY, JSON.stringify(encounterSelection));
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify({
      return_route: "map",
      resume_map: true,
      map_id: mapDefinition.id,
    }));
    store.patch({
      selectedLocationGroup: encounterSelection.selected_location_group,
      selectedLocation: encounterSelection.selected_location,
    });
    navigate("battle");
  }

  async function tryMove(direction) {
    if (!mapDefinition || !mapState || mapTransitionLocked) return;
    const result = moveMapPosition(mapDefinition, mapState, direction);
    if (!result.moved) {
      mapStatus.textContent = result.reason === "blocked"
        ? "その方向には進めません。"
        : "移動できません。";
      return;
    }
    mapState = result.nextState;
    persistCurrentMapState(mapState);
    redraw();
    const standingObject = findStandingObject(mapDefinition, mapState);
    if (standingObject?.type === "exit" && standingObject?.target_map) {
      const moved = await applyMapTransition(
        String(standingObject.target_map),
        standingObject.target_spawn,
      );
      if (!moved) {
        mapStatus.textContent = "出入口の移動に失敗しました。";
      }
      return;
    }
    const standing = describeStandingObject(mapDefinition, mapState);
    if (shouldTriggerEncounter(
      mapDefinition,
      Math.random(),
      asNumber(mapState?.steps_since_reset, 0),
    )) {
      mapStatus.textContent = "敵が現れた！ 戦闘へ移行します。";
      navigateToEncounter();
      return;
    }
    mapStatus.textContent = standing || "移動しました。";
  }

  const onKeyDown = (event) => {
    const keyMap = {
      ArrowUp: "up",
      ArrowDown: "down",
      ArrowLeft: "left",
      ArrowRight: "right",
    };
    const direction = keyMap[event.key];
    if (direction) {
      event.preventDefault();
      void tryMove(direction);
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      tryConfirm();
    }
  };

  const onConfirm = () => tryConfirm();
  const onGoLocation = () => {
    patchMapMenuState({ map_return_pending: false });
    navigate("location");
  };
  const onGoMenu = () => {
    patchMapMenuState({ map_return_pending: true });
    navigate("menu");
  };
  const onGoBattle = () => navigate("battle");
  const padHandlers = new Map();

  confirmBtn.addEventListener("click", onConfirm);
  locationBtn.addEventListener("click", onGoLocation);
  menuBtn.addEventListener("click", onGoMenu);
  battleBtn.addEventListener("click", onGoBattle);
  padButtons.forEach((button) => {
    const direction = String(button.dataset.dir || "");
    const onPointerDown = (event) => {
      event.preventDefault();
      holdRepeater.start(direction);
    };
    const onPointerUp = (event) => {
      event.preventDefault();
      holdRepeater.stop(direction);
    };
    const onPointerLeave = () => {
      holdRepeater.stop(direction);
    };
    padHandlers.set(button, {
      onPointerDown,
      onPointerUp,
      onPointerLeave,
    });
    button.addEventListener("pointerdown", onPointerDown);
    button.addEventListener("pointerup", onPointerUp);
    button.addEventListener("pointercancel", onPointerUp);
    button.addEventListener("pointerleave", onPointerLeave);
  });
  window.addEventListener("keydown", onKeyDown);

  try {
    const appState = store.getState();
    const battleReturnContext = readBattleReturnContext();
    const mapEntryContext = readMapEntryContext();
    const {
      freshLocationEntry,
      resumeFromSavedPosition,
      returningFromBattle,
      requestedMapId,
    } = deriveMapLaunchContext(appState, battleReturnContext, mapEntryContext);
    mapDefinition = await loadMapDefinition(requestedMapId);
    const currentSelection = returningFromBattle
      ? buildEncounterSelection(mapDefinition, {
        selected_location_group: appState.selectedLocationGroup,
        selected_location: appState.selectedLocation,
      })
      : {
        selected_location_group: appState.selectedLocationGroup,
        selected_location: appState.selectedLocation,
      };
    if (returningFromBattle) {
      store.patch({
        selectedLocationGroup: currentSelection.selected_location_group,
        selectedLocation: currentSelection.selected_location,
      });
    }
    if (!isMapSelectionCompatible(mapDefinition, currentSelection)) {
      mapStatus.textContent = "現在のLocationではこのマップへ移動できません。";
      mapMeta.innerHTML = "<div>Locationを対応する場所に合わせてから移動してください。</div>";
      return () => {
        confirmBtn.removeEventListener("click", onConfirm);
        locationBtn.removeEventListener("click", onGoLocation);
        menuBtn.removeEventListener("click", onGoMenu);
        battleBtn.removeEventListener("click", onGoBattle);
        padButtons.forEach((button) => {
          const handlers = padHandlers.get(button);
          if (!handlers) return;
          button.removeEventListener("pointerdown", handlers.onPointerDown);
          button.removeEventListener("pointerup", handlers.onPointerUp);
          button.removeEventListener("pointercancel", handlers.onPointerUp);
          button.removeEventListener("pointerleave", handlers.onPointerLeave);
        });
        holdRepeater.stop();
        window.removeEventListener("keydown", onKeyDown);
      };
    }
    mapState = deriveInitialMapState(appState, mapDefinition, {
      resumeFromSavedPosition,
    });
    mapDefinition = applySwitchStateToMap(
      { ...mapDefinition, openedTreasures: mapState.opened_treasures },
      mapState.switch_states,
    );
    if (freshLocationEntry) {
      sessionStorage.removeItem(MAP_ENTRY_CONTEXT_KEY);
      patchMapMenuState({ map_return_pending: false });
    }
    if (resumeFromSavedPosition) {
      sessionStorage.removeItem(BATTLE_RETURN_CONTEXT_KEY);
      patchMapMenuState({ map_return_pending: false });
      if (returningFromBattle) {
        mapState = {
          ...mapState,
          steps_since_reset: 0,
        };
      }
    }
    if (!canOccupyTile(mapDefinition, mapState.tile_x, mapState.tile_y)) {
      mapState = {
        current_map_id: mapDefinition.id,
        tile_x: mapDefinition.spawn.x,
        tile_y: mapDefinition.spawn.y,
        steps_since_reset: 0,
        switch_states: normalizeSwitchStates(mapState?.switch_states),
        opened_treasures: normalizeTreasureStates(mapState?.opened_treasures),
      };
    }
    renderMapTiles(mapLayer, mapDefinition);
    persistCurrentMapState(mapState);
    redraw();
    mapStatus.textContent = resumeFromSavedPosition
      ? `戦闘前の位置から再開しました。エンカウント率 ${(mapDefinition.encounterRate * 100).toFixed(0)}%。`
      : `方向ボタンかキーボード矢印キーで移動できます。エンカウント率 ${(mapDefinition.encounterRate * 100).toFixed(0)}%。`;

    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => redraw());
      resizeObserver.observe(mapViewport);
    } else {
      window.addEventListener("resize", redraw);
    }
  } catch (error) {
    mapStatus.textContent = `マップ読込失敗: ${String(error)}`;
  }

  return () => {
    confirmBtn.removeEventListener("click", onConfirm);
    locationBtn.removeEventListener("click", onGoLocation);
    menuBtn.removeEventListener("click", onGoMenu);
    battleBtn.removeEventListener("click", onGoBattle);
    padButtons.forEach((button) => {
      const handlers = padHandlers.get(button);
      if (!handlers) return;
      button.removeEventListener("pointerdown", handlers.onPointerDown);
      button.removeEventListener("pointerup", handlers.onPointerUp);
      button.removeEventListener("pointercancel", handlers.onPointerUp);
      button.removeEventListener("pointerleave", handlers.onPointerLeave);
    });
    holdRepeater.stop();
    window.removeEventListener("keydown", onKeyDown);
    if (resizeObserver) {
      resizeObserver.disconnect();
    } else {
      window.removeEventListener("resize", redraw);
    }
  };
}
