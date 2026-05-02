export function configureAmbientAudioSession(targetNavigator = globalThis.navigator) {
  const audioSession = targetNavigator?.audioSession;
  if (!audioSession || typeof audioSession !== "object") return false;
  try {
    if (audioSession.type !== "ambient") {
      audioSession.type = "ambient";
    }
    return audioSession.type === "ambient";
  } catch (_error) {
    return false;
  }
}
