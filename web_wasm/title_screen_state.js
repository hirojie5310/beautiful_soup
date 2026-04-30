import { FIXED_PARTY_SLOT_KEYS, FIXED_PARTY_SLOT_LABELS } from "./shared_party.js";
import { saveRepository } from "./save_repository.js";

export const MANUAL_SAVE_SLOT_IDS = ["slot-1", "slot-2", "slot-3"];

function blankStatusEffects() {
  return {
    Poison: false,
    Blind: false,
    Mini: false,
    Silence: false,
    Toad: false,
    Petrification: false,
    KO: false,
    Confusion: false,
    Sleep: false,
    Paralysis: false,
    "Partial Petrification (1/3)": false,
    "Partial Petrification (1/2)": false,
    "Partial Petrification (Full)": false,
  };
}

function blankMpLevels() {
  return Object.fromEntries(
    Array.from({ length: 8 }, (_unused, index) => [
      String(index + 1),
      { current: 0, max: 0 },
    ]),
  );
}

function blankMagicSlots() {
  return Object.fromEntries(
    Array.from({ length: 8 }, (_unused, index) => [
      `LV${index + 1}`,
      [null, null, null],
    ]),
  );
}

function buildNewGamePartyMember(index) {
  const portraitKey = FIXED_PARTY_SLOT_KEYS[index] || `member-${index + 1}`;
  const name = FIXED_PARTY_SLOT_LABELS[index] || `Member ${index + 1}`;
  return {
    index,
    name,
    level: 1,
    exp: 0,
    job: "Onion Knight",
    current_job: "Onion Knight",
    job_level: { level: 1, skill_point: 0 },
    job_levels: {
      "Onion Knight": { level: 1, skill_point: 0 },
    },
    mp_levels: blankMpLevels(),
    Magic: blankMagicSlots(),
    equipment: {
      main_hand: "Knife",
      off_hand: null,
      head: null,
      body: "Vest",
      arms: null,
    },
    status_effects: blankStatusEffects(),
    row: "front",
    portrait_key: portraitKey,
    image_name: portraitKey,
  };
}

function withoutKoStatusIcons(value) {
  return Array.isArray(value)
    ? value.filter((icon) => String(icon || "").trim().toLowerCase().replace(/[_-]/g, " ") !== "ko")
    : [];
}

export function reviveContinueSaveParty(save) {
  if (!save || typeof save !== "object") return 0;
  const party = Array.isArray(save.party) ? save.party : [];
  let revivedCount = 0;

  party.forEach((member) => {
    if (!member || typeof member !== "object") return;
    if (Number(member.hp ?? 0) > 0) return;
    member.hp = 1;
    member.status_icons = withoutKoStatusIcons(member.status_icons);
    if (member.status_effects && typeof member.status_effects === "object" && !Array.isArray(member.status_effects)) {
      member.status_effects = {
        ...member.status_effects,
        KO: false,
      };
    }
    revivedCount += 1;
  });

  save.party = party;
  return revivedCount;
}

export function createNewGameSaveData() {
  return {
    schema_version: 2,
    gil: 0,
    CP: 0,
    inventory: {},
    item_stock: {},
    event_flag: {},
    treasures: {},
    party: FIXED_PARTY_SLOT_KEYS.map((_key, index) => buildNewGamePartyMember(index)),
  };
}

export async function getDefaultLocationSelection(pyodide) {
  const getSelectionJson = pyodide.globals.get("get_location_selection_json");
  const payload = JSON.parse(String(getSelectionJson() || "{}"));
  return {
    selectedLocationGroup: String(payload?.selected_group || ""),
    selectedLocation: String(payload?.selected_location || ""),
  };
}

export async function hydrateEnvelopeWithRuntime(pyodide, envelope) {
  const baseEnvelope = envelope && typeof envelope === "object"
    ? envelope
    : saveRepository.makeEnvelope(createNewGameSaveData());
  reviveContinueSaveParty(baseEnvelope.save);
  const fallbackSelection = await getDefaultLocationSelection(pyodide);
  const selectedLocationGroup = String(
    baseEnvelope?.selected_location_group || fallbackSelection.selectedLocationGroup || "",
  );
  const selectedLocation = String(
    baseEnvelope?.selected_location || fallbackSelection.selectedLocation || "",
  );

  const bootWithSave = pyodide.globals.get("boot_engine_for_location_with_save_json");
  const getMenuStateJson = pyodide.globals.get("get_menu_state_json");
  const exportRuntimeSaveJson = pyodide.globals.get("export_runtime_save_json");

  bootWithSave(
    selectedLocationGroup,
    selectedLocation,
    JSON.stringify(baseEnvelope.save || createNewGameSaveData()),
    7,
  );

  const runtimeSave = JSON.parse(String(exportRuntimeSaveJson() || "{}"));
  const menuState = JSON.parse(String(getMenuStateJson() || "{}"));

  return {
    ...baseEnvelope,
    saved_at: new Date().toISOString(),
    selected_location_group: selectedLocationGroup,
    selected_location: selectedLocation,
    save: runtimeSave,
    menu_state: menuState,
  };
}

export async function persistAutoSave(envelope) {
  const result = await saveRepository.commit({
    reason: "new_game_initialized",
    envelope,
  });
  return result.persisted;
}
