/** Mirrors backend `app.schemas_tasks.DEFAULT_DESKTOP_ALLOWED_TOOLS`. */
export const DEFAULT_DESKTOP_ALLOWED_TOOLS: string[] = [
  "list_apps",
  "open_app",
  "get_app_state",
  "desktop_click",
  "desktop_type",
  "desktop_key",
  "desktop_scroll",
  "finish",
  "wait",
];

/** Browser-centric defaults without desktop tools (backend DEFAULT_ALLOWED_TOOLS). */
export const DEFAULT_BROWSER_ALLOWED_TOOLS: string[] = [
  "navigate",
  "click_element",
  "type_text",
  "select_option",
  "scroll",
  "drag_element",
  "go_back",
  "wait",
  "extract",
  "finish",
  "http_request",
];

/** Merge browser + desktop tool surfaces for hybrid tasks. */
export function mergeDesktopAllowedTools(
  includeBrowser: boolean,
): string[] {
  if (!includeBrowser) {
    return [...DEFAULT_DESKTOP_ALLOWED_TOOLS];
  }
  return Array.from(
    new Set([...DEFAULT_BROWSER_ALLOWED_TOOLS, ...DEFAULT_DESKTOP_ALLOWED_TOOLS]),
  );
}
