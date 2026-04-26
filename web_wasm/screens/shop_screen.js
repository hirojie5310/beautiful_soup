import {
  addPurchasedItemToInventory,
  asArray,
  asNumber,
  clone,
  currentGil,
  loadShopMasterData,
  normalizeShopTypeToInventoryBucket,
  persistMenuStateFromEnvelope,
  shopRowLabel,
  syncMenuStateAfterPurchase,
} from "../location_shared.js";
import { mergeMenuStateIntoSave } from "../menu_save_sync.js";
import { selectedLocationText } from "./screen_shared.js";

const SHOP_START_CONTEXT_KEY = "ff3_wasm_shop_start_context_v1";

function renderLayout() {
  return `
    <div class="screen medium" data-screen="shop">
      <section class="frame">
        <h1 class="title">Battle Wasm Runner / Shop</h1>
        <div id="statusLine" class="status">起動中...</div>
        <div id="selectedLocationLine" class="status"></div>
        <div id="shopGilLine" class="resource-line">GIL ---</div>

        <div class="shop-grid">
          <label for="shopMapSelect">map</label>
          <select id="shopMapSelect"></select>
          <label for="shopTypeSelect">type</label>
          <select id="shopTypeSelect"></select>
          <label for="shopGoodsSelect">goods</label>
          <select id="shopGoodsSelect"></select>
        </div>

        <div class="buttons">
          <button id="buyShopBtn" class="btn" type="button" disabled>購入</button>
          <button id="mapBackBtn" class="btn" type="button" disabled>マップに戻る</button>
          <button id="backBtn" class="btn" type="button">Locationへ戻る</button>
          <button id="menuBtn" class="btn" type="button">メニュー</button>
        </div>
        <div id="shopStatusLine" class="meta"></div>
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
    if (String(value) === wanted) option.selected = true;
    select.appendChild(option);
  });
  if (values.length && !select.value) {
    select.value = String(values[0]);
  }
}

function readShopStartContext() {
  try {
    const raw = sessionStorage.getItem(SHOP_START_CONTEXT_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(SHOP_START_CONTEXT_KEY);
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function canReturnToStoredMap(startContext, appState) {
  if (startContext?.return_route === "map" && startContext?.map_id) return true;
  return Boolean(
    appState?.menuState?.map_return_pending
    && appState?.menuState?.map_state?.current_map_id
  );
}

export async function mountScreen({ mountNode, store, navigate }) {
  mountNode.innerHTML = renderLayout();

  const statusLine = mountNode.querySelector("#statusLine");
  const selectedLocationLine = mountNode.querySelector("#selectedLocationLine");
  const shopMapSelect = mountNode.querySelector("#shopMapSelect");
  const shopTypeSelect = mountNode.querySelector("#shopTypeSelect");
  const shopGoodsSelect = mountNode.querySelector("#shopGoodsSelect");
  const shopGilLine = mountNode.querySelector("#shopGilLine");
  const shopStatusLine = mountNode.querySelector("#shopStatusLine");
  const buyShopBtn = mountNode.querySelector("#buyShopBtn");
  const mapBackBtn = mountNode.querySelector("#mapBackBtn");
  const backBtn = mountNode.querySelector("#backBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");

  let masterData = null;
  const startContext = readShopStartContext();
  const canReturnToMap = canReturnToStoredMap(startContext, store.getState());
  mapBackBtn.disabled = !canReturnToMap;

  function selectedShopEntry() {
    return masterData?.shopEntries.find(
      (entry) => String(entry?.map || "") === String(shopMapSelect.value || ""),
    ) || null;
  }

  function selectedShopTypeRow() {
    const entry = selectedShopEntry();
    return asArray(entry?.shops).find(
      (row) => shopRowLabel(row) === String(shopTypeSelect.value || ""),
    ) || null;
  }

  function selectedGoodsRow() {
    const row = selectedShopTypeRow();
    return asArray(row?.goods).find(
      (good) => String(good?.name || "") === String(shopGoodsSelect.value || ""),
    ) || null;
  }

  function renderGilDisplay() {
    shopGilLine.textContent = `GIL ${currentGil(store.getState().saveEnvelope).toLocaleString()}`;
  }

  function renderStoredLocation() {
    selectedLocationLine.textContent = selectedLocationText(store.getState());
  }

  function renderShopGoods() {
    const row = selectedShopTypeRow();
    const goods = asArray(row?.goods);
    setSelectOptions(
      shopGoodsSelect,
      goods.map((good) => String(good?.name || "")).filter(Boolean),
      shopGoodsSelect.value || "",
    );
    const selectedGood = selectedGoodsRow();
    const price = asNumber(selectedGood?.price, 0);
    shopStatusLine.textContent = selectedGood
      ? `${selectedGood.name} / ${price.toLocaleString()} GIL`
      : "購入する商品を選択してください。";
    buyShopBtn.disabled = !selectedGood;
  }

  function renderShopTypes(preferredType = "") {
    const entry = selectedShopEntry();
    const shops = asArray(entry?.shops);
    const typeLabels = shops.map((row) => shopRowLabel(row)).filter(Boolean);
    const currentType = String(preferredType || shopTypeSelect.value || "");
    const selectedType = typeLabels.includes(currentType) ? currentType : "";
    setSelectOptions(
      shopTypeSelect,
      typeLabels,
      selectedType,
    );
    renderShopGoods();
  }

  function renderShopSelectors() {
    const maps = asArray(masterData?.shopEntries)
      .map((entry) => String(entry?.map || ""))
      .filter(Boolean);
    const state = store.getState();
    const contextMap = String(startContext?.map || "");
    const currentMap = String(contextMap || shopMapSelect.value || state.selectedLocation || "");
    const preferredMap = maps.includes(currentMap) ? currentMap : maps[0] || "";
    setSelectOptions(shopMapSelect, maps, preferredMap);
    renderShopTypes(String(startContext?.type || ""));
    renderGilDisplay();
  }

  function purchaseSelectedGoods() {
    const goods = selectedGoodsRow();
    const typeRow = selectedShopTypeRow();
    if (!goods || !typeRow || !masterData) {
      shopStatusLine.textContent = "購入する商品を選択してください。";
      return;
    }

    const currentState = store.getState();
    const gil = currentGil(currentState.saveEnvelope);
    const price = asNumber(goods.price, 0);
    if (gil < price) {
      shopStatusLine.textContent = `GIL が足りません。必要: ${price.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
      return;
    }

    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
      nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
    }
    if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
      nextEnvelope.menu_state = { party: [], resources: { cp: 0, cp_max: 255, gil } };
    }
    const bucketName = normalizeShopTypeToInventoryBucket(masterData, typeRow, goods.name);
    nextEnvelope.save.gil = Math.max(0, gil - price);
    if (!addPurchasedItemToInventory(nextEnvelope.save, masterData.spellLevelByName, bucketName, goods.name, 1)) {
      shopStatusLine.textContent = `${goods.name} の保存先を解決できませんでした。`;
      return;
    }

    syncMenuStateAfterPurchase(nextEnvelope, masterData.spellLevelByName, goods.name, bucketName);
    nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextEnvelope.menu_state);
    nextEnvelope.saved_at = new Date().toISOString();
    nextEnvelope.selected_location_group = currentState.selectedLocationGroup;
    nextEnvelope.selected_location = currentState.selectedLocation;

    if (!store.updateSaveEnvelope(nextEnvelope)) {
      shopStatusLine.textContent = "購入内容の保存に失敗しました。";
      return;
    }

    persistMenuStateFromEnvelope(nextEnvelope);
    renderGilDisplay();
    shopStatusLine.textContent = `${goods.name} を購入しました。-${price.toLocaleString()} GIL`;
  }

  const handleMapChange = () => renderShopTypes();
  const handleTypeChange = () => renderShopGoods();
  const handleGoodsChange = () => renderShopGoods();
  const handleBuy = () => purchaseSelectedGoods();
  const handleBack = () => navigate("location");
  const handleMapBack = () => {
    if (!canReturnToMap) return;
    navigate("map");
  };
  const handleMenu = () => navigate("menu");

  shopMapSelect.addEventListener("change", handleMapChange);
  shopTypeSelect.addEventListener("change", handleTypeChange);
  shopGoodsSelect.addEventListener("change", handleGoodsChange);
  buyShopBtn.addEventListener("click", handleBuy);
  mapBackBtn.addEventListener("click", handleMapBack);
  backBtn.addEventListener("click", handleBack);
  menuBtn.addEventListener("click", handleMenu);

  try {
    statusLine.textContent = "Shop データを読み込み中...";
    masterData = await loadShopMasterData();
    renderStoredLocation();
    renderShopSelectors();
    statusLine.textContent = "商品を選んで購入できます。";
  } catch (error) {
    statusLine.textContent = `起動失敗: ${String(error)}`;
  }

  return () => {
    shopMapSelect.removeEventListener("change", handleMapChange);
    shopTypeSelect.removeEventListener("change", handleTypeChange);
    shopGoodsSelect.removeEventListener("change", handleGoodsChange);
    buyShopBtn.removeEventListener("click", handleBuy);
    mapBackBtn.removeEventListener("click", handleMapBack);
    backBtn.removeEventListener("click", handleBack);
    menuBtn.removeEventListener("click", handleMenu);
  };
}
