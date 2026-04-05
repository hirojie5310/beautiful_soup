import {
  getStoredLocationSelection,
  syncStoredLocationSelection,
} from "../location_shared.js";
import {
  LOCAL_MENU_STORAGE_KEY,
  makeSaveEnvelope,
  parseMenuStateFromStorage,
  persistSaveEnvelopeToStorage,
  restoreSaveEnvelopeFromStorage,
} from "../shared_storage.js";

function cloneState(state) {
  if (typeof structuredClone === "function") {
    return structuredClone(state);
  }
  return JSON.parse(JSON.stringify(state));
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

  const storedSelection = getStoredLocationSelection();
  const storedEnvelope = restoreSaveEnvelopeFromStorage();
  const storedMenuState = parseMenuStateFromStorage();
  state = {
    ...state,
    selectedLocationGroup: String(storedSelection?.selected_location_group || ""),
    selectedLocation: String(storedSelection?.selected_location || ""),
    menuState: storedMenuState && typeof storedMenuState === "object"
      ? storedMenuState
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
    state = {
      ...state,
      menuState,
    };
    try {
      localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(menuState));
    } catch (_error) {
      // noop
    }
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
    const persisted = persistSaveEnvelopeToStorage(nextEnvelope);
    if (!persisted) return false;

    state = {
      ...state,
      saveEnvelope: nextEnvelope,
      selectedLocationGroup: String(nextEnvelope.selected_location_group || ""),
      selectedLocation: String(nextEnvelope.selected_location || ""),
      menuState: nextEnvelope.menu_state && typeof nextEnvelope.menu_state === "object"
        ? nextEnvelope.menu_state
        : state.menuState,
    };
    if (nextEnvelope.menu_state && typeof nextEnvelope.menu_state === "object") {
      try {
        localStorage.setItem(LOCAL_MENU_STORAGE_KEY, JSON.stringify(nextEnvelope.menu_state));
      } catch (_error) {
        // noop
      }
    }
    notify();
    return true;
  }

  function createDefaultEnvelope() {
    return makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {
      selectedLocationGroup: state.selectedLocationGroup,
      selectedLocation: state.selectedLocation,
      menuState: state.menuState,
    });
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  }

  return {
    getState,
    patch,
    updateMenuState,
    updateSaveEnvelope,
    createDefaultEnvelope,
    subscribe,
  };
}
