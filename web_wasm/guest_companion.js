export const SEALED_CAVE_B2_2_SARA_EVENT_FLAG = "sealed_cave_b2_2_sara_escort_started";
export const SEALED_CAVE_SARA_LEAVE_EVENT_FLAG = "sara_left_party";
export const KAZUS_CID_FOLLOWER_EVENT_FLAG = "kazus_cid_follower_joined";
export const SARA_PORTRAIT_URL = "../assets/images/faces/portrait_sara.png";
export const CID_PORTRAIT_URL = "../assets/images/faces/portrait_cid.png";

export function isSaraGuestActive(envelope) {
  const flags = envelope?.save?.event_flag;
  if (!flags || typeof flags !== "object") return false;
  return Boolean(flags[SEALED_CAVE_B2_2_SARA_EVENT_FLAG]) && !Boolean(flags[SEALED_CAVE_SARA_LEAVE_EVENT_FLAG]);
}

export function isCidGuestActive(envelope) {
  const flags = envelope?.save?.event_flag;
  if (!flags || typeof flags !== "object") return false;
  return Boolean(flags[KAZUS_CID_FOLLOWER_EVENT_FLAG]);
}

export function resolveActiveGuestFollowerType(envelope, options = {}) {
  if (options?.forceSaraVisible) return "sara";
  if (isSaraGuestActive(envelope)) return "sara";
  if (isCidGuestActive(envelope)) return "cid";
  return "";
}

export function resolveGuestPortraitDescriptor(envelope) {
  if (isSaraGuestActive(envelope)) {
    return {
      label: "SARA",
      alt: "Sara portrait",
      imageUrl: SARA_PORTRAIT_URL,
      fallbackText: "SARA",
    };
  }
  if (isCidGuestActive(envelope)) {
    return {
      label: "CID",
      alt: "Cid portrait",
      imageUrl: CID_PORTRAIT_URL,
      fallbackText: "CID",
    };
  }
  return null;
}
