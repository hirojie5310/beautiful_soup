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
export const SHOP_PURCHASE_QUANTITY_OPTIONS = Object.freeze([1, 4, 10]);
export const SHOP_MODE_BUY = "buy";
export const SHOP_MODE_SELL = "sell";

export function shopPurchaseDiscountPercent(quantity = 1) {
  const normalizedQuantity = Math.max(1, Number(quantity || 1));
  if (normalizedQuantity >= 10) return 8;
  if (normalizedQuantity >= 4) return 5;
  return 0;
}

export function resolveShopPurchasePricing(unitPrice = 0, quantity = 1) {
  const normalizedUnitPrice = Math.max(0, asNumber(unitPrice, 0));
  const normalizedQuantity = Math.max(1, asNumber(quantity, 1));
  const discountPercent = shopPurchaseDiscountPercent(normalizedQuantity);
  const undiscountedTotal = normalizedUnitPrice * normalizedQuantity;
  const discountedTotal = Math.floor(undiscountedTotal * (100 - discountPercent) / 100);
  return {
    unitPrice: normalizedUnitPrice,
    quantity: normalizedQuantity,
    discountPercent,
    undiscountedTotal,
    totalPrice: discountedTotal,
  };
}

export function formatShopSelectionStatus(good, quantity = 1) {
  if (!good) {
    return "購入する商品を選択してください。";
  }
  const pricing = resolveShopPurchasePricing(good.price, quantity);
  const quantityLabel = `${good.name} x${pricing.quantity}`;
  if (pricing.discountPercent <= 0) {
    return `${quantityLabel} / 所要金額 ${pricing.totalPrice.toLocaleString()} GIL`;
  }
  return `${quantityLabel} / ${pricing.discountPercent}% OFF / 所要金額 ${pricing.totalPrice.toLocaleString()} GIL`;
}

export function resolveShopSellPrice(itemValue = 0) {
  return Math.floor(Math.max(0, asNumber(itemValue, 0)) / 2);
}

export function resolveShopModeVisibility(mode = SHOP_MODE_BUY) {
  return {
    showBuyFields: mode === SHOP_MODE_BUY,
    showSellFields: mode === SHOP_MODE_SELL,
  };
}

export function applyShopModeVisibility(elements, mode = SHOP_MODE_BUY) {
  const visibility = resolveShopModeVisibility(mode);
  const buyContextGrid = elements?.shopBuyContextGrid || null;
  const buyGrid = elements?.shopBuyGrid || null;
  const sellGrid = elements?.shopSellGrid || null;
  if (buyContextGrid) {
    buyContextGrid.hidden = true;
    buyContextGrid.style.display = "none";
  }
  if (buyGrid) {
    buyGrid.hidden = !visibility.showBuyFields;
    buyGrid.style.display = visibility.showBuyFields ? "grid" : "none";
  }
  if (sellGrid) {
    sellGrid.hidden = !visibility.showSellFields;
    sellGrid.style.display = visibility.showSellFields ? "grid" : "none";
  }
  return visibility;
}

export function buildSellableInventoryRows(masterData, saveEnvelope) {
  const inventory = saveEnvelope?.save?.inventory && typeof saveEnvelope.save.inventory === "object"
    ? saveEnvelope.save.inventory
    : {};
  const sellValueByName = masterData?.sellValueByName && typeof masterData.sellValueByName === "object"
    ? masterData.sellValueByName
    : {};
  const rows = [];
  Object.entries(inventory).forEach(([bucketName, bucket]) => {
    if (!bucket || typeof bucket !== "object" || bucketName === "Key Item") return;
    if (bucketName === "Magic") {
      Object.entries(bucket).forEach(([levelKey, levelBucket]) => {
        if (!levelBucket || typeof levelBucket !== "object") return;
        Object.entries(levelBucket).forEach(([name, count]) => {
          const quantity = Math.max(0, asNumber(count, 0));
          const value = Math.max(0, asNumber(sellValueByName[name], 0));
          if (quantity <= 0 || value <= 0) return;
          rows.push({
            key: `Magic:${levelKey}:${name}`,
            bucketName: "Magic",
            levelKey: String(levelKey),
            itemName: String(name),
            quantity,
            unitValue: value,
            sellPrice: resolveShopSellPrice(value),
          });
        });
      });
      return;
    }
    Object.entries(bucket).forEach(([name, count]) => {
      const quantity = Math.max(0, asNumber(count, 0));
      const value = Math.max(0, asNumber(sellValueByName[name], 0));
      if (quantity <= 0 || value <= 0) return;
      rows.push({
        key: `${bucketName}:${name}`,
        bucketName: String(bucketName),
        itemName: String(name),
        quantity,
        unitValue: value,
        sellPrice: resolveShopSellPrice(value),
      });
    });
  });
  rows.sort((left, right) => (
    left.itemName.localeCompare(right.itemName, "ja")
    || left.bucketName.localeCompare(right.bucketName, "ja")
  ));
  return rows;
}

