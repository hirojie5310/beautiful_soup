import { createRouter } from "./router.js?v=20260417-mapfix1";
import { createAppStore } from "./store/app_store.js?v=20260417-mapfix1";

const mountNode = document.getElementById("app");

if (!mountNode) {
  throw new Error("SPA mount node #app was not found.");
}

async function bootstrapApp() {
  const store = createAppStore();
  await store.initialize();
  const router = createRouter({ mountNode, store });
  router.start();
}

void bootstrapApp();
