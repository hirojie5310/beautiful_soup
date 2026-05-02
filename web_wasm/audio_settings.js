export const AUDIO_SETTINGS_STORAGE_KEY = "ff3_wasm_audio_settings_v1";
export const DEFAULT_BGM_VOLUME = 1;

export function normalizeBgmVolume(value, fallback = DEFAULT_BGM_VOLUME) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.min(1, Math.max(0, numeric));
}

export function loadAudioSettings(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem?.(AUDIO_SETTINGS_STORAGE_KEY);
    if (!raw) {
      return { bgmVolume: DEFAULT_BGM_VOLUME };
    }
    const parsed = JSON.parse(raw);
    return {
      bgmVolume: normalizeBgmVolume(parsed?.bgmVolume),
    };
  } catch (_error) {
    return { bgmVolume: DEFAULT_BGM_VOLUME };
  }
}

export function saveAudioSettings(settings, storage = globalThis.localStorage) {
  const nextSettings = {
    bgmVolume: normalizeBgmVolume(settings?.bgmVolume),
  };
  try {
    storage?.setItem?.(AUDIO_SETTINGS_STORAGE_KEY, JSON.stringify(nextSettings));
    return nextSettings;
  } catch (_error) {
    return nextSettings;
  }
}

export function getStoredBgmVolume(storage = globalThis.localStorage) {
  return loadAudioSettings(storage).bgmVolume;
}

export function applyStoredBgmVolume(audioElement, storage = globalThis.localStorage) {
  if (!audioElement || typeof audioElement !== "object") return null;
  const bgmVolume = getStoredBgmVolume(storage);
  try {
    audioElement.volume = bgmVolume;
  } catch (_error) {
    return null;
  }
  return bgmVolume;
}
