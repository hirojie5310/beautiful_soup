export const DEFAULT_MAP_ID = "Alter_Cave_B1";

const MAP_MANIFEST = {
  Airship_of_Cid: new URL("../assets/maps/Airship_of_Cid.json", import.meta.url).href,
  Alter_Cave_B1: new URL("../assets/maps/Alter_Cave_B1.json", import.meta.url).href,
  Alter_Cave_B2: new URL("../assets/maps/Alter_Cave_B2.json", import.meta.url).href,
  Alter_Cave_B3: new URL("../assets/maps/Alter_Cave_B3.json", import.meta.url).href,
  Alter_Cave_B4: new URL("../assets/maps/Alter_Cave_B4.json", import.meta.url).href,
  Alter_Cave_Crystal_Room: new URL("../assets/maps/Alter_Cave_Crystal_Room.json", import.meta.url).href,
  Castle_Sasune: new URL("../assets/maps/Castle_Sasune.json", import.meta.url).href,
  Castle_Sasune_MainKeep_B1F: new URL("../assets/maps/Castle_Sasune_MainKeep_B1F.json", import.meta.url).href,
  Castle_Sasune_MainKeep_1F: new URL("../assets/maps/Castle_Sasune_MainKeep_1F.json", import.meta.url).href,
  Castle_Sasune_MainKeep_2F: new URL("../assets/maps/Castle_Sasune_MainKeep_2F.json", import.meta.url).href,
  Castle_Sasune_MainKeep_3F: new URL("../assets/maps/Castle_Sasune_MainKeep_3F.json", import.meta.url).href,
  Castle_Sasune_MainKeep_4F: new URL("../assets/maps/Castle_Sasune_MainKeep_4F.json", import.meta.url).href,
  Castle_Sasune_Tower_West_1F: new URL("../assets/maps/Castle_Sasune_Tower_West_1F.json", import.meta.url).href,
  Castle_Sasune_Tower_West_2F: new URL("../assets/maps/Castle_Sasune_Tower_West_2F.json", import.meta.url).href,
  Castle_Sasune_Tower_West_3F: new URL("../assets/maps/Castle_Sasune_Tower_West_3F.json", import.meta.url).href,
  Castle_Sasune_Tower_West_4F: new URL("../assets/maps/Castle_Sasune_Tower_West_4F.json", import.meta.url).href,
  Castle_Sasune_Tower_East_1F: new URL("../assets/maps/Castle_Sasune_Tower_East_1F.json", import.meta.url).href,
  Castle_Sasune_Tower_East_2F: new URL("../assets/maps/Castle_Sasune_Tower_East_2F.json", import.meta.url).href,
  Castle_Sasune_Tower_East_3F: new URL("../assets/maps/Castle_Sasune_Tower_East_3F.json", import.meta.url).href,
  Castle_Sasune_Tower_East_4F: new URL("../assets/maps/Castle_Sasune_Tower_East_4F.json", import.meta.url).href,
  FloatingContinent: new URL("../assets/maps/FloatingContinent.json", import.meta.url).href,
  Kazus_Inn_ItemShop_1F: new URL("../assets/maps/Kazus-Inn_ItemShop_1F.json", import.meta.url).href,
  Kazus_Inn_ItemShop_2F: new URL("../assets/maps/Kazus-Inn_ItemShop_2F.json", import.meta.url).href,
  Kazus: new URL("../assets/maps/Kazus.json", import.meta.url).href,
  Kazus_ArmorShop: new URL("../assets/maps/Kazus-ArmorShop.json", import.meta.url).href,
  Kazus_Blacksmith: new URL("../assets/maps/Kazus-Blacksmith.json", import.meta.url).href,
  Kazus_MagicShop: new URL("../assets/maps/Kazus-MagicShop.json", import.meta.url).href,
  Kazus_Shrine: new URL("../assets/maps/Kazus-Shrine.json", import.meta.url).href,
  Kazus_WeaponShop: new URL("../assets/maps/Kazus-WeaponShop.json", import.meta.url).href,
  Mythril_Mine_B1: new URL("../assets/maps/Mythril_Mine_B1.json", import.meta.url).href,
  Mythril_Mine_B2: new URL("../assets/maps/Mythril_Mine_B2.json", import.meta.url).href,
  Sealed_Cave_B1: new URL("../assets/maps/Sealed_Cave_B1.json", import.meta.url).href,
  Sealed_Cave_B2: new URL("../assets/maps/Sealed_Cave_B2.json", import.meta.url).href,
  Sealed_Cave_B2_1: new URL("../assets/maps/Sealed_Cave_B2_1.json", import.meta.url).href,
  Sealed_Cave_B2_2: new URL("../assets/maps/Sealed_Cave_B2_2.json", import.meta.url).href,
  Sealed_Cave_B3: new URL("../assets/maps/Sealed_Cave_B3.json", import.meta.url).href,
  Ur: new URL("../assets/maps/Ur.json", import.meta.url).href,
  Ur_ElderHouse_1: new URL("../assets/maps/Ur-ElderHouse_1.json", import.meta.url).href,
  Ur_ElderHouse_2: new URL("../assets/maps/Ur-ElderHouse_2.json", import.meta.url).href,
  Ur_ArmorShop: new URL("../assets/maps/Ur-ArmorShop.json", import.meta.url).href,
  Ur_MagicShop: new URL("../assets/maps/Ur-MagicShop.json", import.meta.url).href,
  Ur_WeaponShop: new URL("../assets/maps/Ur-WeaponShop.json", import.meta.url).href,
  Ur_Inn_ItemShop: new URL("../assets/maps/Ur-Inn_ItemShop.json", import.meta.url).href,
  Ur_Pub: new URL("../assets/maps/Ur-Pub.json", import.meta.url).href,
  Ur_Well: new URL("../assets/maps/Ur-Well.json", import.meta.url).href,
  Ur_Shed_1F: new URL("../assets/maps/Ur-Shed_1F.json", import.meta.url).href,
  Ur_Shed_2F: new URL("../assets/maps/Ur-Shed_2F.json", import.meta.url).href,
};

