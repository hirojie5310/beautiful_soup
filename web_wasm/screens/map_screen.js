import {
  buildEncounterSelection,
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
  shouldTriggerEncounter,
} from "../map_data.js";
import { triggerAutoSaveFromEnvelope } from "./screen_shared.js";

const DISPLAY_TILE_SIZE = 22;
const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function asNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
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
    };
  }
  return {
    current_map_id: wantedMapId,
    tile_x: asNumber(mapDefinition?.spawn?.x, 0),
    tile_y: asNumber(mapDefinition?.spawn?.y, 0),
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
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 68px));
        justify-content: center;
        gap: 8px;
      }
      [data-screen="map"] .map-pad-spacer {
        visibility: hidden;
      }
      [data-screen="map"] .map-pad-btn {
        min-height: 54px;
        font-size: 1rem;
        font-weight: 700;
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
            <span class="map-pad-spacer"></span>
            <button class="btn map-pad-btn" type="button" data-dir="up">↑</button>
            <span class="map-pad-spacer"></span>
            <button class="btn map-pad-btn" type="button" data-dir="left">←</button>
            <button class="btn map-pad-btn" type="button" data-dir="down">↓</button>
            <button class="btn map-pad-btn" type="button" data-dir="right">→</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function objectLabel(type) {
  if (type === "exit") return "EXIT";
  if (type === "switch") return "SW";
  if (type === "chest") return "宝";
  return "OBJ";
}

export function findStandingObject(mapDefinition, mapState) {
  return (mapDefinition?.objects || []).find((row) => (
    Number(row?.x) === Number(mapState?.tile_x) && Number(row?.y) === Number(mapState?.tile_y)
  ));
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

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const mapStatus = mountNode.querySelector("#mapStatus");
  const mapViewport = mountNode.querySelector("#mapViewport");
  const mapLayer = mountNode.querySelector("#mapLayer");
  const mapMeta = mountNode.querySelector("#mapMeta");
  const locationBtn = mountNode.querySelector("#locationBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");
  const battleBtn = mountNode.querySelector("#battleBtn");
  const padButtons = Array.from(mountNode.querySelectorAll("[data-dir]"));

  let mapDefinition = null;
  let mapState = null;
  let resizeObserver = null;
  let encounterLocked = false;
  let mapTransitionLocked = false;

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
      };
      if (!canOccupyTile(mapDefinition, mapState.tile_x, mapState.tile_y)) {
        mapState = {
          current_map_id: nextMapDefinition.id,
          tile_x: asNumber(nextMapDefinition.spawn?.x, 0),
          tile_y: asNumber(nextMapDefinition.spawn?.y, 0),
        };
      }
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
    if (shouldTriggerEncounter(mapDefinition)) {
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
    if (!direction) return;
    event.preventDefault();
    void tryMove(direction);
  };

  const onGoLocation = () => navigate("location");
  const onGoMenu = () => navigate("menu");
  const onGoBattle = () => navigate("battle");
  const padHandlers = new Map();

  locationBtn.addEventListener("click", onGoLocation);
  menuBtn.addEventListener("click", onGoMenu);
  battleBtn.addEventListener("click", onGoBattle);
  padButtons.forEach((button) => {
    const onClick = () => {
      void tryMove(String(button.dataset.dir || ""));
    };
    padHandlers.set(button, onClick);
    button.addEventListener("click", onClick);
  });
  window.addEventListener("keydown", onKeyDown);

  try {
    const appState = store.getState();
    const battleReturnContext = readBattleReturnContext();
    const resumeFromSavedPosition = Boolean(
      battleReturnContext?.return_route === "map"
      && battleReturnContext?.resume_map,
    );
    const requestedMapId = String(
      (resumeFromSavedPosition && battleReturnContext?.map_id)
      || appState?.menuState?.map_state?.current_map_id
      || appState?.saveEnvelope?.save?.map?.map
      || DEFAULT_MAP_ID,
    );
    mapDefinition = await loadMapDefinition(requestedMapId);
    const currentSelection = {
      selected_location_group: appState.selectedLocationGroup,
      selected_location: appState.selectedLocation,
    };
    if (!isMapSelectionCompatible(mapDefinition, currentSelection)) {
      mapStatus.textContent = "現在のLocationではこのマップへ移動できません。";
      mapMeta.innerHTML = "<div>Locationを対応する場所に合わせてから移動してください。</div>";
      return () => {
        locationBtn.removeEventListener("click", onGoLocation);
        menuBtn.removeEventListener("click", onGoMenu);
        battleBtn.removeEventListener("click", onGoBattle);
        padButtons.forEach((button) => {
          const onClick = padHandlers.get(button);
          if (onClick) button.removeEventListener("click", onClick);
        });
        window.removeEventListener("keydown", onKeyDown);
      };
    }
    mapState = deriveInitialMapState(appState, mapDefinition, {
      resumeFromSavedPosition,
    });
    if (resumeFromSavedPosition) {
      sessionStorage.removeItem(BATTLE_RETURN_CONTEXT_KEY);
    }
    if (!canOccupyTile(mapDefinition, mapState.tile_x, mapState.tile_y)) {
      mapState = {
        current_map_id: mapDefinition.id,
        tile_x: mapDefinition.spawn.x,
        tile_y: mapDefinition.spawn.y,
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
    locationBtn.removeEventListener("click", onGoLocation);
    menuBtn.removeEventListener("click", onGoMenu);
    battleBtn.removeEventListener("click", onGoBattle);
    padButtons.forEach((button) => {
      const onClick = padHandlers.get(button);
      if (onClick) {
        button.removeEventListener("click", onClick);
      }
    });
    window.removeEventListener("keydown", onKeyDown);
    if (resizeObserver) {
      resizeObserver.disconnect();
    } else {
      window.removeEventListener("resize", redraw);
    }
  };
}
