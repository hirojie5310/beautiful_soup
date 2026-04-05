import {
  INN_PRICE,
  buildRecoveredPartySnapshot,
  clone,
  currentGil,
  persistMenuStateFromEnvelope,
  syncMenuPartyRecovery,
  syncSavePartyRecovery,
} from "../location_shared.js";
import { getPyodideRuntime } from "../pyodide_runtime.js";
import { selectedLocationText } from "./screen_shared.js";

function renderLayout() {
  return `
    <div class="screen medium" data-screen="inn">
      <section class="frame">
        <h1 class="title">Battle Wasm Runner / Inn</h1>
        <div id="statusLine" class="status">起動中...</div>
        <div id="selectedLocationLine" class="status"></div>
        <div id="gilLine" class="resource-line">GIL ---</div>
        <div class="resource-line">宿泊料 10 GIL</div>

        <div class="buttons">
          <button id="stayInnBtn" class="btn" type="button" disabled>宿泊</button>
          <button id="backBtn" class="btn" type="button">Locationへ戻る</button>
          <button id="menuBtn" class="btn" type="button">メニュー</button>
        </div>
        <div id="innStatusLine" class="meta"></div>
      </section>
    </div>
  `;
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const statusLine = mountNode.querySelector("#statusLine");
  const selectedLocationLine = mountNode.querySelector("#selectedLocationLine");
  const gilLine = mountNode.querySelector("#gilLine");
  const stayInnBtn = mountNode.querySelector("#stayInnBtn");
  const innStatusLine = mountNode.querySelector("#innStatusLine");
  const backBtn = mountNode.querySelector("#backBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");

  let pyodide = null;

  function renderGilDisplay() {
    gilLine.textContent = `GIL ${currentGil(store.getState().saveEnvelope).toLocaleString()}`;
  }

  function renderSelection() {
    selectedLocationLine.textContent = selectedLocationText(store.getState());
  }

  async function stayAtInn() {
    const currentState = store.getState();
    const gil = currentGil(currentState.saveEnvelope);
    if (gil < INN_PRICE) {
      innStatusLine.textContent = `GIL が足りません。必要: ${INN_PRICE.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
      return;
    }

    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
      nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
    }

    const recoveredParty = await buildRecoveredPartySnapshot(
      pyodide,
      nextEnvelope.save,
      currentState.selectedLocationGroup,
      currentState.selectedLocation,
    );
    if (!recoveredParty.length) {
      innStatusLine.textContent = "宿屋の回復処理に失敗しました。";
      return;
    }

    nextEnvelope.save.gil = Math.max(0, gil - INN_PRICE);
    syncSavePartyRecovery(nextEnvelope.save, recoveredParty);
    if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
      nextEnvelope.menu_state = { party: [], resources: { cp: 0, cp_max: 255, gil: nextEnvelope.save.gil } };
    }
    if (!nextEnvelope.menu_state.resources || typeof nextEnvelope.menu_state.resources !== "object") {
      nextEnvelope.menu_state.resources = {};
    }
    nextEnvelope.menu_state.resources.gil = nextEnvelope.save.gil;
    syncMenuPartyRecovery(nextEnvelope.menu_state, recoveredParty);
    nextEnvelope.saved_at = new Date().toISOString();
    nextEnvelope.selected_location_group = currentState.selectedLocationGroup;
    nextEnvelope.selected_location = currentState.selectedLocation;

    if (!store.updateSaveEnvelope(nextEnvelope)) {
      innStatusLine.textContent = "宿泊内容の保存に失敗しました。";
      return;
    }

    persistMenuStateFromEnvelope(nextEnvelope);
    renderGilDisplay();
    innStatusLine.textContent = `宿に泊まりました。HP・MP・状態異常が全快しました。-${INN_PRICE.toLocaleString()} GIL`;
  }

  const handleStay = () => {
    stayAtInn().catch(() => {
      innStatusLine.textContent = "宿屋処理でエラーが発生しました。";
    });
  };
  const handleBack = () => navigate("location");
  const handleMenu = () => navigate("menu");

  stayInnBtn.addEventListener("click", handleStay);
  backBtn.addEventListener("click", handleBack);
  menuBtn.addEventListener("click", handleMenu);

  try {
    statusLine.textContent = "Inn を起動中...";
    pyodide = await getPyodideRuntime();
    renderSelection();
    renderGilDisplay();
    stayInnBtn.disabled = false;
    statusLine.textContent = "宿泊できます。";
  } catch (error) {
    statusLine.textContent = `起動失敗: ${String(error)}`;
  }

  return () => {
    stayInnBtn.removeEventListener("click", handleStay);
    backBtn.removeEventListener("click", handleBack);
    menuBtn.removeEventListener("click", handleMenu);
  };
}