const mapCache = new Map();

function asNumber(value, fallback = 0) {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function parseRow(rowValue) {
  if (Array.isArray(rowValue)) {
    return rowValue.map((value) => asNumber(value, 0));
  }
  return String(rowValue || "")
    .split(",")
    .map((chunk) => asNumber(chunk.trim(), 0));
}

function normalizeObject(row) {
  const targetSpawn = row?.target_spawn && typeof row.target_spawn === "object"
    ? {
      x: asNumber(row.target_spawn.x, 0),
      y: asNumber(row.target_spawn.y, 0),
    }
    : null;
  const spriteImage = String(row?.sprite_image || "");
  return {
    ...row,
    type: String(row?.type || ""),
    name: String(row?.name || ""),
    x: asNumber(row?.x, 0),
    y: asNumber(row?.y, 0),
    target_map: String(row?.target_map || ""),
    target_spawn: targetSpawn,
    sprite_image: spriteImage,
    movement: String(row?.movement || row?.npc_movement || ""),
    direction: String(row?.direction || row?.facing_direction || row?.initial_direction || ""),
    spriteImageUrl: spriteImage ? new URL(spriteImage, import.meta.url).href : "",
  };
}

function normalizeLocationRequirement(rawValue) {
  const source = rawValue && typeof rawValue === "object" ? rawValue : {};
  return {
    group: String(source.group || ""),
    locations: Array.isArray(source.locations)
      ? source.locations.map((value) => String(value || "")).filter(Boolean)
      : [],
  };
}

function normalizeEncounterArea(row) {
  const source = row && typeof row === "object" ? row : {};
  return {
    xMin: asNumber(source.x_min ?? source.xMin, 0),
    yMin: asNumber(source.y_min ?? source.yMin, 0),
    xMax: asNumber(source.x_max ?? source.xMax, 0),
    yMax: asNumber(source.y_max ?? source.yMax, 0),
  };
}

function normalizeEncounterAreas(rawValue) {
  return Array.isArray(rawValue)
    ? rawValue.map(normalizeEncounterArea).filter((row) => row.xMax >= row.xMin && row.yMax >= row.yMin)
    : [];
}

export function buildRenderRows(rows, width, height, padding) {
  const left = asNumber(padding?.left, 0);
  const right = asNumber(padding?.right, 0);
  const top = asNumber(padding?.top, 0);
  const bottom = asNumber(padding?.bottom, 0);
  const fillGid = asNumber(padding?.fill_gid, 0);
  const renderWidth = width + left + right;
  const renderHeight = height + top + bottom;

  return Array.from({ length: renderHeight }, (_unused, renderY) => {
    if (renderY < top || renderY >= top + height) {
      return Array.from({ length: renderWidth }, () => fillGid);
    }
    const sourceY = renderY - top;
    const centerRow = Array.isArray(rows[sourceY]) ? rows[sourceY].slice(0, width) : [];
    while (centerRow.length < width) centerRow.push(fillGid);
    return [
      ...Array.from({ length: left }, () => fillGid),
      ...centerRow,
      ...Array.from({ length: right }, () => fillGid),
    ];
  });
}

export function normalizeMapDefinition(rawMap) {
  const width = asNumber(rawMap?.width, 0);
  const height = asNumber(rawMap?.height, 0);
  const tileWidth = asNumber(rawMap?.tile_width, 16);
  const tileHeight = asNumber(rawMap?.tile_height, tileWidth);
  const tileset = rawMap?.tileset && typeof rawMap.tileset === "object"
    ? rawMap.tileset
    : {};
  const rows = Array.isArray(rawMap?.rows) ? rawMap.rows.map(parseRow) : [];
  const normalizedRows = Array.from({ length: height }, (_unused, y) => {
    const row = Array.isArray(rows[y]) ? rows[y].slice(0, width) : [];
    while (row.length < width) row.push(0);
    return row;
  });
  const renderPadding = {
    top: Math.max(0, asNumber(rawMap?.padding?.top, 0)),
    right: Math.max(0, asNumber(rawMap?.padding?.right, 0)),
    bottom: Math.max(0, asNumber(rawMap?.padding?.bottom, 0)),
    left: Math.max(0, asNumber(rawMap?.padding?.left, 0)),
    fillGid: asNumber(rawMap?.padding?.fill_gid, 0),
  };
  const renderRows = buildRenderRows(normalizedRows, width, height, {
    top: renderPadding.top,
    right: renderPadding.right,
    bottom: renderPadding.bottom,
    left: renderPadding.left,
    fill_gid: renderPadding.fillGid,
  });

  return {
    id: String(rawMap?.id || DEFAULT_MAP_ID),
    name: String(rawMap?.name || rawMap?.id || DEFAULT_MAP_ID),
    width,
    height,
    renderWidth: width + renderPadding.left + renderPadding.right,
    renderHeight: height + renderPadding.top + renderPadding.bottom,
    tileWidth,
    tileHeight,
    baseRows: normalizedRows.map((row) => row.slice()),
    rows: normalizedRows,
    renderRows,
    renderPadding,
    collisionGids: new Set(
      Array.isArray(rawMap?.collision_gids)
        ? rawMap.collision_gids.map((value) => asNumber(value, -1)).filter((value) => value > 0)
        : [],
    ),
    spawn: {
      x: asNumber(rawMap?.spawn?.x, 0),
      y: asNumber(rawMap?.spawn?.y, 0),
    },
    locationRequirement: normalizeLocationRequirement(rawMap?.location_requirement),
    encounterRate: Math.min(1, Math.max(0, asNumber(rawMap?.encounter_rate, 0))),
    encounterAreas: normalizeEncounterAreas(rawMap?.encounter_areas),
    objects: Array.isArray(rawMap?.objects) ? rawMap.objects.map(normalizeObject) : [],
    tileset: {
      name: String(tileset?.name || ""),
      imageUrl: String(tileset?.image ? new URL(tileset.image, import.meta.url).href : ""),
      columns: Math.max(1, asNumber(tileset?.columns, 1)),
      tileCount: Math.max(1, asNumber(tileset?.tile_count, 1)),
    },
  };
}

export function isMapSelectionCompatible(mapDefinition, selection) {
  const requirement = mapDefinition?.locationRequirement && typeof mapDefinition.locationRequirement === "object"
    ? mapDefinition.locationRequirement
    : { group: "", locations: [] };
  if (!requirement.group && (!Array.isArray(requirement.locations) || !requirement.locations.length)) {
    return true;
  }
  const selectedGroup = String(selection?.selected_location_group || selection?.selectedLocationGroup || "");
  const selectedLocation = String(selection?.selected_location || selection?.selectedLocation || "");
  if (requirement.group && selectedGroup !== requirement.group) {
    return false;
  }
  if (Array.isArray(requirement.locations) && requirement.locations.length) {
    return requirement.locations.includes(selectedLocation);
  }
  return true;
}

function hasExplicitLocationRequirement(mapDefinition) {
  const requirement = mapDefinition?.locationRequirement && typeof mapDefinition.locationRequirement === "object"
    ? mapDefinition.locationRequirement
    : { group: "", locations: [] };
  return Boolean(
    String(requirement.group || "")
    || (Array.isArray(requirement.locations) && requirement.locations.length),
  );
}

export function buildEncounterSelection(mapDefinition, fallbackSelection = {}) {
  const requirement = mapDefinition?.locationRequirement && typeof mapDefinition.locationRequirement === "object"
    ? mapDefinition.locationRequirement
    : { group: "", locations: [] };
  return {
    selected_location_group: String(
      requirement.group
      || fallbackSelection?.selected_location_group
      || fallbackSelection?.selectedLocationGroup
      || "",
    ),
    selected_location: String(
      requirement.locations?.[0]
      || fallbackSelection?.selected_location
      || fallbackSelection?.selectedLocation
      || "",
    ),
  };
}

export function getEncounterRateForStep(mapDefinition, stepCountSinceReset = 0) {
  const baseRate = Math.min(1, Math.max(0, Number(mapDefinition?.encounterRate || 0)));
  const normalizedStepCount = Math.max(0, Number(stepCountSinceReset) || 0);
  if (normalizedStepCount >= 1 && normalizedStepCount <= 5) {
    return baseRate / 5;
  }
  return baseRate;
}

export function isInEncounterArea(mapDefinition, position) {
  const areas = Array.isArray(mapDefinition?.encounterAreas) ? mapDefinition.encounterAreas : [];
  if (!areas.length) return true;
  const x = asNumber(position?.tile_x ?? position?.x, NaN);
  const y = asNumber(position?.tile_y ?? position?.y, NaN);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
  return areas.some((area) => (
    x >= area.xMin
    && x <= area.xMax
    && y >= area.yMin
    && y <= area.yMax
  ));
}

export function shouldTriggerEncounter(
  mapDefinition,
  randomValue = Math.random(),
  stepCountSinceReset = 0,
  position = null,
) {
  if (position && !isInEncounterArea(mapDefinition, position)) return false;
  const rate = getEncounterRateForStep(mapDefinition, stepCountSinceReset);
  return Number(randomValue) < rate;
}

export function getMapManifestUrl(mapId) {
  const normalizedId = String(mapId || DEFAULT_MAP_ID);
  return MAP_MANIFEST[normalizedId] || MAP_MANIFEST[DEFAULT_MAP_ID];
}

export async function findCompatibleMapDefinition(selection, options = {}) {
  const preferredMapId = String(options?.preferredMapId || "");
  const hasSelectionContext = Boolean(
    String(selection?.selected_location_group || selection?.selectedLocationGroup || "")
    || String(selection?.selected_location || selection?.selectedLocation || ""),
  );
  const candidateIds = [
    ...(preferredMapId ? [preferredMapId] : []),
    ...Object.keys(MAP_MANIFEST),
  ].filter((value, index, values) => value && values.indexOf(value) === index);

  let fallbackMatch = null;
  for (const mapId of candidateIds) {
    const mapDefinition = await loadMapDefinition(mapId);
    if (!isMapSelectionCompatible(mapDefinition, selection)) {
      continue;
    }
    if (hasExplicitLocationRequirement(mapDefinition)) {
      return mapDefinition;
    }
    fallbackMatch ??= mapDefinition;
  }
  return hasSelectionContext ? null : fallbackMatch;
}

export async function loadMapDefinition(mapId = DEFAULT_MAP_ID) {
  const normalizedId = String(mapId || DEFAULT_MAP_ID);
  if (mapCache.has(normalizedId)) {
    return mapCache.get(normalizedId);
  }
  const request = fetch(getMapManifestUrl(normalizedId))
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`map load failed: ${normalizedId}`);
      }
      const payload = await response.json();
      return normalizeMapDefinition(payload);
    });
  mapCache.set(normalizedId, request);
  return request;
}
