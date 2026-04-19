export const DEFAULT_BATTLE_RETURN_CONTEXT = Object.freeze({
  return_route: "location",
  resume_map: false,
});

export function normalizeBattleReturnContext(rawContext) {
  if (!rawContext || typeof rawContext !== "object") return null;
  const returnRoute = String(rawContext.return_route || "").trim();
  return {
    ...rawContext,
    return_route: returnRoute === "map" ? "map" : "location",
    resume_map: Boolean(rawContext.resume_map),
  };
}

export function resolveMountedBattleReturnContext(sessionContext, currentContext = null) {
  return (
    normalizeBattleReturnContext(sessionContext)
    || normalizeBattleReturnContext(currentContext)
    || { ...DEFAULT_BATTLE_RETURN_CONTEXT }
  );
}
