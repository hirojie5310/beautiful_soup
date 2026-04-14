const DEFAULT_ROUTE = "title";

function normalizeRoute(rawRoute) {
  const route = String(rawRoute || "")
    .trim()
    .replace(/^#\/?/, "")
    .replace(/^\/+/, "");
  return route || DEFAULT_ROUTE;
}

async function loadScreenModule(routeName) {
  switch (routeName) {
    case "title":
      return import("./screens/title_screen.js");
    case "location":
      return import("./screens/location_screen.js");
    case "menu":
      return import("./screens/menu_screen.js");
    case "shop":
      return import("./screens/shop_screen.js");
    case "inn":
      return import("./screens/inn_screen.js");
    case "battle":
      return import("./screens/battle_screen.js");
    case "item":
      return import("./screens/item_screen.js");
    case "equip":
      return import("./screens/equip_screen.js");
    case "magic":
      return import("./screens/magic_screen.js");
    case "status":
      return import("./screens/status_screen.js");
    case "job":
      return import("./screens/job_screen.js");
    default:
      return import("./screens/title_screen.js");
  }
}

export function createRouter({ mountNode, store }) {
  let unmountCurrent = null;
  let activeRouteToken = 0;

  async function renderCurrentRoute() {
    const routeName = normalizeRoute(window.location.hash);
    const routeToken = activeRouteToken + 1;
    activeRouteToken = routeToken;

    store.patch({ route: routeName });

    if (typeof unmountCurrent === "function") {
      unmountCurrent();
      unmountCurrent = null;
    }

    mountNode.innerHTML = "";

    const screenModule = await loadScreenModule(routeName);
    if (routeToken !== activeRouteToken) return;

    const cleanup = await screenModule.mountScreen({
      mountNode,
      routeName,
      store,
      navigate,
    });
    unmountCurrent = typeof cleanup === "function" ? cleanup : null;
  }

  function navigate(routeName) {
    const nextHash = `#/${normalizeRoute(routeName)}`;
    if (window.location.hash === nextHash) {
      void renderCurrentRoute();
      return;
    }
    window.location.hash = nextHash;
  }

  function start() {
    window.addEventListener("hashchange", renderCurrentRoute);
    if (!window.location.hash) {
      window.location.hash = `#/${DEFAULT_ROUTE}`;
      return;
    }
    void renderCurrentRoute();
  }

  return {
    navigate,
    start,
  };
}
