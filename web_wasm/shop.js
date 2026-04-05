import {
  addPurchasedItemToInventory,
  asArray,
  asNumber,
  clone,
  currentGil,
  getStoredLocationSelection,
  loadShopMasterData,
  normalizeShopTypeToInventoryBucket,
  persistMenuStateFromEnvelope,
  readStoredEnvelope,
  syncMenuStateAfterPurchase,
} from "./location_shared.js";
import { makeSaveEnvelope, persistSaveEnvelopeToStorage } from "./shared_storage.js";

const statusLine = document.getElementById("statusLine");
const selectedLocationLine = document.getElementById("selectedLocationLine");
const shopMapSelect = document.getElementById("shopMapSelect");
const shopTypeSelect = document.getElementById("shopTypeSelect");
const shopGoodsSelect = document.getElementById("shopGoodsSelect");
const shopGilLine = document.getElementById("shopGilLine");
const shopStatusLine = document.getElementById("shopStatusLine");
const buyShopBtn = document.getElementById("buyShopBtn");
const backBtn = document.getElementById("backBtn");
const menuBtn = document.getElementById("menuBtn");

let masterData = null;

function setSelectOptions(select, values, selectedValue = "") {
  if (!select) return;
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

function selectedShopEntry() {
  return masterData?.shopEntries.find((entry) => String(entry?.map || "") === String(shopMapSelect?.value || "")) || null;
}

function selectedShopTypeRow() {
  const entry = selectedShopEntry();
  return asArray(entry?.shops).find((row) => String(row?.type || "") === String(shopTypeSelect?.value || "")) || null;
}

function selectedGoodsRow() {
  const row = selectedShopTypeRow();
  return asArray(row?.goods).find((good) => String(good?.name || "") === String(shopGoodsSelect?.value || "")) || null;
}

function renderGilDisplay() {
  if (!shopGilLine) return;
  shopGilLine.textContent = `GIL ${currentGil().toLocaleString()}`;
}

function renderStoredLocation() {
  if (!selectedLocationLine) return;
  const selection = getStoredLocationSelection();
  if (selection.selected_location_group || selection.selected_location) {
    selectedLocationLine.textContent = `現在のLocation: ${selection.selected_location_group || "-"} / ${selection.selected_location || "-"}`;
    return;
  }
  selectedLocationLine.textContent = "現在のLocationは未選択です。";
}

function renderShopGoods() {
  const row = selectedShopTypeRow();
  const goods = asArray(row?.goods);
  setSelectOptions(shopGoodsSelect, goods.map((good) => String(good?.name || "")).filter(Boolean), shopGoodsSelect?.value || "");
  const selectedGood = selectedGoodsRow();
  const price = asNumber(selectedGood?.price, 0);
  if (shopStatusLine) {
    shopStatusLine.textContent = selectedGood
      ? `${selectedGood.name} / ${price.toLocaleString()} GIL`
      : "購入する商品を選択してください。";
  }
  if (buyShopBtn) {
    buyShopBtn.disabled = !selectedGood;
  }
}

function renderShopTypes() {
  const entry = selectedShopEntry();
  const shops = asArray(entry?.shops);
  setSelectOptions(shopTypeSelect, shops.map((row) => String(row?.type || "")).filter(Boolean), shopTypeSelect?.value || "");
  renderShopGoods();
}

function renderShopSelectors() {
  const maps = asArray(masterData?.shopEntries).map((entry) => String(entry?.map || "")).filter(Boolean);
  const selection = getStoredLocationSelection();
  const currentMap = String(shopMapSelect?.value || selection.selected_location || "");
  const preferredMap = maps.includes(currentMap) ? currentMap : maps[0] || "";
  setSelectOptions(shopMapSelect, maps, preferredMap);
  renderShopTypes();
  renderGilDisplay();
}

function purchaseSelectedGoods() {
  const goods = selectedGoodsRow();
  const typeRow = selectedShopTypeRow();
  if (!goods || !typeRow || !masterData) {
    if (shopStatusLine) shopStatusLine.textContent = "購入する商品を選択してください。";
    return;
  }

  const price = asNumber(goods.price, 0);
  const gil = currentGil();
  if (gil < price) {
    if (shopStatusLine) {
      shopStatusLine.textContent = `GIL が足りません。必要: ${price.toLocaleString()} / 所持: ${gil.toLocaleString()}`;
    }
    return;
  }

  const originalEnvelope = readStoredEnvelope();
  const nextEnvelope = originalEnvelope ? clone(originalEnvelope) : makeSaveEnvelope({ gil: 0, inventory: {}, party: [] }, {});
  if (!nextEnvelope.save || typeof nextEnvelope.save !== "object") {
    nextEnvelope.save = { gil: 0, inventory: {}, party: [] };
  }
  if (!nextEnvelope.menu_state || typeof nextEnvelope.menu_state !== "object") {
    nextEnvelope.menu_state = { party: [], resources: { cp: 0, cp_max: 255, gil } };
  }
  const bucketName = normalizeShopTypeToInventoryBucket(masterData, typeRow.type, goods.name);
  nextEnvelope.save.gil = Math.max(0, gil - price);
  if (!addPurchasedItemToInventory(nextEnvelope.save, masterData.spellLevelByName, bucketName, goods.name, 1)) {
    if (shopStatusLine) {
      shopStatusLine.textContent = `${goods.name} の保存先を解決できませんでした。`;
    }
    return;
  }

  syncMenuStateAfterPurchase(nextEnvelope, masterData.spellLevelByName, goods.name, bucketName);
  nextEnvelope.saved_at = new Date().toISOString();

  if (!persistSaveEnvelopeToStorage(nextEnvelope)) {
    if (shopStatusLine) {
      shopStatusLine.textContent = "購入内容の保存に失敗しました。";
    }
    return;
  }

  persistMenuStateFromEnvelope(nextEnvelope);
  renderGilDisplay();
  if (shopStatusLine) {
    shopStatusLine.textContent = `${goods.name} を購入しました。-${price.toLocaleString()} GIL`;
  }
}

async function bootShopScreen() {
  statusLine.textContent = "Shop データを読み込み中...";
  masterData = await loadShopMasterData();
  renderStoredLocation();
  renderShopSelectors();
  statusLine.textContent = "商品を選んで購入できます。";
}

shopMapSelect?.addEventListener("change", () => renderShopTypes());
shopTypeSelect?.addEventListener("change", () => renderShopGoods());
shopGoodsSelect?.addEventListener("change", () => renderShopGoods());
buyShopBtn?.addEventListener("click", () => purchaseSelectedGoods());
backBtn?.addEventListener("click", () => {
  window.location.href = "./index.html";
});
menuBtn?.addEventListener("click", () => {
  window.location.href = "./menu.html";
});

bootShopScreen().catch((error) => {
  statusLine.textContent = `起動失敗: ${String(error)}`;
});
