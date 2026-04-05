export function syncMenuMemberSelection(store, requestedIndex) {
  const state = store.getState();
  const party = Array.isArray(state.menuState?.party) ? state.menuState.party : [];
  if (!party.length) {
    if (Number(state.menuMemberIndex ?? 0) !== 0) {
      store.patch({ menuMemberIndex: 0 });
    }
    return { party, memberIndex: 0, member: null };
  }

  const rawIndex = Number(requestedIndex ?? state.menuMemberIndex ?? 0);
  const safeIndex = Number.isFinite(rawIndex) ? rawIndex : 0;
  const memberIndex = ((safeIndex % party.length) + party.length) % party.length;
  if (memberIndex !== Number(state.menuMemberIndex ?? 0)) {
    store.patch({ menuMemberIndex });
  }
  return { party, memberIndex, member: party[memberIndex] || null };
}

export function persistMenuEnvelope(store, nextMenuState, nextEnvelope) {
  store.updateMenuState(nextMenuState);
  if (!nextEnvelope || typeof nextEnvelope !== "object") {
    return true;
  }
  nextEnvelope.menu_state = nextMenuState;
  return store.updateSaveEnvelope(nextEnvelope);
}

export function selectedLocationText(state) {
  if (state?.selectedLocationGroup || state?.selectedLocation) {
    return `現在のLocation: ${state?.selectedLocationGroup || "-"} / ${state?.selectedLocation || "-"}`;
  }
  return "現在のLocationは未選択です。";
}

export function bindButtonHandlers(bindings) {
  const cleanups = [];
  bindings.forEach(({ target, eventName = "click", handler }) => {
    if (!target || typeof handler !== "function") return;
    target.addEventListener(eventName, handler);
    cleanups.push(() => target.removeEventListener(eventName, handler));
  });
  return () => {
    cleanups.forEach((cleanup) => cleanup());
  };
}

export function bindMenuSubpageNavigation({
  leftBtn,
  rightBtn,
  backBtn,
  onLeft,
  onRight,
  onBack,
  listenTarget = window,
}) {
  const onKey = (event) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onLeft?.();
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      onRight?.();
      return;
    }
    if (event.key === "Escape" || event.key === "Enter" || event.key === "Backspace") {
      event.preventDefault();
      onBack?.();
    }
  };

  const unbindButtons = bindButtonHandlers([
    { target: leftBtn, handler: onLeft },
    { target: rightBtn, handler: onRight },
    { target: backBtn, handler: onBack },
  ]);
  listenTarget.addEventListener("keydown", onKey);

  return () => {
    unbindButtons();
    listenTarget.removeEventListener("keydown", onKey);
  };
}
