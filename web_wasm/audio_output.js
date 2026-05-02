import { getStoredBgmVolume } from "./audio_settings.js";

let sharedAudioContext = null;
const managedAudioGraphs = new WeakMap();

export function resetManagedAudioStateForTests() {
  sharedAudioContext = null;
}

function resolveAudioContextClass(runtime = globalThis) {
  return runtime?.AudioContext || runtime?.webkitAudioContext || null;
}

function getSharedAudioContext(runtime = globalThis) {
  if (sharedAudioContext) return sharedAudioContext;
  const AudioContextClass = resolveAudioContextClass(runtime);
  if (typeof AudioContextClass !== "function") return null;
  try {
    sharedAudioContext = new AudioContextClass();
    return sharedAudioContext;
  } catch (_error) {
    return null;
  }
}

export function ensureManagedAudioGraph(audioElement, runtime = globalThis) {
  if (!audioElement || typeof audioElement !== "object") return null;
  const existingGraph = managedAudioGraphs.get(audioElement);
  if (existingGraph) return existingGraph;
  const context = getSharedAudioContext(runtime);
  if (
    !context
    || typeof context.createMediaElementSource !== "function"
    || typeof context.createGain !== "function"
  ) {
    return null;
  }
  try {
    const sourceNode = context.createMediaElementSource(audioElement);
    const gainNode = context.createGain();
    sourceNode.connect(gainNode);
    gainNode.connect(context.destination);
    const graph = { context, sourceNode, gainNode };
    managedAudioGraphs.set(audioElement, graph);
    return graph;
  } catch (_error) {
    return null;
  }
}

export function applyStoredBgmVolume(audioElement, storage = globalThis.localStorage, runtime = globalThis) {
  if (!audioElement || typeof audioElement !== "object") return null;
  const bgmVolume = getStoredBgmVolume(storage);
  const graph = ensureManagedAudioGraph(audioElement, runtime);
  if (graph?.gainNode?.gain && typeof graph.gainNode.gain === "object") {
    try {
      graph.gainNode.gain.value = bgmVolume;
      audioElement.volume = 1;
      return bgmVolume;
    } catch (_error) {
      // Fall back to plain element volume below.
    }
  }
  try {
    audioElement.volume = bgmVolume;
  } catch (_error) {
    return null;
  }
  return bgmVolume;
}

export function resumeManagedAudioContext(audioElement, runtime = globalThis) {
  const graph = ensureManagedAudioGraph(audioElement, runtime);
  const context = graph?.context;
  if (!context || typeof context.resume !== "function" || context.state !== "suspended") {
    return Promise.resolve(context || null);
  }
  try {
    return Promise.resolve(context.resume()).then(() => context).catch(() => null);
  } catch (_error) {
    return Promise.resolve(null);
  }
}

export function playManagedBgm(audioElement, options = {}) {
  if (!audioElement || typeof audioElement.play !== "function") return null;
  const storage = options?.storage ?? globalThis.localStorage;
  const runtime = options?.runtime ?? globalThis;
  applyStoredBgmVolume(audioElement, storage, runtime);
  return Promise.resolve(resumeManagedAudioContext(audioElement, runtime))
    .catch(() => null)
    .then(() => audioElement.play());
}
