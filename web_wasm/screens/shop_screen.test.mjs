import test from "node:test";
import assert from "node:assert/strict";

import {
  applyShopModeVisibility,
  buildSellableInventoryRows,
  formatShopSelectionStatus,
  formatShopSellStatus,
  removeSoldInventoryItem,
  resolveShopPurchasePricing,
  resolveShopModeVisibility,
  resolveShopSellPrice,
  shopPurchaseDiscountPercent,
} from "./shop_screen.js";

test("shopPurchaseDiscountPercent resolves NES-style quantity discounts", () => {
  assert.equal(shopPurchaseDiscountPercent(1), 0);
  assert.equal(shopPurchaseDiscountPercent(3), 0);
  assert.equal(shopPurchaseDiscountPercent(4), 5);
  assert.equal(shopPurchaseDiscountPercent(9), 5);
  assert.equal(shopPurchaseDiscountPercent(10), 8);
});

test("resolveShopPurchasePricing applies quantity discounts and floors fractions", () => {
  assert.deepEqual(resolveShopPurchasePricing(50, 1), {
    unitPrice: 50,
    quantity: 1,
    discountPercent: 0,
    undiscountedTotal: 50,
    totalPrice: 50,
  });
  assert.deepEqual(resolveShopPurchasePricing(33, 4), {
    unitPrice: 33,
    quantity: 4,
    discountPercent: 5,
    undiscountedTotal: 132,
    totalPrice: 125,
  });
  assert.deepEqual(resolveShopPurchasePricing(37, 10), {
    unitPrice: 37,
    quantity: 10,
    discountPercent: 8,
    undiscountedTotal: 370,
    totalPrice: 340,
  });
});

test("formatShopSelectionStatus shows quantity and discounted required gil", () => {
  assert.equal(
    formatShopSelectionStatus({ name: "Potion", price: 50 }, 1),
    "Potion x1 / 所要金額 50 GIL",
  );
  assert.equal(
    formatShopSelectionStatus({ name: "Potion", price: 50 }, 4),
    "Potion x4 / 5% OFF / 所要金額 190 GIL",
  );
  assert.equal(
    formatShopSelectionStatus({ name: "Phoenix Down", price: 37 }, 10),
    "Phoenix Down x10 / 8% OFF / 所要金額 340 GIL",
  );
});

test("resolveShopSellPrice returns half value rounded down", () => {
  assert.equal(resolveShopSellPrice(75), 37);
  assert.equal(resolveShopSellPrice(50), 25);
  assert.equal(resolveShopSellPrice(0), 0);
});

test("buildSellableInventoryRows flattens sellable inventory with counts and prices", () => {
  const rows = buildSellableInventoryRows({
    sellValueByName: {
      Potion: 50,
      Staff: 100,
      Cure: 100,
      Crystal: 9999,
    },
  }, {
    save: {
      inventory: {
        Anywhere: {
          Potion: 3,
        },
        Weapon: {
          Staff: 1,
        },
        Magic: {
          LV1: {
            Cure: 2,
          },
        },
        "Key Item": {
          Crystal: 1,
        },
      },
    },
  });
  assert.deepEqual(rows, [
    {
      key: "Magic:LV1:Cure",
      bucketName: "Magic",
      levelKey: "LV1",
      itemName: "Cure",
      quantity: 2,
      unitValue: 100,
      sellPrice: 50,
    },
    {
      key: "Anywhere:Potion",
      bucketName: "Anywhere",
      itemName: "Potion",
      quantity: 3,
      unitValue: 50,
      sellPrice: 25,
    },
    {
      key: "Weapon:Staff",
      bucketName: "Weapon",
      itemName: "Staff",
      quantity: 1,
      unitValue: 100,
      sellPrice: 50,
    },
  ]);
});

test("removeSoldInventoryItem decrements normal and magic inventory rows", () => {
  const save = {
    inventory: {
      Anywhere: {
        Potion: 2,
      },
      Magic: {
        LV1: {
          Cure: 1,
        },
      },
    },
  };
  assert.equal(removeSoldInventoryItem(save, {
    bucketName: "Anywhere",
    itemName: "Potion",
  }), true);
  assert.deepEqual(save.inventory.Anywhere, { Potion: 1 });
  assert.equal(removeSoldInventoryItem(save, {
    bucketName: "Magic",
    levelKey: "LV1",
    itemName: "Cure",
  }), true);
  assert.equal("Magic" in save.inventory, false);
});

test("formatShopSellStatus shows count and sell price", () => {
  assert.equal(
    formatShopSellStatus({
      itemName: "Potion",
      quantity: 3,
      sellPrice: 25,
    }),
    "Potion x3 / 売値 25 GIL",
  );
});

test("resolveShopModeVisibility enables only the relevant field group", () => {
  assert.deepEqual(resolveShopModeVisibility("buy"), {
    showBuyFields: true,
    showSellFields: false,
  });
  assert.deepEqual(resolveShopModeVisibility("sell"), {
    showBuyFields: false,
    showSellFields: true,
  });
});

test("applyShopModeVisibility updates grid display styles per mode", () => {
  const elements = {
    shopBuyContextGrid: { hidden: false, style: {} },
    shopBuyGrid: { hidden: false, style: {} },
    shopSellGrid: { hidden: false, style: {} },
  };
  applyShopModeVisibility(elements, "buy");
  assert.equal(elements.shopBuyContextGrid.hidden, true);
  assert.equal(elements.shopBuyContextGrid.style.display, "none");
  assert.equal(elements.shopBuyGrid.hidden, false);
  assert.equal(elements.shopBuyGrid.style.display, "grid");
  assert.equal(elements.shopSellGrid.hidden, true);
  assert.equal(elements.shopSellGrid.style.display, "none");

  applyShopModeVisibility(elements, "sell");
  assert.equal(elements.shopBuyGrid.hidden, true);
  assert.equal(elements.shopBuyGrid.style.display, "none");
  assert.equal(elements.shopSellGrid.hidden, false);
  assert.equal(elements.shopSellGrid.style.display, "grid");
});
