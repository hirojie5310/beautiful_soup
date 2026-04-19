import { getPyodideRuntime } from "../pyodide_runtime.js";
import {
  DEFAULT_MAP_ID,
  isMapSelectionCompatible,
  loadMapDefinition,
} from "../map_data.js";
import { resolveLocationMapImageUrl } from "../map_images.js";

const BATTLE_START_SELECTION_KEY = "ff3_wasm_battle_start_selection_v1";
const BATTLE_RETURN_CONTEXT_KEY = "ff3_wasm_battle_return_context_v1";
const MAP_ENTRY_CONTEXT_KEY = "ff3_wasm_map_entry_context_v1";

function renderLayout() {
  return `
    <style>
      [data-screen="location"] .frame.location-frame {
        position: relative;
        overflow: hidden;
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        isolation: isolate;
      }
      [data-screen="location"] .frame.location-frame::after {
        content: "";
        position: absolute;
        inset: 0;
        z-index: 0;
        pointer-events: none;
        background: linear-gradient(rgba(8,14,34,0.42), rgba(8,14,34,0.42));
      }
      [data-screen="location"] .frame.location-frame > * {
        position: relative;
        z-index: 1;
      }
    </style>
    <div class="screen medium" data-screen="location">
      <section id="locationFrame" class="frame location-frame">
        <h1 class="title">Battle Wasm Runner / Location選択</h1>
        <div id="statusLine" class="status">起動中...</div>

        <div class="selector-row">
          <label for="locationGroupSelect">LocationGroup</label>
          <select id="locationGroupSelect"></select>
          <label for="locationSelect">Location</label>
          <select id="locationSelect"></select>
        </div>

        <div class="buttons">
          <button id="startBattleBtn" class="btn" type="button" disabled>戦闘開始</button>
          <button id="mapBtn" class="btn" type="button">マップ</button>
          <button id="titleBtn" class="btn" type="button">タイトルへ戻る</button>
          <button id="shopBtn" class="btn" type="button">Shop</button>
          <button id="innBtn" class="btn" type="button">Inn</button>
          <button id="menuBtn" class="btn" type="button">メニュー</button>
        </div>
      </section>
    </div>
  `;
}

function setSelectOptions(select, values, selectedValue = "") {
  const wanted = String(selectedValue || "");
  select.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    if (String(value) === wanted) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  if (values.length && !select.value) {
    select.value = String(values[0]);
  }
}

function renderLocationOptions({ locationGroups, locationGroupSelect, locationSelect, state }) {
  setSelectOptions(
    locationGroupSelect,
    locationGroups.map((group) => group.group_name),
    state.selectedLocationGroup,
  );

  const currentGroup = locationGroups.find((group) => group.group_name === locationGroupSelect.value)
    || locationGroups[0];
  const locations = Array.isArray(currentGroup?.locations) ? currentGroup.locations : [];
  setSelectOptions(locationSelect, locations, state.selectedLocation);
}

