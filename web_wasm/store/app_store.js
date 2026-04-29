import {
  clearStoredLocationSelection,
  getStoredLocationSelection,
  getStoredLocationSelectionAsync,
  syncStoredLocationSelection,
} from "../location_shared.js";
import { saveRepository } from "../save_repository.js";
import {
  normalizeMemberIndexedRows,
  normalizePartyIdentityOrder,
} from "../shared_party.js";

function cloneState(state) {
  if (typeof structuredClone === "function") {
    return structuredClone(state);
  }
  return JSON.parse(JSON.stringify(state));
}

function normalizeMenuState(menuState) {
  const raw = menuState && typeof menuState === "object" ? menuState : {};
  const sourceParty = Array.isArray(raw.party) ? raw.party : [];
  const party = normalizePartyIdentityOrder(sourceParty);
  const magicSetup = raw.magic_setup && typeof raw.magic_setup === "object"
    ? raw.magic_setup
    : {};
  return {
    ...raw,
    party,
    equipment_by_member: normalizeMemberIndexedRows(sourceParty, raw.equipment_by_member),
    job_candidates_by_member: normalizeMemberIndexedRows(sourceParty, raw.job_candidates_by_member),
    equip_candidates_by_member: normalizeMemberIndexedRows(sourceParty, raw.equip_candidates_by_member),
    magic_candidates_by_member: normalizeMemberIndexedRows(sourceParty, raw.magic_candidates_by_member),
    magic_setup: {
      ...magicSetup,
      equipped_by_member: normalizeMemberIndexedRows(sourceParty, magicSetup.equipped_by_member),
    },
  };
}

export function createAppStore() {
  const listeners = new Set();
  let state = {
    route: "location",
    selectedLocationGroup: "",
    selectedLocation: "",
    menuMemberIndex: 0,
    menuState: { party: [], resources: { cp: 0, cp_max: 255, gil: 0 } },
    saveEnvelope: null,
  };
  let initialized = false;

  const storedSelection = getStoredLocationSelection();
  const storedEnvelope = saveRepository.loadLocalMirror();
  const storedMenuState = saveRepository.loadMenuState();
  const initialMenuStateSource = (
    storedEnvelope?.menu_state && typeof storedEnvelope.menu_state === "object"
      ? storedEnvelope.menu_state
      : storedMenuState
  );
  state = {
    ...state,
    selectedLocationGroup: String(storedSelection?.selected_location_group || ""),
    selectedLocation: String(storedSelection?.selected_location || ""),
    menuState: initialMenuStateSource && typeof initialMenuStateSource === "object"
      ? normalizeMenuState(initialMenuStateSource)
      : state.menuState,
    saveEnvelope: storedEnvelope,
  };

  function getState() {
    return cloneState(state);
  }

  function notify() {
    const snapshot = getState();
    listeners.forEach((listener) => listener(snapshot));
  }

  async function initialize() {
    if (initialized) return getState();
    initialized = true;

    const storedSelectionAsync = await getStoredLocationSelectionAsync();
    const storedEnvelopeAsync = await saveRepository.load();
    const hasAsyncSelection = (
      storedSelectionAsync
      && typeof storedSelectionAsync === "object"
      && (
        storedSelectionAsync.selected_location_group
        || storedSelectionAsync.selected_location
      )
    );
    if (hasAsyncSelection) {
      state = {
        ...state,
        selectedLocationGroup: String(storedSelectionAsync.selected_location_group || ""),
        selectedLocation: String(storedSelectionAsync.selected_location || ""),
      };
    }
    if (!storedEnvelopeAsync || typeof storedEnvelopeAsync !== "object") {
      return getState();
    }

    const normalizedEnvelope = {
      ...storedEnvelopeAsync,
      selected_location_group: String(
        storedEnvelopeAsync.selected_location_group || state.selectedLocationGroup || "",
      ),
      selected_location: String(
        storedEnvelopeAsync.selected_location || state.selectedLocation || "",
      ),
    };
    const nextMenuState = (
      normalizedEnvelope.menu_state && typeof normalizedEnvelope.menu_state === "object"
    )
      ? normalizeMenuState(normalizedEnvelope.menu_state)
      : state.menuState;

    state = {
      ...state,
      saveEnvelope: normalizedEnvelope,
      selectedLocationGroup: String(normalizedEnvelope.selected_location_group || ""),
      selectedLocation: String(normalizedEnvelope.selected_location || ""),
      menuState: nextMenuState,
    };

    if (normalizedEnvelope.menu_state && typeof normalizedEnvelope.menu_state === "object") {
      saveRepository.saveMenuState(nextMenuState);
    }

    return getState();
  }

  function patch(partialState) {
    const nextState = {
      ...state,
      ...(partialState && typeof partialState === "object" ? partialState : {}),
    };

    const locationChanged = (
      nextState.selectedLocationGroup !== state.selectedLocationGroup
      || nextState.selectedLocation !== state.selectedLocation
    );

    state = nextState;

    if (locationChanged) {
      syncStoredLocationSelection(nextState.selectedLocationGroup, nextState.selectedLocation);
    }

    notify();
  }

  function updateMenuState(menuState) {
    const normalizedMenuState = normalizeMenuState(menuState);
    state = {
      ...state,
      menuState: normalizedMenuState,
    };
    saveRepository.saveMenuState(normalizedMenuState);
    notify();
  }

  function updateSaveEnvelope(envelope) {
    if (!envelope || typeof envelope !== "object") return false;
    const nextEnvelope = {
      ...envelope,
      selected_location_group: String(
        envelope.selected_location_group || state.selectedLocationGroup || "",
      ),
      selected_location: String(
        envelope.selected_location || state.selectedLocation || "",
      ),
    };
    const persisted = saveRepository.saveLocalMirror(nextEnvelope);
    if (!persisted) return false;

    state = {
      ...state,
      saveEnvelope: nextEnvelope,
      selectedLocationGroup: String(nextEnvelope.selected_location_group || ""),
      selectedLocation: String(nextEnvelope.selected_location || ""),
      menuState: nextEnvelope.menu_state && typeof nextEnvelope.menu_state === "object"
        ? normalizeMenuState(nextEnvelope.menu_state)
        : state.menuState,
    };
    if (nextEnvelope.menu_state && typeof nextEnvelope.menu_state === "object") {
      saveRepository.saveMenuState(normalizeMenuState(nextEnvelope.menu_state));
    }
    notify();
    return true;
  }

  function createDefaultEnvelope() {
    return saveRepository.makeEnvelope({ gil: 0, inventory: {}, party: [] }, {
      selectedLocationGroup: state.selectedLocationGroup,
      selectedLocation: state.selectedLocation,
      menuState: state.menuState,
    });
  }

  function resetForTitle() {
    clearStoredLocationSelection();
    saveRepository.clearLocalMirrors();
    state = {
      ...state,
      selectedLocationGroup: "",
      selectedLocation: "",
      menuMemberIndex: 0,
      menuState: { party: [], resources: { cp: 0, cp_max: 255, gil: 0 } },
      saveEnvelope: null,
    };
    notify();
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }

  return {
    getState,
    initialize,
    patch,
    updateMenuState,
    updateSaveEnvelope,
    createDefaultEnvelope,
    resetForTitle,
    subscribe,
  };
}