export function formatShopSellStatus(row) {
  if (!row) {
    return "売却するアイテムを選択してください。";
  }
  return `${row.itemName} x${row.quantity} / 売値 ${row.sellPrice.toLocaleString()} GIL`;
}

export function removeSoldInventoryItem(save, sellRow, quantity = 1) {
  if (!save || typeof save !== "object" || !sellRow) return false;
  if (!save.inventory || typeof save.inventory !== "object") return false;
  const consumeQuantity = Math.max(1, asNumber(quantity, 1));
  if (sellRow.bucketName === "Magic") {
    const magicBucket = save.inventory.Magic;
    if (!magicBucket || typeof magicBucket !== "object") return false;
    const levelBucket = magicBucket[sellRow.levelKey];
    if (!levelBucket || typeof levelBucket !== "object") return false;
    const current = Math.max(0, asNumber(levelBucket[sellRow.itemName], 0));
    if (current < consumeQuantity) return false;
    if (current === consumeQuantity) delete levelBucket[sellRow.itemName];
    else levelBucket[sellRow.itemName] = current - consumeQuantity;
    if (!Object.keys(levelBucket).length) delete magicBucket[sellRow.levelKey];
    if (!Object.keys(magicBucket).length) delete save.inventory.Magic;
    return true;
  }
  const bucket = save.inventory[sellRow.bucketName];
  if (!bucket || typeof bucket !== "object") return false;
  const current = Math.max(0, asNumber(bucket[sellRow.itemName], 0));
  if (current < consumeQuantity) return false;
  if (current === consumeQuantity) delete bucket[sellRow.itemName];
  else bucket[sellRow.itemName] = current - consumeQuantity;
  if (!Object.keys(bucket).length) delete save.inventory[sellRow.bucketName];
  return true;
}

