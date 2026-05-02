import { saveRepository } from "./save_repository.js";

export const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
export const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";

export function readBattleStartSelectionFromSession() {
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
        is_boss: parsed.is_boss === true,
      };
    }
  } catch (_error) {
    return null;
  }
  return null;
}

export function readBattleReturnContextFromSession() {
  try {
    const raw = sessionStorage.getItem(BATTLE_RETURN_CONTEXT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

export function writeBattleReturnContextToSession(nextContext) {
  try {
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify(nextContext || {}));
    return nextContext && typeof nextContext === "object" ? nextContext : null;
  } catch (_error) {
    return null;
  }
}

export function compactSaveEnvelope(envelope) {
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

export function downloadSaveEnvelope(envelope) {
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

export function buildRuntimeSaveEnvelope({
  saveObj,
  currentBattleSelection,
  storedEnvelope = null,
  menuState,
  selectedLocationGroup = "",
  selectedLocation = "",
}) {
  return saveRepository.makeEnvelope(saveObj, {
    selectedLocationGroup: selectedLocationGroup
      || currentBattleSelection?.selected_location_group
      || storedEnvelope?.selected_location_group
      || "",
    selectedLocation: selectedLocation
      || currentBattleSelection?.selected_location
      || storedEnvelope?.selected_location
      || "",
    menuState,
  });
}

function cloneJsonValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function asPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asStringArray(value) {
  return Array.isArray(value)
    ? value.map((row) => String(row || "")).filter(Boolean)
    : [];
}

function ensurePlainObject(parent, key) {
  const current = asPlainObject(parent?.[key]);
  parent[key] = current;
  return current;
}

function findPartyEntryByName(saveObj, name) {
  const party = Array.isArray(saveObj?.party) ? saveObj.party : [];
  return party.find((entry) => entry && typeof entry === "object" && entry.name === name) || null;
}

function setNumericLeaf(root, path, value) {
  if (!root || typeof root !== "object" || !Array.isArray(path) || !path.length) return;
  let current = root;
  for (const segment of path.slice(0, -1)) {
    const key = String(segment || "");
    if (!key) return;
    current = ensurePlainObject(current, key);
  }
  current[String(path[path.length - 1] || "")] = Number(value || 0);
}

export function applyBattleSavePatchToSave(saveObj, battleSavePatch) {
  const nextSave = cloneJsonValue(saveObj || {});
  const patch = asPlainObject(battleSavePatch);
  const resourceChanges = asPlainObject(patch.resource_changes);
  const partyChanges = Array.isArray(patch.party_changes) ? patch.party_changes : [];
  const inventoryChanges = Array.isArray(patch.inventory_changes) ? patch.inventory_changes : [];
  const itemStockChanges = Array.isArray(patch.item_stock_changes) ? patch.item_stock_changes : [];

  if (resourceChanges.gil && typeof resourceChanges.gil === "object") {
    nextSave.gil = Number(resourceChanges.gil.after ?? nextSave.gil ?? 0);
  }
  if (resourceChanges.cp && typeof resourceChanges.cp === "object") {
    nextSave.CP = Number(resourceChanges.cp.after ?? nextSave.CP ?? 0);
  }

  if (!Array.isArray(nextSave.party)) {
    nextSave.party = [];
  }
  partyChanges.forEach((memberPatch) => {
    if (!memberPatch || typeof memberPatch !== "object") return;
    const name = String(memberPatch.name || "");
    if (!name) return;
    const entry = findPartyEntryByName(nextSave, name);
    if (!entry) return;
    ["hp", "max_hp", "level", "exp"].forEach((key) => {
      if (memberPatch[key] && typeof memberPatch[key] === "object" && "after" in memberPatch[key]) {
        entry[key] = Number(memberPatch[key].after ?? entry[key] ?? 0);
      }
    });

    if (memberPatch.job_level && typeof memberPatch.job_level === "object") {
      const nextJobLevel = ensurePlainObject(entry, "job_level");
      ["level", "skill_point"].forEach((key) => {
        if (memberPatch.job_level[key] && typeof memberPatch.job_level[key] === "object") {
          nextJobLevel[key] = Number(memberPatch.job_level[key].after ?? nextJobLevel[key] ?? 0);
        }
      });
    }

    if (memberPatch.mp_levels && typeof memberPatch.mp_levels === "object") {
      const nextMpLevels = ensurePlainObject(entry, "mp_levels");
      const nextMp = ensurePlainObject(entry, "mp");
      Object.entries(memberPatch.mp_levels).forEach(([level, levelPatch]) => {
        if (!levelPatch || typeof levelPatch !== "object") return;
        const row = ensurePlainObject(nextMpLevels, String(level));
        if ("current_after" in levelPatch) {
          row.current = Number(levelPatch.current_after ?? row.current ?? 0);
          nextMp[`L${level}MP`] = row.current;
        }
        if ("max_after" in levelPatch) {
          row.max = Number(levelPatch.max_after ?? row.max ?? 0);
        }
      });
    }

    if (memberPatch.status_effects && typeof memberPatch.status_effects === "object") {
      entry.status_effects = { ...asPlainObject(memberPatch.status_effects.after) };
    }
    if (memberPatch.status_icons && typeof memberPatch.status_icons === "object") {
      entry.status_icons = asStringArray(memberPatch.status_icons.after);
    }
  });

  const inventory = ensurePlainObject(nextSave, "inventory");
  inventoryChanges.forEach((change) => {
    if (!change || typeof change !== "object" || !Array.isArray(change.path)) return;
    setNumericLeaf(inventory, change.path, change.after);
  });

  const itemStock = ensurePlainObject(nextSave, "item_stock");
  itemStockChanges.forEach((change) => {
    if (!change || typeof change !== "object" || !Array.isArray(change.path)) return;
    setNumericLeaf(itemStock, change.path, change.after);
  });

  return nextSave;
}

export function buildPatchedBattleEnvelope({
  currentEnvelope,
  result,
  menuState,
}) {
  if (!currentEnvelope || typeof currentEnvelope !== "object") return null;
  if (!currentEnvelope.save || typeof currentEnvelope.save !== "object") return null;
  if (!result?.battle_save_patch || typeof result.battle_save_patch !== "object") return null;
  const nextSave = applyBattleSavePatchToSave(currentEnvelope.save, result.battle_save_patch);
  return saveRepository.makeEnvelope(nextSave, {
    selectedLocationGroup: result?.selected_location_group || currentEnvelope.selected_location_group || "",
    selectedLocation: result?.selected_location || currentEnvelope.selected_location || "",
    menuState,
  });
}

export function syncRuntimeSaveToBrowser({
  pyodide,
  appStore = null,
  cachedStoredEnvelope = null,
  currentBattleSelection,
  menuState,
}) {
  if (!pyodide) return { persisted: false, envelope: null };
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return { persisted: false, envelope: null };
  try {
    const saveObj = JSON.parse(saveJson);
    const storedEnvelope = appStore?.getState()?.saveEnvelope || cachedStoredEnvelope || saveRepository.loadLocalMirror();
    const envelope = buildRuntimeSaveEnvelope({
      saveObj,
      currentBattleSelection,
      storedEnvelope,
      menuState,
    });
    const persisted = appStore
      ? appStore.updateSaveEnvelope(envelope, { reason: "runtime_checkpoint" })
      : saveRepository.commitSync({ reason: "runtime_checkpoint", envelope }).persisted;
    return { persisted, envelope };
  } catch (_error) {
    return { persisted: false, envelope: null };
  }
}

export async function persistFinishedBattleSave({
  pyodide,
  appStore = null,
  result,
  menuState,
}) {
  const currentEnvelope = appStore?.getState()?.saveEnvelope || saveRepository.loadLocalMirror();
  const patchedEnvelope = buildPatchedBattleEnvelope({
    currentEnvelope,
    result,
    menuState,
  });
  const patchMirrored = patchedEnvelope
    ? (
      appStore
        ? appStore.updateSaveEnvelope(patchedEnvelope, { reason: "battle_finished" })
        : saveRepository.commitSync({ reason: "battle_finished", envelope: patchedEnvelope }).persisted
    )
    : false;

  async function commitFallbackEnvelope() {
    if (!patchedEnvelope) return { persisted: false, autosaved: false, envelope: null };
    const commitResult = await saveRepository.commit({
      reason: "battle_finished",
      envelope: patchedEnvelope,
      alreadyMirrored: patchMirrored,
    });
    return {
      persisted: patchMirrored || commitResult.persisted,
      autosaved: commitResult.autosaved,
      envelope: patchedEnvelope,
    };
  }

  if (!pyodide) return commitFallbackEnvelope();
  const exportSaveJson = pyodide.globals.get("export_runtime_save_json");
  const saveJson = exportSaveJson ? String(exportSaveJson() || "") : "";
  if (!saveJson) return commitFallbackEnvelope();
  try {
    const saveObj = JSON.parse(saveJson);
    const envelope = saveRepository.makeEnvelope(saveObj, {
      selectedLocationGroup: result?.selected_location_group,
      selectedLocation: result?.selected_location,
      menuState,
    });
    const persisted = appStore
      ? appStore.updateSaveEnvelope(envelope, { reason: "battle_finished" })
      : saveRepository.commitSync({ reason: "battle_finished", envelope }).persisted;
    const commitResult = await saveRepository.commit({
      reason: "battle_finished",
      envelope,
      alreadyMirrored: persisted,
    });
    const autosaved = commitResult.autosaved;
    return { persisted, autosaved, envelope };
  } catch (_error) {
    return commitFallbackEnvelope();
  }
}
