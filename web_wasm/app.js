import { createRouter } from "./router.js";
import { createAppStore } from "./store/app_store.js";

const mountNode = document.getElementById("app");

if (!mountNode) {
  throw new Error("SPA mount node #app was not found.");
}

const store = createAppStore();
const router = createRouter({ mountNode, store });

router.start();
