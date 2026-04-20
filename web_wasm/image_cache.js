const resolvedImageUrlCache = new Map();
const pendingImageUrlCache = new Map();

function normalizeCandidateList(candidates) {
  return Array.isArray(candidates)
    ? candidates.map((candidate) => String(candidate || "")).filter(Boolean)
    : [];
}

function candidateCacheKey(candidates) {
  return normalizeCandidateList(candidates).join("\n");
}

export function readCachedImageUrl(candidates) {
  const key = candidateCacheKey(candidates);
  if (!key || !resolvedImageUrlCache.has(key)) return null;
  return resolvedImageUrlCache.get(key);
}

export function resolveCachedImageUrl(candidates, { onResolved } = {}) {
  const normalized = normalizeCandidateList(candidates);
  const key = normalized.join("\n");
  if (!key) {
    if (typeof onResolved === "function") onResolved("");
    return Promise.resolve("");
  }

  if (resolvedImageUrlCache.has(key)) {
    const cached = resolvedImageUrlCache.get(key);
    if (typeof onResolved === "function") onResolved(cached);
    return Promise.resolve(cached);
  }

  const pending = pendingImageUrlCache.get(key);
  if (pending) {
    if (typeof onResolved === "function") pending.then(onResolved);
    return pending;
  }

  const promise = new Promise((resolve) => {
    const tryLoad = (index) => {
      if (index >= normalized.length) {
        resolvedImageUrlCache.set(key, "");
        pendingImageUrlCache.delete(key);
        resolve("");
        return;
      }

      const image = new Image();
      const url = normalized[index];
      image.addEventListener("load", () => {
        resolvedImageUrlCache.set(key, url);
        pendingImageUrlCache.delete(key);
        resolve(url);
      }, { once: true });
      image.addEventListener("error", () => {
        tryLoad(index + 1);
      }, { once: true });
      image.src = url;
    };

    tryLoad(0);
  });

  pendingImageUrlCache.set(key, promise);
  if (typeof onResolved === "function") promise.then(onResolved);
  return promise;
}

export function resetImageCandidateCache() {
  resolvedImageUrlCache.clear();
  pendingImageUrlCache.clear();
}
