import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";
import { prepareExplicitGroups, preparePythonBundle } from "./location_shared.js";

let runtimePromise = null;

export function getPyodideRuntime() {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      const instance = await loadPyodide();
      await instance.loadPackage("typing-extensions");
      await instance.loadPackage("jsonschema");
      await preparePythonBundle(instance);
      await prepareExplicitGroups(instance);

      const bootstrapResponse = await fetch("./bootstrap_runtime.py");
      if (!bootstrapResponse.ok) {
        throw new Error(`bootstrap_runtime.py fetch failed: ${bootstrapResponse.status}`);
      }
      const bootstrapPython = await bootstrapResponse.text();
      await instance.runPythonAsync(bootstrapPython);
      return instance;
    })();
  }
  return runtimePromise;
}
