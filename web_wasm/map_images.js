const locationMapImageCache = Object.create(null);

export function locationGroupToMapKey(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/'/g, "")
    .replace(/\s+/g, "_");
}

export function resolveLocationMapImageCandidates(locationGroupName) {
  const key = locationGroupToMapKey(locationGroupName);
  if (!key) return [];
  return [
    `/web_wasm/maps/${key}.jpg`,
    `/web_wasm/maps/${key}.jpeg`,
    `/web_wasm/maps/${key}.png`,
    `../assets/images/maps/${key}.jpg`,
    `../assets/images/maps/${key}.jpeg`,
    `../assets/images/maps/${key}.png`,
  ];
}

export function resolveLocationMapImageUrl(locationGroupName, onResolved) {
  const key = locationGroupToMapKey(locationGroupName);
  if (!key) return "";

  const cached = locationMapImageCache[key];
  if (typeof cached === "string") {
    return cached;
  }
  if (cached === "__loading__") {
    return "";
  }

  const candidates = resolveLocationMapImageCandidates(locationGroupName);
  if (!candidates.length) {
    locationMapImageCache[key] = "";
    return "";
  }

  locationMapImageCache[key] = "__loading__";

  const tryLoad = (index) => {
    if (index >= candidates.length) {
      locationMapImageCache[key] = "";
      if (typeof onResolved === "function") onResolved("");
      return;
    }
    const image = new Image();
    const url = candidates[index];
    image.addEventListener("load", () => {
      locationMapImageCache[key] = url;
      if (typeof onResolved === "function") onResolved(url);
    });
    image.addEventListener("error", () => {
      tryLoad(index + 1);
    });
    image.src = url;
  };

  tryLoad(0);
  return "";
}