function renderLayout() {
  return `
    <div class="screen medium" data-screen="shop">
      <section class="frame">
        <h1 class="title">Battle Wasm Runner / Shop</h1>
        <div id="statusLine" class="status">起動中...</div>
        <div id="selectedLocationLine" class="status"></div>
        <div id="shopGilLine" class="resource-line">GIL ---</div>

        <div class="buttons">
          <button id="buyModeBtn" class="btn" type="button">買う</button>
          <button id="sellModeBtn" class="btn" type="button">売る</button>
        </div>

        <div id="shopBuyContextGrid" class="shop-grid">
          <label for="shopMapSelect">map</label>
          <select id="shopMapSelect"></select>
          <label for="shopTypeSelect">type</label>
          <select id="shopTypeSelect"></select>
        </div>

        <div id="shopBuyGrid" class="shop-grid">
          <label for="shopGoodsSelect">goods</label>
          <select id="shopGoodsSelect"></select>
          <label for="shopQuantitySelect">quantity</label>
          <select id="shopQuantitySelect"></select>
        </div>

        <div id="shopSellGrid" class="shop-grid" hidden>
          <label for="shopSellGoodsSelect">inventory</label>
          <select id="shopSellGoodsSelect"></select>
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
  const shopQuantitySelect = mountNode.querySelector("#shopQuantitySelect");
  const shopSellGoodsSelect = mountNode.querySelector("#shopSellGoodsSelect");
  const shopBuyContextGrid = mountNode.querySelector("#shopBuyContextGrid");
  const shopBuyGrid = mountNode.querySelector("#shopBuyGrid");
  const shopSellGrid = mountNode.querySelector("#shopSellGrid");
  const shopGilLine = mountNode.querySelector("#shopGilLine");
  const shopStatusLine = mountNode.querySelector("#shopStatusLine");
  const buyShopBtn = mountNode.querySelector("#buyShopBtn");
  const buyModeBtn = mountNode.querySelector("#buyModeBtn");
  const sellModeBtn = mountNode.querySelector("#sellModeBtn");
  const mapBackBtn = mountNode.querySelector("#mapBackBtn");
  const backBtn = mountNode.querySelector("#backBtn");
  const menuBtn = mountNode.querySelector("#menuBtn");

  let masterData = null;
  let shopMode = SHOP_MODE_BUY;
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

  function selectedPurchaseQuantity() {
    const quantity = asNumber(shopQuantitySelect.value, 1);
    return SHOP_PURCHASE_QUANTITY_OPTIONS.includes(quantity) ? quantity : 1;
  }

  function sellableInventoryRows() {
    return buildSellableInventoryRows(masterData, store.getState().saveEnvelope);
  }

  function selectedSellInventoryRow() {
    return sellableInventoryRows().find(
      (row) => row.key === String(shopSellGoodsSelect.value || ""),
    ) || null;
  }

  function renderGilDisplay() {
    shopGilLine.textContent = `GIL ${currentGil(store.getState().saveEnvelope).toLocaleString()}`;
  }

  function renderStoredLocation() {
    selectedLocationLine.textContent = selectedLocationText(store.getState());
  }

  function setSelectOptionsWithLabels(select, rows, selectedValue = "") {
    const wanted = String(selectedValue || "");
    select.innerHTML = "";
    rows.forEach((row) => {
      const option = document.createElement("option");
      option.value = String(row.value);
      option.textContent = String(row.label);
      if (String(row.value) === wanted) option.selected = true;
      select.appendChild(option);
    });
    if (rows.length && !select.value) {
      select.value = String(rows[0].value);
    }
  }

  function renderShopGoods() {
    const row = selectedShopTypeRow();
    const goods = asArray(row?.goods);
    setSelectOptions(
      shopGoodsSelect,
      goods.map((good) => String(good?.name || "")).filter(Boolean),
      shopGoodsSelect.value || "",
    );
    setSelectOptions(
      shopQuantitySelect,
      SHOP_PURCHASE_QUANTITY_OPTIONS.map((value) => String(value)),
      shopQuantitySelect.value || "1",
    );
    const selectedGood = selectedGoodsRow();
    shopStatusLine.textContent = formatShopSelectionStatus(selectedGood, selectedPurchaseQuantity());
    buyShopBtn.disabled = !selectedGood;
  }

  function renderSellInventory() {
    const rows = sellableInventoryRows();
    setSelectOptionsWithLabels(
      shopSellGoodsSelect,
      rows.map((row) => ({
        value: row.key,
        label: `${row.itemName} x${row.quantity}`,
      })),
      shopSellGoodsSelect.value || "",
    );
    const selectedRow = selectedSellInventoryRow();
    shopStatusLine.textContent = formatShopSellStatus(selectedRow);
    buyShopBtn.disabled = !selectedRow;
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

  function renderMode() {
    const visibility = applyShopModeVisibility({
      shopBuyContextGrid,
      shopBuyGrid,
      shopSellGrid,
    }, shopMode);
    buyModeBtn.disabled = visibility.showBuyFields;
    sellModeBtn.disabled = visibility.showSellFields;
    buyShopBtn.textContent = visibility.showBuyFields ? "購入" : "売却";
    if (visibility.showBuyFields) {
      renderShopGoods();
    } else {
      renderSellInventory();
    }
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
    const quantity = selectedPurchaseQuantity();
    const pricing = resolveShopPurchasePricing(goods.price, quantity);
    if (gil < pricing.totalPrice) {
      shopStatusLine.textContent = `GIL が足りません。必要: ${pricing.totalPrice.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
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
    nextEnvelope.save.gil = Math.max(0, gil - pricing.totalPrice);
    if (!addPurchasedItemToInventory(nextEnvelope.save, masterData.spellLevelByName, bucketName, goods.name, quantity)) {
      shopStatusLine.textContent = `${goods.name} の保存先を解決できませんでした。`;
      return;
    }

    syncMenuStateAfterPurchase(nextEnvelope, masterData.spellLevelByName, goods.name, bucketName);
    nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextEnvelope.menu_state);
    nextEnvelope.saved_at = new Date().toISOString();
    nextEnvelope.selected_location_group = currentState.selectedLocationGroup;
    nextEnvelope.selected_location = currentState.selectedLocation;

    if (!store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" })) {
      shopStatusLine.textContent = "購入内容の保存に失敗しました。";
      return;
    }

    persistMenuStateFromEnvelope(nextEnvelope);
    renderGilDisplay();
    shopStatusLine.textContent = `${goods.name} を${quantity}個購入しました。-${pricing.totalPrice.toLocaleString()} GIL`;
  }

  function sellSelectedGoods() {
    const sellRow = selectedSellInventoryRow();
    if (!sellRow || !masterData) {
      shopStatusLine.textContent = "売却するアイテムを選択してください。";
      return;
    }
    const currentState = store.getState();
    const originalEnvelope = currentState.saveEnvelope;
    const nextEnvelope = originalEnvelope
      ? clone(originalEnvelope)
      : store.createDefaultEnvelope();
    if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
      nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
    }
    if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
      nextEnvelope.menu_state = {
        party: [],
        resources: { cp: 0, cp_max: 255, gil: Math.max(0, asNumber(nextEnvelope.save.gil, 0)) },
      };
    }
    if (!removeSoldInventoryItem(nextEnvelope.save, sellRow, 1)) {
      shopStatusLine.textContent = `${sellRow.itemName} を売却できませんでした。`;
      return;
    }
    nextEnvelope.save.gil = Math.max(0, asNumber(nextEnvelope.save.gil, 0)) + sellRow.sellPrice;
    if (!nextEnvelope.menu_state.resources || typeof nextEnvelope.menu_state.resources !== "object") {
      nextEnvelope.menu_state.resources = { cp: 0, cp_max: 255, gil: 0 };
    }
    nextEnvelope.menu_state.resources.gil = Math.max(0, asNumber(nextEnvelope.save.gil, 0));
    nextEnvelope.save = mergeMenuStateIntoSave(nextEnvelope.save, nextEnvelope.menu_state);
    nextEnvelope.saved_at = new Date().toISOString();
    nextEnvelope.selected_location_group = currentState.selectedLocationGroup;
    nextEnvelope.selected_location = currentState.selectedLocation;
    if (!store.updateSaveEnvelope(nextEnvelope, { reason: "menu_confirmed" })) {
      shopStatusLine.textContent = "売却内容の保存に失敗しました。";
      return;
    }
    persistMenuStateFromEnvelope(nextEnvelope);
    renderGilDisplay();
    renderSellInventory();
    shopStatusLine.textContent = `${sellRow.itemName} を売却しました。+${sellRow.sellPrice.toLocaleString()} GIL`;
  }

  const handleMapChange = () => renderShopTypes();
  const handleTypeChange = () => renderShopGoods();
  const handleGoodsChange = () => renderShopGoods();
  const handleQuantityChange = () => {
    shopStatusLine.textContent = formatShopSelectionStatus(selectedGoodsRow(), selectedPurchaseQuantity());
  };
  const handleSellGoodsChange = () => {
    shopStatusLine.textContent = formatShopSellStatus(selectedSellInventoryRow());
  };
  const handleBuy = () => {
    if (shopMode === SHOP_MODE_SELL) {
      sellSelectedGoods();
      return;
    }
    purchaseSelectedGoods();
  };
  const handleBuyMode = () => {
    shopMode = SHOP_MODE_BUY;
    renderMode();
  };
  const handleSellMode = () => {
    shopMode = SHOP_MODE_SELL;
    renderMode();
  };
  const handleBack = () => navigate("location");
  const handleMapBack = () => {
    if (!canReturnToMap) return;
    navigate("map");
  };
  const handleMenu = () => navigate("menu");

  shopMapSelect.addEventListener("change", handleMapChange);
  shopTypeSelect.addEventListener("change", handleTypeChange);
  shopGoodsSelect.addEventListener("change", handleGoodsChange);
  shopQuantitySelect.addEventListener("change", handleQuantityChange);
  shopSellGoodsSelect.addEventListener("change", handleSellGoodsChange);
  buyShopBtn.addEventListener("click", handleBuy);
  buyModeBtn.addEventListener("click", handleBuyMode);
  sellModeBtn.addEventListener("click", handleSellMode);
  mapBackBtn.addEventListener("click", handleMapBack);
  backBtn.addEventListener("click", handleBack);
  menuBtn.addEventListener("click", handleMenu);

  try {
    statusLine.textContent = "Shop データを読み込み中...";
    masterData = await loadShopMasterData();
    renderStoredLocation();
    renderShopSelectors();
    renderMode();
    statusLine.textContent = "商品を選んで購入できます。";
  } catch (error) {
    statusLine.textContent = `起動失敗: ${String(error)}`;
  }

  return () => {
    shopMapSelect.removeEventListener("change", handleMapChange);
    shopTypeSelect.removeEventListener("change", handleTypeChange);
    shopGoodsSelect.removeEventListener("change", handleGoodsChange);
    shopQuantitySelect.removeEventListener("change", handleQuantityChange);
    shopSellGoodsSelect.removeEventListener("change", handleSellGoodsChange);
    buyShopBtn.removeEventListener("click", handleBuy);
    buyModeBtn.removeEventListener("click", handleBuyMode);
    sellModeBtn.removeEventListener("click", handleSellMode);
    mapBackBtn.removeEventListener("click", handleMapBack);
    backBtn.removeEventListener("click", handleBack);
    menuBtn.removeEventListener("click", handleMenu);
  };
}
