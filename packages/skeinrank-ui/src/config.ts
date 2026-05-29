export const LEGACY_WRITE_TOOLS_ENV = "VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS";
export const LEGACY_WRITE_TOOLS_STORAGE_KEY = "skeinrank-ui-enable-legacy-write-tools";

export function areLegacyWriteToolsEnabled() {
  if (typeof window !== "undefined") {
    const override = window.localStorage.getItem(LEGACY_WRITE_TOOLS_STORAGE_KEY);
    if (override === "true" || override === "false") {
      return override === "true";
    }
  }
  return import.meta.env.VITE_SKEINRANK_ENABLE_LEGACY_WRITE_TOOLS === "true";
}

export function getLegacyWriteToolsModeLabel() {
  return areLegacyWriteToolsEnabled() ? "Legacy write tools enabled" : "Legacy write tools locked";
}

export const LEGACY_WRITE_TOOLS_LOCKED_MESSAGE =
  "Legacy write tools are read-only by default. Production terminology and binding changes should go through proposals, validation, snapshots, and GitOps rollout.";