function syncStoreSelection(store, locationGroupSelect, locationSelect) {
  store.patch({
    selectedLocationGroup: String(locationGroupSelect.value || ""),
    selectedLocation: String(locationSelect.value || ""),
  });
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const statusLine = mountNode.querySelector("#statusLine");
  const locationFrame = mountNode.querySelector("#locationFrame");
  const locationGroupSelect = mountNode.querySelector("#locationGroupSelect");
  const locationSelect = mountNode.querySelector("#locationSelect");
  const startBattleBtn = mountNode.querySelector("#startBattleBtn");
  const mapBtn = mountNode.querySelector("#mapBtn");
  const titleBtn = mountNode.querySelector("#titleBtn");
  const shopBtn = mountNode.querySelector("#shopBtn");
  const innBtn = mountNode.querySelector("#innBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");

  let locationGroups = [];

  const clearMapReturnPending = () => {
    const currentState = store.getState();
    if (!currentState.menuState?.map_return_pending) return;
    const nextMenuState = {
      ...(currentState.menuState && typeof currentState.menuState === "object" ? currentState.menuState : {}),
      map_return_pending: false,
    };
    store.updateMenuState(nextMenuState);
    if (currentState.saveEnvelope && typeof currentState.saveEnvelope === "object") {
      store.updateSaveEnvelope({
        ...currentState.saveEnvelope,
        menu_state: nextMenuState,
        selected_location_group: currentState.selectedLocationGroup,
        selected_location: currentState.selectedLocation,
        saved_at: new Date().toISOString(),
      });
    }
  };

  const applyLocationFrameBackground = (locationGroupName) => {
    const mapImageUrl = resolveLocationMapImageUrl(locationGroupName, () => {
      applyLocationFrameBackground(locationGroupName);
    });
    if (!locationFrame) return;
    if (mapImageUrl) {
      locationFrame.style.backgroundImage = `linear-gradient(rgba(8,14,34,0.42), rgba(8,14,34,0.42)), url("${mapImageUrl}")`;
      return;
    }
    locationFrame.style.backgroundImage = "none";
  };

  const handleGroupChange = () => {
    renderLocationOptions({
      locationGroups,
      locationGroupSelect,
      locationSelect,
      state: {
        selectedLocationGroup: String(locationGroupSelect.value || ""),
        selectedLocation: "",
      },
    });
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    applyLocationFrameBackground(locationGroupSelect.value);
  };
  const handleLocationChange = () => {
    syncStoreSelection(store, locationGroupSelect, locationSelect);
  };
  const handleStartBattle = () => {
    const payload = {
      selected_location_group: String(locationGroupSelect.value || ""),
      selected_location: String(locationSelect.value || ""),
    };
    sessionStorage.setItem(BATTLE_START_SELECTION_KEY, JSON.stringify(payload));
    sessionStorage.setItem(BATTLE_RETURN_CONTEXT_KEY, JSON.stringify({
      return_route: "location",
      resume_map: false,
    }));
    store.patch({
      selectedLocationGroup: payload.selected_location_group,
      selectedLocation: payload.selected_location,
    });
    navigate("battle");
  };
  const handleGoTitle = () => {
    store.resetForTitle();
    navigate("title");
  };
  const handleGoMap = () => {
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    statusLine.textContent = "マップ整合性を確認中...";
    void loadMapDefinition(DEFAULT_MAP_ID)
      .then((mapDefinition) => {
        const selection = {
          selected_location_group: String(locationGroupSelect.value || ""),
          selected_location: String(locationSelect.value || ""),
        };
        if (!isMapSelectionCompatible(mapDefinition, selection)) {
          statusLine.textContent = "このLocationでは対応するマップへ移動できません。";
          return;
        }
        sessionStorage.setItem(MAP_ENTRY_CONTEXT_KEY, JSON.stringify({
          entry_route: "location",
          fresh_start: true,
          map_id: DEFAULT_MAP_ID,
        }));
        statusLine.textContent = "マップへ移動します。";
        navigate("map");
      })
      .catch((error) => {
        statusLine.textContent = `マップ確認失敗: ${String(error)}`;
      });
  };
  const handleGoShop = () => {
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    navigate("shop");
  };
  const handleGoInn = () => {
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    navigate("inn");
  };
  const handleGoMenu = () => {
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    navigate("menu");
  };

  locationGroupSelect.addEventListener("change", handleGroupChange);
  locationSelect.addEventListener("change", handleLocationChange);
  startBattleBtn.addEventListener("click", handleStartBattle);
  mapBtn.addEventListener("click", handleGoMap);
  titleBtn.addEventListener("click", handleGoTitle);
  shopBtn.addEventListener("click", handleGoShop);
  innBtn.addEventListener("click", handleGoInn);
  menuBtn.addEventListener("click", handleGoMenu);

  try {
    clearMapReturnPending();
    statusLine.textContent = "Pyodide 起動中...";
    const pyodide = await getPyodideRuntime();
    const getSelectionJson = pyodide.globals.get("get_location_selection_json");
    const selectionPayload = JSON.parse(getSelectionJson());
    locationGroups = Array.isArray(selectionPayload?.groups) ? selectionPayload.groups : [];

    const storedState = store.getState();
    const selectedLocationGroup = storedState.selectedLocationGroup || selectionPayload?.selected_group || "";
    const selectedLocation = storedState.selectedLocation || selectionPayload?.selected_location || "";

    renderLocationOptions({
      locationGroups,
      locationGroupSelect,
      locationSelect,
      state: {
        selectedLocationGroup,
        selectedLocation,
      },
    });
    syncStoreSelection(store, locationGroupSelect, locationSelect);
    applyLocationFrameBackground(locationGroupSelect.value);

    startBattleBtn.disabled = false;
    statusLine.textContent = "Locationを選択して「戦闘開始」を押してください。";
  } catch (error) {
    statusLine.textContent = `起動失敗: ${String(error)}`;
  }

  return () => {
    locationGroupSelect.removeEventListener("change", handleGroupChange);
    locationSelect.removeEventListener("change", handleLocationChange);
    startBattleBtn.removeEventListener("click", handleStartBattle);
    mapBtn.removeEventListener("click", handleGoMap);
    titleBtn.removeEventListener("click", handleGoTitle);
    shopBtn.removeEventListener("click", handleGoShop);
    innBtn.removeEventListener("click", handleGoInn);
    menuBtn.removeEventListener("click", handleGoMenu);
  };
}
